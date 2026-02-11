import requests, json, io, hashlib, re, gspread, asyncio, discord, os, uuid, platform, subprocess, pytesseract
from datetime import datetime
from random import randbytes
from PIL import Image, ImageEnhance
from django.db import models
from corpoch import __user_agent__
from corpoch import settings 
from corpoch.models import GSheetAPI, Chart, Tournament, TournamentQualifier

#TODO: Add requests-cached to not hit encore hard for /chopt runs

#Big shoutout to @mirjay for this until they actually get a proper collaborator role on the project
class SNGHandler:
	def __init__(self, chartFolder: os.path=None, sngData: bytes=None, playlist: str=None):
		if chartFolder is None and sngData is None:
			raise ValueError("chartFolder or sngData must be provided")
		self._playlist = playlist
		
		if sngData is not None:
			self._files = self.get_sng_files(sngData)
		else:
			results = []
			files = os.listdir(chartFolder)
			
			valid_picture_names = ("album.","background.","highway.")
			valid_picture_extensions = ("png","jpg","jpeg")
			valid_music_names = ("guitar.","bass.","rhythm.","vocals.","vocals_1.","vocals_2.","drums.","drums_1.","drums_2.","drums_3.","drums_4.","keys.","song.","crowd.","preview.")
			valid_music_extensions = ("mp3","ogg","opus","wav")
			valid_video_names = ("video.")
			valid_video_extensions = ("mp4","avi","webm","vp8","ogv","mpeg")
			valid_notes = ["notes.chart","notes.mid"]
			valid_songini = "song.ini"
			
			for file in files:
				if ((file.lower().startswith(valid_picture_names) and file.lower().endswith(valid_picture_extensions)) or
					(file.lower().startswith(valid_music_names) and file.lower().endswith(valid_music_extensions)) or
					(file.lower().startswith(valid_video_names) and file.lower().endswith(valid_video_extensions)) or
					(file.lower() in valid_notes) or
					(file.lower() == valid_songini)):
					with open(os.path.join(chartFolder,file), 'rb') as f:
						file_bytes = f.read()
						results.append([file.lower(), file_bytes])
			self._files = results

	def parse_metadataPairArray(self, data: bytes) -> list[str, str]:
		results = []
		byte_stream = io.BytesIO(data)
		while True:
			keyLen_bytes = byte_stream.read(4)
			if not keyLen_bytes:
				break
			keyLen = int.from_bytes(keyLen_bytes, byteorder='little')
			
			key_bytes = byte_stream.read(keyLen)
			key = key_bytes.decode('utf-8')
			
			valueLen_bytes = byte_stream.read(4)
			valueLen = int.from_bytes(valueLen_bytes, byteorder='little')
			
			value_bytes = byte_stream.read(valueLen)
			value = value_bytes.decode('utf-8')
			
			results.append([key, value])
		return results

	def parse_fileMetaArray(self, data: bytes) -> list[str, int, int]:
		results = []
		byte_stream = io.BytesIO(data)
		while True:
			filenameLen_bytes = byte_stream.read(1)
			if not filenameLen_bytes:
				break
			filenameLen = int.from_bytes(filenameLen_bytes, byteorder='little')
			
			filename_bytes = byte_stream.read(filenameLen)
			filename = filename_bytes.decode('utf-8').casefold()
				
			contentsLen_bytes = byte_stream.read(8)
			contentsLen = int.from_bytes(contentsLen_bytes, byteorder='little')
			
			contentsIndex_bytes = byte_stream.read(8)
			contentsIndex = int.from_bytes(contentsIndex_bytes, byteorder='little')
			
			results.append([filename, contentsLen, contentsIndex])
		return results
			
	def unmaskFileByteArray(self, dataArray: list[int], xorMask:list[int]) -> list[int]:
		unmasked_file_bytes = [None] * len(dataArray)
		for i in range(len(dataArray)):
			xorKey = xorMask[i % 16] ^ (i % 256)
			unmasked_file_bytes[i] = dataArray[i] ^ xorKey
		return unmasked_file_bytes

	#Meant to be fed in raw content - this may be able to be improved?
	def get_sng_files(self, all_bytes: bytes) -> list[str, bytes]:
		all_bytes_stream = io.BytesIO(all_bytes)
		all_bytes_stream.seek(10)
		
		xor_mask_bytes = all_bytes_stream.read(16)
		xorMask = list(xor_mask_bytes)

		metadataLen_bytes = all_bytes_stream.read(8)
		metadataLen = int.from_bytes(metadataLen_bytes, byteorder='little', signed=False)
		
		all_bytes_stream.seek(8,1)
		
		metadataPairArray_bytes = all_bytes_stream.read(metadataLen-8)
		metadataPairArray = self.parse_metadataPairArray(metadataPairArray_bytes)
		
		fileMetaLen_bytes = all_bytes_stream.read(8)
		fileMetaLen = int.from_bytes(fileMetaLen_bytes, byteorder='little', signed=False)

		all_bytes_stream.seek(8, 1)

		fileMetaArray_bytes = all_bytes_stream.read(fileMetaLen-8)
		fileMetaArray = self.parse_fileMetaArray(fileMetaArray_bytes)

		results = []
		with io.BytesIO() as songini_stream:
			songini_stream.write(bytes(f"[song]\n".encode('utf-8')))
			for row in metadataPairArray:
				line = f"{row[0]} = {row[1]}\n"
				line_bytes = bytes(line.encode('utf-8'))
				songini_bytes = songini_stream.write(line_bytes)
			results.append(["song.ini", songini_bytes])
			
		for row in fileMetaArray:
			all_bytes_stream.seek(row[2])
			results.append([row[0],bytes(self.unmaskFileByteArray(list(all_bytes_stream.read(row[1])),xorMask))])
			
		return results

	def get_chart_data(self) -> bytes:
		for row in self._files:
			filename = row[0]
			if "notes.chart" in filename or "notes.mid" in filename:
				return row[1]
	
	def get_md5(self) -> str:
		return hashlib.md5(self.get_chart_data()).hexdigest()
	
	def build_sng(self) -> bytes:
		with io.BytesIO() as sng_stream:
			header ="SNGPKG"
			sng_stream.write(bytes(header.encode('utf-8')))
			version = 1
			sng_stream.write(version.to_bytes(4, byteorder="little"))
			xorMask = randbytes(16)
			sng_stream.write(xorMask)

			metadataPairArray = []
			for row in self._files:
				filename = row[0].lower()
				if "song.ini" in filename:
					songini_bytes = row[1]
			songini_text = songini_bytes.decode('utf-8').split('\n',1)[-1]
			for line in songini_text.strip().split('\n'):
				line = line.split('=',1)
				key = line[0].strip()
				value = line[1].strip()
				metadataPairArray.append([key,value])
			if "playlist" not in metadataPairArray[0] and self._playlist is not None:
				metadataPairArray.append(["playlist",self._playlist])
			with io.BytesIO() as songini_stream:
				for row in metadataPairArray:
					if "playlist" == row[0] and self._playlist is not None:
						key = bytes("playlist".encode('utf-8'))
						keyLen = len(key).to_bytes(4, byteorder="little",signed=True)
						value = bytes(self._playlist.encode('utf-8'))
						valueLen = len(value).to_bytes(4, byteorder='little',signed=True)
						songini_stream.write(keyLen)
						songini_stream.write(key)
						songini_stream.write(valueLen)
						songini_stream.write(value)	
						continue
					key = bytes(row[0].encode('utf-8'))
					keyLen = len(key).to_bytes(4, byteorder="little",signed=True)
					value = bytes(row[1].encode('utf-8'))
					valueLen = len(value).to_bytes(4, byteorder='little',signed=True)
					songini_stream.write(keyLen)
					songini_stream.write(key)
					songini_stream.write(valueLen)
					songini_stream.write(value)
				metadataLen = (8+songini_stream.getbuffer().nbytes).to_bytes(8, byteorder='little',signed=False)
				metadataCount = len(metadataPairArray).to_bytes(8, byteorder='little',signed=False)
				sng_stream.write(metadataLen)
				sng_stream.write(metadataCount)
				songini_stream.seek(0)
				sng_stream.write(songini_stream.read())
			
			fileCount = len(self._files)-1
			fileMetaLen = 8 + (17)*fileCount
			for row in self._files:
				if "song.ini" == row[0]:
					continue
				fileMetaLen += len(bytes(row[0].encode('utf-8')))
			sng_stream.write(fileMetaLen.to_bytes(8, byteorder='little', signed=False))
			sng_stream.write(fileCount.to_bytes(8, byteorder='little' ,signed=False))

			fileDataArray_index = sng_stream.getbuffer().nbytes + fileMetaLen
			fileDataArray_Array =[]
			with io.BytesIO() as fileMeta_stream:
				for row in self._files:
					if "song.ini" == row[0]:
						continue
					filename = bytes(row[0].lower().encode('utf-8'))
					filenameLen = len(filename).to_bytes(1, byteorder="little",signed=False)
					contentsLen = len(row[1]).to_bytes(8, byteorder='little',signed=False)
					contentsIndex = (fileDataArray_index).to_bytes(8, byteorder='little',signed=False)
					fileMeta_stream.write(filenameLen)
					fileMeta_stream.write(filename)
					fileMeta_stream.write(contentsLen)
					fileMeta_stream.write(contentsIndex)
					fileDataArray_Array.append([row[0], len(row[1]), fileDataArray_index])
					fileDataArray_index += len(row[1])
				fileMeta_stream.seek(0)
				sng_stream.write(fileMeta_stream.read())
			
			fileDataLen = 0
			for row in fileDataArray_Array:
				fileDataLen += row[1]
			sng_stream.write((fileDataLen).to_bytes(8, byteorder='little',signed=False))

			for row in self._files:
				if "song.ini" == row[0].lower():
					continue
				sng_stream.write(bytes(self.unmaskFileByteArray(list(row[1]),xorMask)))

			sng_stream.seek(0)
			return sng_stream.read()

