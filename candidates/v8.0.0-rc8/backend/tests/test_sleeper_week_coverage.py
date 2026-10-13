"""Regression cases for real-provider semantics; TEST_ONLY synthetic fixtures."""
from app.enrichment import apply_calendar

def _fixture(platform='Sleeper'):
    mine=[
        {'_team':'Mine','_teamId':'1','slot':'Starter','player':'Available WR','pos':'WR','nfl':'KC','currentProjection':9.91},
        {'_team':'Mine','_teamId':'1','slot':'Starter','player':'Injured WR','pos':'WR','nfl':'PIT','injuryStatus':'Out','currentProjection':None,'projectionEstimate':12.0,'projectionMissingStats':['fgm']},
        {'_team':'Mine','_teamId':'1','slot':'Starter','player':'Bye DEF','pos':'DEF','nfl':'MIN','currentProjection':None},
    ]
    opponent=[{'_team':'Opponent','_teamId':'2','slot':'Starter','player':'Opponent QB','pos':'QB','nfl':'LAC','currentProjection':12}]
    league={'platform':platform,'team':'Mine','teamId':'1','sourceAnalysisWeek':6,'summary':{},'roster':[dict(p) for p in mine],
            '_allRosters':mine+opponent,'waivers':[],'matchup':{'oppTeam':'Opponent','oppTeamId':'2'}}
    calendar={'weeks':[{'week':6,'complete':True,'games':[{'home':'KC','away':'LAC','startTime':'2030-10-15T18:00:00Z'},
        {'home':'PIT','away':'TB','startTime':'2030-10-18T18:00:00Z'}]}]}
    return league,calendar

def test_bye_out_and_position_values_are_numeric_for_sleeper():
    league,calendar=_fixture()
    apply_calendar(league,calendar)
    assert league['roster'][1]['currentProjection']==0
    assert league['roster'][2]['byeWeek']==6
    assert league['roster'][2]['currentProjection']==0
    assert league['matchup']['myProjection']==9.91
    assert league['matchup']['oppProjection']==12
    assert league['matchup']['myProjectionCoverage']=={'known':3,'total':3,'missingRules':[]}
    assert league['summary']['projectedStarterCurrent']==9.91
    assert league['_allRosters'][1]['projectionEstimate'] is None

def test_out_does_not_override_espn_provider_projection():
    league,calendar=_fixture('ESPN')
    apply_calendar(league,calendar)
    assert league['_allRosters'][1]['currentProjection'] is None

def test_live_or_completed_out_is_not_zeroed():
    for flag in ('live','completed'):
        league,calendar=_fixture()
        league['_allRosters'][1]['currentProjection']=7
        for g in calendar['weeks'][0]['games']:
            if g['home']=='PIT':g[flag]=True
        apply_calendar(league,calendar)
        assert league['_allRosters'][1]['currentProjection']==7

def test_unknown_team_keeps_missing_projection():
    league,calendar=_fixture()
    league['_allRosters'][2]['nfl']='FA'
    league['roster'][2]['nfl']='FA'
    apply_calendar(league,calendar)
    assert league['_allRosters'][2]['currentProjection'] is None
    assert 'myProjection' not in league['matchup']

def test_incomplete_schedule_does_not_infer_bye():
    league,calendar=_fixture()
    calendar['weeks'][0]['complete']=False
    apply_calendar(league,calendar)
    assert league['_allRosters'][2]['currentProjection'] is None

def test_alias_team_code_matches_game_and_does_not_mark_bye():
    league,calendar=_fixture()
    league['_allRosters'][2]['nfl']='JAC'
    league['roster'][2]['nfl']='JAC'
    calendar['weeks'][0]['games'].append({'home':'JAX','away':'HOU','startTime':'2030-10-18T18:00:00Z'})
    apply_calendar(league,calendar)
    assert 'byeWeek' not in league['_allRosters'][2]
    assert league['_allRosters'][2]['kickoffAt']=='2030-10-18T18:00:00Z'
    assert 'myProjection' not in league['matchup']

def test_not_all_out_statuses_are_zero():
    for status in ('Questionable','Doubtful','IR',''):
        league,calendar=_fixture()
        league['_allRosters'][1]['injuryStatus']=status
        league['roster'][1]['injuryStatus']=status
        apply_calendar(league,calendar)
        assert league['_allRosters'][1]['currentProjection'] is None
        assert 'myProjection' not in league['matchup']
