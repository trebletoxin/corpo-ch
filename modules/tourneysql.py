import mysqlhandler, json, aiomysql, discord
from cogs.tourneycmds import DiscordMatch, DiscordMatchView

#CREATE TABLE match_views ( matchid INT AUTO_INCREMENT NOT NULL, channelid BIGINT UNSIGNED NOT NULL, messageid BIGINT UNSIGNED NOT NULL, matchjson TEXT NULL, PRIMARY KEY (matchid) ) ENGINE=INNODB;

class TourneyDB():
	def __init__(self, client, sqlBroker):
		self.client = client
		self.sqlBroker = sqlBroker

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