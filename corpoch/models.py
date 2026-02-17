import uuid, typing, json, pydantic
from corpoch import settings#corpoch.settings.py

from multiselectfield import MultiSelectField
from django.db import models
from django.contrib import admin
from django.core.validators import MaxValueValidator, MinValueValidator
from django.core.serializers.json import DjangoJSONEncoder
from encrypted_json_fields import fields
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.db import models

CH_MODIFIERS = (
	("NM", "NoModifiers"),
	("DN", "Double Notes"),
	("DS", "Dropless Sustains"),
	("AS", "All Strums"),
	("NS", "Note Shuffle"),
	("BM", "Brutal Mode")
)

CH_VERSIONS = [
	("v1.0.0.4080-final", "v1.0.0.4080-final"),
]

class GSheetAPI(models.Model):
	api_key = fields.EncryptedJSONField(null=False, blank=True, default=dict, encoder=DjangoJSONEncoder)
	sa_name = models.CharField(verbose_name="API Service Account Name", max_length=96)
	#ONLY ONE KEY SHOULD BE IN THIS TABLE

	class Meta:
		verbose_name = "Google Sheets API"

class Chart(models.Model):
	id = models.AutoField(primary_key=True)
	name = models.CharField(verbose_name="Chart Name", max_length=256, blank=True)
	artist = models.CharField(verbose_name="Artist", max_length=256, blank=True)
	album = models.CharField(verbose_name="Album", max_length=256, blank=True)
	charter = models.CharField(verbose_name="Charter", max_length=32, blank=True)
	tiebreaker = models.BooleanField(verbose_name="Tiebreaker", default=False)
	modifiers = MultiSelectField("Modifiers", choices=CH_MODIFIERS, default=['NM'])
	speed = models.PositiveIntegerField(verbose_name="Speed", validators=[MinValueValidator(5), MaxValueValidator(1000)], default=100)
	category = models.CharField(verbose_name="Chart Category", max_length=16, default="Hybrid")#This needs to be choices
	brackets = models.ManyToManyField("TournamentBracket", related_name="setlist", verbose_name="Bracket Setlist", blank=True)
	md5 = models.CharField(verbose_name="MD5 Hash", max_length=32, blank=True)
	blake3 = models.CharField(verbose_name="Blake3 Hash", max_length=32, blank=True)
	url = models.URLField(verbose_name="Chart URL", blank=True)

	class Meta:
		verbose_name = "Chart"
		verbose_name_plural = "Charts"

	@property
	def long_name(self):
		return f"{self.name} - {self.charter} - {self.artist} - {self.album}"

	@property
	def encore_search_query(self):
		return { 'name' : self.name, 'charter' : self.charter, 'artist' : self.artist, 'album' : self.album, 'blake3' : self.blake3 }

	@property
	def modifiers_short(self):
		outStr = ""
		if self.modifiers[0][1] != "NoModifiers":
			return outStr
		else:
			for mod in self.modifiers:
				outStr += f" ,{mod[0]}"
	@property
	def tournament_name(self):
		retStr = f"{self.name}"
		if self.name.speed != 100:
			retStr += f" ({speed}%) "
		if self.modifiers.short != ['NM']:
			retStr += self.modifiers_short
		return retStr

	def __str__(self):
		return self.name

	def save(self, force_insert=False, force_update=False, using=None, update_fields=None):
		self.blake3 = self.blake3.upper() #Force these always upper 
		self.md5 = self.md5.upper() #Steg is output as always upper
		super().save()

