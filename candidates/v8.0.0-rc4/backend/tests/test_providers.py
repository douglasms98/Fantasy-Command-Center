"""Explicit TEST_ONLY provider fixtures. No live-provider validation is implied."""
import asyncio
from copy import deepcopy
from app.providers import Providers, fractional_points, num
from app.calendar import normalize, Calendar

ROW={'id':'TEST_ONLY_LEAGUE','platform':'Sleeper','leagueId':'1001','teamId':'1','season':2026,'name':'TEST_ONLY','team':'TEST_ONLY_TEAM'}

def test_sleeper_preserves_zero_and_missing_projection_and_dynamic_history():
    provider=Providers()
    async def get(client,url,**kwargs):
        if url.endswith('/state/nfl'):return {'season':'2026','week':6}
        if url.endswith('/rosters'):return [{'roster_id':1,'owner_id':'TEST_ONLY_OWNER','players':['TEST_ONLY_PLAYER'],'starters':['TEST_ONLY_PLAYER'],'settings':{'wins':3,'losses':2,'fpts':0,'fpts_decimal':0}},{'roster_id':2,'owner_id':'TEST_ONLY_OTHER','players':[],'settings':{}}]
        if url.endswith('/users'):return [{'user_id':'TEST_ONLY_OWNER','display_name':'TEST_ONLY_TEAM'}]
        if url.endswith('/players/nfl'):return {'TEST_ONLY_PLAYER':{'full_name':'TEST_ONLY_PLAYER','position':'WR','team':'BUF'}}
        if '/matchups/' in url:
            week=int(url.rsplit('/',1)[-1])
            return [{'roster_id':1,'matchup_id':1,'points':0,'custom_points':4 if week==6 else None,'players_points':{'TEST_ONLY_PLAYER':0}},{'roster_id':2,'matchup_id':1,'points':10}]
        return {'league_id':'1001','name':'TEST_ONLY','scoring_settings':{'rec':1}}
    provider.get=get
    data=asyncio.run(provider.sleeper(None,deepcopy(ROW)))
    assert data['sourceAnalysisWeek']==6;assert data['confirmedThroughWeek']==5
    assert data['roster'][0]['currentProjection'] is None
    assert data['roster'][0]['historicalScores']=={str(i):0 for i in range(1,6)}
    assert data['roster'][0]['ppg3']==0;assert data['matchup']['myScore']==4
    assert data['user']['pf']==0;assert data['standings'][1]['pf'] is None

def test_espn_uses_selected_user_team_and_actual_projection_week():
    provider=Providers()
    async def get(client,url,**kwargs):
        return {'status':{'currentMatchupPeriod':6},'settings':{'name':'TEST_ONLY','scoringSettings':{'scoringItems':[{'statId':53,'points':1}]}},'teams':[
            {'id':1,'name':'TEST_ONLY_MINE','record':{'overall':{'wins':2,'losses':3,'pointsFor':0}},'roster':{'entries':[{'lineupSlotId':20,'playerPoolEntry':{'player':{'id':99,'fullName':'TEST_ONLY_PLAYER','defaultPositionId':3,'proTeamId':2,'stats':[
                {'seasonId':2026,'scoringPeriodId':4,'statSplitTypeId':1,'statSourceId':0,'appliedTotal':0},
                {'seasonId':2026,'scoringPeriodId':5,'statSplitTypeId':1,'statSourceId':1,'appliedTotal':40},
                {'seasonId':2026,'scoringPeriodId':6,'statSplitTypeId':1,'statSourceId':1,'appliedTotal':0}]}}}]}},
            {'id':2,'name':'TEST_ONLY_OTHER','roster':{'entries':[]}}],
            'schedule':[{'matchupPeriodId':5,'winner':'AWAY','home':{'teamId':1,'totalPoints':0},'away':{'teamId':2,'totalPoints':10}}]}
    provider.get=get
    data=asyncio.run(provider.espn(None,{**ROW,'platform':'ESPN'},None))
    assert len(data['roster'])==1;assert data['roster'][0]['currentProjection']==0
    assert data['roster'][0]['projectionWeek']==6;assert data['roster'][0]['historicalScores']=={'4':0.0}
    assert data['weekly'][0]['result']=='L';assert data['confirmedThroughWeek']==5

def test_absent_scores_remain_unknown():
    assert fractional_points({}) is None;assert fractional_points({'fpts':0})==0
    assert num(None) is None;assert num(True) is None;assert num('0')==0

def test_international_early_game_keeps_provider_timestamp_and_location():
    raw={'events':[{'id':'TEST_ONLY','date':'2026-10-11T13:30:00Z','status':{'type':{'state':'pre','completed':False}},'competitions':[{'neutralSite':True,'venue':{'fullName':'TEST_ONLY_LONDON','address':{'country':'England'}},'competitors':[{'homeAway':'home','team':{'abbreviation':'JAC'}},{'homeAway':'away','team':{'abbreviation':'WSH'}}]}]}]}
    week=normalize(raw,6);game=week['games'][0]
    assert game['international'] is True;assert game['startTime']=='2026-10-11T13:30:00Z'
    assert game['home']=='JAX';assert game['away']=='WAS';assert game['live'] is False

def test_calendar_reuses_fresh_cloud_cache_without_provider_request():
    import time
    class Cache:
        def public_cache(self,key):
            assert key=='nfl-2026-6'
            return {'savedEpoch':time.time(),'payload':{'ok':True,'season':2026,'weeks':[{'week':6,'games':[]}]}}
    assert asyncio.run(Calendar(Cache()).get(2026,6))['weeks'][0]['week']==6
