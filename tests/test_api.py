import pytest
import pytest_asyncio
from httpx import AsyncClient


# ─── Auth Tests ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestAuth:

    async def test_register_student_success(self, client: AsyncClient):
        resp = await client.post("/api/v1/auth/register", json={
            "name": "Alice Smith",
            "email": "alice@test.com",
            "password": "alice123",
            "role": "student",
        })
        assert resp.status_code == 201
        data = resp.json()
        assert "user_id" in data
        assert data["email"] == "alice@test.com"

    async def test_register_duplicate_email(self, client: AsyncClient):
        payload = {"name": "Bob", "email": "bob@test.com", "password": "bob12345", "role": "student"}
        await client.post("/api/v1/auth/register", json=payload)
        resp = await client.post("/api/v1/auth/register", json=payload)
        assert resp.status_code == 400
        assert "already registered" in resp.json()["detail"]

    async def test_register_weak_password(self, client: AsyncClient):
        resp = await client.post("/api/v1/auth/register", json={
            "name": "Weak", "email": "weak@test.com", "password": "abc", "role": "student",
        })
        assert resp.status_code == 422

    async def test_login_success(self, client: AsyncClient):
        await client.post("/api/v1/auth/register", json={
            "name": "Carol", "email": "carol@test.com", "password": "carol123", "role": "student",
        })
        resp = await client.post("/api/v1/auth/login", json={
            "email": "carol@test.com", "password": "carol123",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["token_type"] == "bearer"

    async def test_login_wrong_password(self, client: AsyncClient):
        await client.post("/api/v1/auth/register", json={
            "name": "Dave", "email": "dave@test.com", "password": "dave1234", "role": "student",
        })
        resp = await client.post("/api/v1/auth/login", json={
            "email": "dave@test.com", "password": "wrongpassword",
        })
        assert resp.status_code == 401

    async def test_login_nonexistent_user(self, client: AsyncClient):
        resp = await client.post("/api/v1/auth/login", json={
            "email": "ghost@test.com", "password": "ghost1234",
        })
        assert resp.status_code == 401

    async def test_get_me(self, client: AsyncClient, student_token: str):
        resp = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {student_token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert "email" in data
        assert "role" in data

    async def test_get_me_no_token(self, client: AsyncClient):
        resp = await client.get("/api/v1/auth/me")
        assert resp.status_code == 403

    async def test_get_me_invalid_token(self, client: AsyncClient):
        resp = await client.get("/api/v1/auth/me", headers={"Authorization": "Bearer invalidtoken"})
        assert resp.status_code == 401

    async def test_refresh_token(self, client: AsyncClient):
        await client.post("/api/v1/auth/register", json={
            "name": "Eve", "email": "eve@test.com", "password": "eve12345", "role": "student",
        })
        login_resp = await client.post("/api/v1/auth/login", json={
            "email": "eve@test.com", "password": "eve12345",
        })
        refresh_token = login_resp.json()["refresh_token"]
        resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
        assert resp.status_code == 200
        assert "access_token" in resp.json()

    async def test_logout(self, client: AsyncClient, student_token: str):
        resp = await client.post("/api/v1/auth/logout", headers={"Authorization": f"Bearer {student_token}"})
        assert resp.status_code == 200

    async def test_forgot_password(self, client: AsyncClient):
        resp = await client.post("/api/v1/auth/forgot-password", json={"email": "alice@test.com"})
        assert resp.status_code == 200

    async def test_change_password(self, client: AsyncClient):
        await client.post("/api/v1/auth/register", json={
            "name": "Frank", "email": "frank@test.com", "password": "frank123", "role": "student",
        })
        login_resp = await client.post("/api/v1/auth/login", json={
            "email": "frank@test.com", "password": "frank123",
        })
        token = login_resp.json()["access_token"]
        resp = await client.post("/api/v1/auth/change-password",
            headers={"Authorization": f"Bearer {token}"},
            json={"current_password": "frank123", "new_password": "newpass456"},
        )
        assert resp.status_code == 200


# ─── Student Tests ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestStudent:

    async def test_get_profile(self, client: AsyncClient, student_token: str):
        resp = await client.get("/api/v1/student/profile", headers={"Authorization": f"Bearer {student_token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert "xp" in data
        assert "streak" in data
        assert "level" in data

    async def test_update_profile(self, client: AsyncClient, student_token: str):
        resp = await client.put("/api/v1/student/profile",
            headers={"Authorization": f"Bearer {student_token}"},
            json={"language": "ta", "college": "MIT"},
        )
        assert resp.status_code == 200

    async def test_get_dashboard(self, client: AsyncClient, student_token: str):
        resp = await client.get("/api/v1/student/dashboard", headers={"Authorization": f"Bearer {student_token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert "recent_emotions" in data
        assert "badges" in data
        assert "recommended_topics" in data

    async def test_get_progress(self, client: AsyncClient, student_token: str):
        resp = await client.get("/api/v1/student/progress?period=weekly",
            headers={"Authorization": f"Bearer {student_token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "period" in data

    async def test_get_streak(self, client: AsyncClient, student_token: str):
        resp = await client.get("/api/v1/student/streak", headers={"Authorization": f"Bearer {student_token}"})
        assert resp.status_code == 200
        assert "streak" in resp.json()

    async def test_get_badges(self, client: AsyncClient, student_token: str):
        resp = await client.get("/api/v1/student/badges", headers={"Authorization": f"Bearer {student_token}"})
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    async def test_get_leaderboard(self, client: AsyncClient, student_token: str):
        resp = await client.get("/api/v1/student/leaderboard", headers={"Authorization": f"Bearer {student_token}"})
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    async def test_dashboard_no_auth(self, client: AsyncClient):
        resp = await client.get("/api/v1/student/dashboard")
        assert resp.status_code == 403


# ─── Teacher Tests ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestTeacher:

    async def test_teacher_dashboard(self, client: AsyncClient, teacher_token: str):
        resp = await client.get("/api/v1/teacher/dashboard", headers={"Authorization": f"Bearer {teacher_token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert "total_students" in data
        assert "stress_alerts" in data

    async def test_class_list(self, client: AsyncClient, teacher_token: str):
        resp = await client.get("/api/v1/teacher/class", headers={"Authorization": f"Bearer {teacher_token}"})
        assert resp.status_code == 200
        assert "students" in resp.json()

    async def test_teacher_alerts(self, client: AsyncClient, teacher_token: str):
        resp = await client.get("/api/v1/teacher/alerts", headers={"Authorization": f"Bearer {teacher_token}"})
        assert resp.status_code == 200
        assert "alerts" in resp.json()

    async def test_teacher_reports(self, client: AsyncClient, teacher_token: str):
        resp = await client.get("/api/v1/teacher/reports", headers={"Authorization": f"Bearer {teacher_token}"})
        assert resp.status_code == 200

    async def test_student_cannot_access_teacher_route(self, client: AsyncClient, student_token: str):
        resp = await client.get("/api/v1/teacher/dashboard", headers={"Authorization": f"Bearer {student_token}"})
        assert resp.status_code == 403


# ─── Emotion Detection Tests ──────────────────────────────────────────────────

@pytest.mark.asyncio
class TestEmotionDetection:

    async def test_emotion_history_empty(self, client: AsyncClient, student_token: str):
        resp = await client.get("/api/v1/emotion/history", headers={"Authorization": f"Bearer {student_token}"})
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    async def test_image_upload_invalid_type(self, client: AsyncClient, student_token: str):
        resp = await client.post("/api/v1/emotion/image",
            headers={"Authorization": f"Bearer {student_token}"},
            files={"file": ("test.txt", b"not an image", "text/plain")},
        )
        assert resp.status_code == 400


# ─── AI Chat Tests ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestAIChat:

    async def test_chat_message(self, client: AsyncClient, student_token: str):
        resp = await client.post("/api/v1/chat",
            headers={"Authorization": f"Bearer {student_token}"},
            json={"message": "Hello, I need help with Python", "emotion_context": "neutral"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "reply" in data
        assert "session_id" in data
        assert "suggestions" in data

    async def test_chat_empty_message(self, client: AsyncClient, student_token: str):
        resp = await client.post("/api/v1/chat",
            headers={"Authorization": f"Bearer {student_token}"},
            json={"message": ""},
        )
        assert resp.status_code == 422

    async def test_chat_sessions(self, client: AsyncClient, student_token: str):
        resp = await client.get("/api/v1/chat/sessions", headers={"Authorization": f"Bearer {student_token}"})
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)


# ─── Learning Tests ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestLearning:

    async def test_get_recommendations(self, client: AsyncClient, student_token: str):
        resp = await client.get("/api/v1/learning/recommendations", headers={"Authorization": f"Bearer {student_token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        if data:
            assert "title" in data[0]
            assert "difficulty" in data[0]
            assert "reason" in data[0]

    async def test_generate_quiz(self, client: AsyncClient, student_token: str):
        resp = await client.post("/api/v1/learning/quiz/generate",
            headers={"Authorization": f"Bearer {student_token}"},
            json={"topic": "Python basics", "difficulty": "easy", "num_questions": 3},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "quiz_id" in data
        assert "questions" in data
        assert len(data["questions"]) == 3

    async def test_generate_notes(self, client: AsyncClient, student_token: str):
        resp = await client.post("/api/v1/learning/notes/generate",
            headers={"Authorization": f"Bearer {student_token}"},
            json={"content": "Python is a high-level programming language. It supports multiple paradigms including object-oriented, functional, and procedural programming.", "topic": "Python"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "summary" in data
        assert "key_points" in data


# ─── Analytics Tests ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestAnalytics:

    async def test_get_weekly_analytics(self, client: AsyncClient, student_token: str):
        resp = await client.get("/api/v1/analytics?period=weekly", headers={"Authorization": f"Bearer {student_token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert "period" in data
        assert "summary" in data
        assert "insights" in data

    async def test_invalid_period(self, client: AsyncClient, student_token: str):
        resp = await client.get("/api/v1/analytics?period=yearly", headers={"Authorization": f"Bearer {student_token}"})
        assert resp.status_code == 422


# ─── Notification Tests ───────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestNotifications:

    async def test_list_notifications(self, client: AsyncClient, student_token: str):
        resp = await client.get("/api/v1/notifications", headers={"Authorization": f"Bearer {student_token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "total" in data

    async def test_mark_notifications_read(self, client: AsyncClient, student_token: str):
        resp = await client.post("/api/v1/notifications/mark-read",
            headers={"Authorization": f"Bearer {student_token}"},
        )
        assert resp.status_code == 200


# ─── Settings Tests ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestSettings:

    async def test_get_settings(self, client: AsyncClient, student_token: str):
        resp = await client.get("/api/v1/settings", headers={"Authorization": f"Bearer {student_token}"})
        assert resp.status_code == 200

    async def test_update_settings(self, client: AsyncClient, student_token: str):
        resp = await client.put("/api/v1/settings",
            headers={"Authorization": f"Bearer {student_token}"},
            json={"dark_mode": True, "language": "hi", "stress_alert_threshold": 75.0},
        )
        assert resp.status_code == 200


# ─── Health Tests ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestHealth:

    async def test_health_check(self, client: AsyncClient):
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"

    async def test_root(self, client: AsyncClient):
        resp = await client.get("/")
        assert resp.status_code == 200
        assert "version" in resp.json()