class Tournament(models.Model):
	id = models.AutoField(primary_key=True)
	guild = models.BigIntegerField(verbose_name="Discord Server ID", db_index=True)
	name = models.CharField(verbose_name="Name", max_length=128, default="New Tournament")
	short_name = models.CharField(verbose_name="Short Name", max_length=16, default="NT1")
	active = models.BooleanField(verbose_name="In-Progress", default=False)

	class Meta:
		verbose_name = "Tournament"
		verbose_name_plural = "Tournaments"

	def __str__(self):
		return self.name

	def active_players(self):
		return self.players.filter(active=True)

	def save(self, force_insert=False, force_update=False, using=None, update_fields=None):
		is_new = self.pk is None
		super().save()
		TournamentConfig.objects.create(tournament=self) if is_new else None

class TournamentConfig(models.Model):
	tournament = models.OneToOneField(Tournament, related_name="config", verbose_name="Tournament Configuration", on_delete=models.CASCADE)
	rules = models.TextField(verbose_name="Rules", max_length=1024, default="Some rules go here")
	ref_role = models.BigIntegerField(verbose_name="Discord Ref Role ID", null=True, blank=True)
	proof_channel = models.BigIntegerField(verbose_name="Discord Proof Channel ID", null=True, blank=True)
	enable_gsheets = models.BooleanField(verbose_name="Gsheets Integration", default=True)
	gsheet = models.URLField(verbose_name="Match Reporting Google Sheet", null=True, blank=True)
	version = models.CharField(verbose_name="Clone Hero Version", choices=CH_VERSIONS, max_length=32, default=['v1.0.0.4080-final'])

	class Meta:
		verbose_name = "Config"
		verbose_name_plural = "Configurations"

	def __str__(self):
		return f"{self.tournament.name} - Configuration"

class TournamentBracket(models.Model):
	id = models.AutoField(primary_key=True)
	tournament = models.ForeignKey(Tournament, related_name="brackets", on_delete=models.CASCADE, verbose_name="Tournament")
	num_players = models.PositiveIntegerField(verbose_name="Players", validators=[MinValueValidator(2), MaxValueValidator(4)], default=2)
	num_rounds = models.PositiveIntegerField(verbose_name="Best Of", validators=[MinValueValidator(3), MaxValueValidator(25)], default=7)
	num_bans = models.IntegerField(verbose_name="Num Bans", default=1)
	allow_defer = models.BooleanField(verbose_name="Allow Ban Deferral", default=True)
	defer_swap = models.BooleanField(verbose_name="Using Defer Alters First Pick", default=False)
	last_loser_picks = models.BooleanField(verbose_name="Loser Last Round Picks", default=True)
	tiebeaker_csc = models.BooleanField(verbose_name="Tibeaker CSC Rules", default=False)
	score_log = models.BigIntegerField(verbose_name="Score Log Channel Discord ID", default=-1)
	name = models.CharField(verbose_name="Bracket Name", max_length=128, default=f"New Bracket")

	class Meta:
		verbose_name = "Bracket"
		verbose_name_plural = "Brackets"
	
	def __str__(self):
		return f"{self.tournament.short_name} - {self.name}"

	@property
	def total_bans(self) -> int:
		return self.num_bans * self.num_players

	@property
	def short_name(self):
		return self.name

class TournamentPlayer(models.Model):
	id = models.AutoField(primary_key=True)
	user = models.BigIntegerField(verbose_name="Player Discord ID", db_index=True)
	name = models.CharField(verbose_name="Discord Name", max_length=128, null=True, blank=True)
	tournament = models.ForeignKey(Tournament, related_name="players", verbose_name="Tournament", on_delete=models.CASCADE)
	is_active = models.BooleanField(verbose_name="Player Active", default=False)
	ch_name = models.CharField(verbose_name="Clone Hero Name", max_length=128, default="New Player")
	config = models.JSONField(verbose_name="Player Configuration", default=dict, blank=True)

	class Meta:
		verbose_name = "Player"
		verbose_name_plural = "Players"

	def __str__(self):
		return self.ch_name

	#This needs to be checked - probably not used/not right
	@property
	def brackets(self):
		return self.tournament.brackets.objects.select_related('player').filter(players__id=self.id)

	def check_ch_name(self, testname):
		return True if testname.replace(" ", "") in self.ch_name.replace(" ", "") else False

