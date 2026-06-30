from fastapi import APIRouter, Depends, HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.database.base import get_db
from app.services.auth_service import (
    register_user, login_user, refresh_access_token,
    forgot_password, reset_password, verify_email,
    verify_password, hash_password,
)
from app.schemas.schemas import (
    RegisterRequest, LoginRequest, TokenResponse, RefreshRequest,
    ForgotPasswordRequest, ResetPasswordRequest, ChangePasswordRequest,
)
from app.api.deps import get_current_active_user
from app.services.gamification_service import update_streak, award_xp, check_and_award_badge

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(data: RegisterRequest, db: AsyncIOMotorDatabase = Depends(get_db)):
    try:
        user = await register_user(db, data)
        return {"message": "Registration successful. Please verify your email.", "user_id": user["_id"], "email": user["email"]}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/login", response_model=TokenResponse)
async def login(data: LoginRequest, db: AsyncIOMotorDatabase = Depends(get_db)):
    try:
        user, access_token, refresh_token = await login_user(db, data)
        await update_streak(db, user["_id"])
        await award_xp(db, user["_id"], "daily_login")
        await check_and_award_badge(db, user["_id"], "login_once")
        return TokenResponse(access_token=access_token, refresh_token=refresh_token,
                             user_id=user["_id"], role=user["role"], name=user["name"])
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))


@router.post("/refresh", response_model=TokenResponse)
async def refresh(data: RefreshRequest, db: AsyncIOMotorDatabase = Depends(get_db)):
    try:
        access_token, new_refresh = await refresh_access_token(db, data.refresh_token)
        return {"access_token": access_token, "refresh_token": new_refresh, "token_type": "bearer", "user_id": "", "role": "", "name": ""}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))


@router.post("/forgot-password")
async def forgot_password_route(data: ForgotPasswordRequest, db: AsyncIOMotorDatabase = Depends(get_db)):
    await forgot_password(db, data.email)
    return {"message": "If the email exists, a reset link has been sent."}


@router.post("/reset-password")
async def reset_password_route(data: ResetPasswordRequest, db: AsyncIOMotorDatabase = Depends(get_db)):
    try:
        await reset_password(db, data.token, data.new_password)
        return {"message": "Password reset successful."}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/verify-email/{token}")
async def verify_email_route(token: str, db: AsyncIOMotorDatabase = Depends(get_db)):
    try:
        await verify_email(db, token)
        return {"message": "Email verified successfully."}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/change-password")
async def change_password(
    data: ChangePasswordRequest,
    user: dict = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    if not verify_password(data.current_password, user["hashed_password"]):
        raise HTTPException(status_code=400, detail="Current password is incorrect")
    await db.users.update_one({"_id": user["_id"]}, {"$set": {"hashed_password": hash_password(data.new_password)}})
    return {"message": "Password changed successfully."}


@router.get("/me")
async def get_me(user: dict = Depends(get_current_active_user)):
    return {
        "id": user["_id"], "name": user["name"], "email": user["email"],
        "role": user["role"], "avatar": user.get("avatar"), "college": user.get("college"),
        "department": user.get("department"), "language": user.get("language"),
        "is_verified": user.get("is_verified"), "created_at": str(user.get("created_at")),
    }


@router.post("/logout")
async def logout(user: dict = Depends(get_current_active_user), db: AsyncIOMotorDatabase = Depends(get_db)):
    from app.database.redis_client import cache
    await db.refresh_tokens.update_many({"user_id": user["_id"]}, {"$set": {"is_revoked": True}})
    await cache.delete(f"user:{user['_id']}")
    return {"message": "Logged out successfully."}
