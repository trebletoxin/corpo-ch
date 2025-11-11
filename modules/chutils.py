import subprocess, requests, sys, platform, uuid, json, os, operator, re, cv2, pytesseract

from PIL import Image, ImageEnhance
from discord import File
from datetime import datetime, timezone

import discord

class CHUtils():
	def __init__(self):
		# CHOpt path
		self.CHOptPath = 'CHOpt/CHOpt.exe' if platform.system() == 'Windows' else 'CHOpt/CHOpt'

		# SngCli Converter
		self.sngCliPath = 'SngCli/SngCli.exe' if platform.system() == 'Windows' else 'SngCli/SngCli'
		self.sngCliInput = 'SngCli/input'
		self.sngCliOutput = 'SngCli/output'

		self.stegCliPath = 'steg/ch_steg_reader.exe' if platform.system() == 'Windows' else 'steg/ch_steg_reader'
		self.stegCliInput = 'steg/input'

		# encore.us API urls
		self.encore={}
		self.encore['gen'] = 'https://api.enchor.us/search'
		self.encore['adv'] = 'https://api.enchor.us/search/advanced'
		self.encore['dl'] = 'https://files.enchor.us/'

	def CHOpt(self, sngUuid, opts, outputPath) -> str:
		if os.path.isfile(f'{self.sngCliOutput}/{sngUuid}/notes.chart'):
			inChart = f'{self.sngCliOutput}/{sngUuid}/notes.chart'
		elif os.path.isfile(f'{self.sngCliOutput}/{sngUuid}/notes.mid'):
			inChart = f'{self.sngCliOutput}/{sngUuid}/notes.mid'
		else:
			print(f"Can't find chart file for song {sngUuid}")
			return None

		outPng = f'./CHOpt/output/{sngUuid}.png'
		print(f"Output PNG: {outPng}")

		if outputPath:
			choptCall = f"{self.CHOptPath} -s {opts['speed']} --ew {opts['whammy']} --sqz {opts['squeeze']} -f {inChart} -i guitar -d expert -o {outPng}"
		else:
			choptCall = f"{self.CHOptPath} -s {opts['speed']} --ew {opts['whammy']} --sqz {opts['squeeze']} -f {inChart} -b -i guitar -d expert -o {outPng}"

		try:
			subprocess.run(choptCall, check=True, shell=True, stdout=subprocess.DEVNULL)
		except Exception as e:
			print(f"CHOpt call failed with exception: {e}")
			return None

		return outPng

	def encoreSearch(self, query: dict):
		d = { 'number' : 1, 'page' : 1 }

		for i in query:
			d[i] = { 'value' : query[i], 'exact' : True, 'exclude' : False }

		resp = requests.post(self.encore['adv'], data = json.dumps(d), headers = {"Content-Type":"application/json"})

		#remove dupelicate chart entries from search
		theJson = resp.json()['data']
		for i, chart1 in enumerate(theJson):
			for j, chart2 in enumerate(theJson):
				if chart1['ordering'] == chart2['ordering'] and i != j:
					del theJson[j]

		retData = []
		atts = ['name','artist','md5','charter','album','hasVideoBackground']
		for i, v in enumerate(theJson):
			if i > 10:
				break

			s = {}
			d = theJson[i]
			for j in atts:
				s[j] = d[j]

			retData.append(s)

		return retData

	def encoreDownload(self, theChart: dict) -> str:
		url = f"{self.encore['dl']}{theChart['md5']}{('_novideo','')[not theChart['hasVideoBackground']]}.sng"
		resp=requests.get(url)
		sngUuid = str(uuid.uuid4())
		os.makedirs(f'{self.sngCliInput}/{sngUuid}')
		filePath=f'{self.sngCliInput}/{sngUuid}/{sngUuid}.sng'

		with open(filePath,'wb') as file:
			file.write(resp.content)

		return sngUuid

	def sngDecode(self, sngUuid: str) -> bool:
		os.makedirs(f'{self.sngCliOutput}/{sngUuid}')
		inputSng = f'{self.sngCliInput}/{sngUuid}'
		outputSng = f'{self.sngCliOutput}'
		try:
			proc = subprocess.run(f'{self.sngCliPath} decode -in {inputSng} -out {outputSng} --noStatusBar', check=True, shell=True, stdout=subprocess.DEVNULL)
		except Exception as e:
			print(f"SngCli Decode Failed: {e}")
			return False

		return True

	def getOverStrums(self, imageName: str, roundData: dict) -> dict:
		#img = Image.open(imageName)
		image = cv2.imread(imageName)
		gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
		blur = cv2.GaussianBlur(gray, (3,3), 0)
		thresh = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]

		# Morph open to remove noise and invert image
		#kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3,3))
		#opening = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel, iterations=1)
		#invert = 255 - opening
		img = Image.fromarray(thresh)
		osImg = img.crop((0, 690, 1080, 727))
		outStr = pytesseract.image_to_string(osImg)
		osCnt = re.findall("(?<=Overstrums )([0-9]+)", outStr)

		#Sanity check OS's before adding
		for i, player in enumerate(roundData['players']):
			## TODO: THIS NEEDS TO BE FIXED FOR ACTUAL ROUND DATA INFO
			if len(osCnt) == len(roundData['players']):
				player['overstrums'] = osCnt[i]
			else:
				player['overstrums'] = '-'

	async def getStegInfo(self, image: File) -> dict:
		imageName = f"{self.stegCliInput}/{image.filename}"
		print(f"Steg Input PNG: {imageName}")
		await image.save(imageName, seek_begin=True)
		stegCall = f"{self.stegCliPath} --json {imageName}"

		try:
			proc = subprocess.run(stegCall.split(), stdout = subprocess.PIPE, stderr = subprocess.PIPE)
			if proc.returncode != 0 or proc.returncode != '0':
				output = json.loads(proc.stdout.decode("utf-8"))

				#populate data not present in steg
				self.getOverStrums(imageName, output)
				output['image_name'] = re.sub(r'[^a-zA-Z0-9-_.]', '', image.filename)
				#Notes missed isn't explicitly in steg :shrug:
				for i, player in enumerate(output['players']):
					player["notes_missed"] = player["total_notes"] - player['notes_hit']

			else:
				print(f"Error returned from steg tool, usually invalid chart: [ {" ".join(proc.args)} ] - {proc.stderr.decode("utf-8")}")
				os.remove(imageName)
				return None
		except Exception as e:
			print(f"Steg Cli Failed: {e}")
			os.remove(imageName)
			return None

		os.remove(imageName)
		return output

	def buildStatsEmbed(self, title: str, stegData: dict, isQualifier=False) -> discord.Embed:
		embed = discord.Embed(colour=0x3FFF33)
		embed.title = title

		chartStr = ""
		if isQualifier:
			chartStr = chartStr + f"Chart Name: {stegData["song_name"]}\n"
			chartStr = chartStr + f"Submission Time: <t:{int(round(datetime.strptime(stegData["submission_timestamp"], '%Y-%m-%dT%H:%M:%S.%fZ').replace(tzinfo=timezone.utc).timestamp()))}:f>\n"
		else:
			chartStr = chartStr + f"Chart Name: {stegData["song_name"]}\n"

		chartStr = chartStr + f"Run Time: <t:{int(round(datetime.strptime(stegData["score_timestamp"], '%Y-%m-%dT%H:%M:%S.%fZ').replace(tzinfo=timezone.utc).timestamp()))}:f>\n"
		chartStr = chartStr + f"Game Version: {stegData['game_version']}"
		embed.add_field(name="Submission Stats", value=chartStr, inline=False)

		for i, player in enumerate(stegData["players"]):
			plyStr = ""
			plyStr = plyStr + f"Player Name: {player["profile_name"]}\n"
			plyStr = plyStr + f"Score: {player["score"]}\n"
			plyStr = plyStr + f"Notes Hit: {player["notes_hit"]}/{player["total_notes"]} - {(player["notes_hit"]/player["total_notes"]) * 100:.2f}% {' - 👑' if player['is_fc'] else ''}\n"
			plyStr = plyStr + f"Overstrums: {player["overstrums"]}\n"
			plyStr = plyStr + f"Ghosts: {player["frets_ghosted"]}\n"
			plyStr = plyStr + f"SP Phrases: {player["sp_phrases_earned"]}/{player["sp_phrases_total"]}\n"
			embed.add_field(name=f"Player {i+1}", value=plyStr, inline=False)

		return embed
