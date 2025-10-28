import subprocess, requests, sys, platform, uuid, json, os, operator, re

from PIL import Image
from discord import File
import pytesseract

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
		outStr = pytesseract.image_to_string(Image.open(imageName))
		osCnt = re.findall("(?<=Overstrums )([0-9]+)", outStr)
		print(f"OS Counts: {osCnt}")
		#Sanity check OS's before adding
		for i, player in enumerate(roundData['players']):
			player['overstrums'] = osCnt[i]

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
				output['image_name'] = image.filename
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
