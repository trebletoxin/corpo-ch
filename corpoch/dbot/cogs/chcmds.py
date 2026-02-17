import discord, os, sys, json, shutil

from discord.ext import commands
from discord.ui import *
from discord.enums import ComponentType, InputTextStyle

from corpoch.providers import CHOpt, EncoreClient, CHStegTool
from corpoch.models import Tournament, TournamentBracket, Chart

class CHOptModal(discord.ui.DesignerModal):
	def __init__(self, path, *args, **kwargs):
		self.path = path
		whm = discord.ui.Label("Early Whammy %", discord.ui.InputText(style=discord.InputTextStyle.short, required=True, placeholder='0-100'))
		sqz = discord.ui.Label("Squeeze %", discord.ui.InputText(style=discord.InputTextStyle.short, required=True, placeholder='0-100'))
		spd = discord.ui.Label("Song Speed (10-1000)", discord.ui.InputText(style=discord.InputTextStyle.short, required=True, value=100))
		pth = discord.ui.Label("Show Path in Image", discord.ui.Select(max_values=1, options=[discord.SelectOption(label='True', value=True, default=True), discord.SelectOption(label="False", value=False)], required=True))
		super().__init__(discord.ui.TextDisplay("CHOpt Options"), whm, sqz, spd, pth, *args, **kwargs)

	async def callback(self, interaction: discord.Interaction):
		retData = {}
		if not self.children[0][0].value.isdigit() and not int(self.children[0][0].content) >= 0 and not int(self.children[0][0].content <= 100):
			await interaction.response.send_message("Invalid whammy value, please use a number between 0 and 100", ephemeral=True)
			self.stop()
			return
		else:
			retData['whammy'] = int(self.children[0][0].value)

		if not self.children[0][1].value.isdigit() and not int(self.children[0][1].content) >= 0 and not int(self.children[0][1].content <= 100):
			await interaction.response.send_message("Invalid squeeze value, please use a number between 0 and 100", ephemeral=True)
			self.stop()
			return
		else:
			retData['squeeze'] = int(self.children[0][1].value)

		if not self.children[2].value.isdigit() and not int(self.children[0][2].content) >= 10 and not int(self.children[0][2].content <= 1000):
			await interaction.response.send_message("Invalid speed value, please use a number between 10 and 250", ephemeral=True)
			self.stop()
			return
		else:
			retData['speed'] = int(self.children[0][2].value)

		if self.children[0][3].value in "True":
			retData['output_path'] = True
		else:
			retData['output_path'] = False

		await interaction.response.defer(invisible=True)
		self.path.chopt.opts = retData
		self.stop()

