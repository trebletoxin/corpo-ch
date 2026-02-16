# celery.py
import os
from celery import Celery
from celery.app import trace
# Set default Django settings
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'DiscordOauth2.settings')

# Initialize Celery with Django loader
app = Celery('corpoch')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.conf.task_routes = {'corpoch.dbot.tasks.*': {'queue': 'corpoch.dbot'}}
app.conf.ONCE = {
    'backend': 'services.tasks.DjangoBackend',
    'settings': {}
}
app.conf.task_send_sent_events = True
app.conf.broker_connection_retry_on_startup = True

# setup priorities ( 0 Highest, 9 Lowest )
app.conf.broker_transport_options = {
    'priority_steps': list(range(10)),  # setup que to have 10 steps
    'queue_order_strategy': 'priority',  # setup que to use prio sorting
}
trace.LOG_SUCCESS = "Task %(name)s[%(id)s] succeeded in %(runtime)ss"
app.autodiscover_tasks()  # Discovers tasks in INSTALLED_APPS

@app.task(bind=True, ignore_result=True)
def debug_task(self):
    print(f'Request: {self.request!r}')