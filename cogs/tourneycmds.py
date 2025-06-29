import discord
from discord.ext import commands
from discord.ui import *
from discord.enums import ComponentType, InputTextStyle

class RefToolModal(Modal):
	def __init__(self, *args, **kwargs):
		self.title="CSC Ref Tool Submission"
		super().__init__(*args, **kwargs)
		self.refToolInput = None
		self.add_item(InputText(label="Ref Tool Output", style=discord.InputTextStyle.long))

	async def callback(self, interaction: discord.Interaction):
		#need sanity checking first, but placeholder for now
		await interaction.response.send_message("Accepting your submission blindly for now!", ephemeral=True)
		self.refToolInput = self.children[0].value
		self.stop()

class PlayerSelect(discord.ui.Select):
	def __init__(self, match, custom_id):
		self.match = match
		if 'player1' in custom_id:
			placeholder = "Player 1"
		elif 'player2' in custom_id:
			placeholder = "Player 2"

		super().__init__(placeholder=placeholder, max_values=1,	select_type=discord.ComponentType.user_select, custom_id=custom_id)

	async def callback(self, interaction: discord.Interaction):
		if "player1" in self.custom_id:
			self.match.player1 = self.values[0]
		elif "player2" in self.custom_id:
			self.match.player2 = self.values[0]

		await self.match.showTool(interaction)

class BanSelect(discord.ui.Select):
	def __init__(self, match, custom_id):
		self.match = match

		if 'player1' in custom_id:
			if self.match.ban1:
				placeholder = f"{self.match.player1.display_name} bans {self.match.ban1}"
			else:
				placeholder = f"Select {self.match.player1.display_name}\'s Ban"
		elif 'player2' in custom_id:
			if self.match.ban2:
				placeholder = f"{self.match.player2.display_name} bans {self.match.ban2}"
			else:
				placeholder = f"Select {self.match.player2.display_name}\'s Ban"

		songOpts = []
		for song in self.match.setlist:
			if (self.match.ban1 and song['name'] in self.match.ban1) or (self.match.ban2 and song['name'] in self.match.ban2):
				continue
			else:
				theSong = discord.SelectOption(label=song['name'], description=f"{song['artist']} - {song['charter']}")
				songOpts.append(theSong)

		super().__init__(placeholder=placeholder, max_values=1,	options=songOpts, custom_id=custom_id)

	async def callback(self, interaction: discord.Interaction):
		theSong = {}
		for song in self.match.setlist:
			if self.values[0] in song['name']:
				theSong = song['name']
				break

		if "player1" in self.custom_id:
			self.match.ban1 = theSong
		elif "player2" in self.custom_id:
			self.match.ban2 = theSong

		await self.match.showTool(interaction)

class SongRoundSelect(discord.ui.Select):
	def __init__(self, match):
		self.match = match
		if self.match.roundSngPlchldr != "":
			placeholder = f"Song Played: {self.match.roundSngPlchldr}"
		else:
			placeholder = "Song Played"

		playedSongs = []
		for rnd in self.match.rounds:
			playedSongs.append(rnd['song'])

		songOpts = []
		for song in self.match.setlist:
			if song['name'] in self.match.ban1 or song['name'] in self.match.ban2 or song['name'] in playedSongs:
				continue
			else:
				theSong = discord.SelectOption(label=song['name'], description=f"{song['artist']} - {song['charter']}")
				songOpts.append(theSong)
		super().__init__(placeholder=placeholder, max_values=1, options=songOpts, custom_id="roundsong_sel")

	async def callback(self, interaction: discord.Integration):
		self.match.roundSngPlchldr = self.values[0]
		await self.match.showTool(interaction)

class PlayerRoundSelect(discord.ui.Select):
	def __init__(self, match):
		self.match = match
		if self.match.roundWinPlchldr:
			placeholder = f"Round Winner: {self.match.roundWinPlchldr.display_name}"
		else:
			placeholder = "Round Winner"

		player1 = discord.SelectOption(label=self.match.player1.display_name)
		player2 = discord.SelectOption(label=self.match.player2.display_name)
		super().__init__(placeholder=placeholder, max_values=1, options=[player1, player2], custom_id="roundwin_sel")

	async def callback(self, interaction: discord.Integration):
		if self.values[0] == self.match.player1.display_name:
			winner = self.match.player1
		elif self.values[0] == self.match.player2.display_name:
			winner = self.match.player2

		self.match.roundWinPlchldr = winner
		await self.match.showTool(interaction)

