from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, Query, BackgroundTasks
from fastapi.responses import StreamingResponse
from motor.motor_asyncio import AsyncIOMotorDatabase
import io, uuid

from app.database.base import get_db
from app.api.deps import get_current_active_user
from app.models.models import new_emotion_history, new_voice_emotion, new_chat_message, new_document
from app.schemas.schemas import (
    ChatRequest, QuizGenerateRequest, QuizSubmitRequest,
    NotesGenerateRequest, RAGQueryRequest, SettingsUpdateRequest,
)
from app.services.ai.emotion_service import analyze_image_emotion
from app.services.ai.voice_service import analyze_voice_emotion
from app.services.ai.chat_service import chat_with_tutor, generate_quiz_with_llm, generate_notes_with_llm
from app.services.ai.pdf_service import process_pdf, rag_query
from app.services.analytics.analytics_service import get_student_analytics
from app.services.analytics.recommendation_service import get_recommendations
from app.services.notifications.notification_service import (
    get_user_notifications, mark_notifications_read, send_stress_alert,
)
from app.services.report_service import generate_pdf_report, generate_csv_report
from app.services.gamification_service import award_xp, check_and_award_badge
from app.database.redis_client import cache

# ─── Emotion ──────────────────────────────────────────────────────────────────
emotion_router = APIRouter(prefix="/emotion", tags=["Emotion Detection"])


