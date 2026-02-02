import math
import discord
from discord.ext import commands
from discord.ui import *
from discord.enums import ComponentType, InputTextStyle
from asgiref.sync import sync_to_async

from corpoch.models import Chart, Tournament, TournamentBracket, BracketGroup, TournamentPlayer, TournamentMatchOngoing, TournamentMatchCompleted, GroupSeed, TournamentRound

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

class BanSelect(discord.ui.Select):
	def __init__(self, match):
		self.match = match

	async def init(self):
		index = ((self.match.bracket.total_bans - len(self.match.bans)) % self.match.bracket.num_players)
		print(f"INDEX: {index}")
		opts = []
		setlist = await self.get_setlist_no_bans()
		for chart in setlist:
			opts.append(discord.SelectOption(label=chart.name, description=f"{chart.artist} - {chart.charter}"))
		super().__init__(placeholder=f"{self.match.seeding[index].player.ch_name} Ban", max_values=1, options=opts, custom_id="ban_sel")

	@sync_to_async
	def get_setlist_no_bans(self) -> list:
		banList = []
		for ban in self.match.bans:
			banList.append(ban.id)
		return list(self.match.setlist.filter(tiebreaker=False).exclude(id__in=banList))

	@sync_to_async
	def get_chart_from_name(self, name: str) -> Chart:
		return self.match.setlist.get(name=name)

	async def callback(self, interaction: discord.Interaction):
		#Models should all be loaded at this point
		self.match.bans.append(await self.get_chart_from_name(self.values[0]))
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
			if (song['name'] in self.match.ban1['name'] and not self.match.ban1['save']):
				continue
			elif song['name'] in self.match.ban2['name'] or song['name'] in playedSongs:
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

class BracketSelect(discord.ui.Select):
	def __init__(self, match):
		self.match = match

	async def init(self):
		brackets = []
		for bracket in await self.get_brackets():
			brackets.append(discord.SelectOption(label=bracket.name))
		super().__init__(max_values=1, options=brackets, custom_id="bracket_sel")

	@sync_to_async
	def get_brackets(self) -> list:
		return list(self.match.tourney.brackets.all())

	@sync_to_async
	def set_bracket(self, bracket):
		self.match.bracket = self.match.tourney.brackets.get(name=bracket, tournament=self.match.tourney)

	async def callback(self, interaction: discord.Integration):
		await self.set_bracket(self.values[0])
		await self.match.showTool(interaction)

class GroupSelect(discord.ui.Select):
	def __init__(self, match):
		self.match = match

	async def init(self):
		groups = []
		for group in await self.get_groups():
			groups.append(discord.SelectOption(label=group.name))
		super().__init__(max_values=1, options=groups, custom_id="group_sel")

	@sync_to_async
	def get_groups(self) -> list:
		return list(self.match.bracket.groups.all())

	@sync_to_async
	def set_bracket_group(self, group):
		self.match.group = self.match.bracket.groups.get(name=group, bracket=self.match.bracket)

	async def callback(self, interaction: discord.Integration):
		await self.set_bracket_group(self.values[0])
		await self.match.showTool(interaction)

