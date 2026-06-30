from pydantic import BaseModel, EmailStr, Field, validator
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class UserRoleEnum(str, Enum):
    student = "student"
    teacher = "teacher"
    admin = "admin"


class EmotionEnum(str, Enum):
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


class DifficultyEnum(str, Enum):
    easy = "easy"
    medium = "medium"
    hard = "hard"


class RegisterRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=255)
    email: EmailStr
    password: str = Field(..., min_length=6, max_length=100)
    role: UserRoleEnum = UserRoleEnum.student
    college: Optional[str] = None
    department: Optional[str] = None

    @validator("password")
    def password_strength(cls, v):
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user_id: str
    role: str
    name: str


class RefreshRequest(BaseModel):
    refresh_token: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(..., min_length=6)


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=6)


class UserBase(BaseModel):
    id: str
    name: str
    email: str
    role: str
    college: Optional[str]
    department: Optional[str]
    avatar: str
    language: str
    is_active: bool
    is_verified: bool
    created_at: datetime

    class Config:
        from_attributes = True


class UserUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=255)
    college: Optional[str] = None
    department: Optional[str] = None
    avatar: Optional[str] = None
    language: Optional[str] = None
    camera_consent: Optional[bool] = None
    mic_consent: Optional[bool] = None
    anonymous_mode: Optional[bool] = None
    fcm_token: Optional[str] = None


class EmotionResponse(BaseModel):
    emotion: str
    confidence: float
    stress_score: float
    focus_score: float
    recommendation: str
    session_id: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class EmotionHistoryItem(BaseModel):
    id: str
    emotion: str
    confidence: float
    stress_score: float
    focus_score: float
    source: str
    created_at: datetime

    class Config:
        from_attributes = True


class VoiceEmotionResponse(BaseModel):
    emotion: str
    tone: str
    confidence: float
    stress_score: float
    transcript: str
    sentiment: str
    recommendation: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class StudentDashboardResponse(BaseModel):
    user: Dict[str, Any]
    xp: int
    level: int
    streak: int
    focus_score: float
    stress_score: float
    total_study_minutes: int
    recent_emotions: List[Dict[str, Any]]
    weekly_analytics: List[Dict[str, Any]]
    recommended_topics: List[Dict[str, Any]]
    badges: List[Dict[str, Any]]
    notifications_count: int


class TeacherDashboardResponse(BaseModel):
    total_students: int
    online_students: int
    average_focus: float
    average_stress: float
    students: List[Dict[str, Any]]
    stress_alerts: List[Dict[str, Any]]
    emotion_distribution: Dict[str, int]
    leaderboard: List[Dict[str, Any]]


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    session_id: Optional[str] = None
    emotion_context: Optional[str] = None
    language: Optional[str] = "en"


class ChatResponse(BaseModel):
    reply: str
    session_id: str
    sentiment: str
    emotion_detected: Optional[str] = None
    suggestions: List[str] = []
    tokens_used: int = 0


class ChatHistoryItem(BaseModel):
    id: str
    role: str
    content: str
    emotion_context: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class RecommendationResponse(BaseModel):
    topic: str
    difficulty: str
    reason: str
    resources: List[Dict[str, Any]]
    estimated_minutes: int
    match_score: float


class QuizGenerateRequest(BaseModel):
    topic: str
    difficulty: DifficultyEnum = DifficultyEnum.medium
    num_questions: int = Field(default=5, ge=1, le=20)
    question_types: List[str] = ["mcq", "true_false"]
    language: str = "en"


class QuizQuestion(BaseModel):
    id: str
    question: str
    question_type: str
    options: Optional[List[str]] = None
    correct_answer: str
    explanation: Optional[str] = None
    difficulty: str


class QuizResponse(BaseModel):
    quiz_id: str
    topic: str
    difficulty: str
    questions: List[QuizQuestion]
    time_limit_minutes: int


class QuizSubmitRequest(BaseModel):
    quiz_id: str
    answers: Dict[str, str]
    time_taken_seconds: int
    emotion_during: Optional[str] = None


class QuizResultResponse(BaseModel):
    score: float
    max_score: float
    percentage: float
    xp_earned: int
    correct_answers: int
    wrong_answers: int
    feedback: List[Dict[str, Any]]
    badges_earned: List[str]


class NotesGenerateRequest(BaseModel):
    content: str = Field(..., min_length=50)
    topic: Optional[str] = None
    language: str = "en"


class NotesResponse(BaseModel):
    summary: str
    key_points: List[str]
    mind_map: Dict[str, Any]
    revision_notes: str
    flashcards: List[Dict[str, str]]


class AnalyticsPeriodEnum(str, Enum):
    daily = "daily"
    weekly = "weekly"
    monthly = "monthly"


class AnalyticsResponse(BaseModel):
    period: str
    data_points: List[Dict[str, Any]]
    summary: Dict[str, Any]
    insights: List[str]


class NotificationResponse(BaseModel):
    id: str
    title: str
    body: str
    notif_type: str
    is_read: bool
    created_at: datetime

    class Config:
        from_attributes = True


class ReportRequest(BaseModel):
    report_type: str = "weekly"
    format: str = "pdf"


class DocumentResponse(BaseModel):
    id: str
    filename: str
    page_count: Optional[int]
    embedding_stored: bool
    created_at: datetime

    class Config:
        from_attributes = True


class RAGQueryRequest(BaseModel):
    query: str = Field(..., min_length=5)
    document_ids: Optional[List[str]] = None
    language: str = "en"


class RAGQueryResponse(BaseModel):
    answer: str
    sources: List[Dict[str, Any]]
    confidence: float


class SettingsUpdateRequest(BaseModel):
    dark_mode: Optional[bool] = None
    language: Optional[str] = None
    offline_mode: Optional[bool] = None
    email_notifications: Optional[bool] = None
    push_notifications: Optional[bool] = None
    stress_alert_threshold: Optional[float] = Field(None, ge=0, le=100)
    break_reminder_interval: Optional[int] = Field(None, ge=10, le=240)


class PaginatedResponse(BaseModel):
    items: List[Any]
    total: int
    page: int
    per_page: int
    pages: int