class Qualifier(models.Model):
	id = models.AutoField(primary_key=True)
	#Use either tournament or bracket+tourney - allows for multiple "main" brackets to have a single qualifier or a qualifier per bracket
	tournament = models.ForeignKey(Tournament, related_name='qualifier', verbose_name="Tournament", on_delete=models.CASCADE)
	bracket = models.ForeignKey(TournamentBracket, related_name='qualifier', verbose_name="Bracket", blank=True, null=True, on_delete=models.CASCADE)
	charts = models.ManyToManyField(Chart, related_name="charts", verbose_name="Qualifier Chart(s)")
	limit_submissions = models.BooleanField(verbose_name="Limit Submissions to # Required", default=False)
	required_submissions = models.PositiveIntegerField(verbose_name="Required Submissions", default=1)
	form_link = models.URLField(verbose_name="Google Form Link", null=True, blank=True)
	end_time = models.DateTimeField(verbose_name="End Time", default=timezone.now)
	rules = models.TextField(verbose_name="Rules", max_length=1024, default="Placeholder rules")
	channel = models.BigIntegerField(verbose_name="Submission Discord Channel ID", db_index=True, blank=True, null=True)
	gsheet = models.URLField(verbose_name="Submissions Google Sheet", null=True, blank=True)

	class Meta:
		verbose_name = "Qualifier"
		verbose_name_plural = "Qualifiers"

	def __str__(self):
		if self.bracket:
			return f"{self.bracket.tournament.short_name} - {self.bracket.name}"
		else:
			return f"{self.tournament.short_name}"

class BracketGroup(models.Model):
	id = models.AutoField(primary_key=True, db_index=True)
	bracket = models.ForeignKey(TournamentBracket, related_name="groups", verbose_name="Bracket Groups", on_delete=models.CASCADE)
	name = models.CharField(verbose_name="Group Name", max_length=8, default="A")
	role = models.BigIntegerField(verbose_name="Discord Group Role ID", null=True, blank=True, db_index=True)

	class Meta:
		verbose_name = "Bracket Group"
		verbose_name_plural = "Bracket Groups"

	@property
	def tournament(self) -> Tournament:
		return self.bracket.tournament

	@property
	def active_players(self) -> list:
		return self.players.objects.filter(is_active=True)

	def __str__(self):
		return f"{self.tournament.short_name} - {self.bracket.name} - {self.name}"

class GroupSeed(models.Model):
	seed = models.PositiveIntegerField(blank=False, null=False)
	group = models.ForeignKey(BracketGroup, related_name="seeding", verbose_name="Group Seeding", null=True, on_delete=models.CASCADE)
	player = models.ForeignKey(TournamentPlayer, related_name="group_seeding", verbose_name="Group Seed", null=True, on_delete=models.SET_NULL)

	class Meta:
		verbose_name = "Seed Placement"
		verbose_name_plural = "Seed Placements"
		ordering = ['seed']

	def __str__(self):
		return f"{self.player.ch_name} ({self.seed})"

	@property
	def seed_num(self):
		return str(self.seed)

	@property
	def player_ch_name(self):
		return self.player.ch_name 

	@property
	def full_name(self):
		return f"{self.group.tournament.short_name} - {self.group.bracket.name} - Group {self.group.name} - Seed {self.seed}"

	def check_ch_name(self, testname):
		return True if testname in self.player.ch_name else False ## do more checks for formatting, testing now

