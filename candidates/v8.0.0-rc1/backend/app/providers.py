"""Only provider-returned data is normalized. Missing projections stay null."""
from datetime import datetime, timezone
from urllib.parse import urlparse, parse_qs
import asyncio
import math
import time
import re
import httpx
from fastapi import HTTPException
from pydantic import BaseModel, Field, ConfigDict, field_validator

class LeagueInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    platform: str
    leagueId: str = Field(min_length=1, max_length=300)
    teamId: str = Field(default='', max_length=20)
    username: str = Field(default='', max_length=80)
    name: str = Field(default='', max_length=100)
    season: int = Field(ge=2000, le=2100)

    @field_validator('platform')
    @classmethod
    def platform_check(cls, value):
        if value not in ('Sleeper', 'ESPN'):
            raise ValueError('Plataforma inválida')
        return value

    def provider_id(self):
        raw = self.leagueId.strip()
        if raw.startswith('https://'):
            parsed = urlparse(raw)
            if self.platform == 'Sleeper' and parsed.hostname in ('sleeper.app', 'sleeper.com'):
                raw = parsed.path.rstrip('/').split('/')[-1]
            elif self.platform == 'ESPN' and parsed.hostname in ('fantasy.espn.com', 'www.espn.com'):
                raw = parse_qs(parsed.query).get('leagueId', [''])[0]
            else:
                raise HTTPException(422, 'INVALID_LEAGUE_URL')
        if not re.fullmatch(r'[0-9]{1,22}', raw):
            raise HTTPException(422, 'INVALID_LEAGUE_ID')
        if self.teamId and not re.fullmatch(r'[0-9]{1,20}', self.teamId):
            raise HTTPException(422, 'INVALID_TEAM_ID')
        return raw

def timestamp():
    return datetime.now(timezone.utc).isoformat()

def empty_league(row, status='pending'):
    return dict(id=row['id'], platform=row['platform'], name=row.get('name') or row['platform'],
                team=row.get('team') or 'Selecionar time', loaded=False, scoring='—', roster=[], waivers=[],
                pendingReason=row.get('lastError') or ('Liga privada: conexão autorizada pendente.' if status == 'private_pending' else 'Aguardando primeira atualização.'),
                freshness='Aguardando dados', status=status)

def league_base(row, name, team, scoring, week):
    return dict(id=row['id'], platform=row['platform'], name=name, team=team, loaded=True, scoring=scoring,
                leagueId=row['leagueId'], teamId=row.get('teamId'), analysisWeek=week, sourceAnalysisWeek=week,
                projectionWeek=week, roster=[], waivers=[], weekly=[], standings=[], poscomp=[], posRanks={},
                tradeSuggestions=[], watchlist=[], summary={}, transactions=[],
                action={'level':'Baixa', 'title':'Dados em atualização', 'detail':'Recomendações dependem das estatísticas recebidas.', 'strength':'Sem projeções completas.'},
                sourceUpdatedAt=timestamp(), source=f"FCC Cloud • {row['platform']}", freshness='Atualizada pelo provedor',
                user={'wins':None,'losses':None,'pf':None,'relativeIndex':None})

def num(v):
    if v is None or isinstance(v, bool):
        return None
    try:
        result=float(v)
        return result if math.isfinite(result) else None
    except (ValueError, TypeError):
        return None

def fractional_points(settings):
    whole=num(settings.get('fpts'));fraction=num(settings.get('fpts_decimal'))
    if whole is None and fraction is None:return None
    return (whole or 0)+(fraction or 0)/100

def matchup_points(match):
    custom=num(match.get('custom_points'))
    return num(match.get('points')) if custom is None else custom

