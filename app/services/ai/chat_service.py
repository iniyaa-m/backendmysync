import uuid
import json
from typing import List, Optional, Dict, Any

from app.config.settings import settings
from app.database.redis_client import cache
from app.utils.logger import logger

SYSTEM_PROMPT = """You are MindSync AI Tutor, an empathetic and intelligent educational assistant.
Adapt responses based on student emotion, explain concepts clearly, generate quizzes on request,
provide hints for coding problems, and support multiple languages (English, Tamil, Hindi).
Current student emotion: {emotion}
Language: {language}
"""

SUGGESTIONS_MAP = {
    "confused":  ["Can you explain this more simply?", "Give me an example", "What are the prerequisites?"],
    "stressed":  ["Give me an easier topic", "Help me with a breathing exercise", "What should I prioritize?"],
    "happy":     ["Give me a harder challenge", "Generate a quiz for me", "What should I learn next?"],
    "focused":   ["Give me a deep-dive topic", "Generate a hard quiz", "Suggest advanced resources"],
    "tired":     ["Give me a short summary", "Quick 5-question quiz", "What is most important to know?"],
    "default":   ["Explain with an example", "Generate a quiz", "Summarize this topic"],
}

MENTAL_HEALTH_KEYWORDS = ["anxious", "depressed", "hopeless", "worthless", "suicide", "harm", "stress", "overwhelmed", "burnout"]

GROQ_MODELS = [
    "llama-3.3-70b-versatile",
    "llama-3.1-70b-versatile",
    "llama-3.1-8b-instant",
    "mixtral-8x7b-32768",
    "gemma2-9b-it",
]


def _detect_mental_health_concern(text: str) -> bool:
    lower = text.lower()
    return any(kw in lower for kw in MENTAL_HEALTH_KEYWORDS)


async def _get_llm_response(messages: List[dict], language: str = "en") -> tuple:
    if not settings.GROQ_API_KEY:
        logger.warning("GROQ_API_KEY not set — using mock response")
        return _mock_response(messages[-1]["content"] if messages else ""), 0

    primary = settings.GROQ_MODEL
    fallback = settings.GROQ_FALLBACK_MODEL
    model_queue = [primary, fallback] + [m for m in GROQ_MODELS if m not in (primary, fallback)]

    import asyncio
    from groq import Groq, RateLimitError, APIStatusError

    client = Groq(api_key=settings.GROQ_API_KEY)

    for model in model_queue:
        try:
            loop = asyncio.get_event_loop()

            def _call():
                return client.chat.completions.create(
                    model=model, messages=messages,
                    max_tokens=1024, temperature=0.7, top_p=0.9,
                )

            response = await loop.run_in_executor(None, _call)
            text = response.choices[0].message.content or ""
            tokens = response.usage.total_tokens if response.usage else len(text.split()) * 2
            logger.info(f"Groq [{model}] responded — {tokens} tokens")
            return text, tokens

        except RateLimitError:
            logger.warning(f"Groq rate limit on '{model}', trying next...")
            continue
        except APIStatusError as e:
            logger.warning(f"Groq API error on '{model}': {e.status_code}")
            continue
        except Exception as e:
            logger.error(f"Groq error on '{model}': {e}")
            continue

    logger.error("All Groq models failed — returning mock response")
    return _mock_response(messages[-1]["content"] if messages else ""), 0


def _mock_response(message: str) -> str:
    lower = message.lower()
    if any(w in lower for w in ["hello", "hi", "hey"]):
        return "Hello! I'm your MindSync AI Tutor. How can I help you learn today? 🎓"
    if "quiz" in lower:
        return "Sure! What is the time complexity of binary search?\nA) O(n)  B) O(log n)  C) O(n²)  D) O(1)\n\nAnswer: **B) O(log n)**"
    if any(w in lower for w in ["stress", "anxious", "overwhelmed"]):
        return "I understand you're stressed. Try the **4-7-8 breathing technique**: inhale 4s → hold 7s → exhale 8s. 💙"
    return "I'm here to help! Could you share more details about what you'd like to learn? 📚"


async def get_chat_session(user_id: str, session_id: str) -> List[dict]:
    cached = await cache.get(f"chat:{user_id}:{session_id}")
    return cached or []


async def save_chat_session(user_id: str, session_id: str, messages: List[dict]):
    await cache.set(f"chat:{user_id}:{session_id}", messages[-30:], ttl=86400)


