import json
import discord
from discord.ext import commands
from discord.ui import *
from discord.enums import ComponentType, InputTextStyle

class TourneyConfigModal(Modal):
	def __init__(self, sql, *args, **kwargs):
		self.sql = sql
		super().__init__(*args, **kwargs)
		self.add_item(InputText(label="Tourney Config", style=discord.InputTextStyle.long, required=False))
		self.add_item(InputText(label="Qualifier Config", style=discord.InputTextStyle.long, required=False))
		self.add_item(InputText(label="Bracket Config", style=discord.InputTextStyle.long, required=False))

	async def callback(self, interaction: discord.Interaction):
		tourney = await self.sql.getActiveTournies(interaction.guild.id)
		if tourney == None:
			await interaction.respond("No active tourney")

		for config in self.children:
			if config.label == "Tourney Config" and config.value != "":
				await self.sql.setTourneyConfig(tourney['id'], json.loads(config.value))

			if config.label == "Qualifier Config" and config.value != "":
				await self.sql.setTourneyQualifiers(tourney['id'], json.loads(config.value))

			if config.label == "Bracket Config" and config.value != "":
				await self.sql.setTourneyBrackets(tourney['id'], json.loads(config.value))		

		await interaction.respond("Successfully set whatever you sent me :shrug:", ephemeral=True, delete_after=5)
		self.stop()

class TourneyMatchInProcessModal(Modal):
	def __init__(self, sql, *args, **kwargs):
		self.sql = sql
		super().__init__(*args, **kwargs)
		self.add_item(InputText(label="TourneyID", style=discord.InputTextStyle.short, max_length=4, required=True))
		self.add_item(InputText(label="Finished", style=discord.InputTextStyle.short, max_length=1, required=True, value=1))
		self.add_item(InputText(label="Match/Reftool JSON", style=discord.InputTextStyle.long, required=True))
		self.callback = self.callback

	async def callback(self, interaction: discord.Interaction):
		tourney = await self.sql.getActiveTournies(interaction.guild.id)
		if tourney == None:
			await interaction.followup.send("No active tourney")

		#Get UUID from Json rather than separate modal field
		data = json.loads(self.children[2].value)
		await self.sql.replaceRefToolMatch(data['uuid'], int(self.children[0].value), bool(self.children[1].value), json.loads(self.children[2].value))

		await interaction.respond("Successfully set whatever you sent me :shrug:", ephemeral=True, delete_after=5)
		self.stop()

class OwnerCmds(commands.Cog):
	def __init__(self, bot):
		self.bot = bot

	owner = discord.SlashCommandGroup('owner','Bot Owner Commands')

	@owner.command(name='tourneyconfig', description='Submit a tourney config/quali/bracket config for this server', integration_types={discord.IntegrationType.guild_install})
	@commands.is_owner()
	async def setTourney(self, ctx):
		modal = TourneyConfigModal(self.bot.tourneyDB, title="Mindful of the 4000 limit!")
		await ctx.send_modal(modal=modal)
		#await modal.wait()

	@owner.command(name='reftoolmatchadd', description='Submit a refmatch entry for testing', integration_types={discord.IntegrationType.guild_install})
	@commands.is_owner()
	async def setTourney(self, ctx):
		modal = TourneyMatchInProcessModal(self.bot.tourneyDB, title="Reftool match add")
		await ctx.send_modal(modal=modal)
		#await modal.wait()

	@commands.Cog.listener()
	async def on_application_command_error(self, ctx: discord.ApplicationContext, error: discord.DiscordException):
		if isinstance(error, commands.NotOwner):
			await ctx.respond("You don't own me! (You cannot run this command)", ephemeral=True)
		else:
			raise error

def setup(bot):
	bot.add_cog(OwnerCmds(bot))