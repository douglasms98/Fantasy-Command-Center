"""TEST_ONLY regression fixtures for partial scoring and safe NFL language."""
from app.sleeper_projections import projection_details,score_projection
from app.enrichment import apply_calendar
from app.news_language import contextual_title,protected_names
from app.translation import protect_title
import asyncio
import time
import httpx
from app.calendar import Calendar

def test_sparse_native_ranges_do_not_fabricate_unknown_special_rules():
    stats={'sack':2,'pts_allow_21_27':1,'pts_allow':24,'def_fum_td':0.1}
    assert score_projection(stats,{'sack':1,'pts_allow_0':10,'pts_allow_21_27':-1},'DEF')==1
    assert score_projection({'sack':2,'pts_allow':24},{'pts_allow_0':10},'DEF') is None
    assert projection_details(stats,{'sack':1,'def_st_ff':1},'DEF')=={'value':2,'missing':['def_st_ff']}
    assert score_projection({'fgm':2,'fgm_50p':1},{'fgm_50_59':5,'fgm_60p':6},'K') is None
    assert score_projection({'pass_yd':200,'pass_int_td':0.1},{'pass_yd':0.04,'pass_int_td':-2},'QB')==7.8
    assert score_projection({'pass_yd':200,'pass_int':None},{'pass_int':-2},'QB') is None

def test_unknown_nfl_team_is_not_a_confirmed_bye_or_zero_projection():
    unknown={'nfl':'FA','slot':'Starter','currentProjection':None,'_team':'TEST_ONLY'}
    league={'platform':'Sleeper','team':'TEST_ONLY','sourceAnalysisWeek':6,'summary':{},
            'roster':[unknown],'_allRosters':[unknown],'waivers':[],
            'matchup':{'oppTeam':'TEST_ONLY_OTHER'}}
    apply_calendar(league,{'weeks':[{'week':6,'complete':True,'games':[{'home':'BUF','away':'NYJ'}]}]})
    assert 'byeWeek' not in unknown and unknown['currentProjection'] is None
    assert 'myRemaining' not in league['matchup'] and 'myProjection' not in league['matchup']

def test_calendar_retains_a_confirmed_week_when_only_one_request_fails(monkeypatch):
    old={'week':6,'complete':True,'games':[{'home':'BUF','away':'NYJ','startTime':'2030-10-20T18:00:00Z'}]}
    class Cache:
        saved=None
        def public_cache(self,key):return {'savedEpoch':time.time()-600,'payload':{'season':2026,'weeks':[old]}}
        def save_public_cache(self,key,value):self.saved=value
    cache=Cache();original=httpx.AsyncClient
    def response(request):
        week=int(request.url.params['week'])
        if week==6:return httpx.Response(503,json={})
        return httpx.Response(200,json={'season':{'year':2026},'week':{'number':week},'events':[{
            'id':'TEST_ONLY','date':'2030-10-27T18:00:00Z','competitions':[{'competitors':[
                {'homeAway':'home','team':{'abbreviation':'BUF'}},
                {'homeAway':'away','team':{'abbreviation':'NYJ'}}]}]}]})
    monkeypatch.setattr('app.calendar.httpx.AsyncClient',lambda **kwargs:original(transport=httpx.MockTransport(response),**kwargs))
    result=asyncio.run(Calendar(cache).get(2026,6))
    kept=next(w for w in result['weeks'] if w['week']==6)
    assert kept['games']==old['games'] and kept['stale'] is True
    assert result['retainedWeeks']==[6] and result['stale'] is True
    assert len(result['weeks'])==5 and cache.saved==result

def test_calendar_coverage_uses_team_ids_and_keeps_missing_players_unknown():
    # Two identical nicknames must not merge two rosters into one forecast.
    players=[{'_team':'TEST_ONLY_SAME','_teamId':'1','slot':'Starter','nfl':'BUF','currentProjection':12},
             {'_team':'TEST_ONLY_SAME','_teamId':'2','slot':'Starter','nfl':'NYJ','currentProjection':None,'projectionEstimate':10,'projectionMissingStats':['TEST_ONLY_RULE']}]
    l={'platform':'Sleeper','team':'TEST_ONLY_SAME','teamId':'1','sourceAnalysisWeek':6,'summary':{},'roster':[],
       '_allRosters':players,'matchup':{'oppTeam':'TEST_ONLY_SAME','oppTeamId':'2'}}
    calendar={'weeks':[{'week':6,'complete':True,'games':[{'home':'BUF','away':'NYJ','startTime':'2030-10-20T18:00:00Z'}]}]}
    apply_calendar(l,calendar);m=l['matchup']
    assert m['myProjection']==12 and m['oppProjectionEstimate']==10
    assert m['myProjectionCoverage']['total']==1 and m['oppProjectionCoverage']['missingRules']==['TEST_ONLY_RULE']
    players[1].pop('projectionEstimate');apply_calendar(l,calendar)
    assert 'oppProjectionEstimate' not in m and m['oppProjectionCoverage']['known']==0

def test_completed_game_uses_actual_points_and_never_a_missing_zero():
    l={'platform':'Sleeper','team':'TEST_ONLY','sourceAnalysisWeek':6,'summary':{},'roster':[],
       '_allRosters':[{'_team':'TEST_ONLY','slot':'Starter','nfl':'BUF','currentProjection':12,'currentPoints':17}],
       'matchup':{'oppTeam':'TEST_ONLY_OTHER'}}
    calendar={'weeks':[{'week':6,'complete':True,'games':[{'home':'BUF','away':'NYJ','completed':True}]}]}
    apply_calendar(l,calendar);assert l['matchup']['myProjection']==17
    l['_allRosters'][0]['currentPoints']=None;apply_calendar(l,calendar)
    assert 'myProjection' not in l['matchup'] and 'myProjectionEstimate' not in l['matchup']

def test_headline_context_preserves_teams_surnames_and_uncertainty():
    title="Can the Seahawks' defense again silence the 49ers' hot offense Sunday?"
    pt=contextual_title(title)
    assert 'Seahawks' in pt and '49ers' in pt and 'pode' in pt and 'ataque em boa fase' in pt
    title="Fantasy football buzz: Expect Bears' Swift to retain RB1 role with Monangai out"
    pt=contextual_title(title)
    assert all(x in pt for x in ('Bears','Swift','RB1','Monangai','deve'))
    assert contextual_title('TEST_ONLY unrecognized headline')==''
    assert 'posterior da coxa' in contextual_title('TEST_ONLY DNP due to hamstring issue')
    assert contextual_title('TEST_ONLY is expected to return Week 7').endswith('Semana 7.')

def test_machine_translation_protects_surnames_teams_and_domain_terms():
    title='Bears RB1 Swift, Seahawks and D/ST offense update'
    terms=protected_names(title,["D'Andre Swift"])
    assert {'Swift','Bears','Seahawks','RB1','D/ST'}<=set(terms)
    text,protected=protect_title(title,["D'Andre Swift"])
    assert 'attack' in text and 'Swift' not in text and 'Bears' not in text
    assert set(terms)==set(protected.values())
