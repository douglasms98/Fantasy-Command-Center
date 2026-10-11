"""TEST_ONLY responses test independent accounts and provider normalization."""
import asyncio
from datetime import datetime,timezone
import httpx
import pytest
from fastapi import HTTPException
from app.player_stats import normalize_players,sleeper_score,PublicPlayerStats
from app.providers import Providers
from app.enrichment import apply_calendar,notification_events
from app.identity import Identity

def test_current_projection_requires_matching_season_week_source():
    stats=lambda season,week,source,value:{'seasonId':season,'scoringPeriodId':week,'statSourceId':source,'statSplitTypeId':1,'stats':{'53':value}}
    raw=[{'id':99,'fullName':'TEST_ONLY','defaultPositionId':3,'stats':[
        stats(2025,6,1,99),stats(2026,5,1,80),stats(2026,5,0,0),stats(2026,6,1,2)]}]
    value=normalize_players(raw,2026,6)['99']
    assert value['projection']=={'53':2} and value['history']=={'5':{'53':0}}

def test_sleeper_rescoring_uses_own_settings_and_separates_defense():
    facts={'53':4,'42':60,'43':1,'24':10,'72':1}
    rules={'rec':1,'rec_yd':.1,'rec_td':6,'rush_yd':.1,'fum_lost':-2,'fum_rec':2,'def_st_ff':1}
    assert sleeper_score(facts,rules,'WR')==15
    assert sleeper_score(facts,{**rules,'rec':.5},'WR')==13
    assert sleeper_score(facts,{**rules,'rec_40p':2},'WR') is None
    assert sleeper_score(None,rules,'WR') is None
    assert sleeper_score({'53':0},{'rec':1},'WR')==0
    assert sleeper_score({'80':2,'198':1,'201':1},{'fgm_0_19':3,'fgm_20_29':3,'fgm_30_39':3,'fgm_50_59':5,'fgm_60p':6},'K')==17

def test_public_nfl_stats_are_independent_of_any_fantasy_league():
    requests=[]
    def reply(request):
        requests.append(request)
        return httpx.Response(200,json=[{'id':99,'fullName':'TEST_ONLY','defaultPositionId':3,'stats':[]}])
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(reply)) as client:
            provider=PublicPlayerStats()
            await provider.get(client,2026,6);await provider.get(client,2026,6)
    asyncio.run(run())
    assert len(requests)==2
    assert all('/seasons/2026/players' in r.url.path and '/leagues/' not in r.url.path for r in requests)
    assert all('Cookie' not in r.headers for r in requests)

def test_espn_two_users_resolve_their_own_matchup_logos_and_live_zero():
    provider=Providers();seen=[]
    async def empty(*args):return {}
    provider.player_stats.get=empty
    async def get(client,url,**kwargs):
        seen.append(kwargs)
        return {'seasonId':2026,'scoringPeriodId':6,'status':{'currentMatchupPeriod':6},
          'settings':{'name':'TEST_ONLY','scoringSettings':{'scoringItems':[{'statId':53,'points':1}]}},
          'teams':[{'id':1,'name':'TEST_ONLY_A','logo':'https://example.invalid/a.png'},
                   {'id':2,'name':'TEST_ONLY_B','logo':'https://example.invalid/b.png'}],
          'schedule':[{'matchupPeriodId':6,'home':{'teamId':1,'totalPoints':99,'totalPointsLive':0,'totalProjectedPointsLive':20},'away':{'teamId':2,'totalPointsLive':12}}]}
    provider.get=get
    async def run():
        row={'id':'TEST_ONLY','platform':'ESPN','leagueId':'1001','season':2026,'name':'TEST_ONLY'}
        return await provider.espn(None,{**row,'teamId':'1'},None),await provider.espn(None,{**row,'teamId':'2'},None)
    a,b=asyncio.run(run())
    assert a['matchup']['myScore']==0 and b['matchup']['myScore']==12
    assert a['matchup']['oppTeam']=='TEST_ONLY_B' and b['matchup']['oppTeam']=='TEST_ONLY_A'
    assert a['matchup']['myLogo'].endswith('/a.png') and b['matchup']['myLogo'].endswith('/b.png')
    assert any(('scoringPeriodId',6) in r.get('params',[]) for r in seen)
    assert all('mSchedule' not in str(r) for r in seen)

def test_calendar_keeps_partial_projection_unknown_and_alerts_account_owned_games():
    league={'id':'TEST_ONLY_A','platform':'Sleeper','name':'TEST_ONLY','team':'TEST_ONLY_TEAM','loaded':True,'sourceAnalysisWeek':6,
      'summary':{},'matchup':{'oppTeam':'TEST_ONLY_OTHER'},'waivers':[],
      'roster':[{'nfl':'BUF','slot':'Starter','currentProjection':12}],
      '_allRosters':[{'nfl':'BUF','slot':'Starter','currentProjection':12,'_team':'TEST_ONLY_TEAM'},
                     {'nfl':'BUF','slot':'Starter','currentProjection':None,'_team':'TEST_ONLY_TEAM'}]}
    weeks=[{'week':6,'complete':True,'games':[{'home':'BUF','away':'NYJ','startTime':'2030-10-13T13:30:00Z','international':True}]}]
    apply_calendar(league,{'weeks':weeks})
    assert 'myProjection' not in league['matchup']
    alerts=notification_events([league],weeks,datetime(2030,10,13,12,tzinfo=timezone.utc))
    assert len(alerts)==1 and alerts[0]['leagueId']=='TEST_ONLY_A'
    assert alerts[0]['at']=='2030-10-13T13:00:00+00:00'
    assert notification_events([],weeks)==[]

@pytest.mark.parametrize('code,status',[('INVALID_REFRESH_TOKEN',401),('USER_DISABLED',401),('QUOTA_EXCEEDED',503),('INVALID_API_KEY',503),('INTERNAL_ERROR',503)])
def test_temporary_firebase_failure_does_not_invalidate_session(monkeypatch,code,status):
    class Client:
        async def __aenter__(self):return self
        async def __aexit__(self,*args):pass
        async def post(self,*args,**kwargs):return httpx.Response(400,json={'error':{'message':code}})
    monkeypatch.setattr('app.identity.httpx.AsyncClient',lambda **kwargs:Client())
    monkeypatch.setattr(Identity,'key',lambda self:'TEST_ONLY')
    with pytest.raises(HTTPException) as e:asyncio.run(Identity().refresh('TEST_ONLY_REFRESH'))
    assert e.value.status_code==status
