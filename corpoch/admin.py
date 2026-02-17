import json

from adminsortable2.admin import CustomInlineFormSet, SortableAdminBase, SortableStackedInline, SortableAdminMixin

from django.contrib import admin
from django.contrib.contenttypes.models import ContentType
from corpoch.models import Chart, Tournament, TournamentConfig, TournamentBracket, Qualifier, TournamentPlayer, GroupSeed, MatchRound
from corpoch.models import TournamentMatchCompleted, TournamentMatchOngoing, BracketGroup, QualifierSubmission, CH_MODIFIERS, MatchBan, GSheetAPI
from corpoch.providers import EncoreClient
import corpoch.dbot.tasks

@admin.register(GSheetAPI)
class GSheetAPIAdmin(admin.ModelAdmin):
	pass

@admin.register(Chart)
class ChartAdmin(admin.ModelAdmin):
	list_display = ('name',  '_bracket', 'charter', 'artist', 'album', 'speed', '_modifiers', 'tiebreaker')
	list_filter = ['brackets', 'charter', 'artist', 'tiebreaker']
	actions = ['run_encore_import']

	def _bracket(self,obj):
		retList = []
		for bracket in obj.brackets.iterator():
			retList.append(bracket)
		return retList

	def _modifiers(self, obj):
		return obj.modifiers

	def modifiers_long(self, obj):
		out = []
		for i in range(0, len(obj.modifiers)):
			out.append(CH_MODIFIERS[i][1])
		return out

	@admin.action(description="Run Encore import")
	def run_encore_import(modeladmin, request, queryset):
		encore = EncoreClient()
		for chart in queryset:
			search = encore.search(chart.encore_search_query)

			if len(search) == 0:
				print(f"Chart {chart.name} encore lookup with query {chart.encore_search_query} failed with {search}")
				continue
			if len(search) > 1:
				print(f"Chart {chart.name} returned multiple results")
				continue

			newChart = search[0]
			print(f"new chart: {newChart}")
			chart.url = encore.url(newChart)
			chart.name = newChart['name']
			chart.blake3 = newChart['md5'] #Encore's md5 uses blake3
			chart.md5 = encore.get_md5_from_chart(newChart)
			chart.album = newChart['album']
			chart.artist = newChart['artist']
			chart.charter = newChart['charter']
			chart.save()

@admin.register(Tournament)
class TournamentAdmin(admin.ModelAdmin):
	list_display = ('name', 'guild', 'active')

@admin.register(TournamentConfig)
class TournamentConfigAdmin(admin.ModelAdmin):
	list_display = ('tournament', 'ref_role', 'proof_channel', 'version')

@admin.register(TournamentBracket)
class TournamentBracketAdmin(admin.ModelAdmin):
	list_display = ("_name", 'tournament')
	list_filter = ['tournament']

	def _name(self, obj):
		return f"{obj}"

@admin.register(TournamentPlayer)
class TournamentPlayerAdmin(admin.ModelAdmin):
	list_display = ('user', 'tournament', 'ch_name', 'is_active')
	list_filter = ['tournament']

@admin.register(Qualifier)
class TournamentQualifierAdmin(admin.ModelAdmin):
	list_display = ('id', 'tournament')
	list_filter = ['tournament']

class SeedingInline(SortableStackedInline):
	model = GroupSeed
	extra = 1

@admin.register(BracketGroup)
class BracketGroupAdmin(SortableAdminBase, admin.ModelAdmin):
	list_display = ('name', 'tournament', 'bracket_name')#, 'group_players')
	inlines = [SeedingInline]
	list_per_page = 32
	actions = ['set_group_role']

	def tournament(self, obj):
		return obj.bracket.tournament.short_name

	def group_players(self, obj):
		return ", ".join([seed.player.ch_name for seed in obj.seeding.all()])

	def bracket_name(self, obj):
		return obj.bracket.name

	def formfield_for_foreignkey(self, db_field, request=None, **kwargs):
		 if db_field.name == "group_players":
				 kwargs["queryset"] = Tournament.players.objects.all()
		 return super(BracketGroupAdmin, self).formfield_for_foreignkey(db_field, request, **kwargs)

	@admin.action(description="Set group role for players")
	def set_group_role(modeladmin, request, queryset):
		for group in queryset:
			tourney = group.bracket.tournament
			role = group.role
			guild = tourney.guild
			for seed in group.seeding.all():
				ply = seed.player.user
				corpoch.dbot.tasks.set_group_role(ply, guild, role)

@admin.register(QualifierSubmission)
class QualifierSubmission(admin.ModelAdmin):
	list_display = ('id', 'qualifier', 'player_ch_name')
	list_filter = ["qualifier", "player"]
	def tournament(self, obj):
		return obj.qualifier.tournament.short_name

	def player_ch_name(self, obj):
		return obj.player.ch_name

	@admin.action(description="Mark Qualifiers GS Unsubmitted")
	def set_group_role(modeladmin, request, queryset):
		for quali in queryset:
			quali.submitted = False
			quali.save()

class RoundsOngoingInline(SortableStackedInline):
	model = MatchRound
	exclude = ['completed_match']
	extra = 1

class RoundsCompletedInline(SortableStackedInline):
	model = MatchRound
	exclude = ['ongoing_match']
	extra = 1

class BansOngoingInline(SortableStackedInline):
	model = MatchBan
	exclude = ['completed_match']
	extra = 1

class BansCompletedInline(SortableStackedInline):
	model = MatchBan
	exclude = ['ongoing_match']
	extra = 1

@admin.register(TournamentMatchCompleted)
class TournamentMatchCompletedAdmin(SortableAdminBase, admin.ModelAdmin):
	list_display = ('__str__', 'processed', 'bracket_name', 'group', '_match_players', 'started_on', 'version')
	inlines = [BansCompletedInline, RoundsCompletedInline]
	list_per_page = 16
	exclude = ['ongoing_match']

	def bracket_name(self, obj):
		return obj.group.bracket.name

	def _match_players(self, obj):
		retList = []
		for player in obj.match_players.iterator():
			retList.append(player.ch_name)
		return retList

	def version(self, obj):
		return obj.group.bracket.tournament.config.version

@admin.register(TournamentMatchOngoing)
class TournamentMatchOngoingAdmin(SortableAdminBase, admin.ModelAdmin):
	list_display = ('__str__', 'processed', '_bracket_name', 'group', '_match_players', '_match_bans', 'started_on', 'version')
	inlines = [BansOngoingInline, RoundsOngoingInline]
	list_per_page = 16
	exclude = ['completed_match']

	def _bracket_name(self, obj):
		return obj.group.bracket.name

	def _match_players(self, obj):
		retList = []
		for seed in obj.match_players.iterator():
			retList.append(seed.player.ch_name)
		return retList

	def _match_bans(self, obj):
		retList = []
		for ban in MatchBan.objects.all().iterator():
			retList.append(ban.chart)
		return retList

	def formfield_for_manytomany(self, db_field, request, **kwargs):#Limit options in admin to ONLY players/bans in a group?
		#if db_field.name == "bans":
		#	kwargs["queryset"] = TournamentBracket.setlist.objects.filter(brackets__in=request.group.bracket)
		#if db_field.name == "match_players":
		#	kwargs["queryset"] = self.group.seeding.objects.all()
		return super().formfield_for_foreignkey(db_field, request, **kwargs)
