import os
from dotenv import load_dotenv

load_dotenv('../')
from pathlib import Path

# Celery Settings
CELERY_BROKER_URL = 'redis://localhost:6379/1'
CELERY_RESULT_BACKEND = "django-db"
CELERY_TIMEZONE = "UTC"