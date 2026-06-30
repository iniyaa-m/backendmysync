from typing import List, Dict, Any
from datetime import datetime, timedelta, timezone
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.database.redis_client import cache

TOPIC_POOL = [
    {"id": "ml_basics", "title": "Machine Learning Basics", "subject": "AI", "difficulty": "medium", "tags": ["ml", "ai", "python"], "resources": [{"type": "video", "title": "ML for Beginners", "url": "/resources/ml_basics"}], "estimated_minutes": 60},
    {"id": "deep_learning", "title": "Deep Learning & Neural Networks", "subject": "AI", "difficulty": "hard", "tags": ["dl", "nn", "pytorch"], "resources": [{"type": "video", "title": "Neural Nets Explained", "url": "/resources/nn"}], "estimated_minutes": 90},
    {"id": "python_basics", "title": "Python Programming", "subject": "Programming", "difficulty": "easy", "tags": ["python", "basics", "coding"], "resources": [{"type": "video", "title": "Python Crash Course", "url": "/resources/python"}], "estimated_minutes": 45},
    {"id": "data_structures", "title": "Data Structures & Algorithms", "subject": "CS", "difficulty": "hard", "tags": ["dsa", "algorithms", "cs"], "resources": [{"type": "video", "title": "DSA Masterclass", "url": "/resources/dsa"}], "estimated_minutes": 120},
    {"id": "web_dev", "title": "Web Development with React", "subject": "Development", "difficulty": "medium", "tags": ["react", "web", "frontend"], "resources": [{"type": "video", "title": "React Tutorial", "url": "/resources/react"}], "estimated_minutes": 75},
    {"id": "statistics", "title": "Statistics & Probability", "subject": "Math", "difficulty": "medium", "tags": ["stats", "math", "probability"], "resources": [{"type": "video", "title": "Stats for ML", "url": "/resources/stats"}], "estimated_minutes": 60},
    {"id": "nlp", "title": "Natural Language Processing", "subject": "AI", "difficulty": "hard", "tags": ["nlp", "ai", "transformers"], "resources": [{"type": "video", "title": "NLP with Transformers", "url": "/resources/nlp"}], "estimated_minutes": 90},
    {"id": "db_design", "title": "Database Design & SQL", "subject": "CS", "difficulty": "medium", "tags": ["sql", "database", "backend"], "resources": [{"type": "notes", "title": "SQL Reference", "url": "/resources/sql"}], "estimated_minutes": 50},
]

DIFFICULTY_ORDER = {"easy": 0, "medium": 1, "hard": 2}
EMOTION_DIFFICULTY_MAP = {
    "stressed": "easy", "tired": "easy", "confused": "easy", "fear": "easy",
    "neutral": "medium", "sad": "medium", "happy": "medium",
    "focused": "hard", "confident": "hard", "surprise": "medium",
}


def _score_topic(topic: dict, profile: dict) -> float:
    score = 0.5
    emotion_preferred = profile.get("emotion_preferred_difficulty", "medium")
    diff_distance = abs(DIFFICULTY_ORDER.get(topic["difficulty"], 1) - DIFFICULTY_ORDER.get(emotion_preferred, 1))
    score -= diff_distance * 0.15
    topic_tags = set(topic.get("tags", []))
    if topic_tags & set(profile.get("weak_tags", [])):
        score += 0.25
    if topic["id"] in set(profile.get("completed_topics", [])):
        score -= 0.40
    if topic_tags & set(profile.get("strong_tags", [])):
        score += 0.10
    if topic["id"] in set(profile.get("recent_topics", [])):
        score -= 0.20
    return round(min(max(score, 0.0), 1.0), 3)


def _build_reason(topic: dict, profile: dict, score: float, emotion: str) -> str:
    weak_match = set(topic.get("tags", [])) & set(profile.get("weak_tags", []))
    emotion_diff = profile.get("emotion_preferred_difficulty", "medium")
    if weak_match:
        return f"Addresses your weak areas: {', '.join(list(weak_match)[:2])} 📈"
    if topic["difficulty"] == emotion_diff:
        return f"Perfect difficulty for your current {emotion} state 🎯"
    if score >= 0.7:
        return "Highly personalized based on your learning history ⭐"
    return f"Recommended to strengthen your {topic['subject']} knowledge 📚"


async def get_recommendations(db: AsyncIOMotorDatabase, user_id: str, limit: int = 5) -> List[Dict[str, Any]]:
    cache_key = f"recommendations:{user_id}"
    cached = await cache.get(cache_key)
    if cached:
        return cached

    profile = await db.student_profiles.find_one({"user_id": user_id})
    week_ago = datetime.now(timezone.utc) - timedelta(days=7)

    emotions = await db.emotion_history.find({
        "user_id": user_id, "created_at": {"$gte": week_ago}
    }).sort("created_at", -1).limit(10).to_list(10)

    dominant_emotion = emotions[0]["emotion"] if emotions else "neutral"
    emotion_preferred_difficulty = EMOTION_DIFFICULTY_MAP.get(dominant_emotion, "medium")

    history = await db.learning_history.find({"user_id": user_id}).sort("created_at", -1).limit(20).to_list(20)
    recent_topics = list({h["topic"][:20] for h in history[:5]})

    profile_data = {
        "emotion_preferred_difficulty": emotion_preferred_difficulty
            if not profile else (profile.get("difficulty_preference") or emotion_preferred_difficulty),
        "weak_tags": (profile.get("weak_topics") or []) if profile else [],
        "strong_tags": (profile.get("strong_topics") or []) if profile else [],
        "completed_topics": recent_topics,
        "recent_topics": recent_topics[:3],
    }

    scored = []
    for topic in TOPIC_POOL:
        sc = _score_topic(topic, profile_data)
        reason = _build_reason(topic, profile_data, sc, dominant_emotion)
        scored.append({**topic, "match_score": sc, "reason": reason})

    scored.sort(key=lambda x: x["match_score"], reverse=True)
    result_list = scored[:limit]
    await cache.set(cache_key, result_list, ttl=600)
    return result_list
