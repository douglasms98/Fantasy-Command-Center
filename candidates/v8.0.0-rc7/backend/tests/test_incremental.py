"""TEST_ONLY Firestore double checks storage behavior, UID scope and migration."""
from copy import deepcopy
import gzip
import json
import time
from types import SimpleNamespace
from datetime import datetime, timezone, timedelta
from app.store import Store
from app import store as storage
from app.payload_blocks import split, join

class Ref:
    def __init__(self, db, path): self.db, self.path, self.id = db, path, path.split('/')[-1]
    def collection(self, name): return Collection(self.db, self.path+'/'+name)
    def get(self, transaction=None):
        self.db.reads.append(self.path)
        data=deepcopy(self.db.rows.get(self.path))
        return SimpleNamespace(id=self.id, exists=data is not None, reference=self, to_dict=lambda:data)
    def set(self, value, merge=False):
        self.db.writes.append(self.path)
        self.db.rows[self.path]={**self.db.rows.get(self.path,{}),**deepcopy(value)} if merge else deepcopy(value)
    def update(self, value):
        assert self.path in self.db.rows
        self.set(value,merge=True)
    def delete(self): self.db.rows.pop(self.path,None)

class Collection:
    def __init__(self, db, path): self.db,self.path=db,path
    def document(self, name): return Ref(self.db,self.path+'/'+name)
    def stream(self):
        keys=[k for k in self.db.rows if k.startswith(self.path+'/') and k.count('/')==self.path.count('/')+1]
        return [Ref(self.db,k).get() for k in keys]

class Batch:
    def __init__(self,db): self.db,self.pending=db,[]
    def set(self,ref,value,merge=False): self.pending.append((ref,value,merge))
    def commit(self):
        for ref,value,merge in self.pending: ref.set(value,merge)
        if self.db.after_commit:
            callback=self.db.after_commit;self.db.after_commit=None;callback()

class DB:
    def __init__(self): self.rows={};self.reads=[];self.writes=[];self.after_commit=None
    def collection(self,name): return Collection(self,name)
    def batch(self): return Batch(self)
    def transaction(self): return SimpleNamespace(set=lambda ref,v,merge=False:ref.set(v,merge), update=lambda ref,v:ref.update(v), delete=lambda ref:ref.delete())
    def get_all(self,refs): return [ref.get() for ref in refs]
    def recursive_delete(self,ref):
        for key in list(self.rows):
            if key==ref.path or key.startswith(ref.path+'/'): del self.rows[key]


def repo(monkeypatch):
    monkeypatch.setattr(storage.firestore,'transactional',lambda fn:fn)
    s=Store.__new__(Store);s.db=DB()
    for uid in ('TEST_ONLY_A','TEST_ONLY_B'):
        s.user(uid).set({'leagueCount':1})
        s.league(uid,'TEST_ONLY_L').set({'id':'TEST_ONLY_L','bindingVersion':uid+'_GEN1','season':2026,'status':'registered','platform':'Sleeper'})
    return s


def payload():
    return {'loaded':True,'sourceAnalysisWeek':6,'sourceUpdatedAt':'TEST_ONLY_TIME',
        'roster':[{'playerId':'TEST_ONLY_P','currentProjection':12}],
        'waivers':[{'playerId':f'TEST_ONLY_{i}','currentProjection':i%20} for i in range(800)],
        'weekly':[{'week':1,'score':100}],'standings':[],'user':{}}


