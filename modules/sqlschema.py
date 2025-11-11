import asyncio

class MysqlSchema():
	def __init__(self, mysqlhandler):
		self.sqlBroker = mysqlhandler

	async def update(self):
		print("Checking DB schema...")

		cur = await self.sqlBroker.connect()

		# Convert any latin1 tables to UTF-8
		try:
			await cur.execute("SELECT TABLE_NAME, TABLE_COLLATION FROM INFORMATION_SCHEMA.TABLES WHERE (TABLE_COLLATION LIKE 'latin1%%') AND (TABLE_SCHEMA = %s)", self.sqlBroker.getDatabaseName())
			rows = await cur.fetchall()
			for r in rows:
				print(f"[MysqlSchema] Converting DB table '{r[0]}' to UTF-8...")
				await cur.execute(f"ALTER TABLE {self.sqlBroker.escapeTableName(r[0])} CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci")
		except Exception as e:
			print(f"  Something went wrong during conversion: {e}")
		finally:
			await self.sqlBroker.c_commit(cur)

		if not await self.sqlBroker.hasTable(cur, 'servers'):
			print("[MysqlSchema] Creating table 'servers'...")
			await cur.execute(
			"""
			CREATE TABLE `servers` (
			serverid BIGINT UNSIGNED NOT NULL PRIMARY KEY,
			tournies TEXT,
			config TEXT,
			INDEX (serverid)
			) ENGINE=InnoDB
			"""
			)
			await self.sqlBroker.c_commit(cur)

		if not await self.sqlBroker.hasTable(cur, 'tournies'):
			print("[MysqlSchema] Creating table 'tournies'...")
			await cur.execute(
			"""
			CREATE TABLE `tournies` (
			id INT PRIMARY KEY AUTO_INCREMENT NOT NULL,
			serverid BIGINT UNSIGNED NOT NULL,
			active BOOL NOT NULL, #Is tournament active/running
			config TEXT, #JSON
			qualifier_config TEXT,
			brackets TEXT, #JSON - includes setlists w/ bracket names
			INDEX (serverid, id)
			) ENGINE=InnoDB
			"""
			)
			await self.sqlBroker.c_commit(cur)

		if not await self.sqlBroker.hasTable(cur, 'players'):
			print("[MysqlSchema] Creating table 'players'...")
			await cur.execute(
			"""
			CREATE TABLE `players` (
			id INT PRIMARY KEY AUTO_INCREMENT NOT NULL,
			discordid BIGINT UNSIGNED NOT NULL,
			isactive BOOL NOT NULL DEFAULT FALSE, #Is active in tourney
			chname TEXT NOT NULL, #Raw text for CH name
			tourneyid INT NOT NULL,
			config TEXT, #JSON - config options for specific players in specific tournies
			qualifierid VARCHAR(40) NOT NULL, #Qualifier submissions for a specific tourney
			INDEX (id, discordid)
			) ENGINE=InnoDB
			"""
			)
			await self.sqlBroker.c_commit(cur)

		if not await self.sqlBroker.hasTable(cur, 'qualifiers'):
			print("[MysqlSchema] Creating table 'qualifiers'...")
			await cur.execute(
			"""
			CREATE TABLE `qualifiers` (
			id INT PRIMARY KEY AUTO_INCREMENT NOT NULL,
			qualiuuid VARCHAR(40) NOT NULL,
			discordid BIGINT UNSIGNED NOT NULL,
			tourneyid INT NOT NULL,
			stegjson TEXT, #JSON - steg output plus overstrums if detected
			INDEX (discordid, id)
			) ENGINE=InnoDB
			"""
			)
			await self.sqlBroker.c_commit(cur)

		if not await self.sqlBroker.hasTable(cur, 'matches'):
			print("[MysqlSchema] Creating table 'matches'...")
			await cur.execute(
			"""
			CREATE TABLE `matches` (
			muuid VARCHAR(40) NOT NULL PRIMARY KEY,
			player1id INT NOT NULL,
			player2id INT NOT NULL,
			serverid BIGINT UNSIGNED NOT NULL,
			tourneyid INT NOT NULL,
			matchjson TEXT, #JSON - steg output plus overstrums if detected
			INDEX (muuid, player1id, player2id, serverid)
			) ENGINE=InnoDB
			"""
			)
			await self.sqlBroker.c_commit(cur)

		if not await self.sqlBroker.hasTable(cur, 'match_views'):
			print("[MysqlSchema] Creating table 'match_views'...")
			await cur.execute(
			"""	
			CREATE TABLE match_views (
			matchid INT AUTO_INCREMENT NOT NULL,
			channelid BIGINT UNSIGNED NOT NULL,
			messageid BIGINT UNSIGNED NOT NULL,
			matchjson TEXT NULL,
			PRIMARY KEY (matchid)
			) ENGINE=INNODB;
			"""
			)
			await self.sqlBroker.c_commit(cur)

		if not await self.sqlBroker.hasTable(cur, 'reftool_matches'):
			print("[MysqlSchema] Creating table 'reftool_matches'...")
			await cur.execute(
			"""	
			CREATE TABLE reftool_matches (
			matchuuid VARCHAR(40) NOT NULL,
			tourneyid INT NOT NULL,
			finished BOOL NOT NULL DEFAULT FALSE,
			postid BIGINT UNSIGNED,
			matchjson TEXT NULL,
			PRIMARY KEY (matchuuid)
			) ENGINE=INNODB;
			"""
			)
			await self.sqlBroker.c_commit(cur)

		if not await self.sqlBroker.hasTable(cur, 'completed_matches'):
			print("[MysqlSchema] Creating table 'completed_matches'...")
			await cur.execute(
			"""	
			CREATE TABLE completed_matches (
			matchuuid VARCHAR(40) NOT NULL,
			tourneyid INT NOT NULL,
			ply1 VARCHAR(40) NOT NULL,
			ply2 VARCHAR(40) NOT NULL,
			matchjson TEXT NULL,
			PRIMARY KEY (matchuuid)
			) ENGINE=INNODB;
			"""
			)
			await self.sqlBroker.c_commit(cur)

		await self.sqlBroker.close(cur)

		#if not await self.sqlBroker.hasTable(cur, 'exibmatches'):
		#	print("[MysqlSchema] Creating table 'exibmatches'...")
		#	await cur.execute(
		#	"""
		#	CREATE TABLE `exibmatches` (
		#	uuid VARCHAR(40) NOT NULL PRIMARY KEY,
		#	player1id BIGINT UNSIGNED NOT NULL,
		#	player2id BIGINT UNSIGNED NOT NULL,
		#	serverid BIGINT UNSIGNED NOT NULL,
		#	tourneyid INT NOT NULL,
		#	stegjson TEXT, #JSON - steg output plus overstrums if detected
		#	INDEX (id, player1id, player2id, serverid)
		#	) ENGINE=InnoDB
		#	"""
		#	)
		#	await self.sqlBroker.c_commit(cur)
