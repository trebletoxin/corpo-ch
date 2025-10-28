import gspread
import tourneysql
import asyncio
import discord

class GSheets():
	def __init__(self, bot: discord.Bot, sql: tourneysql.TourneyDB, tid: int):
		self.bot = bot
		self.tid = tid
		self.sql = sql
		self.gc = gspread.service_account(filename="config/gsheets-key.json")

	async def init(self) -> bool:
		self.tourneyConf = await self.sql.getTourneyConfig(self.tid)
		#Create Sheet
		if "qualifier_sheet" not in self.tourneyConf:
			try:
				self.qualiSheet = self.gc.open(f"{self.tourneyConf['name']} - Qualifier Submissions")
			except:
				return False

			print(f"Setting up quali sheet for {self.tourneyConf['name']} : {self.qualiSheet.url}")
			self.ws = self.qualiSheet.add_worksheet(title="Raw Qualifier Submissions", rows=2, cols=9)
			self.ws.update_acell("A1", "DO NOT EDIT THIS WORKSHEET UNLESS TOLD TO OTHERWISE")
			self.ws.format("A1", {'textFormat': {'bold': True }})
			self.ws.update([["Discord Name", "Clone Hero Name", "Score", "Notes Missed", "Notes Hit", "Overstrums", "Ghosts", "Phrases Earned", "Image Name" ]], "A2:I2")
			self.ws.format("A2:I2", {'textFormat': {'bold': True}, 'borders': { 'bottom': { 'style' : 'SOLID' }}}) #'rgbColor': {"red": 0.0, "green": 0.0, "blue": 0.0}, 
			self.tourneyConf['qualifier_sheet'] = self.qualiSheet.url
			await self.sql.setTourneyConfig(self.tid, self.tourneyConf)
		else:
			self.qualiSheet = self.gc.open_by_url(self.tourneyConf['qualifier_sheet'])
			self.ws = self.qualiSheet.worksheet("Raw Qualifier Submissions")

		return True

	async def submitQualifier(self, user, qualifierData: dict):
		chName = qualifierData['players'][0]['profile_name']
		score = qualifierData['players'][0]['score']
		missed = qualifierData['players'][0]['notes_missed']
		hit = qualifierData['players'][0]['notes_hit']
		os = qualifierData['players'][0]['overstrums']
		ghosts = qualifierData['players'][0]['frets_ghosted']
		phrases = qualifierData['players'][0]['sp_phrases_earned']
		imgName = qualifierData['image_name']

		try:
			self.ws.append_row([user.global_name, chName, score, missed, hit, os, ghosts, phrases, imgName])
		except Exception as e:
			print(f"Exception in gspread: {e}")
			return False

		return True