class EncoreModal(discord.ui.Modal):
	def __init__(self, path, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.path = path
		self.add_item(InputText(label="Song Name", style=discord.InputTextStyle.short, required=True))
		self.add_item(InputText(label="Artist", style=discord.InputTextStyle.short, required=False))
		self.add_item(InputText(label="Album", style=discord.InputTextStyle.short, required=False))
		self.add_item(InputText(label="Charter", style=discord.InputTextStyle.short, required=False))

	async def callback(self, interaction: discord.Interaction):
		retData = {}
		retData['name'] = self.children[0].value
		retString = f"Chart Name: {retData['name']}"
		if self.children[1].value:
			retData['artist'] = self.children[1].value
			retString += f" - Artist: {retData['artist']}"
		if self.children[2].value:
			retData['album'] = self.children[2].value
			retString += f" - Album: {retData['album']}"
		if self.children[3].value:
			retData['charter'] = self.children[3].value
			retString += f" - Charter: {retData['charter']}"

		await interaction.response.defer(invisible=True)
		tmp = self.path.encore.search(retData)
		self.path.charts = tmp
		await self.path.show()
		self.stop()

class TournamentSelect(discord.ui.Select):
	def __init__(self, path):
		self.path = path
		self.retOpts = {}

	async def init(self):		
		active = None
		opts = []
		async for tourney in Tournament.objects.all():
			self.retOpts[tourney.name] = tourney
			if tourney.guild == self.path.ctx.guild.id and tourney.active:
				opts.append(discord.SelectOption(label=tourney.name, description=tourney.short_name, default=True))
				active = tourney
			else:
				opts.append(discord.SelectOption(label=tourney.name, description=tourney.short_name))
		
		if active:
			super().__init__(placeholder=active.short_name, options=opts, custom_id="tourney_sel")
		elif self.path.tournament:
			super().__init__(placeholder=self.path.tournament.short_name,  options=opts, custom_id="tourney_sel")
		else:
			super().__init__(placeholder="Select a tournament", options=opts, custom_id="tourney_sel")

	async def callback(self, interaction: discord.Interaction):
		self.path.tournament = self.retOpts[self.values[0]]
		await interaction.response.defer(ephemeral=True)
		await self.path.show()

class BracketSelect(discord.ui.Select):
	def __init__(self, path):
		self.path = path
		self.retOpts = {}

	async def init(self):
		opts = []
		async for bracket in TournamentBracket.objects.select_related('tournament').all():
			self.retOpts[str(bracket)] = bracket
			opts.append(discord.SelectOption(label=str(bracket)))

		if self.path.bracket:
			super().__init__(placeholder=str(self.path.bracket), options=opts, custom_id="bracket_sel")
		else:
			super().__init__(placeholder="Select a bracket", options=opts, custom_id="bracket_sel")

	async def callback(self, interaction: discord.Interaction):
		self.path.bracket = self.retOpts[self.values[0]]
		self.path.charts = [ chart async for chart in self.path.bracket.setlist.all() ]
		await interaction.response.defer(ephemeral=True)
		await self.path.show()

class ChartSelect(discord.ui.Select):
	def __init__(self, path):
		self.path = path
		self.retOpts = {}
		opts = []
		for chart in self.path.charts:
			if isinstance(chart, Chart):
				self.retOpts[chart.md5] = chart
				if self.path.chart == chart:
					opts.append(discord.SelectOption(label=chart.name, value=chart.md5, description=f"{chart.artist} - {chart.album} - {chart.charter}", default=True))
				else:
					opts.append(discord.SelectOption(label=chart.name, value=chart.md5, description=f"{chart.artist} - {chart.album} - {chart.charter}"))
			else:#dict
				opts.append(discord.SelectOption(label=chart['name'], value=chart['md5'], description=f"{chart['artist']} - {chart['album']} - {chart['charter']}"))
				self.retOpts[chart['md5']] = chart

		if self.path.chart:
			if isinstance(chart, Chart):
				super().__init__(placeholder=chart.name, options=opts, max_values=1, custom_id="chart_sel")
			else:
				super().__init__(placeholder=chart['name'], options=opts, max_values=1, custom_id="chart_sel")
		else:
			super().__init__(placeholder="Select a chart", options=opts, max_values=1, custom_id="chart_sel")

	async def callback(self, interaction: discord.Interaction):
		self.path.chart = self.retOpts[self.values[0]]
		await interaction.response.defer(ephemeral=True)
		await self.path.show()

class Path():
	def __init__(self, ctx):
		self.ctx = ctx
		self.user = ctx.user
		self.encore = EncoreClient(exact=False)
		self.chopt = CHOpt()
		self.outputPath = True
		#self.tournament = None #Here as a kindness - presence of these attrs flags touney search enabled
		#self.bracket = None
		self.charts = []
		self.chart = None

	async def show(self):
		view = PathView(self)
		await view.init()
		await self.ctx.interaction.edit_original_response(embeds=[self.genChartEmbed()], content=None, view=view)

	async def hide(self):
		await self.ctx.interaction.delete_original_response()

	async def showResult(self, interaction):
		self.chopt.gen_path(self.chart)
		self.chopt.save_for_upload()
		if not self.chopt.url:
			await interaction.followup.send("Path generation died on CHOpt call.", ephemeral=True)
			await self.hide()
		else:
			await interaction.followup.send(embed=self.genResultEmbed(), ephemeral=True)
			await self.hide()

	async def doSearch(self, inQuery):
		self.searchData = self.chUtils.encoreSearch(inQuery)
		self.numCharts = len(self.searchData)
		self.selection = 1 if self.numCharts == 1 else -1

	def genInstructionEmbed(self) -> discord.Embed:
		embed = discord.Embed(colour=0x3FFF33)
		embed.title = "Instructions"
		embed.add_field(name="Steps", value="Use the search button to search for a chart on Encore\nUse the tournament search button to seach through tournament setlists", inline=False)
		return embed

	def genChartEmbed(self) -> discord.Embed:
		embed = discord.Embed(colour=0x3FFF33)
		embed.title = "CHOpt Path Generator"
		embed.add_field(name="Instructions", value="Set the CHOpt settings, then hit submit", inline=False)
		chartListing = ""
		if self.charts:
			embed.add_field(name="Directions", value="Charts shown in dropdown below.\nSelect the one you want to generate a path for.\nSet CHOpt options, then submit!", inline=False) 
		else:
			embed.add_field(name="Directions", value="No results found for search.\nTry searching again with different options.", inline=False) 

		if self.chart:
			embed.add_field(name="Current CHOpt Options", value=f"Early Whammy: {self.chopt.opts['whammy']}%\nSqueeze: {self.chopt.opts['squeeze']}%\nSong Speed: {self.chopt.opts['speed']}%\nShow path in output: {self.chopt.opts['output_path']}", inline = False)
		return embed

	def genResultEmbed(self) -> discord.Embed:
		embed = discord.Embed(colour=0x00F2FF)
		embed.set_author(name=f"Generated by:{self.ctx.user.display_name}", icon_url=self.ctx.user.avatar.url)
		embed.title = "/ch path run result"
		embed.set_author(name=self.ctx.user.display_name, icon_url=self.ctx.user.avatar.url)
		embed.set_image(url=self.chopt.url)
		if isinstance(self.chart, Chart):
			embed.add_field(name="CHOpt Path For", value=f"{self.chart.name} - {self.chart.artist} - {self.chart.album} - {self.chart.charter}", inline=False)
		else:
			embed.add_field(name="CHOpt Path For", value=f"{self.chart["name"]} - {self.chart["artist"]} - {self.chart["album"]} - {self.chart["charter"]}", inline=False)
		embed.add_field(name="CHOpt Options Used", value=f"Early Whammy: {self.chopt.opts['whammy']}%\nSqueeze: {self.chopt.opts['squeeze']}%\nSong Speed: {self.chopt.opts['speed']}%\nShow Path: {self.chopt.opts['output_path']}", inline=False)
		embed.add_field(name="Path shown", value=f"**{self.outputPath}**", inline=False)
		embed.add_field(name="Image Link", value=f"[Link to Image]({self.chopt.url})", inline=False)
		return embed

class PathView(discord.ui.View):
	def __init__(self, path):
		self.path = path
		super().__init__(timeout = None)
		if not self.path.chart:
			self.get_item('submitBtn').disabled = True
			self.get_item('chopts').disabled = True

	async def init(self):
		if hasattr(self.path, 'tournament'):
			sel = TournamentSelect(self.path)
			await sel.init()
			self.add_item(sel)
		if hasattr(self.path, 'bracket'):
			sel = BracketSelect(self.path)
			await sel.init()
			self.add_item(sel)
		if len(self.path.charts) > 0:
			sel = ChartSelect(self.path)
			self.add_item(sel)

	async def clear(self):
		if hasattr(self.path, "tournament"):
			del self.path.tournament
		if hasattr(self.path, "bracket"):
			del self.path.bracket
		self.path.charts = []

	@discord.ui.button(label="Cancel", style=discord.ButtonStyle.red, custom_id="cancelBtn")
	async def cancelBtn(self, button, interaction: discord.Interaction):
		await interaction.response.edit_message(content="Closing", embed=None, view=None, delete_after=1)
		self.stop()

	@discord.ui.button(label="Search", style=discord.ButtonStyle.secondary)
	async def searchBtn(self, button, interaction: discord.Interaction):
		await self.clear()
		modal = EncoreModal(self.path, title="Encore search for chart")
		await interaction.response.send_modal(modal)
		await modal.wait()
		await self.path.show()

	@discord.ui.button(label="Tourney Search", style=discord.ButtonStyle.secondary, custom_id="tourneyBtn", disabled=True)
	async def tourneyBtn(self, button, interaction: discord.Interaction):
		await self.clear()
		try:
			self.path.tournament = await Tournament.objects.aget(guild=self.path.ctx.guild.id, active=True)	
		except Tournament.DoesNotExist:
			self.path.tournament = None
		self.path.bracket = None
		self.charts = []
		await interaction.response.defer(invisible=True)
		await self.path.show()

	@discord.ui.button(label='CHOpt Options', style=discord.ButtonStyle.secondary, custom_id="chopts")
	async def choptsBtn(self, button, interaction: discord.Interaction):
		choptsModal = CHOptModal(self.path, title="CHOpt options to use for path")
		await interaction.response.send_modal(choptsModal)
		await choptsModal.wait()

		self.path.choptOpts = choptsModal.choptOpts
		await self.path.show()

	@discord.ui.button(label="Submit", style=discord.ButtonStyle.green, custom_id="submitBtn")
	async def submitBtn(self, button, interaction: discord.Interaction):
		await interaction.response.defer(invisible=False)
		await self.path.showResult(interaction)

class CHCmds(commands.Cog):
	def __init__(self, bot):
		self.bot = bot

	ch = discord.SlashCommandGroup('ch','CloneHero tools')

	@ch.command(name='path',description='Generate a path for a given chart on Chorus', integration_types={discord.IntegrationType.guild_install, discord.IntegrationType.user_install})
	async def path(self, ctx):
		path = Path(ctx)
		await ctx.respond(content="Setting up", ephemeral=True)
		await path.show()

	@discord.message_command(name='CH Sten',description='Reads CH Sten data from a screenshot posted to a message', integration_types={discord.IntegrationType.guild_install, discord.IntegrationType.user_install})
	async def getScreenSten(self, ctx: discord.ApplicationContext, msg: discord.Message):
		resp = await ctx.defer(invisible=True)
		if len(msg.attachments) < 1:
			await ctx.respond("No screenshot attached to this post!", delete_after=5)
		elif len(msg.attachments) >= 1:
			#Only gets first screenshot if multiple are attached
			submission = msg.attachments[0]
		
		steg = CHStegTool()
		stegData = await steg.getStegInfo(submission)

		if stegData == None:
			await ctx.respond("Submitted screenshot is not a valid in-game Clone Hero screenshot", delete_after=5)
			return

		embed = steg.buildStatsEmbed("Screenshot Results")
		if len(msg.attachments) > 1:
			await ctx.respond("Only getting first screenshot data from this message", embed=embed)
		else:
			await ctx.respond(embed=embed)	

def setup(bot):
	bot.add_cog(CHCmds(bot))
