import discord, asyncio

from apscheduler.schedulers.asyncio import AsyncIOScheduler
import apscheduler.triggers.cron

import chutils

class ProofCallModal(discord.ui.DesignerModal):
	def __init__(self, *args, **kwargs):
		self.screens = None
		file = discord.ui.Label("Screenshots to upload for this match", discord.ui.FileUpload(max_values=10, required=True))
		super().__init__(discord.ui.TextDisplay("Screenshot Submission"), file, *args, **kwargs)

	async def callback(self, interaction: discord.Interaction):
		print(f"test: {self.children[1]}")
		self.screens = self.children[1].item.values
		await interaction.respond("Processing, wait for embed to update")

class ProofCallView(discord.ui.View):
	def __init__(self, proofcall, tourney, match, *args, **kwargs):
		super().__init__(timeout=None)
		self.msg = self.message
		self.proofcall = proofcall
		self.tourney = tourney
		self.match = match

		## This is for potential discord.ui.DesignerView output to be *fancy* - not now
		#if screens != None:
		#	gallery = discord.ui.MediaGallery()
		#	for screen in screens:
		#		gallery.add_item(screen)
		#	self.add_item(gallery)

		submit = discord.ui.Button(label="Submit Screenshot", style=discord.ButtonStyle.green, custom_id="submitBtn")
		submit.callback = self.submitBtn
		self.add_item(discord.ui.ActionRow(submit))

	async def submitBtn(self, interaction: discord.Interaction):
		modal = ProofCallModal(title="Screenshot Submission")
		await interaction.response.send_modal(modal=modal)
		await modal.wait()
		await self.proofcall.addScreenshots(interaction, self.tourney, self.match, modal.screens)
		#await interaction.edit_original_response(embed=self.proofcall.makeProofEmbed(self.tourney, self.match), view=ProofCallView(self.proofcall, self.tourney, self.match, modal.screens))

