import importlib
import io
import logging
import warnings
from datetime import timedelta

from discord import Embed, File
from discord.ext import tasks
from discord.ext.commands import Bot

import django
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

@tasks.loop()
async def run_tasks(bot: Bot):
	django.db.close_old_connections()
	if len(bot.tasks) > 0:
		task, args, kwargs = bot.tasks.pop(0)
		requeue_task = False
		if hasattr(bot, 'rate_limits'):
			if not bot.rate_limits.check_rate_limit(task.__name__):
				requeue_task = True
		if requeue_task:
			timeout = 1
			eta = timezone.now() + timedelta(seconds=timeout)
			bot.pending_tasks.append((eta, (task, args, kwargs)))
		else:
			try:
				await task(bot, *args, **kwargs)
				bot.dispatch("dbot_task_completed", task.__name__)
			except Exception as e:
				bot.dispatch("dbot_task_failed", task.__name__, args, kwargs, e)
				logger.error(
					f"Failed to run task {task} {args} {kwargs} {e}", exc_info=True)
	else:
		run_tasks.stop()
	django.db.close_old_connections()

async def set_group_role(bot, user_id, guild_id, role_id):
    logger.debug(f"Setting Group role {role_id} discord ID {user_id}")

    guild = bot.get_guild(guild_id)
    user = await guild.fetch_member(user_id)
    role = await guild.fetch_role(role_id)
    await user.add_roles(role)