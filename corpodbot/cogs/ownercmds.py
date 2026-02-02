import discord
import os
from discord.ext import commands
from discord.ui import *
from discord.enums import ComponentType, InputTextStyle
from dotenv import load_dotenv

from corpoch.models import Tournament, TournamentBracket, TournamentPlayer, TournamentQualifier


## These Were obsoleted by django admin - keeping for discord end specific commands
load_dotenv()

class OwnerCmds(commands.Cog):
	def __init__(self, bot):
		self.bot = bot

	#Limit guilds to .env home guild id
	owner = discord.SlashCommandGroup('owner','Bot Owner Commands', guild_ids=[os.getenv('home_guild_id')])

def setup(bot):
	bot.add_cog(OwnerCmds(bot))