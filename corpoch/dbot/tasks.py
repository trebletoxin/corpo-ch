import logging

from corpoch.celery import app

logger = logging.getLogger(__name__)

@app.task
def set_group_role(user_id, guild_id, role_id):
	print(f"Sending task corpoch.dbot.set_group_role({user_id}, {guild_id}, {role_id})")
	res = set_group_role.apply_async(args=[user_id, guild_id, role_id])