class EncoreClient:
	def __init__(self, limit: int=24, exact: bool=True):
		#limit 24 for discord view select options limit
		self._session = requests.Session()
		self._session.headers = {
			'User-Agent' : __user_agent__,
			"Content-Type": "application/json"
		}
		# encore.us API urls
		self._encore={}
		self._encore['gen'] = 'https://api.enchor.us/search'
		self._encore['adv'] = 'https://api.enchor.us/search/advanced'
		self._encore['dl'] = 'https://files.enchor.us/'

		self.limit = limit
		self.exact = exact
		self.sng = SNGHandler()

	def search(self, query: dict) -> dict:
		d = { 'number' : 1, 'page' : 1 }
		if "blake3" in query:
			blake3 = query.pop('blake3')
		else:
			blake3 = None

		for i in query:
			d[i] = { 'value' : query[i], 'exact' : self.exact, 'exclude' : False }

		resp = self._session.post(self._encore['adv'], data = json.dumps(d))
		#remove dupelicate chart entries from search
		theJson = resp.json()['data']
		for i, chart1 in enumerate(theJson):
			for j, chart2 in enumerate(theJson):
				if chart1['ordering'] == chart2['ordering'] and i != j:
					del theJson[j]

		#print(json.dumps(theJson, indent=4))
		retData = []
		atts = ['name','artist','md5','charter','album','hasVideoBackground']
		for i, v in enumerate(theJson):
			if i > self.limit:
				break
			if blake3 != None and blake3 not in v['md5']:
				continue

			s = {}
			d = theJson[i]
			for j in atts:
				s[j] = d[j]
			retData.append(s)

		return retData

	def url(self, chart: dict) -> str:
		return f"{self._encore['dl']}{chart['md5']}{('_novideo','')[not chart['hasVideoBackground']]}.sng"

	def download_from_chart(self, chart: dict) -> str:
		return self._session.get(self.url(chart)).content

	def download_from_url(self, url: str) -> str:
		return self._session.get(url).content

	def get_md5_from_chart(self, chart) -> str:
		return self.sng.get_md5(self.download_from_chart(chart))

	def get_md5_from_url(self, url) -> str:
		return self.sng.get_md5(self.download_from_url(url))