class PlayerSelect(discord.ui.Select):
	def __init__(self, match, custom_id):
		self.match = match
		self.cid = custom_id #Discord doesn't let us access underlying attributes until super() is called

	async def init(self):
		dis = True
		#I feel like this can come down, but not sure what's best
		if 'player1' in self.cid:
			if self.match.bracket.num_players == 2:
				placeholder = "High Seed"
			else:
				placeholder = "Player 1"

			if len(self.match.seeding) > 0:
				placeholder += f" - {self.match.seeding[0].player.ch_name}"
			if len(self.match.seeding) == 0:
				dis = False

		elif 'player2' in self.cid:
			if self.match.bracket.num_players == 2:
				placeholder = "Low Seed"
			else:
				placeholder = "Player 2"

			if len(self.match.seeding) > 1:
				placeholder += f" - {self.match.players[1].player.ch_name}"
			if len(self.match.seeding) == 1:
				dis = False
		elif 'player3' in self.cid:
			placeholder = "Player 3"
			if len(self.match.players) > 2:
				placeholder += f" - {self.match.players[2].ch_name}"
			if len(self.match.players) == 2:
				dis = False
		elif 'player4' in self.cid:
			placeholder = "Player 4"
			if len(self.match.players) > 3:
				placeholder += f" - {self.match.players[3].ch_name}"
			if len(self.match.players) == 3:
				dis = False

		seeding = []
		for seed in await self.get_seeding():
			seeding.append(discord.SelectOption(label=await self.get_seed_name(seed)))
		super().__init__(placeholder=placeholder, max_values=1,	options=seeding, custom_id=self.cid)
		if dis:
			self.disabled = True

	@sync_to_async
	def get_seeding(self) -> list:
		id_list = []
		for seed in self.match.seeding:
			id_list.append(seed.id)
		return list(self.match.group.seeding.all().exclude(id__in=id_list))

	@sync_to_async
	def get_seed_name(self, seed: GroupSeed) -> str:
		return seed.short_name

	@sync_to_async
	def get_seed_from_name(self, theSeed: str) -> GroupSeed:
		for seed in self.match.group.seeding.all():
			if seed.short_name == theSeed:
				return seed

	@sync_to_async
	def set_player(self, seed: GroupSeed):
		self.match.seeding.append(seed)
		self.match.seeding = sorted(self.match.seeding, key=lambda x: x.seed)

	async def callback(self, interaction: discord.Interaction):
		seed = await self.get_seed_from_name(self.values[0])
		await self.set_player(seed)
		await self.match.showTool(interaction)

#This class is being written with the assumption of official tournament matches - exhibition can be made to extend this with custom logging/rules
class DiscordMatch():
	def __init__(self, message):
		#Make non-persistent until match has officiall started?
		#Make it so if user is not a ref, self match where each player picks options is required
		self.msg = message
		self.ref = message.user if hasattr(message, 'user') else None
		self.channel = message.channel if hasattr(message, 'channel') else None
		self.tourney = None
		self.bracket = None
		self.group = None
		self.setlist = None
		self.seeding = []
		self.seeding_discord = []
		self.bans = []
		self.rounds = []
		self.confirmCancel = False
		#TODO - figure out how to allow exhibition matches(?)

	async def init(self):
		self.tourney = await self.get_tournament_from_guild(self.msg.guild)#Assuming single tourney for now
		if not self.tourney:
			await self.msg.respond("No active tourney - running exhibition mode not supported now", ephemeral=True)
		else:
			await self.msg.respond("Setting up")

	async def finishMatch(self, interaction):
		#Save match results to DB
		await interaction.edit(embeds=[self.genMatchEmbed()], content=None, view=None)

	async def showTool(self, interaction):
		view = DiscordMatchView(self)
		await view.init()
		self.msg = await interaction.edit(embeds=[self.genMatchEmbed()], content=None, view=view)

	@sync_to_async
	def get_tournament_from_guild(self, guild: discord.Guild) -> Tournament:
		return Tournament.objects.get(guild=guild.id, active=True)

	@sync_to_async
	def get_setlist(self):
		self.setlist = Chart.objects.filter(brackets__id=self.bracket.id)
		print(f"SETLIST: {self.setlist}")

	def genMatchEmbed(self):
		embed = discord.Embed(colour=0x3FFF33)
		embed.set_author(name=f"Ref: {self.ref.display_name}", icon_url=self.ref.avatar.url)

		if not self.bracket:
			embed.title = f"{self.tourney.short_name}"
			embed.add_field(name="Bracket Select", value=f"Select which bracket the match is for", inline=False)
		elif not self.group:
			embed.title = f"{self.tourney.short_name} - {self.bracket.name}"
			embed.add_field(name="Group Select", value=f"Select which group the match is for", inline=False)
		elif len(self.seeding) < self.bracket.num_players:
			embed.title = f"{self.tourney.short_name} - {self.bracket.name} - Group {self.group.name}"
			embed.add_field(name="Player Select", value=f"Select which players the match is for", inline=False)
			return embed
		elif len(self.bans) < self.bracket.total_bans:
			embed.title = f"{self.tourney.short_name} - {self.bracket.name} - Group {self.group.name} - {self.seeding[0].short_name} vs {self.seeding[1].short_name}"
			outStr = ""
			for i, seed in enumerate(self.seeding):
				outStr += f"**{seed.player.ch_name} Bans**\n"
				for j in range(0, self.bracket.num_bans):
					try:
						outStr += f"{self.bans[j+i]}\n"
					except IndexError:
						outStr += "--\n"
			embed.add_field(name="Bans", value=f"{outStr}\nSelect next ban", inline=False)
		else:
			embed.title = ""
		return embed

