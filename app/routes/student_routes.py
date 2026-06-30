from fastapi import APIRouter, Depends, Query
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.database.base import get_db
from app.api.deps import get_current_active_user
from app.schemas.schemas import UserUpdateRequest
from app.services.analytics.analytics_service import get_student_analytics
from app.services.analytics.recommendation_service import get_recommendations
from app.services.gamification_service import get_leaderboard
from app.database.redis_client import cache
from datetime import datetime, timezone

router = APIRouter(prefix="/student", tags=["Student"])


@router.get("/profile")
async def get_student_profile(user: dict = Depends(get_current_active_user), db: AsyncIOMotorDatabase = Depends(get_db)):
    profile = await db.student_profiles.find_one({"user_id": user["_id"]})
    return {
        "id": user["_id"], "name": user["name"], "email": user["email"],
        "avatar": user.get("avatar"), "college": user.get("college"),
        "department": user.get("department"), "language": user.get("language"), "role": user["role"],
        "xp": profile["xp"] if profile else 0,
        "level": profile["level"] if profile else 1,
        "streak": profile["streak"] if profile else 0,
        "focus_score": profile["focus_score"] if profile else 0.0,
        "stress_score": profile["stress_score"] if profile else 0.0,
        "total_study_minutes": profile["total_study_minutes"] if profile else 0,
        "difficulty_preference": profile["difficulty_preference"] if profile else "medium",
    }


@router.put("/profile")
async def update_student_profile(
    data: UserUpdateRequest,
    user: dict = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    updates = data.model_dump(exclude_none=True)
    if updates:
        await db.users.update_one({"_id": user["_id"]}, {"$set": updates})
    await cache.delete(f"student:dashboard:{user['_id']}")
    return {"message": "Profile updated successfully."}


@router.get("/dashboard")
async def get_dashboard(user: dict = Depends(get_current_active_user), db: AsyncIOMotorDatabase = Depends(get_db)):
    cache_key = f"student:dashboard:{user['_id']}"
    cached = await cache.get(cache_key)
    if cached:
        return cached

    profile = await db.student_profiles.find_one({"user_id": user["_id"]})

    recent_emotions_raw = await db.emotion_history.find({"user_id": user["_id"]}).sort("created_at", -1).limit(10).to_list(10)
    recent_emotions = [
        {"emotion": e["emotion"], "confidence": e["confidence"],
         "stress_score": e["stress_score"], "focus_score": e["focus_score"], "created_at": str(e["created_at"])}
        for e in recent_emotions_raw
    ]

    analytics = await get_student_analytics(db, user["_id"], "weekly")
    recommendations = await get_recommendations(db, user["_id"], limit=4)

    user_badges = await db.user_badges.find({"user_id": user["_id"]}).limit(6).to_list(6)
    badges = []
    for ub in user_badges:
        badge = await db.badges.find_one({"_id": ub["badge_id"]})
        if badge:
            badges.append({"name": badge["name"], "emoji": badge["emoji"],
                           "description": badge["description"], "earned_at": str(ub["earned_at"])})

    notif_count = await db.notifications.count_documents({"user_id": user["_id"], "is_read": False})

    data = {
        "user": {"id": user["_id"], "name": user["name"], "email": user["email"], "avatar": user.get("avatar")},
        "xp": profile["xp"] if profile else 0,
        "level": profile["level"] if profile else 1,
        "streak": profile["streak"] if profile else 0,
        "focus_score": round(profile["focus_score"], 1) if profile else 0.0,
        "stress_score": round(profile["stress_score"], 1) if profile else 0.0,
        "total_study_minutes": profile["total_study_minutes"] if profile else 0,
        "recent_emotions": recent_emotions,
        "weekly_analytics": analytics.get("data_points", []),
        "analytics_summary": analytics.get("summary", {}),
        "insights": analytics.get("insights", []),
        "recommended_topics": recommendations,
        "badges": badges,
        "notifications_count": notif_count,
    }

    await cache.set(cache_key, data, ttl=120)
    return data


@router.get("/progress")
async def get_progress(
    period: str = Query(default="weekly", pattern="^(daily|weekly|monthly)$"),
    user: dict = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    analytics = await get_student_analytics(db, user["_id"], period)
    profile = await db.student_profiles.find_one({"user_id": user["_id"]})
    return {
        **analytics,
        "strong_topics": profile["strong_topics"] if profile else [],
        "weak_topics": profile["weak_topics"] if profile else [],
        "overall_progress": round((profile["xp"] / 7500) * 100, 1) if profile else 0,
    }


@router.get("/streak")
async def get_streak(user: dict = Depends(get_current_active_user), db: AsyncIOMotorDatabase = Depends(get_db)):
    profile = await db.student_profiles.find_one({"user_id": user["_id"]})
    return {
        "streak": profile["streak"] if profile else 0,
        "last_active": str(profile["last_active"]) if profile and profile.get("last_active") else None,
        "xp": profile["xp"] if profile else 0,
        "level": profile["level"] if profile else 1,
    }


@router.get("/badges")
async def get_badges(user: dict = Depends(get_current_active_user), db: AsyncIOMotorDatabase = Depends(get_db)):
    all_badges = await db.badges.find().to_list(100)
    earned = await db.user_badges.find({"user_id": user["_id"]}).to_list(100)
    earned_ids = {ub["badge_id"] for ub in earned}
    return [
        {"id": b["_id"], "name": b["name"], "emoji": b["emoji"], "description": b["description"],
         "xp_reward": b["xp_reward"], "earned": b["_id"] in earned_ids}
        for b in all_badges
    ]


@router.get("/leaderboard")
async def get_leaderboard_route(db: AsyncIOMotorDatabase = Depends(get_db), _: dict = Depends(get_current_active_user)):
    return await get_leaderboard(db, limit=10)