class CHOpt:
	def __init__(self):
		self._path = os.getenv("CHOPT_PATH")
		self._chopt = f"{self._path}/CHOpt.exe" if platform.system() == 'Windows' else f"{self._path}/CHOpt"
		self._scratch = f"{self._path}/scratch"
		self._output = os.getenv("CHOPT_OUTPUT")
		self._url = os.getenv("CHOPT_URL")
		self._encore = EncoreClient()
		self._sng = SNGHandler()
		self.opts = { 'whammy' : 0, 'squeeze' : 0, 'speed' : 100, 'output_path' : True }
		self.url = ""
		self.img = None
		self.file = ""
		#Create dirs
		if not os.path.isdir(self._scratch):
			os.makedirs(self._scratch)
		if not os.path.isdir(self._output):
			os.makedirs(self._output)

	def _prep_chart(self, content):
		outFile = f"{self._scratch}/notes.chart"
		with open(outFile, 'wb') as f:
			f.write(content)
		return outFile

	def gen_path(self, chart) -> str:
		if isinstance(chart, Chart):
			content = self._encore.download_from_url(chart.url)
		elif isinstance(chart, dict):
			content = self._encore.download_from_chart(chart)
		else:
			print("gen_path called incorrectly, chart not type Chart or encore chart dict")
			return None

		chartFile = self._prep_chart(self._sng.get_chart_data(content))
		fileId = uuid.uuid1()
		outPng = f"{self._output}/{fileId}.png"
		print(f"CHOPT: Output PNG: {outPng}")
		choptCall = f"{self._chopt} -s {self.opts['speed']} --ew {self.opts['whammy']} --sqz {self.opts['squeeze']} -f {chartFile} -i guitar -d expert {'' if self.opts['output_path'] else '-b'} -o {outPng}"
		try:
			subprocess.run(choptCall, check=True, shell=True, stdout=subprocess.DEVNULL)
		except Exception as e:
			print(f"CHOpt call failed with exception: {e}")
			os.remove(chartFile)
			return None

		os.remove(chartFile)
		self.url = f"{self._url}/{fileId}.png"
		self.img = Image.open(outPng)
		self.file = outPng
		return self.url