class DiscordMatchView(discord.ui.View):
	def __init__(self, match):
		super().__init__(timeout = None)
		self.match = match
		self.ref = match.ref

		cancel = discord.ui.Button(label="Cancel", style=discord.ButtonStyle.red, custom_id="cancelBtn")
		cancel.callback = self.cancelBtn
		self.add_item(cancel)

		self.back = discord.ui.Button(label="Back", style=discord.ButtonStyle.secondary, custom_id="backBtn")
		self.back.callback = self.backBtn

		self.submit = discord.ui.ButtonS(label='Submit Match', style=discord.ButtonStyle.green, custom_id="submitBtn")
		self.submit.callback = self.SubmitBtn
		self.submit.disabled = True

	async def init(self):
		if not self.match.bracket:
			sel = BracketSelect(self.match)
			await sel.init()
			self.add_item(sel)
		elif not self.match.group:
			self.add_item(self.back)
			sel = GroupSelect(self.match)
			await sel.init()
			self.add_item(sel)
		elif len(self.match.seeding) < self.match.bracket.num_players:
			self.add_item(self.back)
			for i in range(self.match.bracket.num_players):
				sel = PlayerSelect(self.match, f"player{i+1}_sel")
				await sel.init()
				self.add_item(sel)
		elif len(self.match.bans) < self.match.bracket.total_bans:
			self.add_item(self.back)
			await self.match.get_setlist() #Ensure objects are all loaded into the DB before accessing
			sel = BanSelect(self.match)
			await sel.init()
			self.add_item(sel)
		else:
			self.add_item(self.submit)


	async def interaction_check(self, interaction: discord.Interaction):
		if interaction.user.id == self.match.ref.id:
			return True
		else:
			await interaction.response.send_message("You are not the ref for this match", ephemeral=True, delete_after=5)
			return False

	async def backBtn(self, interaction: discord.Interaction):
		if len(self.match.bans) > 0:
			self.match.bans.pop()
		elif len(self.match.seeding) > 0:
			self.match.seeding.pop()
		elif self.match.group:
			self.match.group = None
		elif self.match.bracket:
			self.match.bracket = None
		await self.match.showTool(interaction)

	async def cancelBtn(self, interaction: discord.Interaction):
		if self.match.confirmCancel:
			await interaction.response.edit_message(content="Closing", embed=None, view=None, delete_after=1)
			await self.match.matchDB.cancelMatch(self.match)
			self.stop()
		else:
			self.match.confirmCancel = True
			await interaction.response.send_message(content="Are you sure you want to cancel? Click cancel again to confirm", ephemeral=True, delete_after=5)

	async def startBtn(self, interaction: discord.Interaction):
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
		match = DiscordMatch(ctx)
		await match.init()
		await match.showTool(ctx)

	@match.command(name='reftool', description='Match report done with the ref tool', integration_types={discord.IntegrationType.guild_install})
	async def refToolCmd(self, ctx):
		await ctx.respond.send_modal(modal=RefToolModal())

def setup(bot):
	bot.add_cog(TourneyCmds(bot))
