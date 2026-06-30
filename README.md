# 🧠 MindSync AI Classroom — Backend API

Production-ready FastAPI backend for the MindSync AI emotion-aware learning platform.

---

## 🚀 Quick Start

### Prerequisites
- Python 3.11+
- PostgreSQL 15+
- Redis 7+
- Docker & Docker Compose (optional)

---

### 1. Clone & Setup

```bash
cd backend
python -m venv venv
# Windows:
venv\Scripts\activate
# Mac/Linux:
source venv/bin/activate

pip install -r requirements.txt
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env with your API keys and database credentials
```

### 3. Run with Docker (Recommended)

```bash
docker-compose up -d
```

This starts: FastAPI + PostgreSQL + Redis + Celery + Celery Beat + Flower + MinIO + Nginx

### 4. Run Locally (Dev)

```bash
# Start PostgreSQL and Redis first
# Then run migrations:
alembic upgrade head

# Start server:
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

---

## 📡 API Endpoints

### Authentication (`/api/v1/auth`)
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/register` | Register student/teacher/admin |
| POST | `/login` | Login → returns JWT tokens |
| POST | `/refresh` | Refresh access token |
| POST | `/forgot-password` | Send password reset email |
| POST | `/reset-password` | Reset password with token |
| GET | `/verify-email/{token}` | Verify email address |
| GET | `/me` | Get current user info |
| POST | `/logout` | Revoke refresh tokens |
| POST | `/change-password` | Change password |

### Student (`/api/v1/student`)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/profile` | Get student profile + stats |
| PUT | `/profile` | Update profile |
| GET | `/dashboard` | Full dashboard data |
| GET | `/progress` | Learning progress & analytics |
| GET | `/streak` | Daily streak info |
| GET | `/badges` | All badges with earned status |
| GET | `/leaderboard` | Top 10 leaderboard |

### Teacher (`/api/v1/teacher`)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/dashboard` | Teacher dashboard overview |
| GET | `/class` | Paginated student list |
| GET | `/emotions` | Class emotion data (heatmap) |
| GET | `/alerts` | High-stress student alerts |
| GET | `/reports` | Aggregated class reports |

### Emotion Detection (`/api/v1/emotion`)
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/image` | Upload image → detect emotion |
| POST | `/audio` | Upload audio → voice emotion |
| GET | `/history` | Emotion detection history |

### AI Chat (`/api/v1/chat`)
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `` | Send message to AI tutor |
| GET | `/sessions` | List chat sessions |
| GET | `/history/{session_id}` | Get session messages |

### Adaptive Learning (`/api/v1/learning`)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/recommendations` | Personalized topic recommendations |
| POST | `/quiz/generate` | Generate AI quiz |
| POST | `/quiz/submit` | Submit quiz answers |
| POST | `/notes/generate` | Generate study notes from content |

### Analytics (`/api/v1/analytics`)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `?period=weekly` | Detailed analytics (daily/weekly/monthly) |

### Notifications (`/api/v1/notifications`)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `` | List notifications (paginated) |
| POST | `/mark-read` | Mark notifications as read |

### Reports (`/api/v1/reports`)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/download?format=pdf` | Download PDF report |
| GET | `/download?format=csv` | Download CSV report |

### Documents/RAG (`/api/v1/documents`)
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/upload` | Upload PDF, extract + embed |
| POST | `/query` | RAG-based Q&A over documents |
| GET | `` | List uploaded documents |

### Settings (`/api/v1/settings`)
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `` | Get user settings |
| PUT | `` | Update settings |

---

## 🔌 WebSocket Endpoints

| URL | Description |
|-----|-------------|
| `ws://localhost:8000/ws/emotion?token=<jwt>` | Real-time facial emotion streaming |
| `ws://localhost:8000/ws/audio?token=<jwt>` | Real-time voice emotion streaming |
| `ws://localhost:8000/ws/chat?token=<jwt>` | Chat with typing indicators |
| `ws://localhost:8000/ws/notifications?token=<jwt>` | Live push notifications |
| `ws://localhost:8000/ws/teacher/dashboard?token=<jwt>` | Teacher live dashboard |

---

## 🗃️ Database Migrations

```bash
# Create migration
alembic revision --autogenerate -m "description"

# Apply migrations
alembic upgrade head

# Rollback
alembic downgrade -1
```

---

## 🧪 Running Tests

```bash
pytest tests/ -v --cov=app
```

---

## 🐳 Docker Services

| Service | Port | Description |
|---------|------|-------------|
| FastAPI | 8000 | Main API server |
| Nginx | 80 | Reverse proxy |
| PostgreSQL | 5432 | Main database |
| Redis | 6379 | Cache + message broker |
| Celery Worker | — | Background tasks |
| Celery Beat | — | Task scheduler |
| Flower | 5555 | Celery monitor UI |
| MinIO | 9000/9001 | Object storage |

---

## 🔑 Environment Variables

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | PostgreSQL async connection string |
| `REDIS_URL` | Redis connection URL |
| `SECRET_KEY` | JWT signing key (min 32 chars) |
| `GEMINI_API_KEY` | Google Gemini API key |
| `OPENAI_API_KEY` | OpenAI API key (fallback) |
| `FIREBASE_CREDENTIALS_PATH` | Path to Firebase service account JSON |
| `MINIO_*` | MinIO/S3 object storage config |
| `MAIL_*` | SMTP email configuration |

---

## 🏗️ Architecture

```
Client (React) ──── HTTPS/WSS ──── Nginx ──── FastAPI
                                      │
                     ┌────────────────┼──────────────────┐
                     │                │                  │
                PostgreSQL         Redis          Celery Workers
                (Main DB)      (Cache/Broker)   (Background Tasks)
                                     │
                                  MinIO/S3
                               (File Storage)
```

---

## 📦 AI Stack

- **Emotion Detection**: DeepFace + FER + OpenCV
- **Voice Analysis**: OpenAI Whisper + Transformers (Cardiff NLP)  
- **AI Tutor**: LangChain + Gemini 1.5 Flash / GPT-4o-mini
- **Recommendations**: Scikit-learn scoring model
- **RAG**: SentenceTransformers + FAISS
- **PDF Processing**: PyMuPDF (fitz)
