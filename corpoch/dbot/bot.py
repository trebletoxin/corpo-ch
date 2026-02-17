import sys, os, discord, asyncio, time, json, logging, aiohttp, logging
from discord.ext import commands, tasks

#Django
import pendulum
import django
import django.db
from socket import timeout
from django.apps import apps
from corpoch.dbot import settings
from django.utils import timezone
from kombu import Connection, Consumer, Queue
from kombu.utils.limits import TokenBucket
from redis import asyncio as aioredis
from dotenv import load_dotenv
from corpoch.dbot import bot_tasks

logger = logging.getLogger(__name__)

class CorpoDbot(commands.Bot):
	def __init__(self):
		django.setup()
		intents = discord.Intents.default()
		intents.members = True
		self.client = super().__init__(intents=intents, chunk_guilds_at_startup=False)
		self.session = aiohttp.ClientSession(loop=self.loop)
		self.redis = self.loop.run_until_complete(aioredis.from_url(os.getenv("CELERY_BROKER_URL"), encoding="utf-8", decode_responses=True))
		print(f"redis pool started {os.getenv("CELERY_BROKER_URL")}")
		self.message_connection = Connection(os.getenv("CELERY_BROKER_URL"))
		queuename = "corpoch.dbot"
		queue_keys = [f"{queuename}",
              f"{queuename}\x06\x161",
              f"{queuename}\x06\x162",
              f"{queuename}\x06\x163",
              f"{queuename}\x06\x164",
              f"{queuename}\x06\x165",
              f"{queuename}\x06\x166",
              f"{queuename}\x06\x167",
              f"{queuename}\x06\x168",
              f"{queuename}\x06\x169"]
		queues = []
		for que in queue_keys:
			queues.append(Queue(que))
		self.message_consumer = Consumer(self.message_connection, queues, callbacks=[self.on_queue_message])#, channel=self.chan)
		self.tasks = []
		# cogs - this needs to move to a settings section
		cogList = [
			'chcmds',
			#'tourneycmds',
			'qualifiercmds',
			'ownercmds'
		]

		for cog in cogList:
			self.load_extension(f'corpoch.dbot.cogs.{cog}')
			print(f'Cog loaded: {cog}')

		self.owners = []
		self.proofCalls = None

	def run(self):
		self.startUpLogging()
		print(f"--- Starting up at {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())} ---")
		print('Logging into discord')
		super().run(os.getenv("BOT_TOKEN"), reconnect=True)
		print(f"--- Shutting down at {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())} ---")

	def on_queue_message(self, body, message):
		task = message.headers["task"].replace("corpoch.dbot.tasks.", '')
		_task = getattr(bot_tasks, task, False)
		_args = body[0]
		_kwargs = body[1]
		print(f"Got task.{task}({_args}, {_kwargs})")
		message.ack()
		self.tasks.append((_task, _args, _kwargs))

	async def on_interaction(self, interaction):
		try:
			django.db.close_old_connections()
			await self.process_application_commands(interaction)
		except Exception as e:
			logger.error(f"Interaction Failed {e}", stack_info=True)
		django.db.close_old_connections()

	def startUpLogging(self):
		sys.stdout.reconfigure(line_buffering = True)
		sys.stderr.reconfigure(line_buffering = True)

	async def retrieveOwners(self):
		print("Retrieving bot owners...")
		app = await self.application_info()
		if app.team:
			for mem in app.team.members:
				owner = await self.fetch_user(mem.id)
				if not owner:
					print(f"  Can't get user object for team member {str(mem.name)}#{str(mem.discriminator)} id {mem.id}")
				else:
					self.owners.append(owner)
					print(f"  Loaded owner: {str(owner.name)} id {owner.id}")
		else:
			self.owners = [app.owner]
			print(f"  Loaded owner: {str(app.owner.name)} id {app.owner.id}")

	@tasks.loop(seconds=1.0)
	async def poll_queue(self):
		message_avail = True
		while message_avail:
			try:
				with self.message_consumer:
					self.message_connection.drain_events(timeout=0.01)
			except timeout:
				message_avail = False
		if not bot_tasks.run_tasks.is_running():
			bot_tasks.run_tasks.start(self)


	async def close(self):
		self.poll_queue.stop()
		bot_tasks.run_tasks.stop()
		await super().close()

	async def on_ready(self, once=True):
		print(f"Logged in as {self.user.name}#{self.user.discriminator} id {self.user.id}")

		await self.retrieveOwners()
		print("Loading on-going matches")
		from corpoch.dbot.cogs.tourneycmds import DiscordMatch
		from corpoch.models import TournamentMatchOngoing
		async for match in TournamentMatchOngoing.objects.exclude(channel=None):
			print(f"Got ongoing match {match.id}")
			view = DiscordMatch(self._bot, uuid=match.id)
			await view.init()

		if not bot_tasks.run_tasks.is_running():
			print("Starting tasks")
			self.message_consumer.consume(no_ack=False)
			self.poll_queue.start()

		print('------Done with Startup------')

if __name__ == "__main__":
	bot = CorpoDbot()
	bot.run()
