from app.config.settings import settings
from app.utils.logger import logger


async def send_verification_email(email: str, name: str, token: str):
    verify_url = f"{settings.FRONTEND_URL}/verify-email/{token}"
    subject = "Verify your MindSync AI account"
    body = f"""
    <h2>Welcome to MindSync AI Classroom, {name}!</h2>
    <p>Please verify your email by clicking the link below:</p>
    <a href="{verify_url}" style="background:#7c3aed;color:white;padding:12px 24px;border-radius:8px;text-decoration:none;">
        Verify Email
    </a>
    <p>Link expires in 24 hours.</p>
    """
    await _send_email(email, subject, body)


async def send_reset_email(email: str, name: str, token: str):
    reset_url = f"{settings.FRONTEND_URL}/reset-password/{token}"
    subject = "Reset your MindSync AI password"
    body = f"""
    <h2>Password Reset Request</h2>
    <p>Hi {name}, click below to reset your password:</p>
    <a href="{reset_url}" style="background:#ef4444;color:white;padding:12px 24px;border-radius:8px;text-decoration:none;">
        Reset Password
    </a>
    <p>This link expires in 1 hour.</p>
    """
    await _send_email(email, subject, body)


async def _send_email(to: str, subject: str, html_body: str):
    if not settings.MAIL_USERNAME:
        logger.warning("Email not configured. Skipping email send.")
        return
    try:
        from fastapi_mail import FastMail, MessageSchema, ConnectionConfig, MessageType
        config = ConnectionConfig(
            MAIL_USERNAME=settings.MAIL_USERNAME,
            MAIL_PASSWORD=settings.MAIL_PASSWORD,
            MAIL_FROM=settings.MAIL_FROM,
            MAIL_PORT=settings.MAIL_PORT,
            MAIL_SERVER=settings.MAIL_SERVER,
            MAIL_FROM_NAME=settings.MAIL_FROM_NAME,
            MAIL_STARTTLS=True,
            MAIL_SSL_TLS=False,
            USE_CREDENTIALS=True,
        )
        message = MessageSchema(
            subject=subject,
            recipients=[to],
            body=html_body,
            subtype=MessageType.html,
        )
        fm = FastMail(config)
        await fm.send_message(message)
        logger.info(f"Email sent to {to}")
    except Exception as e:
        logger.error(f"Failed to send email to {to}: {e}")
