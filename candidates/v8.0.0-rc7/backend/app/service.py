import hashlib
import time
from uuid import uuid4
from datetime import datetime, timezone
from fastapi import HTTPException
from .config import settings, MAX_LEAGUES_PER_USER
from .providers import empty_league
from .store import now
from .calendar import Calendar
from .news import News
from .enrichment import apply_calendar, notification_events
import asyncio

PUBLIC_FIELDS=('id','platform','leagueId','teamId','name','team','season','status','lastSuccessAt','lastCheckedAt','lastChangedAt','lastError','createdAt')

def public(row):
    return {k:row[k] for k in PUBLIC_FIELDS if k in row}

def league_quota(count):
    return {'registeredCount':count,'maxLeagues':MAX_LEAGUES_PER_USER,
            'remainingSlots':max(0,MAX_LEAGUES_PER_USER-count)}

class Service:
    def __init__(self,store,providers):
        self.store=store;self.providers=providers

    def owned(self,uid,lid):
        if not lid or '/' in lid:raise HTTPException(404,'LEAGUE_NOT_FOUND')
        row=self.store.get(uid,lid)
        if not row:raise HTTPException(404,'LEAGUE_NOT_FOUND')
        return row

    async def add(self,uid,data):
        inspected=await self.providers.inspect(data)
        # Same public league + followed team is idempotent per account.
        lid=hashlib.sha256(f'{data.platform}:{data.season}:{inspected["leagueId"]}:{inspected["teamId"]}'.encode()).hexdigest()[:32]
        row={**inspected,'id':lid,'platform':data.platform,'season':data.season,'createdAt':now(),'bindingVersion':uuid4().hex,'enabled':True}
        created=self.store.create(uid,lid,row)
        if created is None:raise HTTPException(409,'LEAGUE_LIMIT_REACHED')
        return public(self.store.get(uid,lid)),created

    async def sync(self,uid,lid):
        row=self.owned(uid,lid)
        if not self.store.claim_sync(uid,lid,settings().FCC_SYNC_MIN_SECONDS):
            row=self.owned(uid,lid)
            if row.get('status') in ('error','private_pending'):
                return {'ok':False,'status':row['status'],'error':row.get('lastError') or 'PROVIDER_UNAVAILABLE','league':public(row)}
            return {'ok':True,'status':'cached','league':public(row)}
        credentials=None
        try:
            if row.get('credentialSecret'):
                credentials=self.store.credentials(uid,lid,row['credentialSecret'])
            payload=await self.providers.fetch(row,credentials)
            if getattr(self.providers,'cloud_enrichment',False):
                calendar,news,_=await asyncio.gather(
                    Calendar(self.store).get(row['season'],int(payload['sourceAnalysisWeek'])),
                    News(self.store).get(payload.get('roster',[])),
                    self.providers.enrich_public(payload,row['season']),return_exceptions=True)
                if isinstance(calendar,dict):
                    apply_calendar(payload,calendar)
                    payload.setdefault('dataCoverage',{})['playerProjections']=sum(p.get('currentProjection') is not None for p in payload.get('roster',[]))
                if isinstance(news,list):payload['news']=news
            saved=self.store.save_payload(uid,lid,payload,row.get('bindingVersion'))
            if not saved:
                return {'ok':False,'status':'removed','error':'LEAGUE_NOT_FOUND'}
            result={'ok':True,'status':'unchanged' if isinstance(saved,dict) and not saved['changed'] else 'updated','league':public(self.owned(uid,lid))}
            if isinstance(saved,dict):result['changes']={k:saved[k] for k in ('changedBlocks','totalBlocks')}
            return result
        except HTTPException as e:
            code=e.detail if isinstance(e.detail,str) else 'PROVIDER_UNAVAILABLE'
        except Exception:
            code='PROVIDER_UNAVAILABLE'
        if not self.store.get(uid,lid):
            return {'ok':False,'status':'removed','error':'LEAGUE_NOT_FOUND'}
        # Keep the last valid data. Never reveal a provider response or secret.
        status='private_pending' if code=='PRIVATE_LEAGUE_CONNECTION_REQUIRED' else 'error'
        if not self.store.update_binding(uid,lid,row.get('bindingVersion'),{'status':status,'lastError':code,'lastErrorAt':now()}):
            return {'ok':False,'status':'removed','error':'LEAGUE_NOT_FOUND'}
        return {'ok':False,'status':status,'error':code,'league':public(self.owned(uid,lid))}

    def payload(self,uid):
        leagues=[];sources=[]
        bindings=self.store.list_leagues(uid)
        for row in bindings:
            p=self.store.read_payload(uid,row['id'],row)
            if p is None and row.get('revision'):
                # A storage failure is not an empty league. Let clients retain
                # their valid account cache instead of replacing it with blanks.
                raise HTTPException(503,'CLOUD_SNAPSHOT_UNAVAILABLE')
            if p:
                p={**p,'id':row['id'],'sourceUpdatedAt':row.get('lastCheckedAt') or row.get('lastSuccessAt') or p.get('sourceUpdatedAt','')}
                if row.get('status') in ('error','private_pending'):p['syncError']=row.get('lastError') or 'PROVIDER_UNAVAILABLE';p['freshness']='Última atualização válida; fonte indisponível.'
            else:p=empty_league(row,row.get('status','pending'))
            leagues.append(p)
            sources.append({'id':row['id'],'status':row.get('status'),'updatedAt':row.get('lastCheckedAt') or row.get('lastSuccessAt'),'changedAt':row.get('lastChangedAt'),'error':row.get('lastError','')})
        loaded=[l for l in leagues if l.get('loaded')]
        meta={'loadedCount':len(loaded),'pendingCount':len(leagues)-len(loaded),'combinedWins':sum(l.get('user',{}).get('wins') or 0 for l in loaded),'combinedLosses':sum(l.get('user',{}).get('losses') or 0 for l in loaded),
              'sourceAnalysisWeek':max([int(l.get('sourceAnalysisWeek') or 0) for l in loaded]+[0]),'historyThroughWeek':max([int(l.get('confirmedThroughWeek') or 0) for l in loaded]+[0]),'methodVersion':'v8.0.0-rc7-cloud-data',**league_quota(len(bindings))}
        # No inherited default league, account-independent snapshot or pending league.
        seasons=[int(r['season']) for r in bindings if r.get('season')]
        data={'season':max(seasons) if seasons else datetime.now(timezone.utc).year,'leagues':leagues,'meta':meta,'online':{'news':[],'nflWeeks':[]},'notificationEvents':[]}
        seen=set()
        for league in loaded:
            for item in league.get('news',[]):
                key=item.get('url') or item.get('title')
                if key and key not in seen:data['online']['news'].append(item);seen.add(key)
        data['online']['news'].sort(key=lambda n:n.get('publishedAt',''),reverse=True)
        calendar_version=0
        if loaded:
            cache=self.store.public_cache(Calendar.key(data['season'],meta['sourceAnalysisWeek']))
            if cache:
                data['online']['nflWeeks']=cache['payload'].get('weeks',[])
                data['online']['nflScheduleUpdatedAt']=cache['payload'].get('generatedAt','')
                calendar_version=cache.get('contentHash') or cache.get('savedEpoch',0)
        events=notification_events(loaded,data['online']['nflWeeks'])
        data['notificationEvents']=events
        versions=sorted((r['id'],r.get('bindingVersion',''),r.get('revision',''),r.get('status',''),r.get('lastError','')) for r in bindings)
        version=hashlib.sha256(repr((uid,versions,calendar_version)).encode()).hexdigest()
        return {'ok':True,'schema':'fcc-data-v8','userId':uid,'generatedAt':now(),'dataVersion':version,
                'registrations':[public(r) for r in bindings],'data':data,'sources':sources,'notificationEvents':events}

    def schedule_context(self,uid):
        bindings=self.store.list_leagues(uid)
        seasons=[int(r['season']) for r in bindings if r.get('season')]
        season=max(seasons) if seasons else datetime.now(timezone.utc).year
        weeks=[]
        for row in bindings:
            if int(row.get('season') or 0)!=season:continue
            week=int(row.get('sourceAnalysisWeek') or 0)
            if not week and row.get('revision'):
                # Old bindings migrate on their next successful synchronization.
                payload=self.store.read_payload(uid,row['id'],row) or {}
                week=int(payload.get('sourceAnalysisWeek') or 0)
            if week:weeks.append(week)
        return season,max(weeks+[0])