@emotion_router.post("/image")
async def detect_emotion_from_image(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    session_id: str = Query(default=None),
    user: dict = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    if not user.get("camera_consent"):
        raise HTTPException(status_code=403, detail="Camera consent not given")
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image")

    image_bytes = await file.read()
    result = await analyze_image_emotion(image_bytes, session_id)

    async def _store():
        await db.emotion_history.insert_one(new_emotion_history(
            user_id=user["_id"], emotion=result["emotion"], confidence=result["confidence"],
            stress_score=result["stress_score"], focus_score=result["focus_score"],
            source="upload", recommendation=result["recommendation"],
            session_id=result.get("session_id"), raw_data=result.get("raw_data"),
        ))
        profile = await db.student_profiles.find_one({"user_id": user["_id"]})
        if profile:
            new_stress = profile["stress_score"] * 0.8 + result["stress_score"] * 0.2
            new_focus = profile["focus_score"] * 0.8 + result["focus_score"] * 0.2
            await db.student_profiles.update_one(
                {"user_id": user["_id"]}, {"$set": {"stress_score": new_stress, "focus_score": new_focus}}
            )
        if result["stress_score"] > 70:
            await send_stress_alert(db, user["_id"], result["stress_score"])

    background_tasks.add_task(_store)
    return result


@emotion_router.get("/history")
async def get_emotion_history(
    limit: int = Query(default=20, ge=1, le=100),
    user: dict = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    emotions = await db.emotion_history.find({"user_id": user["_id"]}).sort("created_at", -1).limit(limit).to_list(limit)
    return [
        {"id": e["_id"], "emotion": e["emotion"], "confidence": e["confidence"],
         "stress_score": e["stress_score"], "focus_score": e["focus_score"],
         "source": e["source"], "created_at": str(e["created_at"])}
        for e in emotions
    ]


# ─── Voice ────────────────────────────────────────────────────────────────────
voice_router = APIRouter(prefix="/emotion", tags=["Voice Emotion"])


@voice_router.post("/audio")
async def detect_voice_emotion(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    user: dict = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    if not user.get("mic_consent"):
        raise HTTPException(status_code=403, detail="Microphone consent not given")

    audio_bytes = await file.read()
    result = await analyze_voice_emotion(audio_bytes, file.filename or "audio.wav")

    async def _store():
        await db.voice_emotions.insert_one(new_voice_emotion(
            user_id=user["_id"], emotion=result["emotion"], tone=result["tone"],
            confidence=result.get("confidence", 0.7), stress_score=result["stress_score"],
            transcript=result.get("transcript", ""), sentiment=result.get("sentiment", "neutral"),
        ))

    background_tasks.add_task(_store)
    return result


# ─── Chat ─────────────────────────────────────────────────────────────────────
chat_router = APIRouter(prefix="/chat", tags=["AI Chat"])


@chat_router.post("")
async def chat(
    data: ChatRequest,
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    result = await chat_with_tutor(
        user_id=user["_id"], message=data.message, session_id=data.session_id,
        emotion_context=data.emotion_context or "neutral", language=data.language or user.get("language") or "en",
    )

    async def _store():
        sid = result["session_id"]
        await db.chat_messages.insert_one(new_chat_message(
            user_id=user["_id"], session_id=sid, role="user",
            content=data.message, emotion_context=data.emotion_context, sentiment=result.get("sentiment"),
        ))
        await db.chat_messages.insert_one(new_chat_message(
            user_id=user["_id"], session_id=sid, role="assistant",
            content=result["reply"], tokens_used=result.get("tokens_used", 0),
        ))
        await award_xp(db, user["_id"], "chat_session")

    background_tasks.add_task(_store)
    return result


@chat_router.get("/history/{session_id}")
async def get_chat_history(session_id: str, user: dict = Depends(get_current_active_user), db: AsyncIOMotorDatabase = Depends(get_db)):
    messages = await db.chat_messages.find({"user_id": user["_id"], "session_id": session_id}).sort("created_at", 1).to_list(200)
    return [
        {"id": m["_id"], "role": m["role"], "content": m["content"],
         "emotion_context": m.get("emotion_context"), "created_at": str(m["created_at"])}
        for m in messages
    ]


@chat_router.get("/sessions")
async def get_chat_sessions(user: dict = Depends(get_current_active_user), db: AsyncIOMotorDatabase = Depends(get_db)):
    pipeline = [
        {"$match": {"user_id": user["_id"]}},
        {"$group": {"_id": "$session_id", "last_msg": {"$max": "$created_at"}}},
        {"$sort": {"last_msg": -1}},
        {"$limit": 20},
    ]
    rows = await db.chat_messages.aggregate(pipeline).to_list(20)
    return [{"session_id": r["_id"], "last_message_at": str(r["last_msg"])} for r in rows]


# ─── Learning ─────────────────────────────────────────────────────────────────
learning_router = APIRouter(prefix="/learning", tags=["Adaptive Learning"])


@learning_router.get("/recommendations")
async def get_learning_recommendations(
    limit: int = Query(default=5, ge=1, le=10),
    user: dict = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    return await get_recommendations(db, user["_id"], limit=limit)


@learning_router.post("/quiz/generate")
async def generate_quiz(data: QuizGenerateRequest, user: dict = Depends(get_current_active_user)):
    quiz_id = str(uuid.uuid4())
    questions = await generate_quiz_with_llm(
        topic=data.topic, difficulty=data.difficulty,
        num_questions=data.num_questions, question_types=data.question_types, language=data.language,
    )
    return {"quiz_id": quiz_id, "topic": data.topic, "difficulty": data.difficulty,
            "questions": questions, "time_limit_minutes": data.num_questions * 2}


@learning_router.post("/quiz/submit")
async def submit_quiz(
    data: QuizSubmitRequest,
    background_tasks: BackgroundTasks,
    user: dict = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    total = len(data.answers)
    correct = sum(1 for v in data.answers.values() if v)
    score_pct = (correct / total * 100) if total > 0 else 0.0
    xp_result = await award_xp(db, user["_id"], "quiz_medium", bonus=int(score_pct / 10))
    if score_pct == 100:
        await check_and_award_badge(db, user["_id"], "quiz_perfect")
    return {
        "score": correct, "max_score": total, "percentage": round(score_pct, 1),
        "xp_earned": xp_result["xp_earned"], "level_up": xp_result["level_up"], "badges_earned": [],
    }


@learning_router.post("/notes/generate")
async def generate_notes(data: NotesGenerateRequest, user: dict = Depends(get_current_active_user)):
    return await generate_notes_with_llm(data.content, data.topic, data.language)


# ─── Analytics ────────────────────────────────────────────────────────────────
analytics_router = APIRouter(prefix="/analytics", tags=["Analytics"])


@analytics_router.get("")
async def get_analytics(
    period: str = Query(default="weekly", pattern="^(daily|weekly|monthly)$"),
    user: dict = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    return await get_student_analytics(db, user["_id"], period)


# ─── Notifications ────────────────────────────────────────────────────────────
notif_router = APIRouter(prefix="/notifications", tags=["Notifications"])


@notif_router.get("")
async def list_notifications(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=50),
    unread_only: bool = Query(default=False),
    user: dict = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    return await get_user_notifications(db, user["_id"], page, per_page, unread_only)


@notif_router.post("/mark-read")
async def mark_read(
    notification_ids: list[str] = None,
    user: dict = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    await mark_notifications_read(db, user["_id"], notification_ids)
    return {"message": "Notifications marked as read."}


# ─── Reports ──────────────────────────────────────────────────────────────────
report_router = APIRouter(prefix="/reports", tags=["Reports"])


@report_router.get("/download")
async def download_report(
    period: str = Query(default="weekly"),
    format: str = Query(default="pdf", pattern="^(pdf|csv)$"),
    user: dict = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    if format == "pdf":
        content = await generate_pdf_report(db, user["_id"], user["name"], period)
        return StreamingResponse(io.BytesIO(content), media_type="application/pdf",
                                 headers={"Content-Disposition": f"attachment; filename=mindsync_report_{period}.pdf"})
    else:
        content = await generate_csv_report(db, user["_id"], period)
        return StreamingResponse(io.StringIO(content), media_type="text/csv",
                                 headers={"Content-Disposition": f"attachment; filename=mindsync_report_{period}.csv"})


# ─── PDF / RAG ────────────────────────────────────────────────────────────────
pdf_router = APIRouter(prefix="/documents", tags=["PDF & RAG"])


@pdf_router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    user: dict = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported")
    pdf_bytes = await file.read()
    result = await process_pdf(pdf_bytes)
    doc = new_document(
        user_id=user["_id"], filename=file.filename,
        content_text=result.get("text", "")[:10000],
        page_count=result.get("page_count"),
        embedding_stored=result.get("success", False),
    )
    await db.documents.insert_one(doc)
    await award_xp(db, user["_id"], "pdf_upload")
    return {"id": doc["_id"], "filename": doc["filename"], "page_count": doc["page_count"],
            "embedding_stored": doc["embedding_stored"], "chunks": result.get("chunks", 0)}


@pdf_router.post("/query")
async def query_documents(data: RAGQueryRequest, user: dict = Depends(get_current_active_user)):
    return await rag_query(data.query, data.document_ids, data.language)


@pdf_router.get("")
async def list_documents(user: dict = Depends(get_current_active_user), db: AsyncIOMotorDatabase = Depends(get_db)):
    docs = await db.documents.find({"user_id": user["_id"]}).sort("created_at", -1).to_list(100)
    return [{"id": d["_id"], "filename": d["filename"], "page_count": d.get("page_count"),
             "embedding_stored": d["embedding_stored"], "created_at": str(d["created_at"])} for d in docs]


# ─── Settings ─────────────────────────────────────────────────────────────────
settings_router = APIRouter(prefix="/settings", tags=["Settings"])


@settings_router.get("")
async def get_settings_route(user: dict = Depends(get_current_active_user), db: AsyncIOMotorDatabase = Depends(get_db)):
    s = await db.user_settings.find_one({"user_id": user["_id"]})
    if not s:
        return {}
    return {
        "dark_mode": s["dark_mode"], "language": s["language"], "offline_mode": s["offline_mode"],
        "email_notifications": s["email_notifications"], "push_notifications": s["push_notifications"],
        "stress_alert_threshold": s["stress_alert_threshold"], "break_reminder_interval": s["break_reminder_interval"],
    }


@settings_router.put("")
async def update_settings_route(
    data: SettingsUpdateRequest,
    user: dict = Depends(get_current_active_user),
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    updates = data.model_dump(exclude_none=True)
    if updates:
        await db.user_settings.update_one(
            {"user_id": user["_id"]}, {"$set": updates}, upsert=True
        )
    return {"message": "Settings updated."}
