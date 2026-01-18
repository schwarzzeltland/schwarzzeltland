import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'schwarzzeltland.settings')

app = Celery('schwarzzeltland')
# Namespace='CELERY' means all celery-related configs
# must have a "CELERY_" prefix in settings.py.
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()