def test_one_player_update_writes_one_shard_and_keeps_the_other_sections(monkeypatch):
    s=repo(monkeypatch);p=payload();uid='TEST_ONLY_A';gen=uid+'_GEN1';lid='TEST_ONLY_L'
    first=s.save_payload(uid,lid,p,gen)
    assert first['changed'] and first['totalBlocks']<=20
    original=s.get(uid,lid)['revision'];s.db.writes.clear()
    p['waivers'][77]['currentProjection']=99
    result=s.save_payload(uid,lid,p,gen)
    assert result['changedBlocks']==1
    assert len([x for x in s.db.writes if '/blocks/' in x])==1
    assert original!=s.get(uid,lid)['revision']
    with storage._CACHE_LOCK: storage._PAYLOAD_CACHE.clear();storage._CACHE_BYTES=0
    got=s.read_payload(uid,lid,s.get(uid,lid))
    assert got['waivers']==p['waivers'] and got['roster']==p['roster']


def test_rechecking_unchanged_data_has_no_new_snapshot_or_block_writes(monkeypatch):
    s=repo(monkeypatch);uid='TEST_ONLY_A';gen=uid+'_GEN1';lid='TEST_ONLY_L';p=payload()
    s.save_payload(uid,lid,p,gen);revision=s.get(uid,lid)['revision'];s.db.writes.clear()
    p['sourceUpdatedAt']='TEST_ONLY_NEW_TIME'
    result=s.save_payload(uid,lid,p,gen)
    assert result['changed'] is False and result['changedBlocks']==0
    assert s.get(uid,lid)['revision']==revision
    assert not any('/blocks/' in x or '/revisions/' in x for x in s.db.writes)
    assert s.get(uid,lid)['lastCheckedAt']


def test_account_scope_and_rebinding_cannot_reuse_private_objects(monkeypatch):
    s=repo(monkeypatch);lid='TEST_ONLY_L'
    for uid in ('TEST_ONLY_A','TEST_ONLY_B'):
        p=payload();p['roster'][0]['playerId']=uid
        s.save_payload(uid,lid,p,uid+'_GEN1')
    assert s.read_payload('TEST_ONLY_B',lid,s.get('TEST_ONLY_B',lid))['roster'][0]['playerId']=='TEST_ONLY_B'
    assert s.read_payload('TEST_ONLY_B',lid,s.get('TEST_ONLY_A',lid)) is None
    uid='TEST_ONLY_A';old=s.get(uid,lid);s.league(uid,lid).update({'bindingVersion':uid+'_GEN2','revision':''})
    assert s.save_payload(uid,lid,payload(),uid+'_GEN1') is False
    s.save_payload(uid,lid,payload(),uid+'_GEN2')
    assert s.read_payload(uid,lid,s.get(uid,lid))['waivers']==payload()['waivers']
    assert old['revision']!=s.get(uid,lid)['revision']


def test_stale_sync_cleanup_does_not_delete_readded_account_data(monkeypatch):
    s=repo(monkeypatch);uid='TEST_ONLY_A';lid='TEST_ONLY_L'
    def readd(): s.league(uid,lid).set({'id':lid,'bindingVersion':'TEST_ONLY_NEW','season':2026})
    s.db.after_commit=readd
    assert s.save_payload(uid,lid,payload(),uid+'_GEN1') is False
    assert s.get(uid,lid)['bindingVersion']=='TEST_ONLY_NEW'
    assert not any('/blocks/' in key for key in s.db.rows)
    assert s.save_payload(uid,lid,payload(),'TEST_ONLY_NEW')['changed']


def test_legacy_snapshot_remains_readable_until_next_successful_sync(monkeypatch):
    s=repo(monkeypatch);uid='TEST_ONLY_A';lid='TEST_ONLY_L';p=payload()
    revision=s.league(uid,lid).collection('revisions').document('TEST_ONLY_LEGACY')
    revision.set({'chunks':1,'createdAt':datetime.now(timezone.utc).isoformat()})
    revision.collection('chunks').document('0').set({'data':gzip.compress(json.dumps(p).encode())})
    s.league(uid,lid).update({'revision':revision.id})
    assert s.read_payload(uid,lid,s.get(uid,lid))==p
    result=s.save_payload(uid,lid,p,uid+'_GEN1');assert result['changed']
    assert revision.get().exists
    assert s.read_payload(uid,lid,s.get(uid,lid))['roster']==p['roster']