class CHStegTool:
	def __init__(self):
		self._path = os.getenv("CHSTEG_PATH")
		self._steg = f"{self._path}/ch_steg_reader.exe" if platform.system() == "Windows" else f"{self._path}/ch_steg_reader"
		self._media_root = os.getenv("MEDIA_ROOT")
		self._scratch = f"{self._path}/scratch"
		if not os.path.isdir(self._scratch):
			os.makedirs(self._scratch)

	def _get_over_strums(self, imageName: str, roundData: dict) -> dict:
		#print(f"OS Counts: {osCnt}")
		img = Image.open(imageName)
		osImg = img.crop((0, 690, 1080, 727))
		outStr = pytesseract.image_to_string(osImg)
		osCnt = re.findall("(?<=Overstrums )([Oo0-9]+)", outStr)
		#Sanity check OS's before adding
		for i, player in enumerate(roundData['players']):
			## TODO: THIS NEEDS TO BE FIXED FOR ACTUAL ROUND DATA INFO
			if len(osCnt) == len(roundData['players']):
				player['overstrums'] = osCnt[i]
			else:
				player['overstrums'] = '-'

	#TODO: Needs sync providers for django

	async def _prep_image(self, image) -> str:
		image.filename = re.sub(r'[^a-zA-Z0-9-_.]', '', image.filename)
		out = f"{self._scratch}/{image.filename}"
		await image.save(out, seek_begin=True)
		return out

	def _sanitize_steg(self, steg: dict):
		steg = json.loads(steg.stdout.decode("utf-8"))
		steg['charter_name'] = re.sub(r"(?:<[^>]*>)", "", steg['charter_name'])
		for ply in steg['players']:
			ply['profile_name'] = re.sub(r"(?:<[^>]*>)", "", ply['profile_name'])
		return steg

	def _call_steg(self, imagePath):
		stegCall = f"{self._steg} --json {imagePath}"

		try:
			proc = subprocess.run(stegCall.split(), stdout = subprocess.PIPE, stderr = subprocess.PIPE)
			if proc.returncode != 0 or proc.returncode != '0':
				output = self._sanitize_steg(proc)

				if output['game_version'] in "v1.0.0.4080-final":
					print("Running 1.0.0-4080 fixes")
					self._get_over_strums(imagePath, output)
					#Notes missed isn't explicitly in steg :shrug:
					for i, player in enumerate(output['players']):
						player["notes_missed"] = player["total_notes"] - player['notes_hit']

					os.remove(imagePath)
			else:
				print(f"Error returned from steg tool, usually invalid chart: [ {" ".join(proc.args)} ] - {proc.stderr.decode("utf-8")}")
				os.remove(imagePath)
				return None
		except Exception as e:
			print(f"Steg Cli Failed: {e}")
			os.remove(imagePath)
			return None

		return output

	async def getStegInfo(self, image: discord.Attachment) -> dict:
		img = await self._prep_image(image)
		print(f"Steg Input PNG: {img}")
		info = self._call_steg(img)
		print(f"Steg Json: {info}")
		return info

	def buildStatsEmbed(self, title: str, stegData: dict) -> discord.Embed:
		embed = discord.Embed(colour=0x3FFF33)
		embed.title = title

		if 'image_url' in stegData:
			embed.set_image(url=stegData['image_url'])

		chartStr = f"Chart Name: {stegData["song_name"]}\n"
		chartStr += f"Run Time: <t:{int(round(datetime.strptime(stegData["score_timestamp"], '%Y-%m-%dT%H:%M:%S.%fZ').timestamp()))}:f>\n"
		chartStr += f"Game Version: {stegData['game_version']}"
		embed.add_field(name="Submission Stats", value=chartStr, inline=False)

		for i, player in enumerate(stegData["players"]):
			plyStr = ""
			plyStr += f"Player Name: {player["profile_name"]}\n"
			plyStr += f"Score: {player["score"]}\n"
			plyStr += f"Notes Hit: {player["notes_hit"]}/{player["total_notes"]} - {(player["notes_hit"]/player["total_notes"]) * 100:.2f}% {' - 👑' if player['is_fc'] else ''}\n"
			plyStr += f"Overstrums: {player["overstrums"]}\n"
			plyStr += f"Ghosts: {player["frets_ghosted"]}\n"
			plyStr += f"SP Phrases: {player["sp_phrases_earned"]}/{player["sp_phrases_total"]}\n"
			embed.add_field(name=f"Player {i+1}", value=plyStr, inline=False)

		return embed

