import hashlib
import time
from uuid import uuid4
from datetime import datetime, timezone
from fastapi import HTTPException
from .config import settings
from .providers import empty_league
from .store import now
from .calendar import Calendar

PUBLIC_FIELDS=('id','platform','leagueId','teamId','name','team','season','status','lastSuccessAt','lastError','createdAt')

def public(row):
    return {k:row[k] for k in PUBLIC_FIELDS if k in row}

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
        created=self.store.create(uid,lid,row,settings().FCC_MAX_LEAGUES)
        if created is None:raise HTTPException(409,'LEAGUE_LIMIT_REACHED')
        return public(self.store.get(uid,lid)),created

    async def sync(self,uid,lid):
        row=self.owned(uid,lid)
        if not self.store.claim_sync(uid,lid,settings().FCC_SYNC_MIN_SECONDS):
            return {'ok':True,'status':'cached','league':public(row)}
        credentials=None
        try:
            if row.get('credentialSecret'):
                credentials=self.store.credentials(uid,lid,row['credentialSecret'])
            payload=await self.providers.fetch(row,credentials)
            if not self.store.save_payload(uid,lid,payload,row.get('bindingVersion')):
                return {'ok':False,'status':'removed','error':'LEAGUE_NOT_FOUND'}
            return {'ok':True,'status':'updated','league':public(self.owned(uid,lid))}
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
        for row in self.store.list_leagues(uid):
            p=self.store.read_payload(uid,row['id'],row)
            if p:
                p={**p,'id':row['id']}
                if row.get('status')=='error':p['syncError']=row.get('lastError') or 'PROVIDER_UNAVAILABLE';p['freshness']='Última atualização válida; fonte indisponível.'
            else:p=empty_league(row,row.get('status','pending'))
            leagues.append(p)
            sources.append({'id':row['id'],'status':row.get('status'),'updatedAt':row.get('lastSuccessAt'),'error':row.get('lastError','')})
        loaded=[l for l in leagues if l.get('loaded')]
        meta={'loadedCount':len(loaded),'pendingCount':len(leagues)-len(loaded),'combinedWins':sum(l.get('user',{}).get('wins') or 0 for l in loaded),'combinedLosses':sum(l.get('user',{}).get('losses') or 0 for l in loaded),
              'sourceAnalysisWeek':max([int(l.get('sourceAnalysisWeek') or 0) for l in loaded]+[0]),'historyThroughWeek':max([int(l.get('confirmedThroughWeek') or 0) for l in loaded]+[0]),'methodVersion':'v8.0.0-rc1-user-accounts'}
        # No inherited default league, account-independent snapshot or pending league.
        seasons=[int(r['season']) for r in self.store.list_leagues(uid) if r.get('season')]
        data={'season':max(seasons) if seasons else datetime.now(timezone.utc).year,'leagues':leagues,'meta':meta,'online':{'news':[],'nflWeeks':[]},'notificationEvents':[]}
        if loaded:
            cache=self.store.public_cache(Calendar.key(data['season'],meta['sourceAnalysisWeek']))
            if cache:data['online']['nflWeeks']=cache['payload'].get('weeks',[])
        return {'ok':True,'schema':'fcc-data-v8','userId':uid,'generatedAt':now(),'data':data,'sources':sources,'notificationEvents':[]}