class DiscordMatch():
	def __init__(self, message, matchDB):
		self.matchDB = matchDB
		self.msg = message
		self.ref = message.user if hasattr(message, 'user') else None
		self.channel = message.channel if hasattr(message, 'channel') else None
		self.id = -1
		self.rounds = [] #list to append a dict of a match result
		self.numRounds = 7 #Need to get the number of rounds from the tournament settings
		self.setlist = [ #Test Data
		{"name" : "Conjunction", "artist" : "Casiopea", "charter" : "JoeyD" },
		{"name" : "Cutting Edge", "artist" : "Kiko Loureiro", "charter" : "Thundahk" },
		{"name" : "Break Your Crank", "artist" : "Guilhem Desq", "charter" : "Aren Eternal" },
		{"name" : "Prayer Position", "artist" : "Endarkenment", "charter" : "Chezy" },
		{"name" : "Endarkenment", "artist" : "Anaal Nathrakh", "charter" : "Miscellany" },
		{"name" : "Chakh Le", "artist" : "Bloodywood", "charter" : "Figneutered" },
		{"name" : "Que Pasa (feat. Dave Mustaine)", "artist" : "John 5", "charter" : "OHM" },
		{"name" : "You Think I Ain't Worth a Dollar", "artist" : "Erra", "charter" : "NCV" },
		{"name" : "Crownless", "artist" : "Nightwish", "charter" : "Jackie & Aren Eternal" },
		{"name" : "Orange Grove", "artist" : "Unprocessed", "charter" : "Deltarak" },
		]
		#self.setlist = None #ID for setlist inside of tourney that contains songs - can we tee off of a channel id in discord?
		##NOTE - we may be able to have a command to set a channel in discord for specifc brackets(?)
		self.player1 = None
		self.player2 = None
		self.ban1 = None
		self.ban2 = None
		self.roundSngPlchldr = ""
		self.roundWinPlchldr = None
		#self.tourney = None #ID for tourney in MySQL - based on discord server id obtained from ctx.guild.id
		self.confirmCancel = False
		self.playersPicked = False
		self.bansPicked = False
		#TODO - figure out handling on groups stage vs playoffs
		#TODO - figure out how to allow exhibition matches(?)

	async def init(self):
		pass #Function will be needed when we need to fetch DB data on class construction

	async def finishMatch(self, interaction):
		#Save match results to DB
		await self.matchDB.finishMatch(self)
		await interaction.edit(embeds=[self.genMatchEmbed()], content=None, view=None)

	async def showTool(self, interaction):
		await self.matchDB.saveMatch(self)
		self.msg = await interaction.edit(embeds=[self.genMatchEmbed()], content=None, view=DiscordMatchView(self))

	def genMatchEmbed(self):
		embed = discord.Embed(colour=0x3FFF33)
		embed.title = "Current Match Results"
		embed.set_author(name=f"Ref: {self.ref.display_name}", icon_url=self.ref.avatar.url)

		if self.playersPicked:
			embed.add_field(name="Players", value=f"{self.player1.display_name} vs {self.player2.display_name}", inline=False)
		else:
			embed.add_field(name="Players", value=f"Select players then hit submit to start", inline=False)

		if self.bansPicked:
			embed.add_field(name="Bans", value=f"{self.player1.display_name} bans {self.ban1}\n{self.player2.display_name} bans {self.ban2}", inline=False)
		elif self.playersPicked and not self.bansPicked:
			embed.add_field(name="Bans", value="Select bans then hit submit to continue", inline=False)

		if self.playersPicked and self.bansPicked:
			if len(self.rounds) > 0:
				rndStr = ""
				for i, rnd in enumerate(self.rounds):
					if i == 0:
						playerPick = self.player1 #Need to figure out this on ban deferrals
					else:
						if self.rounds[i-1]['winner'].id == self.player1.id:
							playerPick = self.player2
						else:
							playerPick = self.player1

					rndStr += f"{playerPick.display_name} Picks - {rnd['song']} - {rnd['winner'].display_name} wins!\n"
				embed.add_field(name="Played Rounds", value=rndStr, inline=False)
			else:
				embed.add_field(name="Played Rounds", value="No rounds played yet", inline=False)

		return embed

