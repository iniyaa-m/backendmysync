import uuid
from datetime import datetime, timezone
from enum import Enum


def gen_uuid() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class UserRole(str, Enum):
    student = "student"
    teacher = "teacher"
    admin = "admin"


class EmotionLabel(str, Enum):
    happy = "happy"
    sad = "sad"
    angry = "angry"
    neutral = "neutral"
    confused = "confused"
    stressed = "stressed"
    fear = "fear"
    surprise = "surprise"
    tired = "tired"
    focused = "focused"
    confident = "confident"


class VoiceTone(str, Enum):
    calm = "calm"
    stressed = "stressed"
    frustrated = "frustrated"
    excited = "excited"
    neutral = "neutral"


class Difficulty(str, Enum):
    easy = "easy"
    medium = "medium"
    hard = "hard"


class NotifType(str, Enum):
    stress_alert = "stress_alert"
    achievement = "achievement"
    reminder = "reminder"
    info = "info"
    warning = "warning"


# ── Document factory helpers ────────────────────────────────────────────────

def new_user(name, email, hashed_password, role="student", college=None, department=None, verification_token=None):
    return {
        "_id": gen_uuid(), "name": name, "email": email,
        "hashed_password": hashed_password, "role": role,
        "college": college, "department": department,
        "avatar": "👤", "language": "en",
        "is_active": True, "is_verified": False,
        "verification_token": verification_token,
        "reset_token": None, "reset_token_expiry": None,
        "camera_consent": True, "mic_consent": True,
        "anonymous_mode": False, "fcm_token": None,
        "created_at": utcnow(), "updated_at": None,
    }


def new_student_profile(user_id):
    return {
        "_id": gen_uuid(), "user_id": user_id,
        "xp": 0, "level": 1, "streak": 0,
        "last_active": None, "total_study_minutes": 0,
        "focus_score": 0.0, "stress_score": 0.0,
        "weak_topics": [], "strong_topics": [],
        "difficulty_preference": "medium", "subjects": [],
        "created_at": utcnow(),
    }


def new_teacher_profile(user_id):
    return {
        "_id": gen_uuid(), "user_id": user_id,
        "subjects": [], "total_students": 0,
        "created_at": utcnow(),
    }


def new_user_settings(user_id):
    return {
        "_id": gen_uuid(), "user_id": user_id,
        "dark_mode": True, "language": "en",
        "offline_mode": False, "email_notifications": True,
        "push_notifications": True, "stress_alert_threshold": 70.0,
        "break_reminder_interval": 50,
        "created_at": utcnow(), "updated_at": None,
    }


def new_refresh_token(user_id, token, expires_at):
    return {
        "_id": gen_uuid(), "user_id": user_id,
        "token": token, "expires_at": expires_at,
        "is_revoked": False, "created_at": utcnow(),
    }


def new_emotion_history(user_id, emotion, confidence, stress_score, focus_score,
                        source="webcam", recommendation=None, session_id=None, raw_data=None):
    return {
        "_id": gen_uuid(), "user_id": user_id,
        "emotion": emotion, "confidence": confidence,
        "stress_score": stress_score, "focus_score": focus_score,
        "source": source, "recommendation": recommendation,
        "session_id": session_id, "raw_data": raw_data,
        "created_at": utcnow(),
    }


def new_voice_emotion(user_id, emotion, tone, confidence=0.7, stress_score=0.0,
                      transcript="", sentiment="neutral", audio_duration=None):
    return {
        "_id": gen_uuid(), "user_id": user_id,
        "emotion": emotion, "tone": tone,
        "confidence": confidence, "stress_score": stress_score,
        "transcript": transcript, "sentiment": sentiment,
        "audio_duration": audio_duration, "created_at": utcnow(),
    }


def new_chat_message(user_id, session_id, role, content,
                     emotion_context=None, sentiment=None, tokens_used=0):
    return {
        "_id": gen_uuid(), "user_id": user_id,
        "session_id": session_id, "role": role,
        "content": content, "emotion_context": emotion_context,
        "sentiment": sentiment, "tokens_used": tokens_used,
        "created_at": utcnow(),
    }


def new_notification(user_id, title, body, notif_type="info", extra_data=None):
    return {
        "_id": gen_uuid(), "user_id": user_id,
        "title": title, "body": body,
        "notif_type": notif_type, "is_read": False,
        "extra_data": extra_data or {}, "created_at": utcnow(),
    }


def new_document(user_id, filename, content_text="", page_count=None, embedding_stored=False):
    return {
        "_id": gen_uuid(), "user_id": user_id,
        "filename": filename, "file_url": None,
        "content_text": content_text, "page_count": page_count,
        "embedding_stored": embedding_stored, "created_at": utcnow(),
    }


def new_badge(name, emoji, description, requirement, xp_reward=100):
    return {
        "_id": gen_uuid(), "name": name, "emoji": emoji,
        "description": description, "requirement": requirement,
        "xp_reward": xp_reward, "created_at": utcnow(),
    }


def new_user_badge(user_id, badge_id):
    return {"_id": gen_uuid(), "user_id": user_id, "badge_id": badge_id, "earned_at": utcnow()}


def new_learning_history(user_id, topic, subject=None, action=None, score=None,
                         duration_minutes=0, emotion_at_time=None):
    return {
        "_id": gen_uuid(), "user_id": user_id,
        "topic": topic, "subject": subject, "action": action,
        "score": score, "duration_minutes": duration_minutes,
        "emotion_at_time": emotion_at_time, "created_at": utcnow(),
    }
