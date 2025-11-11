import mysqlhandler, json, aiomysql, discord
import discord
from cogs.tourneycmds import DiscordMatch, DiscordMatchView

from datetime import datetime
import pytz
import uuid
import re

class TourneyDB():
	def __init__(self, client, sqlBroker):
		self.client = client
		self.sqlBroker = sqlBroker

	##Generic Info Grabbers
	async def getServerConfig(self, serverid: int) -> dict:

		async with self.sqlBroker.context() as sql:
			row = await sql.query_first("SELECT config FROM servers WHERE (serverid = %s)", (serverid,))
			retData = json.loads(row['config'])

		return retData

	async def getActiveTournies(self, serverid: int) -> dict:
		ct = datetime.now(pytz.timezone('UTC'))

		#Is assuming only one active tourney for now
		async with self.sqlBroker.context() as sql:
			row = await sql.query_first("SELECT id, config, qualifier_config, brackets FROM tournies WHERE (serverid = %s) AND (active = TRUE)", (serverid,))

		qualiConf = json.loads(row['qualifier_config'])
		qualiConf['qualifiers'][0]['rules'] = qualiConf['qualifiers'][0]['rules'].replace("$", "\n")
		conf = json.loads(row['config'])
		conf['rules'] = conf['rules'].replace("$", '\n')
		brackets = json.loads(row['brackets']) if row['brackets'] != None else None
		return { 'id' : row['id'], 'config' : conf, 'qualifier_config' : qualiConf, 'brackets' : brackets }

	async def getTourneyBrackets(self, tid: int) -> dict:
		async with self.sqlBroker.context() as sql:
			row = await sql.query_first("SELECT brackets FROM tournies WHERE (id = %s)", (tid, ))

		return json.loads(row['brackets'])

	async def setTourneyBrackets(self, tid: int, brackets: dict):
		tourney = await self.getTourney(tid)
		bracketJson = json.dumps(brackets)

		async with self.sqlBroker.context() as sql:
			await sql.query("REPLACE INTO tournies (id, serverid, active, config, qualifier_config, brackets) VALUES (%s, %s, %s, %s, %s, %s)", (tid, tourney['serverid'], tourney['active'], json.dumps(tourney['config']), json.dumps(tourney['qualifier_config']), bracketJson, ))

	async def getTourneyConfig(self, tid: int) -> dict:
		async with self.sqlBroker.context() as sql:
			row = await sql.query_first("SELECT config FROM tournies WHERE (id = %s)", (tid, ))

		return json.loads(row['config'])

	async def getTourney(self, tid: int):
		async with self.sqlBroker.context() as sql:
			row = await sql.query_first("SELECT * from tournies WHERE (id = %s)", (tid, ))

		qualiConf = json.loads(row['qualifier_config'])
		qualiConf['qualifiers'][0]['rules'] = qualiConf['qualifiers'][0]['rules'].replace("\n", "$")
		conf = json.loads(row['config'])
		conf['rules'] = conf['rules'].replace("\n", '$')
		bracketConf = json.loads(row['brackets']) if row['brackets'] != None else None
		return { 'id' : row['id'], 'serverid' : row['serverid'], 'config' : conf, 'active' : bool(row['active']), 'qualifier_config' : qualiConf, 'brackets' : bracketConf }

	async def setTourneyConfig(self, tid: int, data: dict):
		tourney = await self.getTourney(tid)
		data['rules'] = data['rules'].replace("\n", "$")
		configJson = json.dumps(data)

		async with self.sqlBroker.context() as sql:
			await sql.query("REPLACE INTO tournies (id, serverid, active, config, qualifier_config, brackets) VALUES (%s, %s, %s, %s, %s, %s)", (tid, tourney['serverid'], tourney['active'], configJson, json.dumps(tourney['qualifier_config']), json.dumps(tourney['brackets']), ))

	async def setTourneyQualifiers(self, tid: int, qualifiers: dict):
		tourney = await self.getTourney(tid)
		qualifierJson = json.dumps(qualifiers)

		async with self.sqlBroker.context() as sql:
			await sql.query("REPLACE INTO tournies (id, serverid, active, config, qualifier_config, brackets) VALUES (%s, %s, %s, %s, %s, %s)", (tid, tourney['serverid'], tourney['active'], json.dumps(tourney['config']), qualifierJson, json.dumps(tourney['brackets']), ))

	async def getActiveQualifiers(self, serverid: int) -> dict:
		ct = datetime.now(pytz.timezone('UTC'))
		tourney = await self.getActiveTournies(serverid)
		qualifiers = tourney['qualifier_config']
		retData = []

		for i in qualifiers['qualifiers']:
			i['end'] = datetime.strptime(i['end'], '%Y-%m-%d %H:%M:%S.%f%z')
			if ct < i['end']:
				retData.append(i)

		return retData

	async def getPlayerQualifier(self, plyId: int, tourneyId: int) -> dict:
		#Assuming that there can only be ONE qualifier for a tourney for now
		async with self.sqlBroker.context() as sql:
			row = await sql.query_first("SELECT * FROM qualifiers WHERE (discordid = %s) AND (tourneyid = %s)", (plyId, tourneyId))

		if row is not None:
			row['stegjson'] = json.loads(row['stegjson'])

		return row

	async def getPlayerByCHName(self, chName: str, tourneyId: int) -> dict:
		async with self.sqlBroker.context() as sql:
			row = await sql.query_first("SELECT * FROM players WHERE (chname = %s) AND (tourneyid = %s)", (chName, tourneyId))

		if row is not None:
			row['config'] = json.loads(row['config']) if row['config'] != None else None

		return row

	async def getTourneyQualifierSubmissions(self, tourneyId: int) -> list:
		async with self.sqlBroker.context() as sql:
			submissions = await sql.query("SELECT * FROM qualifiers WHERE (tourneyid = {%s})", (tourneyId, ))

		for i, row in submissions:
			if row is not None:
				row['stegjson'] = json.loads(row['stegjson'])

		return submissions

	async def saveQualifier(self, plyId: int, tourneyId: int, stegDict: dict) -> bool:
		quuid = uuid.uuid1()
		stegDict['charter_name'] = re.sub(r"(?:<[^>]*>)", "", stegDict['charter_name'])
		storeJson = json.dumps(stegDict)

		try:
			async with self.sqlBroker.context() as sql:
				await sql.query('INSERT INTO qualifiers (qualiuuid, discordid, tourneyid, stegjson) VALUES (%s, %s, %s, %s)', (quuid, plyId, tourneyId, storeJson, ))
				await sql.query('INSERT INTO players (discordid, chname, tourneyid, qualifierid) VALUES (%s, %s, %s, %s)', (plyId, stegDict['players'][0]['profile_name'], tourneyId, quuid, ))

			return True
		except Exception as e:
			print(f"Error saving player data: {e}")
			return False

	async def getRefToolMatch(self, matchuuid: str) -> dict:
		async with self.sqlBroker.context() as sql:
			row = await sql.query_first("SELECT * FROM reftool_matches WHERE (matchuuid = %s)", (matchuuid, ))

		row['matchjson'] = json.loads(row['matchjson']) if row['matchjson'] != None else None
		row['received_screens'] = json.loads(row['received_screens']) if row['received_screens'] != None else None
		return row

	async def saveCompleteMatch(self, matchuuid: str, tid: int, ply1: str, ply2: str, matchJson: dict):
		storeJson = json.dumps(matchJson)

		async with self.sqlBroker.context() as sql:
			await sql.query("INSERT INTO completed_matches (matchuuid, tourneyid, ply1, ply2, matchjson) VALUES (%s, %s, %s, %s, %s)", (matchuuid, tid, ply1, ply2, storeJson, ))
			await sql.query("DELETE FROM reftool_matches WHERE matchuuid = %s", (matchuuid, ))

	async def replaceRefToolMatch(self, matchuuid: str, tid: int, finished: bool, refToolJson: dict, postid=None):
		match = json.dumps(refToolJson)

		async with self.sqlBroker.context() as sql:
			await sql.query("REPLACE INTO reftool_matches (matchuuid, tourneyid, finished, postid, matchjson) VALUES (%s, %s, %s, %s, %s)", (matchuuid, tid, finished, postid, match, ))

	async def getActiveProofCalls(self) -> dict:
		async with self.sqlBroker.context() as sql:
			matches = await sql.query("SELECT * FROM reftool_matches")

		for row in matches:
			if row is not None:
				row['matchjson'] = json.loads(row['matchjson']) if row['matchjson'] != None else None

		return matches

	async def getProofCall(self, matchUuid: str) -> dict:
		async with self.sqlBroker.context() as sql:
			row = await sql.query_first("SELECT * FROM reftool_matches WHERE (matchuuid = %s)", (matchuuid, ))

		row['matchjson'] = json.loads(row['matchjson'])
		row['received_screens'] = json.loads(row['received_screens'])

		return row

	async def setProofCall(self, matchUuid: str, tid: int, finished: bool, msg: discord.Message, matchJson: dict, screens: dict):
		mjson = json.dumps(matchJson)
		rscreens = json.dumps(screens)

		async with self.sqlBroker.context() as sql:
			await sql.query_first("REPLACE INTO reftool_matches (matchuuid, tourneyid, finished, postid, matchjson, received_screens) VALUES (%s, %s, %s, %s, %s %s)", (matchuuid, tid, finished, msg.id, mjson, rscreens, ))

	## Discord Match Ref Tool Helpers
	async def saveMatch(self, match):
		saveRnds = []
		for rnd in match.rounds:
			#need to replace discord objects in rounds with their ID to properly save
			saveRnds.append({'song' : rnd['song'], 'winner' : rnd['winner'].id })
		saveData = {
			'ref' : match.ref.id,
			'rounds' : saveRnds,
			'numRounds' : match.numRounds,
			'player1' : match.player1.id if match.player1 else None,
			'player2' : match.player2.id if match.player2 else None,
			'ban1' : match.ban1,
			'ban2' : match.ban2,
			'roundSng' : match.roundSngPlchldr,
			'roundWinner' : match.roundWinPlchldr.id if match.roundWinPlchldr else None
		}

		async with self.sqlBroker.context() as sql:
			if match.id > 0:
				row = await sql.query_first("SELECT * FROM match_views WHERE (matchid = %s)", (match.id,))
			else:
				row = await sql.query_first("SELECT * FROM match_views WHERE (messageid = %s)", (match.msg.id, ))

			if row == None:
				await sql.query("INSERT INTO match_views (channelid, messageid, matchjson) VALUES (%s, %s, %s)", (match.channel.id, match.msg.id, json.dumps(saveData),))
				row = await sql.query_first("SELECT * FROM match_views WHERE (messageid = %s)", (match.msg.id, ))
				match.id = row['matchid']
			else:
				#Interactions don't *always* change the messageid, but is needed when it does update
				if hasattr(match.msg, 'id'):
					await sql.query("UPDATE match_views SET matchjson = %s, messageid = %s WHERE (matchid = %s)", (json.dumps(saveData), match.msg.id, match.id, ))						
				else:
					await sql.query("UPDATE match_views SET matchjson = %s WHERE (matchid = %s)", (json.dumps(saveData), match.id, ))					

	async def loadMatches(self):
		cur = await self.sqlBroker.connect(aiomysql.DictCursor)
		await cur.execute("SELECT * FROM match_views")
		rows = await cur.fetchall()

		for row in rows:
			print(f"Loading match view {row['channelid']} {row['messageid']}")
			channel = self.client.get_channel(row['channelid'])
			try:
				msg = await channel.fetch_message(row['messageid'])
			except discord.errors.NotFound as e:
				print(f"Match {row['messageid']} not found, deleting")
				await cur.execute("DELETE FROM match_views WHERE (matchid = %s)", (row['matchid'],))
				continue

			theMatch = DiscordMatch(msg, self)
			theData = json.loads(row['matchjson'])
			await self.client.get_guild(channel.guild.id).chunk()
			if theData['player1']:
				theMatch.player1 = self.client.get_user(theData['player1'])
			if theData['player2']:
				theMatch.player2 = self.client.get_user(theData['player2'])
			if theData['player1'] and theData['player2']:
				theMatch.playersPicked = True

			if theData['ban1']:
				theMatch.ban1 = theData['ban1']
			if theData['ban2']:
				theMatch.ban2 = theData['ban2']
			if theData['ban1'] and theData['ban2']:
				theMatch.bansPicked = True

			theRounds = []
			for rnd in theData['rounds']:
				theWinner = self.client.get_user(rnd['winner'])
				theRounds.append({'song' : rnd['song'], 'winner' : theWinner})

			theMatch.id = row['matchid']
			theMatch.ref = self.client.get_user(theData['ref'])
			theMatch.rounds = theRounds
			theMatch.roundSngPlchldr = theData['roundSng']
			theMatch.numRounds = theData['numRounds']
			theMatch.roundWinPlchldr = self.client.get_user(theData['roundWinner'])

			await theMatch.showTool(msg)

		await self.sqlBroker.commit(cur)

	async def cancelMatch(self, match):
		async with self.sqlBroker.context() as sql:
			await sql.query("DELETE FROM match_views WHERE (matchid = %s)", (match.id,))

	async def finishMatch(self, match):
		async with self.sqlBroker.context() as sql:
			#Save all match
			await sql.query("DELETE FROM match_views WHERE (matchid = %s)", (match.id,))
