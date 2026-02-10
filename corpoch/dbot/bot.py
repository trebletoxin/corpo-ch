import sys, os, discord, asyncio, time, json, logging, aiohttp, logging
from discord.ext import commands, tasks

#Django
import pendulum
import django
import django.db
from django.apps import apps
import settings
from django.utils import timezone
from redis import asyncio as aioredis
from dotenv import load_dotenv
import tasks

dirname = os.path.dirname(sys.argv[0]) or '.'
sys.path.append(f"{dirname}/modules") # This should be able to die soon

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
		
		# cogs
		cogList = [
			'chcmds',
			'tourneycmds',
			'qualifiercmds',
			'ownercmds'
		]

		for cog in cogList:
			self.load_extension(f'cogs.{cog}')
			print(f'Cog loaded: {cog}')

		self.owners = []
		self.proofCalls = None

	def run(self):
		self.startUpLogging()
		print(f"--- Starting up at {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())} ---")
		print('Logging into discord')
		super().run(os.getenv("BOT_TOKEN"), reconnect=True)

		print(f"--- Shutting down at {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())} ---")

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

	async def on_ready(self, once=True):
		print(f"Logged in as {self.user.name}#{self.user.discriminator} id {self.user.id}")

		await self.retrieveOwners()
		print("Loading on-going matches")
		from cogs.tourneycmds import DiscordMatch
		from corpoch.models import TournamentMatchOngoing
		async for match in TournamentMatchOngoing.objects.exclude(channel=None):
			print(f"Got ongoing match {match.id}")
			view = DiscordMatch(self._bot, uuid=match.id)
			await view.init()

		print('------Done with Startup------')

if __name__ == "__main__":
	bot = CorpoDbot()
	bot.run()
