import sys, os

dirname = os.path.dirname(sys.argv[0]) or '.'

import discord, asyncio, time, json

client = discord.Bot(chunk_guilds_at_startup=False)
owners = []
doneStartup = False
configData = None

def loadConfig():
	global configData
	try:
		with open(f"{dirname}/config/bot.json", 'r') as json_config:
			configData = json.load(json_config)

		print('Config Loaded')
	except Exception as e:
		print(f"Failed to load config: {str(e)}")
		quit(1)

async def retrieveOwners():
	global client, owners

	owners = []
	print("Retrieving bot owners...")

	app = await client.application_info()  # Get owners from Discord team api
	if app.team:
		for mem in app.team.members:
			owner = await client.fetch_user(mem.id)
			if not owner:
				print(f"  Can't get user object for team member {str(mem.name)}#{str(mem.discriminator)} id {mem.id}")
			else:
				owners.append(owner)
	else:
		owners = [app.owner]

	for owner in owners:
		print(f"  Loaded owner: {str(owner.name)} id {owner.id}")

	return

@client.event
async def on_ready():
	global client, doneStartup

	if not doneStartup:
		print(f"Logged in as {client.user.name}#{client.user.discriminator} id {client.user.id}")
		await retrieveOwners()
	else:
		print("RECONNECT TO DISCORD")

	doneStartup = True

loadConfig()
print(f"--- Starting up at {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())} ---")
print('Logging into discord')

token = configData['token']
configData['token'] = ""

client.run(token)

print(f"--- Shutting down at {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())} ---")
