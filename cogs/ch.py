import discord, requests, os, sys, json, platform, uuid, subprocess, shutil
from discord.ext import commands
from discord.ui import *
from discord.enums import ComponentType, InputTextStyle
#from sng_parser import decode_sng
#import sng_parser

class EncoreSearch(Modal):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.searchQuery = None
        self.add_item(InputText(label="Song Name", style=discord.InputTextStyle.short, required=True))
        self.add_item(InputText(label="Artist", style=discord.InputTextStyle.short, required=False))
        self.add_item(InputText(label="Album", style=discord.InputTextStyle.short, required=False))
        self.add_item(InputText(label="Charter", style=discord.InputTextStyle.short, required=False))

    async def callback(self, interaction: discord.Interaction):
        retData = {}
        retData['name'] = self.children[0].value

        if self.children[1].value:
            retData['artist'] = self.children[1].value
        if self.children[2].value:
            retData['album'] = self.children[2].value
        if self.children[3].value:
            retData['charter'] = self.children[3].value

        self.searchQuery = retData
        self.stop()

class ch(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

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

    def CHOpt(self, sngUuid) -> str:
        inChart = f'{self.sngCliOutput}/{sngUuid}/notes.chart'
        outPng = f'./CHOpt/output/{sngUuid}.png'

        try:
            subprocess.run(f'{self.CHOptPath} -s 100 --ew 100 --sqz 100 -f {inChart} -i guitar -d expert -o {outPng}', check=True, shell=True)
        except Exception as e:
            print(f"CHOpt call failed with exception: {e}")
            return None

        return outPng

    def encoreSearch(self, query: dict):
        d = {'number':1,
                'page':1}

        for i in query:
            d[i] = {'value':query[i],'exact':False,'exclude':False}

        print(d)
        resp = requests.post(self.encore['adv']
            ,data=json.dumps(d)
            ,headers={"Content-Type":"application/json"})

        #print(resp.json())
        s={}
        d=resp.json()['data'][0]
        atts=['name','artist','md5','charter','album','hasVideoBackground']

        for i in atts:
            s[i]=d[i]
        return s

    def encoreDownload(self, url: str) -> str:
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

    ch = discord.SlashCommandGroup('ch','CloneHero tools')
    @ch.command(name='path',description='Generate a path for a given chart on Chorus')
    async def path(self, ctx):
        searchModal = EncoreSearch(title="Encore search for chart")
        await ctx.send_modal(modal=searchModal)
        await searchModal.wait()

        qList=[ 'name', 'artist', 'charter', 'album' ]
        query={}

        for i,a in locals().items():
            if (i in qList and a != None):
                query[i] = a

        #print(query)
        s = self.encoreSearch(query)

        #await ctx.interaction.response.defer(invisible=True)
        #Form download url
        url = self.encore['dl'] + s['md5'] + ('_novideo','')[not s['hasVideoBackground']] + '.sng'
        sngUuid = self.encoreDownload(url)

        #Decode sng
        if not self.sngDecode(sngUuid):
            await ctx.respond('Path generation died on sng file decode. SNG UUID: {sngUuid}')
            return

        #Generate path
        outPng = self.CHOpt(sngUuid)
        if not outPng:
            await ctx.respond("Path generation died on CHOpt call.")
            return

        # return path image
        fp = discord.File(outPng)
        await ctx.send(content="CHOpt Path for {}", file=fp)

        # clean up
        shutil.rmtree(f'{self.sngCliInput}/{sngUuid}')
        shutil.rmtree(f'{self.sngCliOutput}/{sngUuid}')
	os.remove(outPng)

#https://www.enchor.us/download?md5=d92a3e7e40e733831ebc9f9606dc5a14&isSng=false&downloadNovideoVersion=false&filename=Insomnium%2520-%2520Heart%2520Like%2520a%2520Grave%2520%28K4JK0%29
#https://files.enchor.us/${md5 + (downloadNovideoVersion ? '_novideo' : '')}.sng

def setup(bot):
    bot.add_cog(ch(bot))
