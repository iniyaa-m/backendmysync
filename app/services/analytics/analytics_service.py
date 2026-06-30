from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any
from collections import Counter
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.database.redis_client import cache


def _build_period(period: str) -> tuple:
    now = datetime.now(timezone.utc)
    if period == "daily":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "monthly":
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    else:
        start = now - timedelta(days=7)
    return start, now


async def get_student_analytics(db: AsyncIOMotorDatabase, user_id: str, period: str = "weekly") -> Dict[str, Any]:
    cache_key = f"analytics:{user_id}:{period}"
    cached = await cache.get(cache_key)
    if cached:
        return cached

    start, end = _build_period(period)

    emotions = await db.emotion_history.find({
        "user_id": user_id, "created_at": {"$gte": start, "$lte": end}
    }).sort("created_at", 1).to_list(1000)

    history = await db.learning_history.find({
        "user_id": user_id, "created_at": {"$gte": start}
    }).sort("created_at", 1).to_list(1000)

    quizzes = await db.quiz_attempts.find({
        "user_id": user_id, "created_at": {"$gte": start}
    }).to_list(1000)

    day_data: Dict[str, Dict] = {}
    for e in emotions:
        day = e["created_at"].strftime("%Y-%m-%d")
        if day not in day_data:
            day_data[day] = {"stress": [], "focus": [], "emotions": [], "study_minutes": 0}
        day_data[day]["stress"].append(e["stress_score"])
        day_data[day]["focus"].append(e["focus_score"])
        day_data[day]["emotions"].append(e["emotion"])

    for h in history:
        day = h["created_at"].strftime("%Y-%m-%d")
        if day not in day_data:
            day_data[day] = {"stress": [], "focus": [], "emotions": [], "study_minutes": 0}
        day_data[day]["study_minutes"] += h.get("duration_minutes", 0)

    data_points = []
    for day_str in sorted(day_data.keys()):
        d = day_data[day_str]
        emotion_counts = Counter(d["emotions"])
        data_points.append({
            "date": day_str,
            "avg_stress": round(sum(d["stress"]) / len(d["stress"]), 1) if d["stress"] else 0,
            "avg_focus": round(sum(d["focus"]) / len(d["focus"]), 1) if d["focus"] else 0,
            "study_minutes": d["study_minutes"],
            "dominant_emotion": emotion_counts.most_common(1)[0][0] if emotion_counts else "neutral",
        })

    all_stress = [e["stress_score"] for e in emotions]
    all_focus = [e["focus_score"] for e in emotions]
    quiz_scores = [q["score"] / q["max_score"] * 100 for q in quizzes if q.get("max_score")]
    emotion_dist = Counter(e["emotion"] for e in emotions)

    summary = {
        "avg_stress": round(sum(all_stress) / len(all_stress), 1) if all_stress else 0,
        "avg_focus": round(sum(all_focus) / len(all_focus), 1) if all_focus else 0,
        "total_study_minutes": sum(h.get("duration_minutes", 0) for h in history),
        "avg_quiz_score": round(sum(quiz_scores) / len(quiz_scores), 1) if quiz_scores else 0.0,
        "total_quizzes": len(quizzes),
        "emotion_distribution": dict(emotion_dist),
        "dominant_emotion": emotion_dist.most_common(1)[0][0] if emotion_dist else "neutral",
    }

    result = {
        "period": period,
        "data_points": data_points,
        "summary": summary,
        "insights": _generate_insights(summary),
        "quiz_trend": [{"date": str(q["created_at"].date()), "score": round(q["score"] / q["max_score"] * 100, 1)} for q in quizzes if q.get("max_score")],
    }

    await cache.set(cache_key, result, ttl=300)
    return result


def _generate_insights(summary: Dict) -> List[str]:
    insights = []
    avg_stress = summary.get("avg_stress", 0)
    avg_focus = summary.get("avg_focus", 0)
    total_study = summary.get("total_study_minutes", 0)
    avg_quiz = summary.get("avg_quiz_score", 0)

    if avg_stress > 65:
        insights.append("⚠️ High stress levels detected this period. Consider more breaks and mindfulness exercises.")
    elif avg_stress < 30:
        insights.append("✅ Excellent stress management this period. Keep it up!")
    if avg_focus > 75:
        insights.append("🎯 Outstanding focus levels! Your learning efficiency is above average.")
    elif avg_focus < 50:
        insights.append("📉 Focus levels are low. Try the Pomodoro technique: 25 min study, 5 min break.")
    if total_study >= 420:
        insights.append(f"📚 Great study time: {total_study // 60}h {total_study % 60}m this period.")
    elif total_study < 120:
        insights.append("⏰ Study time is below target. Aim for at least 2 hours daily.")
    if avg_quiz >= 80:
        insights.append("🏆 Excellent quiz performance! Consider advancing to harder difficulty.")
    elif avg_quiz < 50:
        insights.append("📖 Quiz scores need improvement. Review weak topics with AI tutor.")
    dominant = summary.get("dominant_emotion", "neutral")
    if dominant in ("stressed", "angry"):
        insights.append(f"😰 {dominant.capitalize()} is your most frequent emotion. Mental health exercises are recommended.")
    elif dominant in ("happy", "focused", "confident"):
        insights.append(f"😊 {dominant.capitalize()} is your dominant state — a great sign for learning!")
    return insights


async def get_teacher_class_analytics(db: AsyncIOMotorDatabase, student_ids: List[str]) -> Dict[str, Any]:
    if not student_ids:
        return {}
    from datetime import timedelta
    week_ago = datetime.now(timezone.utc) - timedelta(days=7)
    emotions = await db.emotion_history.find({
        "user_id": {"$in": student_ids}, "created_at": {"$gte": week_ago}
    }).to_list(5000)

    emotion_dist = Counter(e["emotion"] for e in emotions)
    return {
        "emotion_distribution": dict(emotion_dist),
        "total_emotions_recorded": len(emotions),
        "average_class_stress": round(sum(e["stress_score"] for e in emotions) / len(emotions), 1) if emotions else 0,
        "average_class_focus": round(sum(e["focus_score"] for e in emotions) / len(emotions), 1) if emotions else 0,
    }
