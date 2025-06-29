import discord, os, sys, json, shutil
from discord.ext import commands
from discord.ui import *
from discord.enums import ComponentType, InputTextStyle

import chutils

class CHOptModal(Modal):
	def __init__(self, path, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.path = path
		self.choptOpts = None
		self.add_item(InputText(label="Early Whammy %", style=discord.InputTextStyle.short, required=True, placeholder='0-100'))
		self.add_item(InputText(label="Squeeze %", style=discord.InputTextStyle.short, required=True, placeholder='0-100'))
		self.add_item(InputText(label="Song Speed (10-250)", style=discord.InputTextStyle.short, required=True, value=100))

	async def callback(self, interaction: discord.Interaction):
		retData = {}
		if not self.children[0].value.isdigit() and not int(self.children[0].value) >= 0 and not int(self.children[0].value <= 100):
			await interaction.response.send_message("Invalid whammy value, please use a number between 0 and 100", ephemeral=True)
			self.stop()
			return
		else:
			retData['whammy'] = int(self.children[0].value)

		if not self.children[1].value.isdigit() and not int(self.children[1].value) >= 0 and not int(self.children[1].value <= 100):
			await interaction.response.send_message("Invalid squeeze value, please use a number between 0 and 100", ephemeral=True)
			self.stop()
			return
		else:
			retData['squeeze'] = int(self.children[1].value)

		if not self.children[0].value.isdigit() and not int(self.children[2].value) >= 10 and not int(self.children[2].value <= 250):
			await interaction.response.send_message("Invalid speed value, please use a number between 10 and 250", ephemeral=True)
			self.stop()
			return
		else:
			retData['speed'] = int(self.children[2].value)
		
		await interaction.response.defer(invisible=True)
		self.choptOpts = retData
		self.stop()

class EncoreModal(Modal):
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
		await self.path.doSearch(retData)
		self.stop()

class SubmitModal(Modal):
	def __init__(self, path, numCharts, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.path = path
		self.selection = -1
		self.numCharts = numCharts
		self.add_item(InputText(label="Chart #", style=discord.InputTextStyle.short, required=True, placeholder=f"1-{self.path.numCharts}"))

	async def callback(self, interaction: discord.Interaction):
		if not self.children[0].value.isdigit() or int(self.children[0].value) < 1 or int(self.children[0].value) > self.path.numCharts:
			await interaction.response.send_message(f"Invalid chart number, needs to be 1-{self.path.numCharts}", ephemeral=True, delete_after=5)
		else:
			self.selection = int(self.children[0].value)
			await interaction.response.defer(invisible=True)
			self.stop()

class Path():
	def __init__(self, ctx):
		self.ctx = ctx
		self.user = ctx.user
		self.chUtils = chutils.CHUtils()
		self.searchData = None
		self.numCharts = -1
		self.selection = -1
		self.choptOpts = { 'whammy' : 0, 'squeeze' : 0, 'speed' : 100 }

	async def show(self):
		await self.ctx.interaction.edit_original_response(embeds=[self.genChartEmbed()], content=None, view=PathView(self, False if self.searchData is None else True))

	async def hide(self):
		await self.ctx.interaction.delete_original_response()

	async def showResult(self, interaction):
		sngUuid = self.chUtils.encoreDownload(self.searchData[self.selection - 1])

		if not self.chUtils.sngDecode(sngUuid):
			await interaction.followup.send(f'Path generation died on sng file decode. SNG UUID: {sngUuid}', ephemeral=True)
			await self.hide()
			return

		outPng = self.chUtils.CHOpt(sngUuid, self.choptOpts)
		if not outPng:
			await interaction.followup.send(f"Path generation died on CHOpt call. SNG UUID: {sngUuid}", ephemeral=True)
			await self.hide()
			return

		embed = self.genResultEmbed(sngUuid)
		await interaction.edit(embed=embed, view=None)
		self.cleanup(sngUuid, outPng)

	async def doSearch(self, inQuery):
		self.searchData = self.chUtils.encoreSearch(inQuery)
		self.numCharts = len(self.searchData)
		self.selection = 1 if self.numCharts == 1 else -1

	def genInstructionEmbed(self) -> discord.Embed:
		embed = discord.Embed(colour=0x3FFF33)
		embed.title = "Instructions"
		embed.add_field(name="Steps", value="Use the search button to search for a chart on Encore\nSet CHOpt options\nSubmit using the # of the chart", inline=False)
		return embed

	def genChartEmbed(self) -> discord.Embed:
		embed = discord.Embed(colour=0x3FFF33)
		embed.title = "Charts found for your search"
		embed.add_field(name="Instructions", value="Search Results from Encore\nSet the CHOpt settings then hit submit to pick the chart to use\nOrder is NUM: Song - Artist - Album - Charter", inline=False)
		chartListing = ""

		if self.numCharts > 0:
			for i, chart in enumerate(self.searchData):
				if i + 1 == self.selection:
					chartListing += f"**{i+1}: {chart["name"]} - {chart["artist"]} - {chart["album"]} - {chart["charter"]}**\n"
				else:
					chartListing += f"{i+1}: {chart["name"]} - {chart["artist"]} - {chart["album"]} - {chart["charter"]}\n"
		else:
			chartListing = "No results found for search"

		embed.add_field(name="Search Results", value=chartListing, inline=False)
		if self.numCharts > 0:
			embed.add_field(name="Current CHOpt Options", value=f"Early Whammy: {self.choptOpts['whammy']}%\nSqueeze: {self.choptOpts['squeeze']}%\nSong Speed: {self.choptOpts['speed']}%")

		return embed

	def genResultEmbed(self, sngUuid) -> discord.Embed:
		theSong = self.searchData[self.selection - 1]
		embed = discord.Embed(colour=0x3FFF33)
		embed.title = "/ch path run result"
		embed.set_author(name=self.ctx.user.display_name, icon_url=self.ctx.user.avatar.url)
		url = f"https://che.crmea.de/{sngUuid}.png"
		embed.set_thumbnail(url=url)
		embed.add_field(name="CHOpt Path For", value=f"{theSong["name"]} - {theSong["artist"]} - {theSong["album"]} - {theSong["charter"]}", inline=False)
		embed.add_field(name="CHOpt Options Used", value=f"Early Whammy: {self.choptOpts['whammy']}%\nSqueeze: {self.choptOpts['squeeze']}%\nSong Speed: {self.choptOpts['speed']}%", inline=False)
		embed.add_field(name="Image Link", value=f"[Link to Image]({url})")
		return embed

	def cleanup(self, sngUuid, outPng):
		shutil.rmtree(f'{self.chUtils.sngCliInput}/{sngUuid}')
		shutil.rmtree(f'{self.chUtils.sngCliOutput}/{sngUuid}')
		#os.remove(outPng)

class PathView(discord.ui.View):
	def __init__(self, path, doneSearch):
		super().__init__()
		self.path = path

		if not doneSearch or self.path.numCharts < 1:
			self.get_item('submit').disabled = True
			self.get_item('chopts').disabled = True

	@discord.ui.button(label="Cancel", style=discord.ButtonStyle.red)
	async def cancelBtn(self, button, interaction: discord.Interaction):
		await interaction.response.edit_message(content="Closing", embed=None, view=None, delete_after=1)
		self.stop()

	@discord.ui.button(label='Search', style=discord.ButtonStyle.secondary)
	async def searchBtn(self, button, interaction: discord.Interaction):
		modal = EncoreModal(self.path, title="Encore search for chart")
		await interaction.response.send_modal(modal)
		await modal.wait()
		await self.path.show()

	@discord.ui.button(label='CHOpt Options', style=discord.ButtonStyle.secondary, custom_id="chopts")
	async def choptsBtn(self, button, interaction: discord.Interaction):
		choptsModal = CHOptModal(self.path, title="CHOpt options to use for path")
		await interaction.response.send_modal(choptsModal)
		await choptsModal.wait()

		self.path.choptOpts = choptsModal.choptOpts
		await self.path.show()

	@discord.ui.button(label="Submit", style=discord.ButtonStyle.green, custom_id="submit")
	async def submitBtn(self, button, interaction: discord.Interaction):
		if self.path.numCharts > 1 and self.path.selection == -1:
			submitModal = SubmitModal(self.path, self.path.numCharts, title="Chart Number to use for CHOpt Path")
			await interaction.response.send_modal(submitModal)
			await submitModal.wait()
			if submitModal.selection > 0:
				self.path.selection = submitModal.selection

			await self.path.show()

			return
		elif self.path.numCharts == 1:
			self.path.selection = 1

		await self.path.hide()
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

def setup(bot):
	bot.add_cog(CHCmds(bot))