class ProofCalls():
	def __init__(self, bot, *args, **kwargs):
		self.bot = bot
		self.sql = bot.tourneyDB
		self.chUtils = chutils.CHUtils()
		self.scheduler = AsyncIOScheduler()
		self.scheduler.add_job(self.watchRefToolMatches, apscheduler.triggers.cron.CronTrigger(hour="*", minute='*', second='0,30', timezone='UTC'))
		self.scheduler.start()

	async def init(self):
		proofs = await self.sql.getActiveProofCalls()
		for match in proofs:
			tourney = await self.sql.getTourney(match['tourneyid'])
			if match['finished'] and match['postid'] != None:
				channel = self.bot.get_channel(tourney['config']['proof_channel'])
				thread = channel.get_thread(match['postid'])
				msg = await thread.fetch_message(match['postid'])

				ply1 = await self.sql.getPlayerByCHName(match['matchjson']['highSeed']['name'], tourney['id'])
				ply2 = await self.sql.getPlayerByCHName(match['matchjson']['lowSeed']['name'], tourney['id'])
				ply1 = await self.bot.fetch_user(ply1['discordid'])
				ply2 = await self.bot.fetch_user(ply2['discordid'])
				print(f"Restarting proof call {match['matchuuid']} with thread id {msg.id}")
				msg = await msg.edit(content=f"Paging {ply1.mention} and {ply2.mention} for screenshots!", embed=self.makeProofEmbed(tourney, match), view=ProofCallView(self, tourney, match))

	async def watchRefToolMatches(self):
		proofs = await self.sql.getActiveProofCalls()

		for match in proofs:
			if match['finished'] and match['postid'] == None:
				tourney = await self.sql.getTourney(match['tourneyid'])
				forumChannel = self.bot.get_channel(tourney['config']['proof_channel'])
				newThr = await self.postProofCall(tourney, forumChannel, match)
				await self.sql.replaceRefToolMatch(match['matchuuid'], tourney['id'], True, match['matchjson'], newThr.id)

	async def postProofCall(self, tourney: dict, channel: discord.ForumChannel, match: dict):
		print(f"Posting proof call for {tourney['config']['name']} match {match['matchjson']['highSeed']['name']} - {match['matchjson']['lowSeed']['name']}")
		ply1 = await self.sql.getPlayerByCHName(match['matchjson']['highSeed']['name'], tourney['id'])
		ply2 = await self.sql.getPlayerByCHName(match['matchjson']['lowSeed']['name'], tourney['id'])

		if ply1 != None:
			ply1 = await self.bot.fetch_user(ply1['discordid'])
		else:
			print(f"Error finding {tourney['name']} player {match['matchjson']['highSeed']['name']}!")

		if ply2 != None:
			ply2 = await self.bot.fetch_user(ply2['discordid'])
		else:
			print(f"Error finding {tourney['name']} player {match['matchjson']['lowSeed']['name']}!")

		return await channel.create_thread(name=f"Proof call for {ply1.mention} and {ply2.mention}!", content=f"Paging {ply1.mention} and {ply2.mention} for screenshots!", embed=self.makeProofEmbed(tourney, match), view=ProofCallView(self, tourney, match, []))

	async def addScreenshots(self, msg: discord.Message, tourney: dict, match: dict, screens: list) -> bool: #Bool if match is complete
		successes = 0
		for screen in screens:
			stegData = await self.chUtils.getStegInfo(screen)
			if stegData == None:
				pass

			print(f'tourney: {tourney['brackets']}')
			chartInfo = tourney['brackets'][match['matchjson']['setlist']]['set_list'][stegData['song_name']]
			if chartInfo['checksum'] == stegData['checksum']:
				stegData['image_url'] = f"https://matches.corpo-ch.org/{tourney['config']['name'].replace(" ", "")}/{stegData['image_name']}"
			else:
				print(f"screenshot not using correct chart")

			if 'tb' in match['matchjson'] and match['matchjson']['tb']['song'] == stegData['song_name']:
				match['matchjson']['tb']['steg_data'] = stegData
			else:
				for song in match['matchjson']['rounds']:
					if song['song'] == stegData['song_name']:
						song['steg_data'] = stegData
						successes += 1
						break

		needed = len(match['matchjson']['rounds']) if "tb" not in match else len(match['matchjson']['rounds'] + 1)
		if successes == needed:
			await self.sql.saveCompleteMatch(match['matchuuid'], match['tourneyid'], match['matchjson']['highSeed']['name'], match['matchjson']['lowSeed']['name'], match['matchJson'])
			await msg.edit_original_response(content=f"Match Complete!", embed=self.makeProofEmbed(tourney, match), view=None)
		else:
			await self.sql.replaceRefToolMatch(match['matchuuid'], match['tourneyid'], True, match['matchjson'], match['postid'])
			await msg.edit_original_response(embed=self.makeProofEmbed(tourney, match), view=ProofCallView(self, tourney, match))

	def makeProofEmbed(self, tourney: dict, match: dict) -> discord.Embed:
		embed = discord.Embed(colour=0x3FFF33)
		ply1 = match['matchjson']['highSeed']
		ply2 = match['matchjson']['lowSeed']
		embed.title = f"{tourney['config']['name']} - {ply1['name']}:{ply1['seed']} vs {ply2['name']}:{ply2['seed']}"

		banStr = f"**{ply1['name']} Bans**\n"
		for ban in ply1['ban']:
			banStr += f"{ban}\n"

		banStr += f"\n**{ply2['name']} Bans**\n"
		for ban in ply2['ban']:
			banStr += f"{ban}\n"

		embed.add_field(name="Bans", value=banStr, inline=False)
		rndStr = ""
		for rnd in match['matchjson']['rounds']:
				rndStr += f"{rnd['pick']} picks {rnd['song']} - {rnd['winner']} wins\n\n"

		if 'tb' in match:
			rndStr += f"TIEBREAKER - {match['tb']['song']} - {match['tb']['winner']} wins!\n"

		if match['matchjson']['winner'] == 0:
			rndStr += f"{ply1['name']} wins the match!"
		else:
			rndStr += f"{ply2['name']} wins the match!"

		embed.add_field(name="Round Results", value=rndStr, inline=False)

		missingStr = ""
		successStr = ""
		for song in match['matchjson']['rounds']:
			if 'steg_data' in song:
				successStr += f"{song['song']}\n"
			else:
				missingStr += f"{song['song']}\n"

		if successStr != "":
			embed.add_field(name="Received Screens", value=successStr, inline=False)
		if missingStr != "":
			embed.add_field(name="Screenshots Needed", value=missingStr, inline=False)
			embed.add_field(name="Instructions", value="Please click 'Submit Screenshot' button to submit the in-game screenshots for this round", inline=False)

		return embed
