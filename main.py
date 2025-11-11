import sys, os, discord, asyncio, time, json

dirname = os.path.dirname(sys.argv[0]) or '.'
sys.path.append(f"{dirname}/modules")

import tourneysql
import proofcalls
import mysqlhandler
import sqlschema

intents = discord.Intents.default()
intents.members = True
intents.message_content = True
client = discord.Bot(intents=intents, chunk_guilds_at_startup=False)

# cogs
cogList = [
	#'fun',
	'chcmds',
	#'tourneycmds',
	'qualifiercmds',
	'ownercmds'
]

for cog in cogList:
	client.load_extension(f'cogs.{cog}')
	print(f'Cog loaded: {cog}')

owners = []
configData = None
mysqlHandler = None
proofCalls = None

def loadConfig():
	global configData
	try:
		with open(f"{dirname}/config/bot.json", 'r') as json_config:
			configData = json.load(json_config)

		print('Config Loaded')
	except Exception as e:
		print(f"Failed to load config: {str(e)} - attempting env variables")
		sys.exit(1)

def startUpLogging():
	if configData.get('output_to_log'):
		os.makedirs(f"{dirname}/logs", exist_ok=True)
		sys.stdout = open(f"{dirname}/logs/discordbot.log", 'a+')
		sys.stdout.reconfigure(line_buffering = True)
		sys.stderr = open(f"{dirname}/logs/discordbot.err", 'a+')
		sys.stderr.reconfigure(line_buffering = True)

def startUpDB():
	global configData, mysqlHandler, client

	mysqlHandler = mysqlhandler.mysqlHandler(configData['mysql_host'], configData['mysql_user'], configData['mysql_pw'], configData['mysql_db'])

	# Get the secrets the F out!
	configData['mysql_host'] = None
	configData['mysql_user'] = None
	configData['mysql_pw'] = None
	configData['mysql_db'] = None

	client.loop.create_task(mysqlHandler.startUp())

async def retrieveOwners():
	global client, owners

	owners = []
	print("Retrieving bot owners...")
	app = await client.application_info()
	if app.team:
		for mem in app.team.members:
			owner = await client.fetch_user(mem.id)
			if not owner:
				print(f"  Can't get user object for team member {str(mem.name)}#{str(mem.discriminator)} id {mem.id}")
			else:
				owners.append(owner)
				print(f"  Loaded owner: {str(owner.name)} id {owner.id}")
	else:
		owners = [app.owner]
		print(f"  Loaded owner: {str(app.owner.name)} id {app.owner.id}")

@client.listen(once=True)
async def on_ready():
	global client, mysqlHandler, proofCalls

	print(f"Logged in as {client.user.name}#{client.user.discriminator} id {client.user.id}")

	await retrieveOwners()
	client.tourneyDB = tourneysql.TourneyDB(client, mysqlHandler)
	await mysqlHandler.wait_for_startup()
	await sqlschema.MysqlSchema(mysqlHandler).update()
	await client.tourneyDB.loadMatches()
	proofCalls = proofcalls.ProofCalls(client)
	await proofCalls.init()

	print('------Done with Startup------')

@client.event
async def on_message(msg):
	#Get rid of any potential bot messages
	if msg.author.bot or msg.type != discord.MessageType.default:
		return

	proofCalls = await client.tourneyDB.getActiveProofCalls()
	for call in proofCalls:
		tourney = await client.tourneyDB.getTourney(call['tourneyid'])
		ply1 = await client.tourneyDB.getPlayerByCHName(call['matchjson']['highSeed']['name'], tourney['id'])
		ply2 = await client.tourneyDB.getPlayerByCHName(call['matchjson']['lowSeed']['name'], tourney['id'])
		ply1 = await client.fetch_user(ply1['discordid'])
		ply2 = await client.fetch_user(ply2['discordid'])
		refRole = msg.guild.get_role(tourney['config']['ref_role'])
		if msg.channel.id == call['postid'] and (ply1.id == msg.author.id or ply2.id == msg.author.id or refRole in msg.author.roles):
			await msg.channel.send("You can repsond to this proof call!")
			break

loadConfig()
startUpLogging()
startUpDB()
print(f"--- Starting up at {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())} ---")
print('Logging into discord')

token = configData['token']
configData['token'] = ""

client.run(token)

print(f"--- Shutting down at {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())} ---")
