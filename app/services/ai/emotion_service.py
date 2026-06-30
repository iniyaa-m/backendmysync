import io
import base64
import uuid
from typing import Optional
import asyncio
from concurrent.futures import ThreadPoolExecutor

from app.utils.logger import logger

_executor = ThreadPoolExecutor(max_workers=4)

EMOTION_SCORES = {
    "happy":     {"stress": 0.10, "focus": 0.80},
    "sad":       {"stress": 0.55, "focus": 0.40},
    "angry":     {"stress": 0.85, "focus": 0.30},
    "neutral":   {"stress": 0.25, "focus": 0.65},
    "confused":  {"stress": 0.60, "focus": 0.50},
    "stressed":  {"stress": 0.90, "focus": 0.25},
    "fear":      {"stress": 0.80, "focus": 0.20},
    "surprise":  {"stress": 0.35, "focus": 0.70},
    "tired":     {"stress": 0.50, "focus": 0.35},
    "focused":   {"stress": 0.15, "focus": 0.95},
    "confident": {"stress": 0.10, "focus": 0.90},
    "disgust":   {"stress": 0.70, "focus": 0.30},
}

RECOMMENDATIONS = {
    "happy":     "Great state! Tackle challenging topics now. 🚀",
    "sad":       "Take a short break. Some calming music may help. 🎵",
    "angry":     "Step away for 5 min. Deep breathing recommended. 🌬️",
    "neutral":   "Steady focus. Good time for regular study. 📚",
    "confused":  "Re-watch the last segment. AI tutor is ready! 💡",
    "stressed":  "Try the 4-7-8 breathing technique right now. 🧘",
    "fear":      "Anxiety detected. Contact your mentor for support. 💙",
    "surprise":  "Interesting! Stay curious and keep exploring. ✨",
    "tired":     "20-min power nap restores focus by 34%. 😴",
    "focused":   "Peak focus mode! Perfect for deep work. 🎯",
    "confident": "Confidence is high! Great time to lead study groups.",
    "disgust":   "Take a break and switch to a preferred topic. 🔄",
}

DEEPFACE_MAP = {
    "happy": "happy", "sad": "sad", "angry": "angry",
    "neutral": "neutral", "fear": "fear", "surprise": "surprise",
    "disgust": "stressed",
}


def _analyze_with_deepface(img_array) -> dict:
    try:
        from deepface import DeepFace
        result = DeepFace.analyze(img_array, actions=["emotion"], enforce_detection=False, silent=True)
        if isinstance(result, list):
            result = result[0]
        emotions = result.get("emotion", {})
        dominant = result.get("dominant_emotion", "neutral").lower()
        confidence = max(emotions.values()) / 100.0 if emotions else 0.7
        emotion = DEEPFACE_MAP.get(dominant, dominant)
        return {"emotion": emotion, "confidence": round(confidence, 3), "raw": emotions}
    except Exception as e:
        logger.warning(f"DeepFace failed: {e}")
        return None


def _analyze_with_fer(img_array) -> dict:
    try:
        from fer import FER
        detector = FER(mtcnn=False)
        result = detector.detect_emotions(img_array)
        if result:
            emotions = result[0]["emotions"]
            dominant = max(emotions, key=emotions.get)
            emotion = DEEPFACE_MAP.get(dominant.lower(), dominant.lower())
            return {"emotion": emotion, "confidence": round(emotions[dominant], 3), "raw": emotions}
    except Exception as e:
        logger.warning(f"FER failed: {e}")
    return None


def _decode_image(image_bytes: bytes):
    import cv2
    import numpy as np
    from PIL import Image
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        img_pil = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        img = cv2.cvtColor(np.array(img_pil), cv2.COLOR_RGB2BGR)
    return img


def _analyze_sync(img_array) -> dict:
    result = _analyze_with_deepface(img_array)
    if not result:
        result = _analyze_with_fer(img_array)
    if not result:
        result = {"emotion": "neutral", "confidence": 0.60, "raw": {}}
    return result


async def analyze_image_emotion(image_bytes: bytes, session_id: Optional[str] = None) -> dict:
    loop = asyncio.get_event_loop()
    img_array = await loop.run_in_executor(_executor, _decode_image, image_bytes)
    analysis = await loop.run_in_executor(_executor, _analyze_sync, img_array)

    emotion = analysis["emotion"]
    scores = EMOTION_SCORES.get(emotion, {"stress": 0.5, "focus": 0.5})

    return {
        "emotion": emotion,
        "confidence": analysis["confidence"],
        "stress_score": round(scores["stress"] * 100, 1),
        "focus_score": round(scores["focus"] * 100, 1),
        "recommendation": RECOMMENDATIONS.get(emotion, "Keep going! 💪"),
        "session_id": session_id or str(uuid.uuid4()),
        "raw_data": analysis.get("raw"),
    }


async def analyze_frame_base64(frame_b64: str) -> dict:
    try:
        image_data = base64.b64decode(frame_b64)
        return await analyze_image_emotion(image_data)
    except Exception as e:
        logger.error(f"Frame analysis error: {e}")
        return {
            "emotion": "neutral", "confidence": 0.5,
            "stress_score": 25.0, "focus_score": 65.0,
            "recommendation": "Keep focused!", "session_id": str(uuid.uuid4()),
        }
