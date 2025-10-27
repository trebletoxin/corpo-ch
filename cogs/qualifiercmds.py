import platform, json, base64, io
from datetime import datetime

import discord
from discord.ext import commands
from discord.ui import *
from discord.enums import ComponentType, InputTextStyle

import chutils

class DiscordQualifierView(discord.ui.View):
	def __init__(self, ctx, sql, chUtils, submission):
		super().__init__(timeout = None)
		self.ctx = ctx
		self.sql = sql
		self.chUtils = chUtils
		self.submission = submission
		self.qualifier = None
		self.tourney = None
		self.acknowledged = False

		cancel = discord.ui.Button(label="Cancel", style=discord.ButtonStyle.red, custom_id="cancelBtn")
		cancel.callback = self.cancelBtn
		self.add_item(cancel)

		submit = discord.ui.Button(label="Submit", style=discord.ButtonStyle.green, custom_id="submitBtn")
		submit.callback = self.submitBtn
		self.add_item(submit)

	async def init(self, ctx):
		await ctx.defer(ephemeral=True)
		self.tourney = await self.sql.getActiveTournies(ctx.guild.id)
		qualifiers = await self.sql.getActiveQualifiers(ctx.guild.id)
		self.stegData = await self.chUtils.getStegInfo(self.submission)
		if len(qualifiers) > 1:
			await self.ctx.respond("I'm not configured to support multiple qualifiers in a tournament - Notifiy my devs for help", ephemeral=True)
			return
		elif len(qualifiers) == 0:
			await self.ctx.respond("There are no active qualifiers running in this server at this time.", ephemeral=True)
			return

		self.qualifier = qualifiers[0]
		if self.stegData == None:
			await self.ctx.respond("Submitted screenshot is not a valid in-game Clone Hero screenshot", ephemeral=True)
			return
		elif self.stegData['checksum'] != self.qualifier['checksum']:
			await self.ctx.respond("Submitted screenshot is not for this qualifier", ephemeral=True)
			return

		prevRun = await self.sql.getPlayerQualifier(ctx.user.id, self.tourney['id'])
		if prevRun is None:
			await self.ctx.respond(embed=self.buildRulesEmbed(), view=self, ephemeral=True)
		else:
			self.stegData = prevRun['stegjson']
			await self.ctx.respond(f"You already submitted a qualifier for {self.tourney['config']['name']}!", embed=self.buildQualifierStatsEmbed(), ephemeral=True)

	async def submitBtn(self, interaction: discord.Interaction):
		await interaction.response.defer()
		if not self.acknowledged:
				await self.ctx.edit(embed=self.buildQualifierStatsEmbed(), view=self)
				self.acknowledged = True
		else:
			#Needs to be tweaked to support multiplayer qualifier runs
			print(f"Submitting qualifier submission for {self.ctx.user.global_name} - {self.stegData["players"][0]["profile_name"]} - {self.stegData['score_timestamp']}")
			#sanityCheck() $to verify once DB is populated to ensure chart name/checksum(?) matches
			self.stegData['imagename'] = self.submission.filename
			print
			if await self.sql.saveQualifier(self.ctx.user.id, self.tourney['id'], self.stegData):
				await self.ctx.interaction.delete_original_response()
				await interaction.followup.send("Submitted!", ephemeral=True)
			else:
				await self.ctx.interaction.delete_original_response()
				await interaction.followup.send("Error in submission, please try to run this command again or report this to my devs", ephemeral=True)

	async def cancelBtn(self, interaction: discord.Interaction):
		await interaction.response.edit_message(content="Closing", embed=None, view=None, delete_after=1)
		self.stop()

	#def buildQualifierInfoEmbed(self):

	def buildRulesEmbed(self) -> discord.Embed:
		embed = discord.Embed(colour=0x3FFF33)
		embed.title = "Qualifier Submission Rules"
		embed.add_field(name=f"{self.tourney['config']['name']} Tourney Rules", value=self.tourney['config']['rules'], inline=False)
		embed.add_field(name=f"Qualifier rules", value=self.qualifier['rules'], inline=False)
		embed.add_field(name=f"Directions", value="If you agree to these rules, please hit submit to review your submitted qualifier", inline=False)

		return embed

	def buildQualifierStatsEmbed(self) -> discord.Embed:
		embed = discord.Embed(colour=0x3FFF33)
		embed.title = "Qualifier Submission Results"

		statsStr = ""
		statsStr = statsStr + f"Qualifier Name: {self.stegData["song_name"]}\n"
		player1 = self.stegData["players"][0]
		statsStr = statsStr + f"Player Name: {player1["profile_name"]}\n"
		statsStr = statsStr + f"Score: {player1["score"]}\n"
		statsStr = statsStr + f"Notes Hit: {player1["notes_hit"]}/{player1["total_notes"]} - {(player1["notes_hit"]/player1["total_notes"]) * 100:.2f}%\n"
		statsStr = statsStr + f"Overstrums: {player1["overstrums"]}\n" # Needs further sanity/error checking
		statsStr = statsStr + f"Ghosts: {player1["frets_ghosted"]}\n"
		statsStr = statsStr + f"SP Phrases: {player1["sp_phrases_earned"]}/{player1["sp_phrases_total"]}\n"
		statsStr = statsStr + f"Completion Time: <t:{int(round(datetime.strptime(self.stegData["score_timestamp"], '%Y-%m-%dT%H:%M:%S.%fZ').timestamp()))}:f>"
		embed.add_field(name="Submission Stats", value=statsStr, inline=False)

		return embed

class QualifierCmds(commands.Cog):
	def __init__(self, bot):
		self.bot = bot
		self.chUtils = chutils.CHUtils()

	qualifier = discord.SlashCommandGroup('qualifier','Clone Hero Tournament Qualifer Commands')

	@qualifier.command(name='submit', description='Submit a qualifier score for a tournament this server is running', integration_types={discord.IntegrationType.guild_install})
	@discord.option("submission", discord.Attachment, description="Attach in-game screenshot of qualifer run", required=True)
	async def qualifierSubmitCmd(self, ctx, submission: discord.Attachment):
		view = DiscordQualifierView(ctx, self.bot.tourneyDB, self.chUtils, submission)
		ret = await view.init(ctx)	
		await view.wait()
		view.stop()
	
	@qualifier.command(name='submissions', description='Retrieve a CSV of all submissions for the active tournament', integration_types={discord.IntegrationType.guild_install})
	async def qualifierCSVCmd(self, ctx):
		# pull data
		tourney = self.bot.tourneyDB.getActiveTournies(ctx.guild.id)
		if type(tourney) != dict: # no active tourney found
			await ctx.respond("No active tournament was found.",ephemeral=True)
			return
		
		submissions = self.bot.tourneyDB.getTourneyQualifierSubmissions(tourney.id)

		# format data
		csv = "Player,Score,Notes Missed,Overstrums,Ghosts\n"
		for i in submissions:
			csv += f"{i.profile_name},{i.score},{i.notes_hit},{i.total_notes - i.notes_hit},{i.overstrums},{i.frets_ghosted}\n"

		# post data
		csvF = io.StringIO()
		csvF.write(csv)
		await ctx.respond(file=csvF,ephemeral=True)
		csvF.close()

def setup(bot):
	bot.add_cog(QualifierCmds(bot))

