"""Only provider-returned data is normalized. Missing projections stay null."""
from datetime import datetime, timezone
from urllib.parse import urlparse, parse_qs
import asyncio
import math
import time
import re
import json
from .player_stats import PublicPlayerStats, POSITIONS, NFL_TEAMS, sleeper_score, espn_score, name_key
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
    messages={'PRIVATE_LEAGUE_CONNECTION_REQUIRED':'Liga privada: conexão autorizada pendente.',
              'PROVIDER_UNAVAILABLE':'O provedor está indisponível. Tente atualizar novamente.',
              'PROVIDER_LEAGUE_NOT_FOUND':'Liga não encontrada no provedor.',
              'TEAM_NOT_IN_LEAGUE':'O time cadastrado não foi encontrado nesta liga.',
              'SEASON_NOT_CURRENT':'Esta liga pertence a uma temporada anterior.',
              'LEAGUE_SEASON_MISMATCH':'Confira a temporada cadastrada para esta liga.'}
    return dict(id=row['id'], platform=row['platform'], name=row.get('name') or row['platform'],
                team=row.get('team') or 'Selecionar time', loaded=False, scoring='—', roster=[], waivers=[],
                pendingReason=messages.get(row.get('lastError'), 'Liga privada: conexão autorizada pendente.' if status == 'private_pending' else 'Aguardando primeira atualização.'),
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
    cloud_enrichment=True
    def __init__(self,store=None):
        self._directory=None;self._directory_at=0;self._directory_lock=asyncio.Lock()
        self.store=store;self.player_stats=PublicPlayerStats(store)

    async def directory(self,client):
        # Sleeper requests that its large public directory be cached for 24 hours.
        if self._directory is not None and time.monotonic()-self._directory_at<86400:return self._directory
        async with self._directory_lock:
            if self._directory is None or time.monotonic()-self._directory_at>=86400:
                if self.store:
                    try:cached=self.store.public_cache('sleeper-directory-rc4')
                    except Exception:cached=None
                    if cached and time.time()-cached.get('savedEpoch',0)<86400:
                        self._directory=cached['payload']['players'];self._directory_at=time.monotonic();return self._directory
                value=await self.get(client,'https://api.sleeper.app/v1/players/nfl')
                if not isinstance(value,dict):raise HTTPException(502,'PROVIDER_UNAVAILABLE')
                fields=('full_name','first_name','last_name','position','fantasy_positions','team','espn_id','active','age','injury_status','injury_body_part','injury_notes','depth_chart_order')
                value={str(pid):{k:p[k] for k in fields if k in p} for pid,p in value.items() if isinstance(p,dict)}
                self._directory=value;self._directory_at=time.monotonic()
                if self.store:
                    try:self.store.save_public_cache('sleeper-directory-rc4',{'players':value})
                    except Exception:pass
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

    async def sleeper(self,c,row):
        base=f"https://api.sleeper.app/v1/league/{row['leagueId']}"
        league,state,rosters,users=await asyncio.gather(self.get(c,base),self.get(c,'https://api.sleeper.app/v1/state/nfl'),self.get(c,base+'/rosters'),self.get(c,base+'/users'))
        if int(state.get('season') or 0)!=int(row['season']):raise HTTPException(409,'SEASON_NOT_CURRENT')
        if str(league.get('season',row['season']))!=str(row['season']):raise HTTPException(409,'LEAGUE_SEASON_MISMATCH')
        week=max(1,min(18,int(state.get('week') or state.get('display_week') or 1)))
        mine=next((r for r in rosters if str(r.get('roster_id'))==str(row['teamId'])),None)
        if not mine:raise HTTPException(422,'TEAM_NOT_IN_LEAGUE')
        directory=await self.directory(c)
        public_stats=await self.player_stats.get(c,row['season'],week)
        facts=(public_stats or {}).get('players',{})
        by_name={(name_key(p['name']),p['pos'],p['nfl']):p for p in facts.values()}
        defenses={p['nfl']:p for p in facts.values() if p['pos']=='DEF'}
        settings=league.get('scoring_settings') or {};ppr=num(settings.get('rec')) or 0
        owners={str(u.get('user_id')):u for u in users}
        names={str(r['roster_id']):sleeper_team_name(owners.get(str(r.get('owner_id')),{}),r['roster_id']) for r in rosters}
        team=names[str(row['teamId'])]
        out=league_base(row,league.get('name') or row['name'],team,('PPR' if ppr==1 else 'Half PPR' if ppr==.5 else 'Standard') if settings else '—',week)
        out['season']=row['season'];out['scoringSettings']=settings;out['rosterPositions']=league.get('roster_positions') or []
        out['dynasty']=(league.get('settings') or {}).get('type') in (1,2)
        out['teamLogos']={names[str(r['roster_id'])]:sleeper_avatar(owners.get(str(r.get('owner_id')),{})) for r in rosters}
        out['teamLogos']={k:v for k,v in out['teamLogos'].items() if v}
        out['teams']=[{'id':str(r['roster_id']),'name':names[str(r['roster_id'])],'logo':out['teamLogos'].get(names[str(r['roster_id'])],'')} for r in rosters]
        limiter=asyncio.Semaphore(4)
        async def matches(w):
            async with limiter:return w,await self.get(c,base+f'/matchups/{w}')
        rounds=dict(await asyncio.gather(*(matches(w) for w in range(1,week+1))))
        history={};latest=rounds.get(week) or [];points={str(m.get('roster_id')):m.get('players_points') or {} for m in latest}
        completed=min(week-1,int((league.get('settings') or {}).get('last_scored_leg',week-1)))
        for w,rows in rounds.items():
            scores=[matchup_points(m) for m in rows];valid=[p for p in scores if p is not None];avg=sum(valid)/len(valid) if valid else None
            for m in rows:
                if w<=completed:
                    for pid,pts in (m.get('players_points') or {}).items():
                        if num(pts) is not None:history.setdefault(str(pid),{})[str(w)]=num(pts)
            me=next((m for m in rows if str(m.get('roster_id'))==str(row['teamId'])),None)
            if not me:continue
            opp=sleeper_opponent(rows,me);score=matchup_points(me);oscore=matchup_points(opp or {})
            if w<=completed:
                result=('W' if score>oscore else 'L' if score<oscore else 'T') if score is not None and oscore is not None else ''
                out['weekly'].append({'week':w,'score':score,'oppScore':oscore,'result':result,'confirmed':bool(result),'preliminary':False,'opp':names.get(str((opp or {}).get('roster_id')),''),'leagueAvg':avg})
        owned={str(pid) for r in rosters for key in ('players','reserve','taxi') for pid in (r.get(key) or [])}
        out['_allRosters']=[];out['teamSummaries']=[]
        def player(pid,roster=None):
            pid=str(pid);p=directory.get(pid) or {};pos=p.get('position') or '—';nfl=p.get('team') or (pid if pos=='DEF' else '')
            name=p.get('full_name') or ' '.join(filter(None,[p.get('first_name'),p.get('last_name')])) or pid
            fact=facts.get(str(p.get('espn_id'))) or (defenses.get(nfl) if pos=='DEF' else by_name.get((name_key(name),pos,nfl))) or {}
            proj=sleeper_score(fact.get('projection'),settings,pos)
            hist={}
            for w,raw in (fact.get('history') or {}).items():
                scored=sleeper_score(raw,settings,pos)
                if scored is not None and int(w)<=completed:hist[w]=scored
            hist.update(history.get(pid,{}))
            slot='Bench';starter_slot=None
            if roster:
                if pid in [str(p) for p in roster.get('reserve') or []]:slot='Reserve'
                elif pid in [str(p) for p in roster.get('taxi') or []]:slot='Taxi'
                elif pid in [str(p) for p in roster.get('starters') or []]:
                    slot='Starter';index=[str(p) for p in roster.get('starters') or []].index(pid)
                    slots=[p for p in out['rosterPositions'] if p!='BN']
                    starter_slot=slots[index] if index<len(slots) else pos
            vals=[hist[w] for w in sorted(hist,key=int)[-3:]]
            current=num(points.get(str((roster or {}).get('roster_id')) ,{}).get(pid)) if roster else None
            return {'playerId':pid,'espnId':str(p.get('espn_id') or fact.get('id') or ''),'player':name,'pos':pos,'nfl':nfl,'slot':slot,'starterSlot':starter_slot,
              'currentProjection':proj,'projectionUnavailableReason':'Regras especiais da liga não cobertas pela fonte de projeção.' if fact.get('projection') and proj is None else '', 'projectionWeek':week,'projectionSource':'ESPN NFL • scoring da liga Sleeper' if proj is not None else '',
              'currentPoints':current,'historicalScores':hist,'recentScores':vals,'ppg3':sum(vals)/len(vals) if vals else None,
              'age':num(p.get('age')),'injuryStatus':p.get('injury_status') or '',
              'injuryBody':p.get('injury_body_part') or '','injuryNotes':p.get('injury_notes') or '',
              'lastWeekPoints':hist.get(str(week-1)),'lastPlayedWeek':max(map(int,hist)) if hist else None}
        for r in rosters:
            rid=str(r['roster_id']);team_players=[{**player(pid,r),'_team':names[rid],'_owner':names[rid]} for pid in dict.fromkeys((r.get('players') or [])+(r.get('reserve') or [])+(r.get('taxi') or [])) if str(pid)!='0']
            out['_allRosters']+=team_players
            summary=roster_summary(team_players);summary['team']=names[rid];summary['rosterId']=rid
            active_capacity=sum(p not in ('IR','TAXI') for p in out['rosterPositions'])
            summary['openActive']=max(0,active_capacity-summary['active']) if active_capacity else 0
            out['teamSummaries'].append(summary)
            if rid==str(row['teamId']):out['roster']=[{k:v for k,v in p.items() if not k.startswith('_')} for p in team_players];out['summary']=summary
            st=r.get('settings') or {};wins=num(st.get('wins'));losses=num(st.get('losses'));ties=num(st.get('ties')) or 0;games=(wins or 0)+(losses or 0)+ties;pf=fractional_points(st)
            record={'team':names[rid],'owner':names[rid],'wins':wins,'losses':losses,'ties':ties,'games':games,'pf':pf,'pa':fractional_points({'fpts':st.get('fpts_against'),'fpts_decimal':st.get('fpts_against_decimal')}),'ppg':pf/games if pf is not None and games else None,'winPct':((wins or 0)+ties/2)/games if games else 0}
            out['standings'].append(record)
            if rid==str(row['teamId']):out['user']={**record,'leagueTeams':len(rosters),'relativeIndex':None}
        # Directory minus every current roster, reserve and taxi is a real free-agent
        # universe. Availability is never inferred from ownership percentages.
        for pid,p in directory.items():
            if str(pid) in owned or p.get('position') not in ('QB','RB','WR','TE','K','DEF') or not (p.get('team') or (pid if p.get('position')=='DEF' else '')) or p.get('active') is False:continue
            out['waivers'].append({**player(pid),'available':True,'onRoster':False,'ownershipVerified':True,'availabilitySource':'Sleeper • rosters, IR e taxi atuais'})
        current=next((m for m in latest if str(m.get('roster_id'))==str(row['teamId'])),None)
        if current:
            opp=sleeper_opponent(latest,current);opp_id=str((opp or {}).get('roster_id',''));opp_name=names.get(opp_id,'')
            out['matchup']={'week':week,'myTeam':team,'oppTeam':opp_name,'opp':opp_name,'oppTeamId':opp_id,
              'myLogo':out['teamLogos'].get(team,''),'oppLogo':out['teamLogos'].get(opp_name,''),
              'myScore':matchup_points(current),'oppScore':matchup_points(opp or {}),'source':'Sleeper'}
        out['confirmedThroughWeek']=max([r['week'] for r in out['weekly'] if r['confirmed']]+[0])
        out['waiverAvailability']='Disponibilidade verificada contra todos os rosters, IR e taxi; regras de aquisição continuam sendo aplicadas pelo Sleeper.'
        out['waiverSource']='Sleeper API • disponibilidade atual • estatísticas NFL no scoring da liga'
        out['freeAgentCount']=len(out['waivers'])
        out['waiverConfig']={'source':'Sleeper API','priority':(mine.get('settings') or {}).get('waiver_position'),'faabBudget':(league.get('settings') or {}).get('waiver_budget'),'faabUsed':(mine.get('settings') or {}).get('waiver_budget_used')}
        out['transactions']=await self.sleeper_transactions(c,base,week,directory,names)
        return finish_league(out)

    async def sleeper_transactions(self,c,base,week,directory,names):
        result=[]
        for w in range(max(1,week-1),week+1):
            try:rows=await self.get(c,base+f'/transactions/{w}')
            except HTTPException:continue
            if not isinstance(rows,list):continue
            for t in rows:
                if t.get('status')!='complete':continue
                for field,action in [('adds','ADD'),('drops','DROP')]:
                    for pid,rid in (t.get(field) or {}).items():
                        p=directory.get(str(pid),{});name=p.get('full_name') or ' '.join(filter(None,[p.get('first_name'),p.get('last_name')])) or str(pid)
                        ms=t.get('status_updated') or t.get('created')
                        result.append({'id':str(t.get('transaction_id',''))+'-'+field+'-'+str(pid),'Player':name,'Action':action,'Type':t.get('type',''),'Team':names.get(str(rid),''),'Owner':names.get(str(rid),''),'Week':w,'at':datetime.fromtimestamp(ms/1000,timezone.utc).isoformat() if isinstance(ms,(int,float)) else ''})
        return sorted(result,key=lambda t:t['at'],reverse=True)[:100]

    async def espn(self,c,row,credentials):
        headers={'Cookie':f"SWID={credentials['SWID']}; espn_s2={credentials['espn_s2']}"} if credentials else {}
        url=f"{BASE_ESPN}/{row['season']}/segments/0/leagues/{row['leagueId']}"
        views=['mSettings','mTeam','mRoster','mStandings','mStatus','mMatchupScore','mScoreboard']
        core=await self.get(c,url,headers=headers,params=[('view',v) for v in views])
        if core.get('seasonId') and int(core['seasonId'])!=int(row['season']):raise HTTPException(409,'LEAGUE_SEASON_MISMATCH')
        status=core.get('status') or {};week=max(1,min(18,int(core.get('scoringPeriodId') or status.get('currentMatchupPeriod') or 1)))
        # mRoster defaults to the last completed scoring period. Explicitly request
        # the operational period so projections and lineup locks follow this week.
        core=await self.get(c,url,headers=headers,params=[('view',v) for v in views]+[('scoringPeriodId',week)])
        teams=core.get('teams') or [];mine=next((t for t in teams if str(t.get('id'))==str(row['teamId'])),None)
        if not mine:raise HTTPException(422,'TEAM_NOT_IN_LEAGUE')
        names={str(t['id']):espn_team_name(t) for t in teams};team=names[str(row['teamId'])]
        score_settings=(core.get('settings') or {}).get('scoringSettings') or {};items=score_settings.get('scoringItems') or []
        reception=next((num(x.get('points')) for x in items if x.get('statId')==53),0)
        scoring=('PPR' if reception==1 else 'Half PPR' if reception==.5 else 'Standard') if items else '—'
        out=league_base(row,(core.get('settings') or {}).get('name') or row['name'],team,scoring,week)
        out['season']=row['season'];out['scoringSettings']=score_settings
        out['teamLogos']={names[str(t['id'])]:safe_logo(t.get('logo')) for t in teams if safe_logo(t.get('logo'))}
        out['teams']=[{'id':str(t['id']),'name':names[str(t['id'])],'logo':out['teamLogos'].get(names[str(t['id'])],'')} for t in teams]
        public=(await self.player_stats.get(c,row['season'],week) or {}).get('players',{})
        def player(entry):
            pool=entry.get('playerPoolEntry') or entry;p=pool.get('player') or {};pid=str(p.get('id') or entry.get('playerId') or pool.get('id'))
            fact=public.get(pid) or {};hist={};proj=None;current=None
            for w,stats in (fact.get('history') or {}).items():
                value=espn_score(stats,items)
                if value is not None:hist[w]=value
            proj=espn_score(fact.get('projection'),items)
            for st in p.get('stats') or []:
                if st.get('statSplitTypeId')!=1 or int(st.get('seasonId') or 0)!=int(row['season']):continue
                w=int(st.get('scoringPeriodId') or 0);value=num(st.get('appliedTotal'))
                if value is None:value=espn_score(st.get('stats'),items)
                if st.get('statSourceId')==0 and 0<w<week and value is not None:hist[str(w)]=value
                if st.get('statSourceId')==1 and w==week and value is not None:proj=value
                if st.get('statSourceId')==0 and w==week:current=value
            vals=[hist[w] for w in sorted(hist,key=int)[-3:]];slot=entry.get('lineupSlotId',20)
            return {'playerId':pid,'player':p.get('fullName') or fact.get('name') or pid,'pos':POSITIONS.get(p.get('defaultPositionId'),'—'),'nfl':NFL_TEAMS.get(p.get('proTeamId'),''),
              'slot':'Reserve' if slot==21 else 'Bench' if slot==20 else 'Starter','starterSlot':ESPN_SLOTS.get(slot),
              'eligibleSlots':p.get('eligibleSlots') or [],'currentProjection':proj,'projectionWeek':week,'projectionSource':'ESPN • scoring da liga' if proj is not None else '',
              'currentPoints':current,'historicalScores':hist,'recentScores':vals,'ppg3':sum(vals)/len(vals) if vals else None,
              'injuryStatus':p.get('injuryStatus') or entry.get('injuryStatus') or '',
              'lastWeekPoints':hist.get(str(week-1)),'lastPlayedWeek':max(map(int,hist)) if hist else None,
              'lineupLocked':pool.get('lineupLocked') is True,'rosterLocked':pool.get('rosterLocked') is True}
        out['_allRosters']=[];out['teamSummaries']=[]
        for t in teams:
            roster=[{**player(e),'_team':names[str(t['id'])],'_owner':names[str(t['id'])]} for e in (t.get('roster') or {}).get('entries',[])]
            out['_allRosters']+=roster;summary=roster_summary(roster);summary['team']=names[str(t['id'])]
            capacity=sum(int(n) for sid,n in (((core.get('settings') or {}).get('rosterSettings') or {}).get('lineupSlotCounts') or {}).items() if str(sid)!='21')
            summary['openActive']=max(0,capacity-summary['active']) if capacity else 0
            out['teamSummaries'].append(summary)
            if t is mine:out['roster']=[{k:v for k,v in p.items() if not k.startswith('_')} for p in roster];out['summary']=summary
            record=(t.get('record') or {}).get('overall') or {};wins=num(record.get('wins'));losses=num(record.get('losses'));ties=num(record.get('ties')) or 0;games=(wins or 0)+(losses or 0)+ties;pf=num(record.get('pointsFor'))
            normalized={'owner':names[str(t['id'])],'team':names[str(t['id'])],'wins':wins,'losses':losses,'ties':ties,'games':games,'pf':pf,'pa':num(record.get('pointsAgainst')),'ppg':pf/games if pf is not None and games else None,'winPct':((wins or 0)+ties/2)/games if games else 0}
            out['standings'].append(normalized)
            if t is mine:out['user']={**normalized,'leagueTeams':len(teams),'relativeIndex':None}
        for m in core.get('schedule') or []:
            w=int(m.get('matchupPeriodId') or 0);home=m.get('home') or {};away=m.get('away') or {}
            if str(home.get('teamId'))!=str(row['teamId']) and str(away.get('teamId'))!=str(row['teamId']):continue
            me,opp=(home,away) if str(home.get('teamId'))==str(row['teamId']) else (away,home)
            score=num(me.get('totalPoints'));oscore=num(opp.get('totalPoints'));winner=m.get('winner');opp_name=names.get(str(opp.get('teamId')),'')
            confirmed=winner in ('HOME','AWAY','TIE') and w<week
            result='T' if winner=='TIE' else 'W' if (winner=='HOME')==(me is home) else 'L'
            if confirmed:
                all_scores=[num(side.get('totalPoints')) for match in core.get('schedule',[]) if match.get('matchupPeriodId')==w for side in [match.get('home') or {},match.get('away') or {}]]
                all_scores=[v for v in all_scores if v is not None]
                out['weekly'].append({'week':w,'score':score,'oppScore':oscore,'result':result,'confirmed':True,'opp':opp_name,'leagueAvg':sum(all_scores)/len(all_scores) if all_scores else None})
            if w==week:
                out['matchup']={'week':week,'myTeam':team,'oppTeam':opp_name,'opp':opp_name,'oppTeamId':str(opp.get('teamId','')),
                 'myLogo':out['teamLogos'].get(team,''),'oppLogo':out['teamLogos'].get(opp_name,''),
                 'myScore':first_number(me.get('totalPointsLive'),score),'oppScore':first_number(opp.get('totalPointsLive'),oscore),
                 'myProjection':first_number(me.get('totalProjectedPointsLive'),me.get('totalProjectedPoints')),
                 'oppProjection':first_number(opp.get('totalProjectedPointsLive'),opp.get('totalProjectedPoints')),'source':'ESPN • placar e projeção do provedor'}
        owned={p['playerId'] for p in out['_allRosters']}
        filters={'players':{'limit':2000,'sortPercOwned':{'sortAsc':False,'sortPriority':1},'filterStatsForTopScoringPeriodIds':{'value':week,'additionalValue':[f'00{row["season"]}']},'filterStatsForExternalIds':{'value':[f'{row["season"]}{week}']}}}
        try:
            pool=await self.get(c,url,headers={**headers,'X-Fantasy-Filter':json.dumps(filters)},params=[('view','kona_player_info'),('scoringPeriodId',week)])
            for entry in pool.get('players') or []:
                pid=str(entry.get('id') or (entry.get('player') or {}).get('id'));on_team=entry.get('onTeamId')
                if pid in owned or on_team not in (None,0,-1) or entry.get('status') not in (None,'FREEAGENT','WAIVERS'):continue
                normalized=player({'playerPoolEntry':entry,'lineupSlotId':20})
                if normalized['pos'] in ('QB','RB','WR','TE','K','DEF'):out['waivers'].append({**normalized,'available':True,'ownershipVerified':True,'onRoster':False,'availabilitySource':'ESPN • pool e rosters atuais'})
            out['waiverAvailability']='Pool de jogadores livres/waivers retornado pela ESPN, cruzado com todos os rosters atuais.'
        except HTTPException:out['waiverAvailability']='Pool ESPN indisponível nesta consulta; nenhum jogador foi tratado como livre sem confirmação.'
        out['waiverSource']='ESPN API • pool da liga e scoring atual';out['freeAgentCount']=len(out['waivers'])
        out['confirmedThroughWeek']=max([r['week'] for r in out['weekly']]+[0])
        out['waiverConfig']={'source':'ESPN API','priority':mine.get('waiverRank'),'lastExecutionAt':status.get('waiverLastExecutionDate')}
        out['transactions']=await self.espn_transactions(c,url,headers,out,names,public,week)
        return finish_league(out)

    async def espn_transactions(self,c,url,headers,out,names,facts,week):
        try:raw=await self.get(c,url,headers=headers,params=[('view','mTransactions2')])
        except Exception:return []
        players={p['playerId']:p['player'] for p in out['_allRosters']+out['waivers']}
        players.update({pid:p['name'] for pid,p in facts.items() if pid not in players})
        result=[]
        for t in raw.get('transactions',[]):
            if t.get('status')!='EXECUTED' or t.get('isPending'):continue
            w=int(t.get('scoringPeriodId') or 0)
            if w<max(1,week-1):continue
            ms=t.get('processDate')
            at=datetime.fromtimestamp(ms/1000,timezone.utc).isoformat() if isinstance(ms,(int,float)) else ''
            for i,item in enumerate(t.get('items') or []):
                pid=str(item.get('playerId',''));action=item.get('type','')
                if action not in ('ADD','DROP','TRADE'):continue
                rid=item.get('toTeamId') if action in ('ADD','TRADE') else item.get('fromTeamId')
                name=players.get(pid)
                if not name:continue
                result.append({'id':str(t.get('id'))+'-'+str(i),'Player':name,'Action':action,
                  'Type':t.get('type',''),'Team':names.get(str(rid or t.get('teamId')),''),
                  'Week':w,'at':at})
        return sorted(result,key=lambda t:t['at'],reverse=True)[:100]

BASE_ESPN='https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons'
ESPN_TEAMS=NFL_TEAMS
ESPN_SLOTS={0:'QB',2:'RB',3:'FLEX',4:'WR',5:'FLEX',6:'TE',7:'SUPER_FLEX',16:'DEF',17:'K',23:'FLEX'}

def first_number(*values):return next((num(v) for v in values if num(v) is not None),None)

def safe_logo(value):
    text=str(value or '')
    try:
        url=urlparse(text)
        return text if url.scheme=='https' and url.hostname and not url.username and not url.password else ''
    except ValueError:return ''

def sleeper_team_name(owner,rid):
    return (owner.get('metadata') or {}).get('team_name') or owner.get('display_name') or f'Time {rid}'

def sleeper_avatar(owner):
    avatar=(owner.get('metadata') or {}).get('avatar') or owner.get('avatar')
    if not avatar:return ''
    if str(avatar).startswith('https://'):return safe_logo(avatar)
    return f'https://sleepercdn.com/avatars/{avatar}' if re.fullmatch(r'[A-Za-z0-9_-]+',str(avatar)) else ''

def sleeper_opponent(rows,current):
    if current.get('matchup_id') is None:return None
    return next((m for m in rows if m.get('matchup_id')==current.get('matchup_id') and str(m.get('roster_id'))!=str(current.get('roster_id'))),None)

def espn_team_name(team):
    return team.get('name') or ' '.join(filter(None,[team.get('location'),team.get('nickname')])) or f'Time {team["id"]}'

def roster_summary(players):
    projections=[p.get('currentProjection') for p in players if p['slot']=='Starter']
    return {'totalPlayers':len(players),'active':sum(p['slot'] not in ('Reserve','Taxi') for p in players),
      'starters':sum(p['slot']=='Starter' for p in players),'bench':sum(p['slot']=='Bench' for p in players),
      'reserve':sum(p['slot']=='Reserve' for p in players),'taxi':sum(p['slot']=='Taxi' for p in players),
      'projectedStarterCurrent':sum(projections) if projections and all(v is not None for v in projections) else None}

def finish_league(out):
    ranks=sorted((r for r in out['standings'] if r.get('pf') is not None),key=lambda r:r['pf'],reverse=True)
    if out['user'].get('pf') is not None:
        values=[r['pf'] for r in ranks];avg=sum(values)/len(values) if values else None
        out['user']['relativeIndex']=out['user']['pf']/avg*100 if avg else None
        out['user']['pfRank']=next((i+1 for i,r in enumerate(ranks) if r['team']==out['team']),None)
    out['dataCoverage']={'roster':len(out['roster']),'allRosters':len(out.get('_allRosters',[])),
      'logos':len(out.get('teamLogos',{})),'weeklyResults':len(out['weekly']),'freeAgents':len(out['waivers']),
      'playerProjections':sum(p['currentProjection'] is not None for p in out['roster']),
      'opponent':bool((out.get('matchup') or {}).get('oppTeam'))}
    return out

