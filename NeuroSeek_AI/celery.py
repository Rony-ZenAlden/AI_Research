"""Celery application — auto-discovers tasks from installed apps."""
import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "NeuroSeek_AI.settings.dev")

app = Celery("neuroseek")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()


@app.task(bind=True)
def debug_task(self):
    print(f"Request: {self.request!r}")
