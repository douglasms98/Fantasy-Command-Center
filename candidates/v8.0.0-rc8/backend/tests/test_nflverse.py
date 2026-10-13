"""TEST_ONLY public files; no selected league/player data is sent to a source."""
import asyncio
from copy import deepcopy
import httpx
import pytest
from app.nflverse import parse_csv, enrich, qb_context, Nflverse

PLAYERS=b'gsis_id,espn_id,pfr_id,position,display_name,birth_date,draft_year,draft_round,draft_pick\nTEST_ONLY_GSIS,101,TEST_ONLY_PFR,WR,TEST_ONLY_RECEIVER,2001-01-01,2023,2,45\n'
STATS=b'player_id,season,season_type,week,carries,targets,receptions,rushing_yards,receiving_yards,attempts,team\nTEST_ONLY_GSIS,2026,REG,4,0,10,7,0,100,0,BUF\nTEST_ONLY_GSIS,2026,REG,5,0,12,8,0,120,0,BUF\nTEST_ONLY_GSIS,2026,REG,6,0,50,50,0,999,0,BUF\nTEST_ONLY_GSIS,2025,REG,3,0,99,99,0,999,0,BUF\nTEST_ONLY_GSIS,2026,POST,3,0,99,99,0,999,0,BUF\n'
SNAPS=b'pfr_player_id,season,game_type,week,offense_snaps,offense_pct,team\nTEST_ONLY_PFR,2026,REG,4,50,0.8,BUF\nTEST_ONLY_PFR,2026,REG,5,60,0.9,BUF\n'

def datasets():return {k:{'records':parse_csv(v,k,2026)} for k,v in [('players',PLAYERS),('stats',STATS),('snaps',SNAPS)]}
def league():return {'platform':'Sleeper','season':2026,'sourceAnalysisWeek':6,'roster':[{'playerId':'TEST_ONLY_SLEEPER','espnId':'101','player':'TEST_ONLY_RECEIVER','pos':'WR','nfl':'BUF','currentProjection':13,'ppg3':8}], '_allRosters':[],'waivers':[]}


def test_ids_draft_usage_snaps_and_qb_feed_each_roster_without_overwriting_scoring():
    l=league();l['_allRosters']=deepcopy(l['roster']);l['waivers']=deepcopy(l['roster'])
    directory={'TEST_ONLY_QB':{'position':'QB','team':'BUF','depth_chart_order':1,'full_name':'TEST_ONLY_QUARTERBACK','injury_status':'Out'}}
    enrich(l,datasets(),directory)
    for p in l['roster']+l['_allRosters']+l['waivers']:
        assert p['draftOverall']==45 and p['draftYear']==2023
        assert p['usageScore']==79.3 and p['snapShare']==.85
        assert [g['week'] for g in p['usageFacts']['games']]==[4,5]
        assert p['qbContext']['status']=='UNAVAILABLE'
        assert p['currentProjection']==13 and p['ppg3']==8
    assert l['enrichmentCoverage']['usage']==1 and l['enrichmentCoverage']['qbContext']==1


def test_espn_id_is_used_without_sleeper_registration():
    l=league();l['platform']='ESPN';l['roster'][0]['playerId']='101';del l['roster'][0]['espnId']
    enrich(l,datasets());assert l['roster'][0]['draftOverall']==45


def test_unknown_and_ambiguous_ids_do_not_guess_another_players_stats():
    l=league();l['roster'][0]['espnId']='999';enrich(l,datasets())
    assert 'usageFacts' not in l['roster'][0] and l['enrichmentCoverage']['usage']==0
    d=datasets();d['players']['records'].append(deepcopy(d['players']['records'][0]))
    l=league();enrich(l,d);assert 'draftOverall' not in l['roster'][0]


def test_missing_measurement_is_not_zero_and_current_week_is_excluded():
    d=datasets();d['stats']['records'][0]['targets']=None;d['stats']['records'][1]['targets']=None
    l=league();enrich(l,d)
    assert 'usageScore' not in l['roster'][0]
    assert l['roster'][0]['usageFacts']['throughWeek']==5
    d['stats']['records']=[{**d['stats']['records'][0],**{k:0 for k in ['targets','carries','receptions','rushingYards','receivingYards']}}]
    l=league();enrich(l,d);assert l['roster'][0]['usageScore']==0


def test_unknown_or_ambiguous_qb_depth_does_not_mark_healthy_or_out():
    assert qb_context({'TEST_ONLY':{'position':'QB','team':'BUF','injury_status':'Out'}})=={}
    p={'position':'QB','team':'BUF','depth_chart_order':1,'full_name':'TEST_ONLY_QB'}
    assert qb_context({'TEST_ONLY_A':p,'TEST_ONLY_B':p})=={}
    assert qb_context({'TEST_ONLY_A':p})['BUF']['status']=='NO_RESTRICTION_REPORTED'


def test_csv_schema_and_period_guards():
    with pytest.raises(ValueError):parse_csv(b'TEST_ONLY_BAD\n1\n','stats',2026)
    rows=parse_csv(STATS,'stats',2026)
    assert [r['week'] for r in rows]==[4,5,6]
    with pytest.raises(ValueError):parse_csv(STATS,'stats',2020)
    with pytest.raises(ValueError):asyncio.run(Nflverse().get('../../TEST_ONLY'))


def test_public_cache_uses_generic_urls_conditional_requests_and_is_shared():
    requests=[]
    def reply(request):
        requests.append(request)
        assert not request.url.query and 'cookie' not in request.headers and 'authorization' not in request.headers
        assert request.url.host=='github.com'
        return httpx.Response(304 if 'if-none-match' in request.headers else 200,content=STATS,headers={'ETag':'TEST_ONLY_TAG'})
    async def run():
        n=Nflverse()
        async with httpx.AsyncClient(transport=httpx.MockTransport(reply)) as client:
            a=await n.dataset(client,'stats',2026);b=await n.dataset(client,'stats',2026)
            assert a==b and len(requests)==1
            n.cache['nflverse-v1-stats-2026']['savedEpoch']=0
            c=await n.dataset(client,'stats',2026);assert c==a
    asyncio.run(run());assert len(requests)==2
    assert str(requests[0].url).endswith('/stats_player/stats_player_week_2026.csv')


def test_source_failure_retains_observed_facts_and_reports_staleness():
    async def run():
        n=Nflverse();key='nflverse-v1-stats-2026';n.cache[key]={'savedEpoch':0,'payload':{'records':parse_csv(STATS,'stats',2026)}}
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r:httpx.Response(503))) as c:
            result=await n.dataset(c,'stats',2026);assert result['stale'] and result['records']
            empty=await n.dataset(c,'snaps',2026);assert empty['unavailable'] and not empty['records']
        l=league();d=datasets();d['stats']=result;enrich(l,d)
        assert l['enrichmentCoverage']['stale']
    asyncio.run(run())
