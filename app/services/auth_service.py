from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple
import secrets

from jose import JWTError, jwt
from passlib.context import CryptContext
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.config.settings import settings
from app.models.models import new_user, new_student_profile, new_teacher_profile, new_user_settings, new_refresh_token
from app.schemas.schemas import RegisterRequest, LoginRequest
from app.database.redis_client import cache
from app.utils.email import send_verification_email, send_reset_email

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_access_token(data: dict) -> str:
    payload = data.copy()
    payload["exp"] = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload["type"] = "access"
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_refresh_token_str() -> str:
    return secrets.token_urlsafe(64)


def decode_token(token: str) -> dict:
    return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])


async def register_user(db: AsyncIOMotorDatabase, data: RegisterRequest) -> dict:
    if await db.users.find_one({"email": data.email}):
        raise ValueError("Email already registered")

    verification_token = secrets.token_urlsafe(32)
    user = new_user(
        name=data.name, email=data.email,
        hashed_password=hash_password(data.password),
        role=data.role, college=data.college,
        department=data.department,
        verification_token=verification_token,
    )
    await db.users.insert_one(user)

    if data.role == "student":
        await db.student_profiles.insert_one(new_student_profile(user["_id"]))
    elif data.role == "teacher":
        await db.teacher_profiles.insert_one(new_teacher_profile(user["_id"]))

    await db.user_settings.insert_one(new_user_settings(user["_id"]))

    try:
        await send_verification_email(user["email"], user["name"], verification_token)
    except Exception:
        pass

    return user


async def login_user(db: AsyncIOMotorDatabase, data: LoginRequest) -> Tuple[dict, str, str]:
    user = await db.users.find_one({"email": data.email})
    if not user or not verify_password(data.password, user["hashed_password"]):
        raise ValueError("Invalid credentials")
    if not user.get("is_active"):
        raise ValueError("Account is disabled")

    access_token = create_access_token({"sub": user["_id"], "role": user["role"], "email": user["email"]})
    refresh_token_str = create_refresh_token_str()

    rt = new_refresh_token(
        user_id=user["_id"], token=refresh_token_str,
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )
    await db.refresh_tokens.insert_one(rt)

    await cache.set(f"user:{user['_id']}", {
        "id": user["_id"], "role": user["role"], "email": user["email"], "name": user["name"]
    }, ttl=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60)

    return user, access_token, refresh_token_str


async def refresh_access_token(db: AsyncIOMotorDatabase, refresh_token: str) -> Tuple[str, str]:
    now = datetime.now(timezone.utc)
    rt = await db.refresh_tokens.find_one({
        "token": refresh_token, "is_revoked": False, "expires_at": {"$gt": now}
    })
    if not rt:
        raise ValueError("Invalid or expired refresh token")

    await db.refresh_tokens.update_one({"_id": rt["_id"]}, {"$set": {"is_revoked": True}})

    new_rt_str = create_refresh_token_str()
    new_rt = new_refresh_token(
        user_id=rt["user_id"], token=new_rt_str,
        expires_at=now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )
    await db.refresh_tokens.insert_one(new_rt)

    user = await db.users.find_one({"_id": rt["user_id"]})
    new_access = create_access_token({"sub": user["_id"], "role": user["role"], "email": user["email"]})
    return new_access, new_rt_str


async def get_current_user(token: str, db: AsyncIOMotorDatabase) -> dict:
    try:
        cached = await cache.get(f"token:{token[:20]}")
        if cached:
            user = await db.users.find_one({"_id": cached["id"]})
            if user and user.get("is_active"):
                return user

        payload = decode_token(token)
        user_id: str = payload.get("sub")
        if not user_id:
            raise ValueError("Invalid token")

        user = await db.users.find_one({"_id": user_id})
        if not user or not user.get("is_active"):
            raise ValueError("User not found or inactive")
        return user
    except JWTError:
        raise ValueError("Could not validate token")


async def forgot_password(db: AsyncIOMotorDatabase, email: str) -> bool:
    user = await db.users.find_one({"email": email})
    if not user:
        return True

    reset_token = secrets.token_urlsafe(32)
    expiry = datetime.now(timezone.utc) + timedelta(hours=1)
    await db.users.update_one({"_id": user["_id"]}, {"$set": {"reset_token": reset_token, "reset_token_expiry": expiry}})

    try:
        await send_reset_email(user["email"], user["name"], reset_token)
    except Exception:
        pass
    return True


async def reset_password(db: AsyncIOMotorDatabase, token: str, new_password: str) -> bool:
    now = datetime.now(timezone.utc)
    user = await db.users.find_one({"reset_token": token, "reset_token_expiry": {"$gt": now}})
    if not user:
        raise ValueError("Invalid or expired reset token")

    await db.users.update_one({"_id": user["_id"]}, {"$set": {
        "hashed_password": hash_password(new_password),
        "reset_token": None, "reset_token_expiry": None,
    }})
    return True


async def verify_email(db: AsyncIOMotorDatabase, token: str) -> bool:
    user = await db.users.find_one({"verification_token": token})
    if not user:
        raise ValueError("Invalid verification token")
    await db.users.update_one({"_id": user["_id"]}, {"$set": {"is_verified": True, "verification_token": None}})
    return True
