from typing import List, Optional, Dict
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models.models import new_notification
from app.database.redis_client import cache
from app.utils.logger import logger


async def create_notification(
    db: AsyncIOMotorDatabase, user_id: str, title: str, body: str,
    notif_type: str = "info", metadata: Optional[Dict] = None,
) -> dict:
    notif = new_notification(user_id, title, body, notif_type, metadata)
    await db.notifications.insert_one(notif)

    await _push_ws_notification(user_id, {
        "id": notif["_id"], "title": title, "body": body,
        "type": notif_type, "created_at": str(notif["created_at"]),
    })

    user = await db.users.find_one({"_id": user_id})
    if user and user.get("fcm_token"):
        await _send_fcm(user["fcm_token"], title, body)

    return notif


async def _push_ws_notification(user_id: str, data: dict):
    try:
        import json
        from app.database.redis_client import get_redis
        client = await get_redis()
        if client:
            await client.publish(f"ws:notifications:{user_id}", json.dumps(data))
    except Exception as e:
        logger.warning(f"WS notification push failed: {e}")


async def _send_fcm(token: str, title: str, body: str):
    try:
        import firebase_admin
        from firebase_admin import messaging, credentials
        from app.config.settings import settings
        import os
        if not firebase_admin._apps:
            if os.path.exists(settings.FIREBASE_CREDENTIALS_PATH):
                firebase_admin.initialize_app(credentials.Certificate(settings.FIREBASE_CREDENTIALS_PATH))
            else:
                return
        messaging.send(messaging.Message(
            notification=messaging.Notification(title=title, body=body), token=token
        ))
    except Exception as e:
        logger.warning(f"FCM send failed: {e}")


async def get_user_notifications(
    db: AsyncIOMotorDatabase, user_id: str, page: int = 1, per_page: int = 20, unread_only: bool = False,
) -> dict:
    query = {"user_id": user_id}
    if unread_only:
        query["is_read"] = False

    total = await db.notifications.count_documents(query)
    cursor = db.notifications.find(query).sort("created_at", -1).skip((page - 1) * per_page).limit(per_page)
    notifications = await cursor.to_list(per_page)

    return {
        "items": [
            {"id": n["_id"], "title": n["title"], "body": n["body"],
             "notif_type": n["notif_type"], "is_read": n["is_read"], "created_at": str(n["created_at"])}
            for n in notifications
        ],
        "total": total, "page": page, "per_page": per_page,
        "pages": (total + per_page - 1) // per_page,
    }


async def mark_notifications_read(
    db: AsyncIOMotorDatabase, user_id: str, notification_ids: Optional[List[str]] = None,
):
    query = {"user_id": user_id, "is_read": False}
    if notification_ids:
        query["_id"] = {"$in": notification_ids}
    await db.notifications.update_many(query, {"$set": {"is_read": True}})


async def send_stress_alert(db: AsyncIOMotorDatabase, user_id: str, stress_score: float):
    await create_notification(
        db, user_id,
        title="⚠️ High Stress Detected",
        body=f"Stress level at {stress_score:.0f}%. Take a 5-minute break and try a breathing exercise.",
        notif_type="warning", metadata={"stress_score": stress_score},
    )


async def send_achievement_notification(db: AsyncIOMotorDatabase, user_id: str, badge_name: str, badge_emoji: str):
    await create_notification(
        db, user_id,
        title=f"{badge_emoji} Achievement Unlocked!",
        body=f"You earned the '{badge_name}' badge. Keep up the great work!",
        notif_type="achievement", metadata={"badge": badge_name},
    )


async def send_break_reminder(db: AsyncIOMotorDatabase, user_id: str, minutes: int):
    await create_notification(
        db, user_id,
        title="⏰ Break Time!",
        body=f"You've been studying for {minutes} minutes. A short break improves retention!",
        notif_type="reminder",
    )