async def chat_with_tutor(
    user_id: str, message: str, session_id: Optional[str],
    emotion_context: Optional[str] = "neutral", language: str = "en",
) -> Dict[str, Any]:
    if not session_id:
        session_id = str(uuid.uuid4())

    system_content = SYSTEM_PROMPT.format(emotion=emotion_context or "neutral", language=language)
    if _detect_mental_health_concern(message):
        system_content += "\n\nIMPORTANT: Student may be in distress. Respond with extra empathy and suggest professional support if needed."

    history = await get_chat_session(user_id, session_id)
    messages = [{"role": "system", "content": system_content}] + history + [{"role": "user", "content": message}]

    reply, tokens = await _get_llm_response(messages, language)

    history.append({"role": "user", "content": message})
    history.append({"role": "assistant", "content": reply})
    await save_chat_session(user_id, session_id, history)

    sentiment = "negative" if any(w in message.lower() for w in ["stress", "confused", "angry", "sad", "fail"]) else "positive"

    return {
        "reply": reply, "session_id": session_id, "sentiment": sentiment,
        "emotion_detected": emotion_context,
        "suggestions": SUGGESTIONS_MAP.get(emotion_context or "default", SUGGESTIONS_MAP["default"]),
        "tokens_used": tokens,
    }


async def generate_quiz_with_llm(
    topic: str, difficulty: str, num_questions: int,
    question_types: List[str], language: str = "en",
) -> List[dict]:
    prompt = f"""Generate exactly {num_questions} quiz questions on "{topic}" at {difficulty} difficulty.
Return ONLY a valid JSON array. Each object must have:
- "id": unique string
- "question": question text
- "question_type": one of {question_types}
- "options": list of 4 strings (mcq) or ["True","False"] (true_false) or null
- "correct_answer": correct answer string
- "explanation": brief explanation
- "difficulty": "{difficulty}"
Language: {language}
Return ONLY the JSON array starting with [ and ending with ]."""

    messages = [
        {"role": "system", "content": "You are an expert quiz generator. Output ONLY valid JSON arrays."},
        {"role": "user", "content": prompt},
    ]

    try:
        reply, _ = await _get_llm_response(messages)
        start = reply.find("[")
        end = reply.rfind("]") + 1
        if start >= 0 and end > start:
            questions = json.loads(reply[start:end])
            for q in questions:
                if not q.get("id"):
                    q["id"] = str(uuid.uuid4())
            return questions
    except Exception as e:
        logger.error(f"Quiz generation failed: {e}")

    return [
        {
            "id": str(uuid.uuid4()),
            "question": f"Which best describes a core concept in {topic}? (Q{i+1})",
            "question_type": "mcq",
            "options": [f"Option A — correct", "Option B — incorrect", "Option C — unrelated", "Option D — partial"],
            "correct_answer": "Option A — correct",
            "explanation": f"Core concept in {topic} at {difficulty} difficulty.",
            "difficulty": difficulty,
        }
        for i in range(num_questions)
    ]


async def generate_notes_with_llm(content: str, topic: Optional[str], language: str) -> dict:
    prompt = f"""Analyze the following content and generate study materials.
Return ONLY a valid JSON object with these keys:
- "summary": string (2-3 paragraphs)
- "key_points": array of strings (max 10)
- "mind_map": object with "main" (string) and "subtopics" (array of strings)
- "revision_notes": string
- "flashcards": array of {{"front": question, "back": answer}} (max 5)
Topic: {topic or "General"}
Language: {language}
Content:
{content[:4000]}
Return ONLY the JSON object starting with {{ and ending with }}."""

    messages = [
        {"role": "system", "content": "You are a study notes generator. Output ONLY valid JSON."},
        {"role": "user", "content": prompt},
    ]

    try:
        reply, _ = await _get_llm_response(messages)
        start = reply.find("{")
        end = reply.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(reply[start:end])
    except Exception as e:
        logger.error(f"Notes generation failed: {e}")

    return {
        "summary": f"Summary of {topic or 'the provided content'}.",
        "key_points": [f"Key point {i+1}" for i in range(5)],
        "mind_map": {"main": topic or "Topic", "subtopics": ["Core Concepts", "Applications", "Examples"]},
        "revision_notes": "Focus on the main concepts, their definitions, and relationships.",
        "flashcards": [{"front": "What is the main concept?", "back": "The core principles discussed."}],
    }
