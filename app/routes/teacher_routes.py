from fastapi import APIRouter, Depends, Query
from motor.motor_asyncio import AsyncIOMotorDatabase
from datetime import datetime, timedelta, timezone

from app.database.base import get_db
from app.api.deps import require_teacher
from app.services.analytics.analytics_service import get_teacher_class_analytics
from app.services.gamification_service import get_leaderboard
from app.database.redis_client import cache

router = APIRouter(prefix="/teacher", tags=["Teacher"])


@router.get("/dashboard")
async def get_teacher_dashboard(user: dict = Depends(require_teacher), db: AsyncIOMotorDatabase = Depends(get_db)):
    cache_key = f"teacher:dashboard:{user['_id']}"
    cached = await cache.get(cache_key)
    if cached:
        return cached

    profiles = await db.student_profiles.find().sort("xp", -1).to_list(500)
    students_data = []
    student_ids = []

    for profile in profiles:
        student_user = await db.users.find_one({"_id": profile["user_id"], "is_active": True})
        if not student_user:
            continue
        last_emo = await db.emotion_history.find_one({"user_id": student_user["_id"]}, sort=[("created_at", -1)])
        last_active = profile.get("last_active")
        is_online = bool(last_active and (datetime.now(timezone.utc) - last_active).total_seconds() < 300)
        students_data.append({
            "id": student_user["_id"],
            "name": student_user["name"] if not student_user.get("anonymous_mode") else "Anonymous",
            "avatar": student_user.get("avatar"), "xp": profile["xp"], "level": profile["level"],
            "streak": profile["streak"], "focus_score": round(profile["focus_score"], 1),
            "stress_score": round(profile["stress_score"], 1),
            "current_emotion": last_emo["emotion"] if last_emo else "neutral",
            "is_online": is_online,
        })
        student_ids.append(student_user["_id"])

    class_analytics = await get_teacher_class_analytics(db, student_ids)
    online_count = sum(1 for s in students_data if s["is_online"])
    stress_alerts = [s for s in students_data if s["stress_score"] > 65]
    leaderboard = await get_leaderboard(db, limit=5)

    dashboard = {
        "total_students": len(students_data),
        "online_students": online_count,
        "average_focus": class_analytics.get("average_class_focus", 0),
        "average_stress": class_analytics.get("average_class_stress", 0),
        "students": students_data,
        "stress_alerts": stress_alerts,
        "emotion_distribution": class_analytics.get("emotion_distribution", {}),
        "leaderboard": leaderboard,
    }
    await cache.set(cache_key, dashboard, ttl=60)
    return dashboard


@router.get("/class")
async def get_class_list(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    user: dict = Depends(require_teacher),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    profiles = await db.student_profiles.find().skip((page - 1) * per_page).limit(per_page).to_list(per_page)
    students = []
    for p in profiles:
        u = await db.users.find_one({"_id": p["user_id"], "is_active": True})
        if u:
            students.append({"id": u["_id"], "name": u["name"], "avatar": u.get("avatar"),
                             "xp": p["xp"], "level": p["level"], "streak": p["streak"],
                             "focus": round(p["focus_score"], 1), "stress": round(p["stress_score"], 1)})
    return {"students": students, "page": page, "per_page": per_page}


@router.get("/emotions")
async def get_class_emotions(
    period: str = Query(default="today"),
    user: dict = Depends(require_teacher),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24 if period == "today" else 168)
    emotions = await db.emotion_history.find({"created_at": {"$gte": cutoff}}).sort("created_at", -1).to_list(500)
    result = []
    for e in emotions:
        u = await db.users.find_one({"_id": e["user_id"]})
        if u:
            result.append({
                "user_name": u["name"] if not u.get("anonymous_mode") else "Anonymous",
                "emotion": e["emotion"], "stress_score": e["stress_score"],
                "focus_score": e["focus_score"], "created_at": str(e["created_at"]),
            })
    return result


@router.get("/alerts")
async def get_teacher_alerts(user: dict = Depends(require_teacher), db: AsyncIOMotorDatabase = Depends(get_db)):
    profiles = await db.student_profiles.find({"stress_score": {"$gte": 60}}).sort("stress_score", -1).to_list(100)
    alerts = []
    for p in profiles:
        u = await db.users.find_one({"_id": p["user_id"], "is_active": True})
        if u:
            alerts.append({"user_id": u["_id"], "name": u["name"], "avatar": u.get("avatar"),
                           "stress_score": round(p["stress_score"], 1), "focus_score": round(p["focus_score"], 1)})
    return {"alerts": alerts, "count": len(alerts)}


@router.get("/reports")
async def get_teacher_reports(user: dict = Depends(require_teacher), db: AsyncIOMotorDatabase = Depends(get_db)):
    profiles = await db.student_profiles.find().to_list(1000)
    if not profiles:
        return {"message": "No students found."}
    return {
        "total_students": len(profiles),
        "average_xp": round(sum(p["xp"] for p in profiles) / len(profiles), 1),
        "average_streak": round(sum(p["streak"] for p in profiles) / len(profiles), 1),
        "average_focus": round(sum(p["focus_score"] for p in profiles) / len(profiles), 1),
        "average_stress": round(sum(p["stress_score"] for p in profiles) / len(profiles), 1),
        "total_class_study_minutes": sum(p["total_study_minutes"] for p in profiles),
    }
