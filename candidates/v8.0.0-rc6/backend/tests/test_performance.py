"""TEST_ONLY regression checks for compression and avoiding duplicate reads."""
from test_accounts import env,hdr,add
from app.service import Service
from app.providers import Providers
from app.sleeper_projections import normalize,score_projection,projection_details,SleeperProjections
from app.enrichment import apply_calendar
from types import SimpleNamespace
import asyncio
import httpx

def test_large_authenticated_payload_compresses_without_shared_user_cache(env):
    client,repo,_=env
    lid=add(client,'A').json()['league']['id']
    repo.data[('TEST_ONLY_A',lid)]={'loaded':True,'sourceAnalysisWeek':6,'roster':[],
        'user':{},'TEST_ONLY_padding':'TEST_ONLY_A'*5000}
    response=client.get('/v2/app-payload',headers={**hdr(),'Accept-Encoding':'gzip'})
    assert response.headers['content-encoding']=='gzip'
    assert int(response.headers['content-length'])<len(response.content)/5
    assert response.headers['cache-control']=='no-store'
    assert response.json()['userId']=='TEST_ONLY_A'
    assert not client.get('/v2/app-payload',headers=hdr('B')).json()['data']['leagues']
    assert client.get('/v2/app-payload').status_code==401

def test_public_html_revalidates_and_carries_no_session_data(env):
    client,_,_=env
    first=client.get('/app',headers={'Accept-Encoding':'gzip'})
    assert first.status_code==200 and first.headers['content-encoding']=='gzip'
    assert first.headers['cache-control']=='public, max-age=0, must-revalidate'
    second=client.get('/app',headers={'If-None-Match':first.headers['etag']})
    assert second.status_code==304 and not second.content
    assert second.headers['etag']==first.headers['etag']
    assert 'TEST_ONLY_A@example.invalid' not in first.text

def test_calendar_context_does_not_decode_all_rosters():
    rows=[{'id':str(i),'season':2026,'sourceAnalysisWeek':7,'revision':'TEST_ONLY'} for i in range(6)]
    repo=SimpleNamespace(list_leagues=lambda uid:rows,
        read_payload=lambda *args:(_ for _ in ()).throw(AssertionError('Full payload must not be loaded')))
    assert Service(repo,None).schedule_context('TEST_ONLY')==(2026,7)
    rows[:]=[{'id':'TEST_ONLY','season':2025,'sourceAnalysisWeek':8}]
    assert Service(repo,None).schedule_context('TEST_ONLY')==(2025,8)

def test_sleeper_public_projection_has_period_and_publication_guards():
    def row(pid,**values):return {'player_id':pid,'season':'2026','week':6,'season_type':'regular',
        'player':{'position':'WR'},'company':'rotowire','stats':{'rec':4,'rec_yd':60,'rec_td':1},**values}
    result=normalize([row('TEST_ONLY'),row('TEST_ONLY_OLD',week=5),row('TEST_ONLY_OTHER_YEAR',season='2025'),
        row('TEST_ONLY_ADP',stats={'adp_dd_ppr':999,'pts_ppr':0}),row('TEST_ONLY_PRE',season_type='pre')],2026,6)
    assert list(result['players'])==['TEST_ONLY']
    stats=result['players']['TEST_ONLY']['stats']
    assert score_projection(stats,{'rec':1,'rec_yd':.1,'rec_td':6},'WR')==16
    assert score_projection(stats,{'rec':.5,'rec_yd':.1,'rec_td':6},'WR')==14
    rules={'rec':1,'rec_yd':.1,'rec_td':6,'bonus_rec_yd_100':2}
    assert score_projection(stats,rules,'WR') is None
    assert projection_details(stats,rules,'WR')=={'value':16,'missing':['bonus_rec_yd_100']}
    assert score_projection({'rec':0},{'rec':1},'WR')==0

def test_sleeper_weekly_projection_is_shared_without_roster_selection():
    requests=[]
    def reply(request):
        requests.append(request)
        return httpx.Response(200,json=[{'player_id':'TEST_ONLY','season':'2026','week':6,
            'season_type':'regular','player':{'position':'WR'},'stats':{'rec':4}}])
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(reply)) as client:
            projections=SleeperProjections()
            a=await projections.get(client,2026,6);b=await projections.get(client,2026,6)
            assert a==b
    asyncio.run(run())
    assert len(requests)==1 and requests[0].url.path=='/projections/nfl/2026/6'
    assert dict(requests[0].url.params)=={'season_type':'regular'}
    assert 'Cookie' not in requests[0].headers

def test_incomplete_sleeper_forecast_has_separate_matchup_estimate():
    players=[{'_team':'TEST_ONLY_TEAM','nfl':'BUF','slot':'Starter','currentProjection':None,'projectionEstimate':12}]
    league={'platform':'Sleeper','team':'TEST_ONLY_TEAM','sourceAnalysisWeek':6,'summary':{},'roster':players,
        '_allRosters':players,'matchup':{'oppTeam':'TEST_ONLY_OPPONENT'},'waivers':[]}
    calendar={'weeks':[{'week':6,'complete':True,'games':[{'home':'BUF','away':'NYJ','startTime':'2030-10-20T18:00:00Z'}]}]}
    apply_calendar(league,calendar)
    assert league['matchup']['myProjectionEstimate']==12
    assert 'myProjection' not in league['matchup']
    assert league['summary']['projectedStarterCurrent'] is None

def test_native_sleeper_forecast_reaches_each_league_payload():
    async def run(ppr):
        provider=Providers()
        async def get(client,url,**kwargs):
            if url.endswith('/state/nfl'):return {'season':'2026','week':6}
            if url.endswith('/rosters'):return [{'roster_id':1,'owner_id':'TEST_ONLY_OWNER','players':['TEST_ONLY_PLAYER'],'starters':['TEST_ONLY_PLAYER'],'settings':{}}]
            if url.endswith('/users'):return [{'user_id':'TEST_ONLY_OWNER','display_name':'TEST_ONLY_TEAM'}]
            if url.endswith('/players/nfl'):return {'TEST_ONLY_PLAYER':{'full_name':'TEST_ONLY_PLAYER','position':'WR','team':'BUF'}}
            if '/matchups/' in url:return []
            return {'league_id':'1001','name':'TEST_ONLY','scoring_settings':{'rec':ppr,'rec_yd':.1,'rec_td':6}}
        async def stats(*args):return {}
        async def projections(*args):return {'players':{'TEST_ONLY_PLAYER':{'pos':'WR','stats':{'rec':4,'rec_yd':60,'rec_td':1,'pts_ppr':16,'pts_half_ppr':14},'source':'Sleeper • TEST_ONLY'}}}
        provider.get=get;provider.player_stats.get=stats;provider.sleeper_projections.get=projections
        row={'id':'TEST_ONLY','platform':'Sleeper','leagueId':'1001','teamId':'1','season':2026,'name':'TEST_ONLY'}
        return await provider.sleeper(None,row)
    a=asyncio.run(run(1));b=asyncio.run(run(.5))
    assert a['roster'][0]['currentProjection']==16 and b['roster'][0]['currentProjection']==14
    assert a['roster'][0]['sleeperPublishedProjection']==16 and b['roster'][0]['sleeperPublishedProjection']==14
    assert a['roster'][0]['projectionSource'].startswith('Sleeper')
    assert a['roster'][0]['projectionWeek']==6
    assert a['dataCoverage']['sleeperPublishedProjections']==1
