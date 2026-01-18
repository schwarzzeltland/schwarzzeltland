from celery import shared_task
import logging

logger = logging.getLogger(__name__)

@shared_task
def heartbeat_task():
    logger.info("The Celery Beat is working!")
