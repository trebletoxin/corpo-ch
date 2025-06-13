import subprocess, requests, sys, platform, uuid, json, os

class CHUtils():
	def __init__(self):
		# CHOpt path
		self.CHOptPath = f'./CHOpt/CHOpt.exe' if platform.system() == 'Windows' else f'CHOpt/CHOpt'

		# SngCli Converter
		self.sngCliPath = f'./SngCli/SngCli.exe' if platform.system() == 'Windows' else f'SngCli/SngCli'
		self.sngCliInput = './SngCli/input'
		self.sngCliOutput = './SngCli/output'

		# encore.us API urls
		self.encore={}
		self.encore['gen'] = 'https://api.enchor.us/search'
		self.encore['adv'] = 'https://api.enchor.us/search/advanced'
		self.encore['dl'] = 'https://files.enchor.us/'

	def CHOpt(self, sngUuid, opts) -> str:
		inChart = f'{self.sngCliOutput}/{sngUuid}/notes.chart'
		outPng = f'./CHOpt/output/{sngUuid}.png'
		choptCall = f"{self.CHOptPath} -s {opts['speed']} --ew {opts['whammy']} --sqz {opts['squeeze']} -f {inChart} -i guitar -d expert -o {outPng}"

		try:
			subprocess.run(choptCall, check=True, shell=True)
		except Exception as e:
			print(f"CHOpt call failed with exception: {e}")
			return None

		return outPng

	def encoreSearch(self, query: dict):
		d = { 'number' : 1, 'page' : 1 }

		for i in query:
			d[i] = { 'value' : query[i], 'exact' : True, 'exclude' : False }

		print(f"Encore Sent Query is: {d}")
		resp = requests.post(self.encore['adv'], data = json.dumps(d), headers = {"Content-Type":"application/json"})

		print(resp.json())
		retData = []
		#d = resp.json()['data'][0]
		atts = ['name','artist','md5','charter','album','hasVideoBackground']
		for i, v in enumerate(resp.json()['data']):
			if i > 10:
				break

			s = {}
			d = resp.json()['data'][i]
			for j in atts:
				s[j] = d[j]

			retData.append(s)

		print(f"SEARCH RETDATA: {retData}")
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

	def sngDecode(self, sngUuid) -> bool:
		os.makedirs(f'{self.sngCliOutput}/{sngUuid}')
		inputSng = f'{self.sngCliInput}/{sngUuid}'
		outputSng = f'{self.sngCliOutput}'
		try:
			proc = subprocess.run(f'{self.sngCliPath} decode -in {inputSng} -out {outputSng} --noStatusBar', check=True, shell=True)
		except Exception as e:
			print(f"SngCli Decode Failed: {e}")
			return False

		return True