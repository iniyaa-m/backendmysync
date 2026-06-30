from app.config.celery_config import celery_app
from app.utils.logger import logger


@celery_app.task(bind=True, max_retries=3)
def send_break_reminders(self):
    try:
        logger.info("Celery: Running break reminder task")
        return {"status": "ok", "reminders_sent": 0}
    except Exception as e:
        logger.error(f"Break reminder task failed: {e}")
        raise self.retry(exc=e, countdown=60)


@celery_app.task(bind=True)
def refresh_analytics_cache(self):
    try:
        logger.info("Celery: Refreshing analytics cache")
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Analytics cache refresh failed: {e}")
        raise self.retry(exc=e, countdown=120)


@celery_app.task(bind=True)
def generate_daily_reports(self):
    try:
        logger.info("Celery: Generating daily reports")
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Daily report generation failed: {e}")
        raise self.retry(exc=e, countdown=300)


@celery_app.task
def process_emotion_batch(user_id: str, emotion_records: list):
    try:
        if not emotion_records:
            return
        avg_stress = sum(r.get("stress_score", 0) for r in emotion_records) / len(emotion_records)
        avg_focus = sum(r.get("focus_score", 0) for r in emotion_records) / len(emotion_records)
        logger.info(f"Batch emotion for {user_id}: stress={avg_stress:.1f}, focus={avg_focus:.1f}")
        return {"user_id": user_id, "avg_stress": avg_stress, "avg_focus": avg_focus}
    except Exception as e:
        logger.error(f"Batch emotion processing failed: {e}")
