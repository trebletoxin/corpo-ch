import gspread
import tourneysql
import asyncio
import discord
from datetime import datetime

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
			self.ws = self.qualiSheet.add_worksheet(title="Raw Qualifier Submissions", rows=2, cols=12)
			self.ws.update_acell("A1", "DO NOT EDIT THIS WORKSHEET UNLESS TOLD TO OTHERWISE")
			self.ws.format("A1", {'textFormat': {'bold': True }})
			self.ws.update([["Discord Name", "Clone Hero Name", "Score", "Notes Missed", "Notes Hit", "Overstrums", "Ghosts", "Phrases Earned", "Submission Timestamp", "Screenshot Timestamp", "Image URL", "Game Version" ]], "A2:L2")
			self.ws.format("A2:L2", {'textFormat': {'bold': True}, "horizontalAlignment": "CENTER", 'borders': { 'bottom': { 'style' : 'SOLID' }, 'left': { 'style' : 'SOLID' }, 'right': { 'style' : 'SOLID' }}})
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
		submissionTimestamp = f"{datetime.strptime(qualifierData['submission_timestamp'], '%Y-%m-%dT%H:%M:%S.%fZ').strftime("%Y-%m-%d %H:%M:%S")}-UTC"
		screenshotTimestamp = f"{datetime.strptime(qualifierData['score_timestamp'], '%Y-%m-%dT%H:%M:%S.%fZ').strftime("%Y-%m-%d %H:%M:%S")}-UTC"
		imgUrl = qualifierData['image_url']
		gameVer = qualifierData['game_version']

		try:
			self.ws.append_row([user.global_name, chName, score, missed, hit, os, ghosts, phrases, submissionTimestamp, screenshotTimestamp, imgUrl, gameVer])
			numRows = len(self.ws.get_all_values())
			self.ws.format(f"A{numRows}:L{numRows}", {'textFormat': {'bold': False}, "horizontalAlignment": "CENTER", 'borders': {'right': {'style' : 'SOLID'}, 'left': {'style' : 'SOLID' }}})
		except Exception as e:
			print(f"Exception in gspread: {e}")
			return False

		return True