class Providers:
    def __init__(self):
        self._directory=None;self._directory_at=0;self._directory_lock=asyncio.Lock()

    async def directory(self,client):
        # Sleeper requests that its large public directory be cached for 24 hours.
        if self._directory is not None and time.monotonic()-self._directory_at<86400:return self._directory
        async with self._directory_lock:
            if self._directory is None or time.monotonic()-self._directory_at>=86400:
                value=await self.get(client,'https://api.sleeper.app/v1/players/nfl')
                if not isinstance(value,dict):raise HTTPException(502,'PROVIDER_UNAVAILABLE')
                self._directory=value;self._directory_at=time.monotonic()
        return self._directory

    async def get(self, client, url, **kwargs):
        response = await client.get(url, **kwargs)
        if response.status_code in (401, 403):
            raise HTTPException(409, 'PRIVATE_LEAGUE_CONNECTION_REQUIRED')
        if response.status_code == 404:
            raise HTTPException(404, 'PROVIDER_LEAGUE_NOT_FOUND')
        if not response.is_success:
            raise HTTPException(502, 'PROVIDER_UNAVAILABLE')
        return response.json()

    async def inspect(self, data: LeagueInput):
        lid = data.provider_id()
        async with httpx.AsyncClient(timeout=20, follow_redirects=False) as client:
            if data.platform == 'Sleeper':
                league = await self.get(client, f'https://api.sleeper.app/v1/league/{lid}')
                if not isinstance(league, dict) or not league.get('league_id'):
                    raise HTTPException(404, 'PROVIDER_LEAGUE_NOT_FOUND')
                if int(league.get('season') or 0) != data.season:
                    raise HTTPException(422, 'LEAGUE_SEASON_MISMATCH')
                rosters = await self.get(client, f'https://api.sleeper.app/v1/league/{lid}/rosters')
                users = await self.get(client, f'https://api.sleeper.app/v1/league/{lid}/users')
                team_id = data.teamId
                if data.username:
                    # Public username selects a followed team, not proof of account ownership.
                    if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', data.username):
                        raise HTTPException(422, 'INVALID_SLEEPER_USERNAME')
                    user = await self.get(client, f'https://api.sleeper.app/v1/user/{data.username}')
                    roster = next((r for r in rosters if str(r.get('owner_id')) == str(user.get('user_id'))), None)
                    team_id = str(roster['roster_id']) if roster else ''
                selected = next((r for r in rosters if str(r.get('roster_id')) == team_id), None)
                if not selected:
                    raise HTTPException(422, 'TEAM_NOT_IN_LEAGUE')
                owner = next((u for u in users if str(u.get('user_id')) == str(selected.get('owner_id'))), {})
                team = (owner.get('metadata') or {}).get('team_name') or owner.get('display_name') or 'Time'
                return {'leagueId': lid, 'name': league.get('name') or data.name or 'Sleeper', 'teamId': team_id, 'team': team, 'status':'registered'}
            if not data.teamId:
                raise HTTPException(422, 'TEAM_ID_REQUIRED')
            url=f'https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/{data.season}/segments/0/leagues/{lid}'
            try:
                core = await self.get(client, url, params=[('view','mTeam'),('view','mSettings')])
            except HTTPException as e:
                if e.detail == 'PRIVATE_LEAGUE_CONNECTION_REQUIRED':
                    return {'leagueId':lid, 'name':data.name or 'ESPN', 'teamId':data.teamId, 'team':f'Time {data.teamId}', 'status':'private_pending'}
                raise
            team = next((t for t in core.get('teams',[]) if str(t.get('id')) == data.teamId), None)
            if not team:
                raise HTTPException(422, 'TEAM_NOT_IN_LEAGUE')
            return {'leagueId':lid, 'name':(core.get('settings') or {}).get('name') or data.name or 'ESPN', 'teamId':data.teamId, 'team':team.get('name') or ' '.join(filter(None,[team.get('location'),team.get('nickname')])) or f'Time {data.teamId}', 'status':'registered'}

    async def fetch(self, row, credentials=None):
        async with httpx.AsyncClient(timeout=25, follow_redirects=False) as client:
            return await (self.sleeper(client,row) if row['platform']=='Sleeper' else self.espn(client,row,credentials))

    async def sleeper(self, c, row):
        base=f"https://api.sleeper.app/v1/league/{row['leagueId']}"
        league=await self.get(c,base)
        state=await self.get(c,'https://api.sleeper.app/v1/state/nfl')
        if int(state.get('season') or 0)!=int(row['season']):
            raise HTTPException(409,'SEASON_NOT_CURRENT')
        week=max(1,min(18,int(state.get('week') or state.get('display_week') or 1)))
        rosters=await self.get(c,base+'/rosters'); users=await self.get(c,base+'/users')
        mine=next((r for r in rosters if str(r.get('roster_id'))==str(row['teamId'])),None)
        if not mine: raise HTTPException(422,'TEAM_NOT_IN_LEAGUE')
        directory=await self.directory(c)
        settings=league.get('scoring_settings') or {}; ppr=num(settings.get('rec')) or 0
        out=league_base(row,league.get('name') or row['name'],row['team'],('PPR' if ppr==1 else 'Half PPR' if ppr==.5 else 'Standard') if settings else '—',week)
        points={}; latest=[]; history={}
        for w in range(1,week+1):
            matches=await self.get(c,base+f'/matchups/{w}')
            mm=next((m for m in matches if str(m.get('roster_id'))==str(row['teamId'])),None)
            if not mm: continue
            opp=next((m for m in matches if m.get('matchup_id')==mm.get('matchup_id') and str(m.get('roster_id'))!=str(row['teamId'])),None)
            score=matchup_points(mm)
            oscore=matchup_points(opp) if opp else None
            if w==week: latest=matches;points=mm.get('players_points') or {}
            else:
                # Completion relies on provider advancement, not calendar dates.
                result=('W' if score>oscore else 'L' if score<oscore else 'T') if score is not None and oscore is not None else ''
                out['weekly'].append({'week':w,'score':score,'oppScore':oscore,'result':result,'confirmed':bool(result),'preliminary':False,'opp':str((opp or {}).get('roster_id',''))})
                for pid,pts in (mm.get('players_points') or {}).items():history.setdefault(str(pid),{})[str(w)]=pts
        for pid in mine.get('players',[]):
            pid=str(pid); player=directory.get(pid) or {}; hist=history.get(pid,{})
            # Sleeper's documented API does not publish current projections; leave them absent.
            slot='Reserve' if pid in map(str,mine.get('reserve') or []) else 'Taxi' if pid in map(str,mine.get('taxi') or []) else 'Starter' if pid in map(str,mine.get('starters') or []) else 'Bench'
            vals=[float(v) for w,v in sorted(hist.items(),key=lambda x:int(x[0]))[-3:] if num(v) is not None]
            out['roster'].append({'playerId':pid,'player':player.get('full_name') or ' '.join(filter(None,[player.get('first_name'),player.get('last_name')])) or pid,'pos':'DEF' if player.get('position')=='DEF' else player.get('position') or '—','nfl':player.get('team') or '', 'slot':slot,'starterSlot':player.get('position') if slot=='Starter' else None,'currentProjection':None,'projectionWeek':week,'historicalScores':hist,'recentScores':vals,'ppg3':sum(vals)/len(vals) if vals else None,'injuryStatus':player.get('injury_status') or '','currentPoints':num(points.get(pid))})
        st=mine.get('settings') or {}; pf=fractional_points(st)
        out['user']={'wins':st.get('wins'),'losses':st.get('losses'),'pf':pf,'relativeIndex':None,'owner':row['team'],'leagueTeams':len(rosters)}
        out['standings']=[{'owner':next((u.get('display_name') for u in users if str(u.get('user_id'))==str(r.get('owner_id'))),str(r.get('roster_id'))),'wins':(r.get('settings') or {}).get('wins'),'losses':(r.get('settings') or {}).get('losses'),'pf':fractional_points(r.get('settings') or {})} for r in rosters]
        current=next((m for m in latest if str(m.get('roster_id'))==str(row['teamId'])),None)
        if current:
            opponent=next((m for m in latest if m.get('matchup_id')==current.get('matchup_id') and m is not current),None)
            out['matchup']={'week':week,'myScore':matchup_points(current),'oppScore':matchup_points(opponent or {}),'opp':str((opponent or {}).get('roster_id',''))}
        out['confirmedThroughWeek']=max([r['week'] for r in out['weekly'] if r['confirmed']]+[0])
        out['waiverAvailability']='Pool completo ainda não fornecido pela API documentada do Sleeper.'
        out['summary']={'totalPlayers':len(out['roster']),'starters':sum(p['slot']=='Starter' for p in out['roster'])}
        return out

    async def espn(self,c,row,credentials):
        # Credentials are an explicit per-UID admin-approved connection. Never global.
        headers={}
        if credentials:
            headers['Cookie']=f"SWID={credentials['SWID']}; espn_s2={credentials['espn_s2']}"
        url=f"https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/{row['season']}/segments/0/leagues/{row['leagueId']}"
        core=await self.get(c,url,headers=headers,params=[('view',v) for v in ['mSettings','mTeam','mRoster','mStandings','mStatus','mSchedule']])
        status=core.get('status') or {};week=max(1,min(18,int(status.get('currentMatchupPeriod') or core.get('scoringPeriodId') or 1)))
        teams=core.get('teams') or [];mine=next((t for t in teams if str(t.get('id'))==str(row['teamId'])),None)
        if not mine:raise HTTPException(422,'TEAM_NOT_IN_LEAGUE')
        out=league_base(row,(core.get('settings') or {}).get('name') or row['name'],row['team'],'—',week)
        score_settings=(core.get('settings') or {}).get('scoringSettings') or {}
        rec=next((num(x.get('points')) for x in score_settings.get('scoringItems',[]) if x.get('statId')==53),0)
        out['scoring']=('PPR' if rec==1 else 'Half PPR' if rec==.5 else 'Standard') if score_settings.get('scoringItems') else '—'
        positions={1:'QB',2:'RB',3:'WR',4:'TE',5:'K',16:'DEF'}
        for e in (mine.get('roster') or {}).get('entries',[]):
            p=(e.get('playerPoolEntry') or {}).get('player') or {};periods=p.get('stats') or [];hist={};proj=None
            for st in periods:
                if st.get('statSplitTypeId')!=1 or int(st.get('seasonId') or 0)!=int(row['season']):continue
                w=int(st.get('scoringPeriodId') or 0);pts=num(st.get('appliedTotal'))
                if st.get('statSourceId')==0 and 0<w<week and pts is not None:hist[str(w)]=pts
                if st.get('statSourceId')==1 and w==week and pts is not None:proj=pts
            vals=[hist[k] for k in sorted(hist,key=int)[-3:]];slot=e.get('lineupSlotId')
            out['roster'].append({'playerId':str(p.get('id') or e.get('playerId')),'player':p.get('fullName') or str(e.get('playerId')),'pos':positions.get(p.get('defaultPositionId'),'—'),'nfl':ESPN_TEAMS.get(p.get('proTeamId'),''),'slot':'Reserve' if slot==21 else 'Bench' if slot==20 else 'Starter','starterSlot':positions.get(p.get('defaultPositionId')),'currentProjection':proj,'projectionWeek':week,'historicalScores':hist,'recentScores':vals,'ppg3':sum(vals)/len(vals) if vals else None,'injuryStatus':p.get('injuryStatus') or ''})
        for m in core.get('schedule') or []:
            w=int(m.get('matchupPeriodId') or 0);home=m.get('home') or {};away=m.get('away') or {}
            if str(home.get('teamId'))!=str(row['teamId']) and str(away.get('teamId'))!=str(row['teamId']):continue
            me,opp=(home,away) if str(home.get('teamId'))==str(row['teamId']) else (away,home)
            score=num(me.get('totalPoints'));oscore=num(opp.get('totalPoints'));winner=m.get('winner')
            confirmed=winner in ('HOME','AWAY','TIE') and w<week
            result='T' if winner=='TIE' else 'W' if (winner=='HOME')==(me is home) else 'L'
            if confirmed:out['weekly'].append({'week':w,'score':score,'oppScore':oscore,'result':result,'confirmed':True,'opp':str(opp.get('teamId',''))})
            if w==week:out['matchup']={'week':week,'myScore':score,'oppScore':oscore,'opp':str(opp.get('teamId',''))}
        for t in teams:
            rec=(t.get('record') or {}).get('overall') or {};wins=rec.get('wins');losses=rec.get('losses')
            record={'owner':t.get('name') or ' '.join(filter(None,[t.get('location'),t.get('nickname')])) or str(t['id']),'wins':wins,'losses':losses,'pf':num(rec.get('pointsFor')),'winPct':(num(wins) or 0)/max(1,(num(wins) or 0)+(num(losses) or 0))}
            out['standings'].append(record)
            if t is mine:out['user']={**record,'leagueTeams':len(teams),'relativeIndex':None}
        out['confirmedThroughWeek']=max([r['week'] for r in out['weekly']]+[0])
        out['summary']={'totalPlayers':len(out['roster']),'starters':sum(p['slot']=='Starter' for p in out['roster'])}
        return out

ESPN_TEAMS={1:'ATL',2:'BUF',3:'CHI',4:'CIN',5:'CLE',6:'DAL',7:'DEN',8:'DET',9:'GB',10:'TEN',11:'IND',12:'KC',13:'LV',14:'LAR',15:'MIA',16:'MIN',17:'NE',18:'NO',19:'NYG',20:'NYJ',21:'PHI',22:'ARI',23:'PIT',24:'LAC',25:'SF',26:'SEA',27:'TB',28:'WAS',29:'CAR',30:'JAX',33:'BAL',34:'HOU'}
