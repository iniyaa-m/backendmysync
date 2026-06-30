from datetime import datetime, timezone
from typing import List, Dict, Any
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.models import new_badge, new_user_badge
from app.database.redis_client import cache
from app.utils.logger import logger

XP_REWARDS = {
    "quiz_easy": 10, "quiz_medium": 20, "quiz_hard": 40,
    "quiz_perfect": 50, "daily_login": 5, "streak_7": 100,
    "streak_30": 500, "course_complete": 150, "pdf_upload": 10, "chat_session": 5,
}

LEVEL_THRESHOLDS = [0, 100, 300, 600, 1000, 1500, 2200, 3000, 4000, 5500, 7500]

DEFAULT_BADGES = [
    {"name": "First Login", "emoji": "👋", "description": "Logged in for the first time", "requirement": "login_once", "xp_reward": 10},
    {"name": "Streak Master", "emoji": "🔥", "description": "7-day learning streak", "requirement": "streak_7", "xp_reward": 100},
    {"name": "Quiz Champion", "emoji": "🏆", "description": "Score 100% on any quiz", "requirement": "quiz_perfect", "xp_reward": 50},
    {"name": "Star Learner", "emoji": "⭐", "description": "Complete 10 study sessions", "requirement": "sessions_10", "xp_reward": 75},
    {"name": "Knowledge Seeker", "emoji": "📚", "description": "Complete 5 courses", "requirement": "courses_5", "xp_reward": 200},
    {"name": "Emotionally Aware", "emoji": "🧠", "description": "Use emotion detection 20 times", "requirement": "emotions_20", "xp_reward": 50},
    {"name": "Diamond Mind", "emoji": "💎", "description": "30-day streak", "requirement": "streak_30", "xp_reward": 500},
    {"name": "Mental Wellness", "emoji": "🧘", "description": "Complete 10 breathing exercises", "requirement": "breathing_10", "xp_reward": 80},
    {"name": "AI Explorer", "emoji": "🤖", "description": "50 AI chat messages", "requirement": "chat_50", "xp_reward": 60},
    {"name": "Rocket Start", "emoji": "🚀", "description": "Reach Level 5", "requirement": "level_5", "xp_reward": 150},
]


def _calculate_level(xp: int) -> tuple:
    level = 1
    for i, threshold in enumerate(LEVEL_THRESHOLDS):
        if xp >= threshold:
            level = i + 1
        else:
            break
    if level >= len(LEVEL_THRESHOLDS):
        return level, 100.0
    current_thresh = LEVEL_THRESHOLDS[level - 1]
    next_thresh = LEVEL_THRESHOLDS[level]
    progress = (xp - current_thresh) / (next_thresh - current_thresh) * 100
    return level, round(progress, 1)


async def award_xp(db: AsyncIOMotorDatabase, user_id: str, action: str, bonus: int = 0) -> Dict[str, Any]:
    xp_amount = XP_REWARDS.get(action, 0) + bonus
    profile = await db.student_profiles.find_one({"user_id": user_id})
    if not profile:
        return {"xp_earned": 0, "level": 1, "level_up": False}

    old_level, _ = _calculate_level(profile["xp"])
    new_xp = profile["xp"] + xp_amount
    new_level, progress = _calculate_level(new_xp)
    await db.student_profiles.update_one({"user_id": user_id}, {"$set": {"xp": new_xp, "level": new_level}})

    level_up = new_level > old_level
    if level_up and new_level == 5:
        await check_and_award_badge(db, user_id, "level_5")

    await cache.delete(f"student:dashboard:{user_id}")
    return {"xp_earned": xp_amount, "total_xp": new_xp, "level": new_level, "level_progress": progress, "level_up": level_up}


async def update_streak(db: AsyncIOMotorDatabase, user_id: str) -> int:
    profile = await db.student_profiles.find_one({"user_id": user_id})
    if not profile:
        return 0

    now = datetime.now(timezone.utc)
    last_active = profile.get("last_active")
    streak = profile.get("streak", 0)

    if last_active:
        days_diff = (now.date() - last_active.date()).days
        if days_diff == 1:
            streak += 1
        elif days_diff > 1:
            streak = 1
    else:
        streak = 1

    await db.student_profiles.update_one({"user_id": user_id}, {"$set": {"streak": streak, "last_active": now}})

    if streak == 7:
        await check_and_award_badge(db, user_id, "streak_7")
        await award_xp(db, user_id, "streak_7")
    elif streak == 30:
        await check_and_award_badge(db, user_id, "streak_30")
        await award_xp(db, user_id, "streak_30")

    return streak


async def check_and_award_badge(db: AsyncIOMotorDatabase, user_id: str, requirement: str):
    badge = await db.badges.find_one({"requirement": requirement})
    if not badge:
        return

    existing = await db.user_badges.find_one({"user_id": user_id, "badge_id": badge["_id"]})
    if existing:
        return

    await db.user_badges.insert_one(new_user_badge(user_id, badge["_id"]))
    await db.student_profiles.update_one({"user_id": user_id}, {"$inc": {"xp": badge["xp_reward"]}})

    from app.services.notifications.notification_service import send_achievement_notification
    await send_achievement_notification(db, user_id, badge["name"], badge["emoji"])
    logger.info(f"Badge '{badge['name']}' awarded to user {user_id}")


async def get_leaderboard(db: AsyncIOMotorDatabase, limit: int = 10) -> List[Dict[str, Any]]:
    cache_key = "leaderboard:global"
    cached = await cache.get(cache_key)
    if cached:
        return cached

    profiles = await db.student_profiles.find().sort("xp", -1).limit(limit).to_list(limit)
    board = []
    for rank, profile in enumerate(profiles, 1):
        user = await db.users.find_one({"_id": profile["user_id"], "anonymous_mode": False})
        if not user:
            continue
        level, _ = _calculate_level(profile["xp"])
        board.append({
            "rank": rank, "user_id": user["_id"], "name": user["name"],
            "avatar": user["avatar"], "xp": profile["xp"],
            "level": level, "streak": profile["streak"],
        })

    await cache.set(cache_key, board, ttl=300)
    return board


async def seed_badges(db: AsyncIOMotorDatabase):
    for badge_data in DEFAULT_BADGES:
        if not await db.badges.find_one({"name": badge_data["name"]}):
            await db.badges.insert_one(new_badge(**badge_data))