def test_daily_cleanup_keeps_shared_blocks_of_current_snapshot(monkeypatch):
    s=repo(monkeypatch);uid='TEST_ONLY_A';lid='TEST_ONLY_L';gen=uid+'_GEN1';p=payload()
    s.save_payload(uid,lid,p,gen);old=s.get(uid,lid)['revision']
    oldref=s.league(uid,lid).collection('revisions').document(old)
    oldref.update({'createdAt':(datetime.now(timezone.utc)-timedelta(days=3)).isoformat()})
    for row in s.league(uid,lid).collection('blocks').stream(): row.reference.update({'createdEpoch':time.time()-3*86400})
    p['waivers'][1]['currentProjection']=101;s.save_payload(uid,lid,p,gen)
    s.collect_payloads(uid,lid,gen)
    assert not oldref.get().exists
    with storage._CACHE_LOCK: storage._PAYLOAD_CACHE.clear();storage._CACHE_BYTES=0
    assert s.read_payload(uid,lid,s.get(uid,lid))['waivers']==p['waivers']


def test_public_calendar_timestamp_does_not_invalidate_user_data(monkeypatch):
    s=repo(monkeypatch);s.save_public_cache('TEST_ONLY',{'games':[],'generatedAt':'TEST_ONLY_1'})
    a=s.public_cache('TEST_ONLY')['contentHash']
    s.save_public_cache('TEST_ONLY',{'games':[],'generatedAt':'TEST_ONLY_2'})
    assert s.public_cache('TEST_ONLY')['contentHash']==a
    s.save_public_cache('TEST_ONLY',{'games':[{'live':True}],'generatedAt':'TEST_ONLY_2'})
    assert s.public_cache('TEST_ONLY')['contentHash']!=a


def test_shard_round_trip_preserves_duplicate_entries_and_order():
    p={'waivers':[{'playerId':'TEST_ONLY_DUP','currentProjection':i} for i in range(140)]}
    manifest,objects=split(p)
    assert join(manifest,objects)==p


def test_sync_response_and_app_version_distinguish_check_from_real_change(monkeypatch):
    import asyncio
    from app.service import Service
    s=repo(monkeypatch);uid='TEST_ONLY_A';lid='TEST_ONLY_L';p=payload();p['season']=2026
    class Provider:
        async def fetch(self,*args): return deepcopy(p)
    svc=Service(s,Provider())
    result=asyncio.run(svc.sync(uid,lid));assert result['status']=='updated'
    before=svc.payload(uid)['dataVersion']
    s.league(uid,lid).update({'lastAttemptEpoch':0})
    p['sourceUpdatedAt']='TEST_ONLY_RECHECK'
    result=asyncio.run(svc.sync(uid,lid))
    assert result['status']=='unchanged' and result['changes']['changedBlocks']==0
    assert svc.payload(uid)['dataVersion']==before
    assert svc.payload(uid)['sources'][0]['updatedAt']==s.get(uid,lid)['lastCheckedAt']
    s.league(uid,lid).update({'lastAttemptEpoch':0})
    p['roster'][0]['currentProjection']=18
    assert asyncio.run(svc.sync(uid,lid))['status']=='updated'
    assert svc.payload(uid)['dataVersion']!=before


def test_cleanup_failure_preserves_new_valid_data(monkeypatch):
    s=repo(monkeypatch)
    s.collect_payloads=lambda *a:(_ for _ in ()).throw(RuntimeError('TEST_ONLY_STORAGE_FAILURE'))
    result=s.save_payload('TEST_ONLY_A','TEST_ONLY_L',payload(),'TEST_ONLY_A_GEN1')
    assert result['changed'] and s.get('TEST_ONLY_A','TEST_ONLY_L')['status']=='ready'
    assert s.get('TEST_ONLY_A','TEST_ONLY_L')['blocksGcEpoch']==0