class GSheets():
	def __init__(self, tournament: Tournament, qualifier: TournamentQualifier=None):	
		self._format_border = None#{'textFormat': {'bold': False}, "horizontalAlignment": "CENTER", 'borders': {'right': {'style' : 'SOLID'}, 'left': {'style' : 'SOLID' }}}
		#TODO: Make a django-admin task to resend the match data to the airtable (or any sheet)
		self._tourney = tournament
		self._qualifier = qualifier

	#Needed as if the GSheetApi objects call is in the normal init, app load fails for dbot due to DB access before django is ready
	def init(self, sheet: str) -> bool:
		self.gc = gspread.service_account(GSheetApi.objects.get())
		self.tourney = self.sql.getTourneyConfig(self.tid)

		if "disable_gsheets" in self.tourneyConf and self.tourneyConf['disable_gsheets']:
			return True

		#Create Sheet
		if "qualifier_sheet" not in self.tourneyConf and "qualifier" in sheet:
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
			#await self.sql.setTourneyConfig(self.tid, self.tourneyConf)
		elif "qualifier" in sheet:
			self.qualiSheet = self.gc.open_by_url(self.tourneyConf['qualifier_sheet'])
			self.qualiws = self.qualiSheet.worksheet("Raw Qualifier Submissions")

		if 'livematch_sheet' not in self.tourneyConf and "livematch" in sheet:
			try:
				self.liveMatchSheet = self.gc.open(f"{self.tourneyConf['name']} - Live Match Data")
				print(f"Setting up live match sheet for {self.tourneyConf['name']} : {self.liveMatchSheet.url}")
				self.lmws = self.liveMatchSheet.worksheet("match_data")
				self.tourneyConf['livematch_sheet'] = self.liveMatchSheet.url
				#await self.sql.setTourneyConfig(self.tid, self.tourneyConf)
			except:
				return False
		elif "livematch" in sheet:
			self.liveMatchSheet = self.gc.open_by_url(self.tourneyConf['livematch_sheet'])
			self.lmws = self.liveMatchSheet.worksheet("match_data")

		if 'stats_sheet' not in self.tourneyConf and "stats" in sheet:
			try:
				self.statsSheet = self.gc.open(f"{self.tourneyConf['name']} - Airtable")
				print(f"Setting up quali sheet for {self.tourneyConf['name']} : {self.statsSheet.url}")
				self.sws = self.statsSheet.worksheet("match_data")
				self.tourneyConf['stats_sheet'] = self.statsSheet.url
				#await self.sql.setTourneyConfig(self.tid, self.tourneyConf)
			except:
				return False
		elif "stats" in sheet:
			self.statsSheet = self.gc.open_by_url(self.tourneyConf['stats_sheet'])
			self.sws = self.statsSheet.worksheet("match_data")

		return True

	def fixSongName(self, song: str, setlist: dict) -> str:
		name = song
		songData = setlist['set_list'][song]

		if songData['speed'] != 100:
			name += f" ({songData['speed']}%)"
		if "NoModifiers" not in songData['modifiers']:
			#Gross
			mods = re.sub('[a-z]', '', str(songData['modifiers'])).replace(" ", "").replace("'", "")
			name += f" {mods}"

		return name

	async def submitLiveMatch(self, match) -> bool:
		if "disable_gsheets" in self.tourneyConf and self.tourneyConf['disable_gsheets']:
			return True

		brackets = await self.sql.getTourneyBrackets(match['tourneyid'])
		bracket = brackets[self.tourneyConf['name']]
		matchJson = match['matchjson']
		ply1 = matchJson['highSeed']
		ply2 = matchJson['lowSeed']
		#Dirty hard-coded indexes for now to get this working - this is going to need to be changed
		ply1Pts = ply1['points'] if 'points' in ply1 else 0
		ply2Pts = ply2['points'] if 'points' in ply1 else 0
		matchList = [match['matchuuid'], ply1['name'], ply1Pts, ply1['ban'][0], ply1['ban'][1], ply2['name'], ply2Pts, ply2['ban'][0], ply2['ban'][1], matchJson['setlist'], matchJson['winner'] ]
		for song in matchJson['rounds']:
			matchList.append(song['pick'])
			matchList.append(self.fixSongName(song['song'], bracket))

		if 'tb' in matchJson:
			matchList.append(self.fixSongName(matchJson['tb']['song'], bracket))
		else:
			matchList.append("")

		for song in matchJson['rounds']:
			matchList.append(song['winner'])

		if 'tb' in matchJson:
			matchList.append(matchJson['tb']['winner'])
		else:
			matchList.append("")

		if match['sheetrow'] is None:
			print("Adding new row to sheet...")
			self.lmws.append_row(matchList)
			numRows = len(self.lmws.get_all_values())
		
			self.lmws.format(f"A{numRows}:AE{numRows}", self.frmtBorder)
			match['sheetrow'] = numRows
			await self.sql.replaceRefToolMatch(match['matchuuid'], match['tourneyid'], match['finished'], matchJson, match['sheetrow'], match['postid'])
		else:
			self.lmws.update([matchList], f"A{match['sheetrow']}:AE{match['sheetrow']}")

	async def submitMatchResults(self, match, tourney) -> bool:
		if "disable_gsheets" in self.tourneyConf and self.tourneyConf['disable_gsheets']:
			return True

		print(f"Submitting {match['matchuuid']} to airtable")
		brackets = await self.sql.getTourneyBrackets(match['tourneyid'])
		bracket = brackets[self.tourneyConf['name']]
		matchJson = match['matchjson']
		ply1 = matchJson['highSeed']
		ply2 = matchJson['lowSeed']
		matchName = f"{ply1['name']} vs {ply2['name']}"

		for song in matchJson['rounds']:
			ply1List = []
			ply2List = []
			ply1Fnd = {}
			ply2Fnd = {}

			if song['index'] == 1:
				ply1List.append(matchName)
				ply2List.append("")
			else:
				ply1List.append("")
				ply2List.append("")

			ply1List.append(self.fixSongName(song['song'], bracket))
			ply2List.append(self.fixSongName(song['song'], bracket))

			stegData = song['steg_data']
			for ply in stegData['players']:
				if ply1['name'] == ply['profile_name']:
						ply1Fnd = ply
						continue
				if ply2['name'] == ply['profile_name']:
						ply2Fnd = ply
						continue

			ply1List.append(ply1Fnd['profile_name'])
			ply2List.append(ply2Fnd['profile_name'])
			ply1List.append(ply1Fnd['score'])
			ply2List.append(ply2Fnd['score'])
			ply1List.append(ply1Fnd['notes_missed'])
			ply2List.append(ply2Fnd['notes_missed'])
			ply1List.append(ply1Fnd['overstrums'])
			ply2List.append(ply2Fnd['overstrums'])
			ply1List.append(ply1Fnd['notes_hit'])
			ply2List.append(ply2Fnd['notes_hit'])
			ply1List.append(ply1Fnd['frets_ghosted'])
			ply2List.append(ply2Fnd['frets_ghosted'])
			ply1List.append(f"{datetime.strptime(stegData['score_timestamp'], '%Y-%m-%dT%H:%M:%S.%fZ').strftime("%Y-%m-%d %H:%M:%S")}-UTC")
			ply2List.append("")
			ply1List.append(stegData['image_url'])
			ply2List.append("")
			try:
				self.sws.append_row(ply1List)
				numRows = len(self.sws.get_all_values())
				self.sws.format(f"A{numRows}:L{numRows}", self.frmtBorder)
				self.sws.append_row(ply2List)
				numRows = len(self.sws.get_all_values())
				self.sws.format(f"A{numRows}:L{numRows}", self.frmtBorder)
			except Exception as e:
				print(f"Exception in gspread: {e}")
				return False

	async def submitQualifier(self, user, qualifierData: dict) -> bool:
		if "disable_gsheets" in self.tourneyConf and self.tourneyConf['disable_gsheets']:
			return True

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
			self.qualiws.append_row([user.global_name, chName, score, missed, hit, os, ghosts, phrases, submissionTimestamp, screenshotTimestamp, imgUrl, gameVer])
			numRows = len(self.ws.get_all_values())
			self.qualiws.format(f"A{numRows}:L{numRows}", self.frmtBorder)
		except Exception as e:
			print(f"Exception in gspread: {e}")
			return False

		return True


#Keeping for future OCR use/reference
#OCR Tweaking - Keep until v6 is dead
#img = Image.open(imageName)
#image = cv2.imread(imageName)
#gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
#blur = cv2.GaussianBlur(gray, (3,3), 0)
#thresh = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
# Morph open to remove noise and invert image
#kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3,3))
#opening = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel, iterations=1)
#invert = 255 - opening