class TournamentMatch(models.Model):#This class is assumed to be an "official" match - new class for exhibition/non-"tracked" matches
	id = models.CharField(primary_key=True, verbose_name="Match ID", max_length=40, default=uuid.uuid1)
	processed = models.BooleanField(verbose_name="Match Processed", default=False)
	group = models.ForeignKey(BracketGroup, related_name='%(class)s_matches', verbose_name="Group", on_delete=models.CASCADE)#limit_options_to groups in bracket somehow?
	match_players = models.ManyToManyField(GroupSeed, related_name="%(class)s_players", verbose_name="Players", blank=True)
	started_on = models.DateTimeField(verbose_name="Match Start Time", auto_now_add=True)

	class Meta:
		ordering = ['-started_on']
		abstract = True

	@property
	def high_seed(self):
		return self.match_players[0]

	@property
	def low_seed(self):
		return self.match_players[1]

	@property
	def tournament(self):
		return self.group.bracket.tournament

	@property
	def bracket(self):
		return self.group.bracket

	@property
	def version(self):
		self.group.bracket.tournament.config.version

	@property
	def full_name(self):
		outStr = f"{self.tournament.short_name} - {self.bracket.name}"
		for i, ply in enumerate(self.match_players.iterator()):
			if i == 0:
				outStr += f" - {ply.ch_name}({self.group.seeding.get(player=ply)})"
			elif i == 1:
				outStr += f" vs {ply.ch_name}({self.group.seeding.get(player=ply)})" 
		return outStr

	def __str__(self):
		outStr = ""
		for i, seed in enumerate(self.match_players.iterator()):
			if i == 0:
				outStr += f"{seed.player.ch_name}({seed.seed})"
			elif i == 1:
				outStr += f" vs {seed.player.ch_name}({seed.seed})" 
		return outStr	

class TournamentMatchCompleted(TournamentMatch):
	ended_on = models.DateTimeField(verbose_name="Match end time", auto_now_add=True)
	winner = models.ForeignKey(TournamentPlayer, related_name="matches_won", verbose_name="Winner", on_delete=models.CASCADE)
	loser = models.ForeignKey(TournamentPlayer, related_name="matches_lost", verbose_name="Loser", on_delete=models.CASCADE)
	submitted = models.BooleanField(verbose_name="Uploaded to GSheet", default=False)

	class Meta:
		verbose_name = "Completed Match"
		verbose_name_plural = "Matches Completed"

	def __str__(self):
		ply1 = self.match_players[0]
		ply2 = self.match_players[1]
		return f"{self.tournament.short_name} - {self.group.bracket.name} - Group {self.group.name} - {ply1.ch_name} vs {ply2.ch_name} "

class TournamentMatchOngoing(TournamentMatch): 
	finished = models.BooleanField(verbose_name="Finished", default=False) #Flag to match in-progress as complete, start triggers to move to completed
	channel = models.BigIntegerField(verbose_name="Ref-Tool Discord Channel ID", null=True, blank=True)
	message = models.BigIntegerField(verbose_name="Ref-Tool Discord Message ID", null=True, blank=True)
	ref = models.BigIntegerField(verbose_name="Discord Ref ID", null=True, blank=True)

	class Meta:
		verbose_name = "Ongoing Match"
		verbose_name_plural = "Ongoing Matches"

	def complete_match(self):
		pass
		#tmpRnds = 
		#compMatch = TournamentMatchCompleted(id=self.id, winner=winner, loser=loser, bracket=self.bracket, player1=self.player1, player1_ban=self.player1_ban, player2=self.player2, player2_ban=self.player2_ban, match_data=self.match_data)

	def __str__(self):
		outStr = f"{self.tournament.short_name} - {self.group.bracket.name} - Group {self.group.name}"
		if len(self.match_players) > 2:#Not going to work 3+ players
			outStr += f" - {self.match_players[0].ch_name} ({self.match_players[0].seed}) vs {self.match_players[1].ch_name} ({self.match_players[0].seed})"
		return 

