"""Calendar enrichment and alerts use actual provider timestamps, never fixed weeks."""
from datetime import datetime,timezone,timedelta

def parse_time(value):
    try:return datetime.fromisoformat(str(value).replace('Z','+00:00')).astimezone(timezone.utc)
    except (ValueError,TypeError):return None

def apply_calendar(league,calendar):
    week=int(league.get('sourceAnalysisWeek') or 0)
    block=next((w for w in calendar.get('weeks',[]) if w.get('week')==week),{})
    games={team:g for g in block.get('games',[]) for team in (g.get('home'),g.get('away'))}
    if not games:return
    for p in league.get('roster',[])+league.get('waivers',[])+league.get('_allRosters',[]):
        g=games.get(p.get('nfl'))
        if g:
            p['kickoffAt']=g.get('startTime');p['gameCompleted']=g.get('completed') is True;p['gameLive']=g.get('live') is True
        elif block.get('complete'):
            p['byeWeek']=week;p['currentProjection']=0.0
    matchup=league.get('matchup')
    if not matchup:return
    for prefix,name in [('my',league['team']),('opp',matchup.get('oppTeam'))]:
        starters=[p for p in league.get('_allRosters',[]) if p.get('_team')==name and p.get('slot')=='Starter']
        known=[p for p in starters if p.get('nfl') in games or (block.get('complete') and p.get('nfl'))]
        if starters and len(known)==len(starters):matchup[prefix+'Remaining']=sum(not p.get('gameCompleted') and p.get('byeWeek')!=week for p in starters)
        if league['platform']=='Sleeper' and starters:
            values=[p.get('currentPoints') if p.get('gameCompleted') else p.get('currentProjection') for p in starters]
            if all(v is not None for v in values):
                matchup[prefix+'Projection']=sum(values);matchup['projectionEstimated']=True
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
