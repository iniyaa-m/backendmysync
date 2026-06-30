import asyncio
import json
from typing import Dict, Set, Optional
from fastapi import WebSocket, WebSocketDisconnect, APIRouter, Query

from app.services.ai.emotion_service import analyze_frame_base64
from app.services.ai.voice_service import analyze_audio_chunk
from app.services.auth_service import decode_token
from app.database.redis_client import get_redis
from app.utils.logger import logger

router = APIRouter(tags=["WebSockets"])


class ConnectionManager:
    def __init__(self):
        self.active: Dict[str, Set[WebSocket]] = {}
        self.rooms: Dict[str, Set[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, user_id: str):
        await websocket.accept()
        if user_id not in self.active:
            self.active[user_id] = set()
        self.active[user_id].add(websocket)

    def disconnect(self, websocket: WebSocket, user_id: str):
        if user_id in self.active:
            self.active[user_id].discard(websocket)
            if not self.active[user_id]:
                del self.active[user_id]

    async def send_to_user(self, user_id: str, data: dict):
        if user_id in self.active:
            dead = set()
            for ws in self.active[user_id]:
                try:
                    await ws.send_json(data)
                except Exception:
                    dead.add(ws)
            self.active[user_id] -= dead

    def join_room(self, websocket: WebSocket, room: str):
        if room not in self.rooms:
            self.rooms[room] = set()
        self.rooms[room].add(websocket)

    def leave_room(self, websocket: WebSocket, room: str):
        if room in self.rooms:
            self.rooms[room].discard(websocket)

    @property
    def online_users(self) -> Set[str]:
        return set(self.active.keys())


manager = ConnectionManager()


def _get_user_id_from_token(token: str) -> Optional[str]:
    try:
        payload = decode_token(token)
        return payload.get("sub")
    except Exception:
        return None


@router.websocket("/ws/emotion")
async def emotion_websocket(websocket: WebSocket, token: str = Query(...)):
    user_id = _get_user_id_from_token(token)
    if not user_id:
        await websocket.close(code=4001, reason="Invalid token")
        return

    await manager.connect(websocket, user_id)
    try:
        while True:
            data = await asyncio.wait_for(websocket.receive_text(), timeout=30)
            payload = json.loads(data)
            frame_b64 = payload.get("frame")
            if not frame_b64:
                await websocket.send_json({"error": "No frame provided"})
                continue
            result = await analyze_frame_base64(frame_b64)
            await websocket.send_json({"type": "emotion", **result})
    except WebSocketDisconnect:
        pass
    except asyncio.TimeoutError:
        await websocket.send_json({"type": "ping", "message": "Connection alive"})
    except Exception as e:
        logger.error(f"Emotion WS error: {e}")
    finally:
        manager.disconnect(websocket, user_id)


@router.websocket("/ws/audio")
async def audio_websocket(websocket: WebSocket, token: str = Query(...)):
    user_id = _get_user_id_from_token(token)
    if not user_id:
        await websocket.close(code=4001, reason="Invalid token")
        return

    await manager.connect(websocket, user_id)
    await websocket.send_json({"type": "ready", "message": "Audio stream ready"})
    try:
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_bytes(), timeout=30)
            except asyncio.TimeoutError:
                await websocket.send_json({"type": "ping"})
                continue
            if len(data) < 100:
                continue
            result = await analyze_audio_chunk(data)
            await websocket.send_json({"type": "voice_emotion", **result})
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"Audio WS error: {e}")
    finally:
        manager.disconnect(websocket, user_id)


@router.websocket("/ws/notifications")
async def notifications_websocket(websocket: WebSocket, token: str = Query(...)):
    user_id = _get_user_id_from_token(token)
    if not user_id:
        await websocket.close(code=4001, reason="Invalid token")
        return

    await manager.connect(websocket, user_id)
    await websocket.send_json({"type": "connected", "message": "Notification stream active"})
    try:
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30)
                if data == "ping":
                    await websocket.send_json({"type": "pong"})
            except asyncio.TimeoutError:
                await websocket.send_json({"type": "ping"})
            except WebSocketDisconnect:
                break
    except Exception as e:
        logger.error(f"Notification WS error: {e}")
    finally:
        manager.disconnect(websocket, user_id)


@router.websocket("/ws/teacher/dashboard")
async def teacher_dashboard_websocket(websocket: WebSocket, token: str = Query(...)):
    user_id = _get_user_id_from_token(token)
    if not user_id:
        await websocket.close(code=4001, reason="Invalid token")
        return

    await manager.connect(websocket, user_id)
    manager.join_room(websocket, "teacher_dashboard")
    await websocket.send_json({"type": "connected", "online_users": len(manager.online_users)})
    try:
        while True:
            try:
                await asyncio.wait_for(websocket.receive_text(), timeout=5)
            except asyncio.TimeoutError:
                await websocket.send_json({"type": "stats_update", "online_users": len(manager.online_users)})
            except WebSocketDisconnect:
                break
    except Exception as e:
        logger.error(f"Teacher dashboard WS error: {e}")
    finally:
        manager.disconnect(websocket, user_id)
        manager.leave_room(websocket, "teacher_dashboard")


@router.websocket("/ws/chat")
async def chat_websocket(websocket: WebSocket, token: str = Query(...)):
    from app.services.ai.chat_service import chat_with_tutor

    user_id = _get_user_id_from_token(token)
    if not user_id:
        await websocket.close(code=4001, reason="Invalid token")
        return

    await manager.connect(websocket, user_id)
    try:
        while True:
            data = await websocket.receive_text()
            payload = json.loads(data)
            if payload.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
                continue
            message = payload.get("message", "")
            if not message:
                continue
            await websocket.send_json({"type": "typing", "is_typing": True})
            result = await chat_with_tutor(
                user_id=user_id, message=message,
                session_id=payload.get("session_id"), emotion_context=payload.get("emotion", "neutral"),
            )
            await websocket.send_json({
                "type": "message", "content": result["reply"],
                "session_id": result["session_id"], "sentiment": result["sentiment"],
                "suggestions": result["suggestions"], "is_typing": False,
            })
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"Chat WS error: {e}")
    finally:
        manager.disconnect(websocket, user_id)