class DiscordMatchView(discord.ui.View):
	def __init__(self, match):
		super().__init__(timeout = None)
		self.match = match

		cancel = discord.ui.Button(label="Cancel", style=discord.ButtonStyle.red, custom_id="cancelBtn")
		cancel.callback = self.cancelBtn
		self.add_item(cancel)

		if not self.match.playersPicked:
			players = discord.ui.Button(label="Players Submit", style=discord.ButtonStyle.secondary, custom_id="playersBtn")
			players.callback = self.playersBtn

			if not self.match.player1 or not self.match.player2:
				players.disabled = True

			self.add_item(players)
			self.add_item(PlayerSelect(self.match, "player1_sel"))
			self.add_item(PlayerSelect(self.match, "player2_sel"))
		elif self.match.playersPicked and not self.match.bansPicked:
			bans = discord.ui.Button(label="Submit Bans", style=discord.ButtonStyle.secondary, custom_id="bansBtn")
			bans.callback = self.bansBtn

			if not self.match.ban1 or not self.match.ban2:
				bans.disabled = True

			self.add_item(bans)
			self.add_item(BanSelect(self.match, "player1_ban"))
			self.add_item(BanSelect(self.match, "player2_ban"))
		elif self.match.playersPicked and self.match.bansPicked:
			rounds = discord.ui.Button(label="Add Round", style=discord.ButtonStyle.secondary, custom_id="roundBtn")
			rounds.callback = self.roundBtn

			if self.match.roundWinPlchldr == None or self.match.roundSngPlchldr == "":
				rounds.disabled = True
			
			self.add_item(rounds)

			submit = discord.ui.Button(label="Submit", style=discord.ButtonStyle.green, custom_id="submitBtn")
			submit.callback = self.submitBtn

			ply1Wins = 0
			ply2Wins = 0
			for rnd in self.match.rounds:
				if rnd['winner'].id == self.match.player1.id:
					ply1Wins += 1
				elif rnd['winner'].id == self.match.player2.id:
					ply2Wins += 1

			if ply1Wins < 4 and ply2Wins < 4:
				submit.disabled = True
				self.add_item(SongRoundSelect(self.match))
				self.add_item(PlayerRoundSelect(self.match))
			
			self.add_item(submit)

	async def interaction_check(self, interaction: discord.Interaction):
		if interaction.user.id == self.match.ref.id:
			return True
		else:
			await interaction.response.send_message("You are not the ref for this match", ephemeral=True, delete_after=5)
			return False

	async def cancelBtn(self, interaction: discord.Interaction):
		if self.match.confirmCancel:
			await interaction.response.edit_message(content="Closing", embed=None, view=None, delete_after=1)
			await self.match.matchDB.cancelMatch(self.match)
			self.stop()
		else:
			self.match.confirmCancel = True
			await interaction.response.send_message(content="Are you sure you want to cancel? Click cancel again to confirm", ephemeral=True, delete_after=5)

	async def playersBtn(self, interaction: discord.Interaction):
		self.match.playersPicked = True
		self.stop()
		await self.match.showTool(interaction)

	async def bansBtn(self, interaction: discord.Interaction):
		self.match.bansPicked = True
		await self.match.showTool(interaction)

	async def roundBtn(self, interaction: discord.Interaction):
		await interaction.response.defer(invisible=True)
		self.match.rounds.append({ 'song' : self.match.roundSngPlchldr, 'winner' : self.match.roundWinPlchldr })
		self.match.roundWinPlchldr = None
		self.match.roundSngPlchldr = ""
		await self.match.showTool(interaction)

	async def submitBtn(self, interaction: discord.Interaction):
		await interaction.response.defer(invisible=True)
		await self.match.finishMatch(interaction)

class TourneyCmds(commands.Cog):
	def __init__(self, bot):
		self.bot = bot

	tourney = discord.SlashCommandGroup('tourney','Clone Hero Tournament Commands')
	match = tourney.create_subgroup('match', 'Tourney Match Reporting Commands')

	@match.command(name='discord',description='Match reporting done within discord', integration_types={discord.IntegrationType.guild_install})
	async def discordMatchCmd(self, ctx):
		#TODO - Self Ref Match Check setup (DM user that didn't run the command to confirm?)
		#     - Can bypass above with having a "Ref" role assigned
		message = await ctx.respond("Setting up")
		match = DiscordMatch(message, self.bot.tourneyDB)
		await match.init()
		await match.showTool(message)

	@match.command(name='reftool', description='Match report done with the ref tool', integration_types={discord.IntegrationType.guild_install})
	async def refToolCmd(self, ctx):
		await ctx.respond.send_modal(modal=RefToolModal())

def setup(bot):
	bot.add_cog(TourneyCmds(bot))