class MatchRound(models.Model):
	num = models.PositiveIntegerField(blank=False, null=False)
	ongoing_match = models.ForeignKey(TournamentMatchOngoing, related_name="ongoing_rounds", verbose_name="Ongoing Match ID", on_delete=models.CASCADE, null=True, blank=True)
	completed_match = models.ForeignKey(TournamentMatchCompleted, related_name="completeds_rounds", verbose_name="Completed Match ID", on_delete=models.CASCADE, null=True, blank=True)
	picked = models.ForeignKey(TournamentPlayer, related_name="picks", verbose_name="Picked", on_delete=models.CASCADE)
	chart = models.ForeignKey(Chart, related_name="rounds_played", verbose_name="Chart Played", null=True, blank=True, on_delete=models.SET_NULL)
	winner = models.ForeignKey(TournamentPlayer, related_name="rounds_won", verbose_name="Winner", null=True, on_delete=models.SET_NULL)
	loser = models.ForeignKey(TournamentPlayer, related_name="rounds_lost", verbose_name="Loser", null=True, on_delete=models.SET_NULL)
	steg = models.JSONField(verbose_name="Steg Data", null=True, blank=True) #This is the players list in the steg data
	screenshot = models.ImageField(upload_to="rounds/", verbose_name="Screenshot", null=True)

	class Meta:
		verbose_name = "Group Match Round"
		verbose_name_plural = "Group Match Rounds"
		ordering=['num']

	def __str__(self):
		outStr = ""
		if self.picked:
			outStr += f"{self.picked} picks"
		if self.chart:
			outStr += f" {self.chart.name}"
		if self.winner:
			outStr += f" - {self.winner.ch_name} wins"
		return outStr

#Potential class for a "Series" of tournaments - just needs to be a list of tournaments for ogranization
#class TournamentSeries(models.Model):
#	id = models.PositiveIntegerField(blank=False, null=False)

class MatchBan(models.Model):
	num = models.PositiveIntegerField(blank=False, null=False)
	chart = models.ForeignKey(Chart, related_name="bans", verbose_name="Chart Banned", null=True, blank=True, on_delete=models.SET_NULL)
	player = models.ForeignKey(GroupSeed, related_name="player_bans", verbose_name="Player", null=True, blank=True, on_delete=models.SET_NULL)
	ongoing_match = models.ForeignKey(TournamentMatchOngoing, related_name="%(class)s_bans", verbose_name="Ongoing Match ID", on_delete=models.CASCADE, null=True, blank=True)
	completed_match = models.ForeignKey(TournamentMatchCompleted, related_name="%(class)s_bans", verbose_name="Completed Match ID", on_delete=models.CASCADE, null=True, blank=True)

	class Meta:
		verbose_name = "Match Ban"
		verbose_name_plural = "Match Bans"
		ordering = ['num']

	def __str__(self):
		return str(self.chart.name)

	@property
	def get_player_ch_name(self):
		return str(self.player.ch_name)

class QualifierSubmission(models.Model):
	id = models.CharField(primary_key=True, verbose_name="Qualifier ID", max_length=40, default=uuid.uuid1)
	player = models.ForeignKey(TournamentPlayer, related_name="qualifiers", verbose_name="Submittor", on_delete=models.CASCADE)
	submit_time = models.DateTimeField(verbose_name="Submission Time", auto_now_add=True)
	screenshot = models.ImageField(upload_to="qualifiers/", verbose_name="Screenshot", null=True)
	qualifier = models.ForeignKey(Qualifier, related_name='submissions', verbose_name="Tournament Qualifier", on_delete=models.CASCADE)
	steg = models.JSONField(verbose_name="Steg Data", default=dict, blank=True) #This is the steg output in it's entirety
	submitted = models.BooleanField(verbose_name="Uploaded to GSheet", default=False)

	class Meta:
		verbose_name = "Qualifier Submission"
		verbose_name_plural = "Qualifier Submissions"

	def __str__(self):
		return f"{self.player.ch_name} - {self.qualifier.tournament.name} {self.qualifier.bracket.name if self.qualifier.bracket else ''} Qualifier"
