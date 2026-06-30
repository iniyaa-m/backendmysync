import os
import asyncio
import tempfile
from concurrent.futures import ThreadPoolExecutor

from app.utils.logger import logger

_executor = ThreadPoolExecutor(max_workers=2)

TONE_EMOTION_MAP = {
    "POSITIVE": ("happy", "calm", 0.15),
    "NEGATIVE": ("stressed", "stressed", 0.80),
    "NEUTRAL":  ("neutral", "calm", 0.25),
}

VOICE_RECOMMENDATIONS = {
    "happy":      "Positive energy detected! Great time to study. 🎵",
    "stressed":   "High stress in voice. Try 4-7-8 breathing now. 🌬️",
    "neutral":    "Calm and steady. Perfect focus state. 🎯",
    "frustrated": "Frustration detected. Switch topics or take a break. 🔄",
    "excited":    "Excitement detected! Channel it into learning! 🚀",
    "sad":        "Low energy detected. A short walk can help. 🚶",
}


def _transcribe_audio(audio_path: str) -> str:
    try:
        import whisper
        model = whisper.load_model("base")
        result = model.transcribe(audio_path, fp16=False)
        return result.get("text", "").strip()
    except Exception as e:
        logger.warning(f"Whisper transcription failed: {e}")
        return ""


def _analyze_sentiment(text: str) -> dict:
    if not text:
        return {"label": "NEUTRAL", "score": 0.5}
    try:
        from transformers import pipeline
        classifier = pipeline(
            "sentiment-analysis",
            model="cardiffnlp/twitter-roberta-base-sentiment-latest",
            truncation=True, max_length=512,
        )
        result = classifier(text[:512])[0]
        label = result["label"].upper()
        if "POS" in label:
            label = "POSITIVE"
        elif "NEG" in label:
            label = "NEGATIVE"
        else:
            label = "NEUTRAL"
        return {"label": label, "score": result["score"]}
    except Exception as e:
        logger.warning(f"Sentiment analysis failed: {e}")
        return {"label": "NEUTRAL", "score": 0.5}


def _voice_pitch_analysis(audio_path: str) -> dict:
    try:
        import librosa
        y, sr = librosa.load(audio_path, sr=None)
        pitches, magnitudes = librosa.piptrack(y=y, sr=sr)
        valid_pitches = pitches[magnitudes > magnitudes.mean()]
        if len(valid_pitches) > 0:
            avg_pitch = float(valid_pitches.mean())
            pitch_std = float(valid_pitches.std())
            tone = "stressed" if pitch_std > 80 else ("excited" if avg_pitch > 200 else "calm")
            return {"avg_pitch": avg_pitch, "pitch_std": pitch_std, "tone": tone}
    except Exception as e:
        logger.warning(f"Pitch analysis failed: {e}")
    return {"avg_pitch": 150.0, "pitch_std": 30.0, "tone": "calm"}


def _full_voice_pipeline(audio_bytes: bytes, filename: str = "audio.wav") -> dict:
    suffix = os.path.splitext(filename)[1] or ".wav"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name
    try:
        transcript = _transcribe_audio(tmp_path)
        sentiment_result = _analyze_sentiment(transcript) if transcript else {"label": "NEUTRAL", "score": 0.5}
        pitch_result = _voice_pitch_analysis(tmp_path)

        sentiment_label = sentiment_result["label"]
        emotion, base_tone, base_stress = TONE_EMOTION_MAP.get(sentiment_label, ("neutral", "calm", 0.25))
        tone = pitch_result["tone"] if pitch_result else base_tone

        stress_score = base_stress
        if tone == "stressed":
            stress_score = max(stress_score, 0.75)
        elif tone == "excited":
            stress_score = min(stress_score, 0.30)
            emotion = "excited"

        return {
            "emotion": emotion, "tone": tone,
            "confidence": round(sentiment_result["score"], 3),
            "stress_score": round(stress_score * 100, 1),
            "transcript": transcript,
            "sentiment": sentiment_label.lower(),
            "recommendation": VOICE_RECOMMENDATIONS.get(emotion, "Keep going! 💪"),
        }
    finally:
        os.unlink(tmp_path)


async def analyze_voice_emotion(audio_bytes: bytes, filename: str = "audio.wav") -> dict:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_executor, _full_voice_pipeline, audio_bytes, filename)


async def analyze_audio_chunk(chunk: bytes) -> dict:
    try:
        loop = asyncio.get_event_loop()
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp.write(chunk)
            tmp_path = tmp.name
        pitch_result = await loop.run_in_executor(_executor, _voice_pitch_analysis, tmp_path)
        os.unlink(tmp_path)
        tone = pitch_result.get("tone", "calm")
        emotion_map = {"calm": "neutral", "stressed": "stressed", "excited": "excited"}
        return {
            "emotion": emotion_map.get(tone, "neutral"), "tone": tone,
            "confidence": 0.70, "stress_score": 75.0 if tone == "stressed" else 20.0,
            "transcript": "", "sentiment": "negative" if tone == "stressed" else "neutral",
        }
    except Exception as e:
        logger.error(f"Streaming audio analysis error: {e}")
        return {"emotion": "neutral", "tone": "calm", "confidence": 0.5, "stress_score": 20.0}
