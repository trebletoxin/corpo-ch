import logging

from celery import shared_task, Celery

logger = logging.getLogger(__name__)
app = Celery('corpoch')
app.config_from_object('django.conf:settings', namespace='CELERY')

@shared_task
def run_task_function(function:str, task_args: list = [], task_kwargs: dict = {}):
	raise Exception(f"This function should be called asynchronously. Failed to queue a task {function}")
