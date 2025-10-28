import platform, json, base64, io, os
from datetime import datetime

import discord
from discord.ext import commands
from discord.ui import *
from discord.enums import ComponentType, InputTextStyle

import chutils
import gsheets

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

	#I don't really like using two bool's here for differing output - dirty but works
	async def init(self, viewInit=True, showRules=False) -> bool:
		await self.ctx.defer(ephemeral=True)
		self.tourney = await self.sql.getActiveTournies(self.ctx.guild.id)
		qualifiers = await self.sql.getActiveQualifiers(self.ctx.guild.id)

		if len(qualifiers) > 1:
			await self.ctx.respond("I'm not configured to support multiple qualifiers in a tournament - Notifiy my devs for help", ephemeral=True)		
			return False
		elif len(qualifiers) == 0:
			await self.ctx.respond("There are no active qualifiers running in this server at this time.", ephemeral=True)
			return False

		self.qualifier = qualifiers[0]
		if showRules:
			await self.ctx.respond(embed=self.buildRulesEmbed(fullRules=True), ephemeral=True)
			return

		if viewInit:
			self.stegData = await self.chUtils.getStegInfo(self.submission)

		if viewInit:
			if self.stegData == None:
				await self.ctx.respond("Submitted screenshot is not a valid in-game Clone Hero screenshot", ephemeral=True)
				return
			elif self.stegData['checksum'] != self.qualifier['checksum']:
				await self.ctx.respond("Submitted screenshot is not for this qualifier", ephemeral=True)
				return

		prevRun = await self.sql.getPlayerQualifier(self.ctx.user.id, self.tourney['id'])
		if prevRun is None:
			if viewInit:
				await self.ctx.respond(embed=self.buildRulesEmbed(), view=self, ephemeral=True)
			else:
				await self.ctx.respond(f"You've not submitted a qualifier for {self.tourney['config']['name']}! Use `/qualifier submit` to submit one!")
		else:
			self.stegData = prevRun['stegjson']
			if viewInit:
				await self.ctx.respond(f"You already submitted a qualifier for {self.tourney['config']['name']}!", embed=self.buildQualifierStatsEmbed(), ephemeral=True)
			else:
				await self.ctx.respond(f"Here's the qualifier info you submitted for {self.tourney['config']['name']}!", embed=self.buildQualifierStatsEmbed(), ephemeral=True)

	async def submitBtn(self, interaction: discord.Interaction):
		await interaction.response.defer()
		if not self.acknowledged:
				self.stegData['submission_timestamp'] = datetime.now().strftime('%Y-%m-%dT%H:%M:%S.%fZ')
				await self.ctx.edit(embed=self.buildQualifierStatsEmbed(), view=self)
				self.acknowledged = True
		else:
			#Needs to be tweaked to support multiplayer qualifier runs
			print(f"Submitting qualifier submission for {self.ctx.user.global_name} - {self.stegData["players"][0]["profile_name"]} - {self.stegData['score_timestamp']}")
			#Save Screenshot
			outDir = f"steg/tournies/{self.tourney['config']['name']}".replace(" ", "")
			if not os.path.isdir(outDir):
				os.makedirs(outDir)

			await self.submission.save(f"{outDir}/{self.submission.filename}", seek_begin=True)
			
			#Set image URL - THIS NEEDS CLEANUP TO AVOID HARD CODED LINK - also make safe url encoding
			self.stegData['image_url'] = f"https://qualifiers.corpo-ch.org/{self.tourney['config']['name'].replace(" ", "")}/{self.stegData['image_name']}"

			if await self.sql.saveQualifier(self.ctx.user.id, self.tourney['id'], self.stegData):
				#Submit to Sheet
				gs = gsheets.GSheets(self.ctx.bot, self.sql, self.tourney['id'])
				await gs.init()
				if not await gs.submitQualifier(self.ctx.user, self.stegData):
					await interaction.followup.send("Something went wrong in the gsheets setup/submission", ephemeral=True)
					return

				await self.ctx.interaction.delete_original_response()
				await interaction.followup.send("Submitted!", ephemeral=True)
			else:
				await self.ctx.interaction.delete_original_response()
				await interaction.followup.send("Error in submission, please try to run this command again or report this to my devs", ephemeral=True)

	async def cancelBtn(self, interaction: discord.Interaction):
		await interaction.response.edit_message(content="Closing", embed=None, view=None, delete_after=1)
		self.stop()

	def buildRulesEmbed(self, fullRules=False) -> discord.Embed:
		embed = discord.Embed(colour=0x3FFF33)
		embed.title = "Qualifier Submission Rules"
		embed.add_field(name=f"{self.tourney['config']['name']} Tourney Rules", value=self.tourney['config']['rules'], inline=False)
		embed.add_field(name=f"Qualifier Rules", value=self.qualifier['rules'], inline=False)

		if fullRules:
			if "form_link" in self.qualifier:
				embed.add_field(name="Qualifier Form Link", value=f"[Link Here]({self.qualifier['form_link']})", inline=False)

			embed.add_field(name=f"Qualifier Chart Link", value=f"[Download Link Here]({self.qualifier["chart_link"]})", inline=False)
		else:
			embed.add_field(name=f"Directions", value="If you agree to these rules, please hit submit to review your submitted qualifier before submission.\n\nIf you do not get a follow up message from me confirming, please notify Jetsurf or Masonjar", inline=False)

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
		statsStr = statsStr + f"Submission Time: <t:{int(round(datetime.strptime(self.stegData["submission_timestamp"], '%Y-%m-%dT%H:%M:%S.%fZ').timestamp()))}:f>\n"
		statsStr = statsStr + f"Run Time: <t:{int(round(datetime.strptime(self.stegData["score_timestamp"], '%Y-%m-%dT%H:%M:%S.%fZ').timestamp()))}:f>"

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
		await view.init()	
		await view.wait()
		view.stop()
	
	@qualifier.command(name='status', description='Shows the status of your qualifier for an active tournament', integration_types={discord.IntegrationType.guild_install})
	async def qualifierSubmitCmd(self, ctx):
		view = DiscordQualifierView(ctx, self.bot.tourneyDB, self.chUtils, None)
		await view.init(viewInit=False)

	@qualifier.command(name='info', description='Shows the info for an active tournament qualifier', integration_types={discord.IntegrationType.guild_install})
	async def qualifierSubmitCmd(self, ctx):
		view = DiscordQualifierView(ctx, self.bot.tourneyDB, self.chUtils, None)
		await view.init(viewInit=False, showRules=True)

	#Keep as a fail-safe - if gsheets submissions breaks, this can be used for data pull - just doesn't have a restriction for staff-role only execution
	#@qualifier.command(name='submissions', description='Retrieve a CSV of all submissions for the active tournament', integration_types={discord.IntegrationType.guild_install})
	#async def qualifierCSVCmd(self, ctx):
		# pull data
		#tourney = self.bot.tourneyDB.getActiveTournies(ctx.guild.id)
		#if type(tourney) != dict: # no active tourney found
			#await ctx.respond("No active tournament was found.",ephemeral=True)
			#return
		
		#submissions = self.bot.tourneyDB.getTourneyQualifierSubmissions(tourney.id)

		# format data
		#csv = "Player,Score,Notes Missed,Overstrums,Ghosts\n"
		#for i in submissions:
			#csv += f"{i["profile_name"]},{i["score"]},{i["notes_hit"]},{i["total_notes"] - i["notes_hit"]},{i["overstrums"]},{i["frets_ghosted"]}\n"

		# post data
		#csvF = io.StringIO()
		#csvF.write(csv)
		#await ctx.respond(file=discord.File(csvF,filename="qualifier_submissions.csv"),ephemeral=True)
		#csvF.close()

def setup(bot):
	bot.add_cog(QualifierCmds(bot))
