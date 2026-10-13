"""Calendar enrichment and alerts use actual provider timestamps, never fixed weeks."""
from datetime import datetime,timezone,timedelta
from .calendar import NFL_TEAMS,team_code

def parse_time(value):
    try:return datetime.fromisoformat(str(value).replace('Z','+00:00')).astimezone(timezone.utc)
    except (ValueError,TypeError):return None

def apply_calendar(league,calendar):
    week=int(league.get('sourceAnalysisWeek') or 0)
    block=next((w for w in calendar.get('weeks',[]) if w.get('week')==week),{})
    games={team_code(team):g for g in block.get('games',[]) for team in (g.get('home'),g.get('away'))}
    if not games:return
    # Normalize once across both providers; roster and allRosters may contain distinct copies.
    for p in league.get('roster',[])+league.get('waivers',[])+league.get('_allRosters',[]):
        team=team_code(p.get('nfl'))
        g=games.get(team)
        # A new week must not retain a previous BYE classification.
        p.pop('byeWeek',None)
        if g:
            p['kickoffAt']=g.get('startTime');p['gameCompleted']=g.get('completed') is True;p['gameLive']=g.get('live') is True
            # An official OUT means zero future playing opportunity in this matchup,
            # but never overwrite a real score for a live or completed contest.
            status=str(p.get('injuryStatus') or '').strip().upper()
            if league.get('platform')=='Sleeper' and status in ('OUT','O') and not p['gameCompleted'] and not p['gameLive']:
                p['currentProjection']=0.0
                p['projectionEstimate']=None
                p['projectionMissingStats']=[]
                p['projectionSource']='FCC • OUT confirmado (jogo ainda não iniciado)'
        elif block.get('complete') and team in NFL_TEAMS:
            p['byeWeek']=week;p['currentProjection']=0.0
            p['projectionEstimate']=None;p['projectionMissingStats']=[]
            p['projectionSource']='FCC • BYE confirmado pelo calendário'
    matchup=league.get('matchup')
    if not matchup:return
    for prefix,name in [('my',league['team']),('opp',matchup.get('oppTeam'))]:
        team_id=str(league.get('teamId') if prefix=='my' else matchup.get('oppTeamId') or '')
        starters=[p for p in league.get('_allRosters',[]) if
                  (str(p.get('_teamId'))==team_id if p.get('_teamId') is not None and team_id else p.get('_team')==name) and p.get('slot')=='Starter']
        known=[p for p in starters if team_code(p.get('nfl')) in games or (block.get('complete') and team_code(p.get('nfl')) in NFL_TEAMS)]
        if starters and len(known)==len(starters):matchup[prefix+'Remaining']=sum(not p.get('gameCompleted') and p.get('byeWeek')!=week for p in starters)
        if league['platform']=='Sleeper' and starters:
            matchup.pop(prefix+'Projection',None);matchup.pop(prefix+'ProjectionEstimate',None)
            matchup.pop(prefix+'ProjectionCoverage',None)
            values=[p.get('currentPoints') if p.get('gameCompleted') else p.get('currentProjection') for p in starters]
            coverage={'known':sum(v is not None for v in values),'total':len(starters),
                      'missingRules':sorted({k for p in starters if not p.get('gameCompleted') for k in p.get('projectionMissingStats',[])})}
            if all(v is not None for v in values):
                matchup[prefix+'Projection']=sum(values);matchup['projectionEstimated']=True
            else:
                partial=[p.get('currentPoints') if p.get('gameCompleted') else
                         p.get('currentProjection') if p.get('currentProjection') is not None else p.get('projectionEstimate') for p in starters]
                coverage['known']=sum(v is not None for v in partial)
                if all(v is not None for v in partial):
                    matchup[prefix+'ProjectionEstimate']=sum(partial);matchup['projectionEstimated']=True
            matchup[prefix+'ProjectionCoverage']=coverage
    league['summary']['projectedStarterCurrent']=starter_total(league.get('roster',[]))

def starter_total(players):
    values=[p.get('currentProjection') for p in players if p.get('slot')=='Starter']
    return sum(values) if values and all(v is not None for v in values) else None

def notification_events(leagues,weeks,current=None):
    now=current or datetime.now(timezone.utc);events={}
    for league in leagues:
        if not league.get('loaded'):continue
        teams={p.get('nfl') for p in league.get('roster',[]) if p.get('slot')=='Starter'}
        slots={}
        for week in weeks:
            for game in week.get('games',[]):
                if not teams.intersection((game.get('home'),game.get('away'))):continue
                kickoff=parse_time(game.get('startTime'));at=kickoff-timedelta(minutes=30) if kickoff else None
                if at is None or at<=now:continue
                slots.setdefault((week['week'],at),[]).append(f"{game['away']} x {game['home']}")
        for (week,at),games in slots.items():
            eid=f"kickoff-{league['id']}-{week}-{int(at.timestamp())}"
            events[eid]={'id':eid,'type':'round_start','leagueId':league['id'],'at':at.isoformat(),
             'title':f"Revisar escalação • {league['name']}",'body':f"W{week}: jogos em 30 minutos ({' • '.join(games)}). Confira seus titulares antes do kickoff."}
    return sorted(events.values(),key=lambda e:e['at'])
