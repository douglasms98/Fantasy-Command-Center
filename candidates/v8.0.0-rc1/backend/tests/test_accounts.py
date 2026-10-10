"""TEST_ONLY fixtures, never packaged as application league data."""
from copy import deepcopy
import time
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from app import main
from app.security import Principal, principal
from app.providers import LeagueInput

class Memory:
    def __init__(self):self.rows={};self.data={};self.profiles={};self.limits={};self.cache={}
    def profile(self,uid,email):self.profiles[uid]={'uid':uid,'email':email}
    def list_leagues(self,uid):return [deepcopy(v) for (u,l),v in self.rows.items() if u==uid]
    def get(self,uid,lid):return deepcopy(self.rows.get((uid,lid)))
    def put(self,uid,lid,row):self.rows[(uid,lid)].update(row)
    def create(self,uid,lid,row,limit):
        if (uid,lid) in self.rows:return False
        if len(self.list_leagues(uid))>=limit:return None
        self.rows[(uid,lid)]=deepcopy(row);return True
    def remove(self,uid,lid):self.rows.pop((uid,lid),None);self.data.pop((uid,lid),None)
    def read_payload(self,uid,lid,row):return deepcopy(self.data.get((uid,lid)))
    def update_binding(self,uid,lid,version,row):
        current=self.rows.get((uid,lid))
        if not current or current.get('bindingVersion')!=version:return False
        current.update(row);return True
    def save_payload(self,uid,lid,p,version):
        if not self.update_binding(uid,lid,version,dict(status='ready',lastSuccessAt='TEST_ONLY',revision='TEST_ONLY')):return False
        self.data[(uid,lid)]=deepcopy(p);return True
    def claim_sync(self,uid,lid,seconds):
        key=(uid,lid);last=self.rows[key].get('lastAttemptEpoch',0)
        if time.time()-last<seconds:return False
        self.rows[key]['lastAttemptEpoch']=time.time();return True
    def throttle(self,key,limit,seconds):self.limits[key]=self.limits.get(key,0)+1;return self.limits[key]<=limit
    def public_cache(self,key):return deepcopy(self.cache.get(key))
    def save_public_cache(self,key,payload):self.cache[key]={'savedEpoch':time.time(),'payload':deepcopy(payload)}

class FixtureProviders:
    fail=False
    async def inspect(self,data):return {'leagueId':data.provider_id(),'teamId':data.teamId or '1','team':'TEST_ONLY','name':data.name or 'TEST_ONLY','status':'registered'}
    async def fetch(self,row,credentials=None):
        if self.fail:raise HTTPException(502,'PROVIDER_UNAVAILABLE')
        return {'id':row['id'],'name':'TEST_ONLY','platform':row['platform'],'team':'TEST_ONLY','scoring':'PPR','loaded':True,'sourceAnalysisWeek':6,'analysisWeek':6,'projectionWeek':6,'weekly':[],'waivers':[],'roster':[], 'user':{'wins':0,'losses':0}}

@pytest.fixture
def env():
    repo=Memory();provider=FixtureProviders()
    main.app.dependency_overrides[main.store]=lambda:repo
    main.app.dependency_overrides[main.providers]=lambda:provider
    # We test real auth extraction separately; endpoint tests use explicit verified test tokens.
    def identify(authorization=None):
        raise AssertionError('not used')
    from fastapi import Header
    def user(authorization:str|None=Header(default=None)):
        if authorization not in ['Bearer TEST_ONLY_A','Bearer TEST_ONLY_B','Bearer TEST_ONLY_UNVERIFIED']:raise HTTPException(401,'LOGIN_REQUIRED')
        uid=authorization.split()[-1];return Principal(uid,uid+'@example.invalid',uid!='TEST_ONLY_UNVERIFIED')
    main.app.dependency_overrides[principal]=user
    with TestClient(main.app,base_url='https://fcc-api-322688211348.southamerica-east1.run.app') as client:yield client,repo,provider
    main.app.dependency_overrides.clear()

def hdr(uid='A'):return {'Authorization':'Bearer TEST_ONLY_'+uid}
def add(client,uid,n=1):return client.post('/v2/leagues',headers=hdr(uid),json={'platform':'Sleeper','leagueId':str(1000+n),'teamId':'1','season':2026})

def test_no_auth_or_shared_key_backdoor(env):
    client,_,_=env
    assert client.get('/v2/leagues').status_code==401
    assert client.get('/v2/leagues',headers={'X-FCC-Key':'TEST_ONLY'}).status_code==401
    assert client.get('/v1/sources').status_code==410
    assert client.get('/v2/app-payload').status_code==401

def test_uid_cannot_be_supplied_by_client(env):
    client,repo,_=env
    r=client.post('/v2/leagues',headers=hdr(),json={'uid':'TEST_ONLY_B','platform':'Sleeper','leagueId':'1001','season':2026})
    assert r.status_code==422;assert not repo.rows

def test_four_vs_two_leagues_and_new_empty_account(env):
    c,repo,_=env
    assert c.get('/v2/app-payload',headers=hdr()).json()['data']['leagues']==[]
    for n in range(4):assert add(c,'A',n).status_code==201
    for n in range(2):assert add(c,'B',n+9).status_code==201
    assert len(c.get('/v2/leagues',headers=hdr()).json()['leagues'])==4
    assert len(c.get('/v2/leagues',headers=hdr('B')).json()['leagues'])==2
    assert len(c.get('/v2/app-payload',headers=hdr()).json()['data']['leagues'])==4
    assert len(c.get('/v2/app-payload',headers=hdr('B')).json()['data']['leagues'])==2

def test_same_external_league_is_independent_per_uid(env):
    c,repo,_=env
    a=add(c,'A').json()['league'];b=add(c,'B').json()['league'];assert a['id']==b['id']
    assert len(repo.rows)==2
    assert add(c,'A').json()['created'] is False
    c.delete('/v2/leagues/'+a['id'],headers=hdr())
    assert c.get('/v2/leagues/'+b['id'],headers=hdr('B')).status_code==200

def test_cross_account_read_sync_delete_return_not_found(env):
    c,_,_=env;lid=add(c,'A').json()['league']['id']
    for method,path in [('get','/v2/leagues/'+lid),('post','/v2/leagues/'+lid+'/sync'),('delete','/v2/leagues/'+lid)]:
        assert getattr(c,method)(path,headers=hdr('B')).status_code==404

def test_confirm_email_before_access(env):
    c,_,_=env
    assert c.get('/v2/me',headers=hdr('UNVERIFIED')).status_code==200
    assert c.get('/v2/app-payload',headers=hdr('UNVERIFIED')).status_code==403
    assert add(c,'UNVERIFIED').status_code==403

def test_unsafe_url_does_not_reach_provider(env):
    c,repo,_=env
    for raw in ['https://attacker.invalid/1001','https://api.sleeper.app/../admin','../../TEST_ONLY','1?uid=B','http://127.0.0.1/']:
        r=c.post('/v2/leagues',headers=hdr(),json={'platform':'Sleeper','leagueId':raw,'season':2026})
        assert r.status_code==422
    assert not repo.rows

def test_sync_failure_preserves_valid_data_and_throttles(env):
    c,repo,provider=env;lid=add(c,'A').json()['league']['id']
    assert c.post('/v2/leagues/'+lid+'/sync',headers=hdr()).json()['status']=='updated'
    assert c.post('/v2/leagues/'+lid+'/sync',headers=hdr()).json()['status']=='cached'
    provider.fail=True;repo.rows[('TEST_ONLY_A',lid)]['lastAttemptEpoch']=0
    assert c.post('/v2/leagues/'+lid+'/sync',headers=hdr()).json()['ok'] is False
    payload=c.get('/v2/app-payload',headers=hdr()).json()
    assert payload['data']['leagues'][0]['loaded'] is True
    assert payload['data']['leagues'][0]['sourceAnalysisWeek']==6
    assert payload['userId']=='TEST_ONLY_A'

def test_secrets_are_never_in_user_responses(env):
    c,repo,_=env;lid=add(c,'A').json()['league']['id']
    repo.rows[('TEST_ONLY_A',lid)].update(credentialSecret='TEST_ONLY_SECRET',SWID='TEST_ONLY_COOKIE',espn_s2='TEST_ONLY_COOKIE')
    assert 'TEST_ONLY_SECRET' not in c.get('/v2/leagues',headers=hdr()).text
    assert 'TEST_ONLY_COOKIE' not in c.get('/v2/leagues/'+lid,headers=hdr()).text

def test_cors_does_not_allow_arbitrary_or_null_origins(env):
    c,_,_=env
    for origin in ['https://attacker.invalid','null']:
        r=c.options('/v2/leagues',headers={'Origin':origin,'Access-Control-Request-Method':'GET','Access-Control-Request-Headers':'Authorization'})
        assert 'access-control-allow-origin' not in r.headers
    origin='https://appassets.androidplatform.net'
    r=c.options('/v2/leagues',headers={'Origin':origin,'Access-Control-Request-Method':'POST','Access-Control-Request-Headers':'Authorization,Content-Type'})
    assert r.headers['access-control-allow-origin']==origin

def test_web_login_rejects_missing_csrf_origin(env):
    c,_,_=env
    body={'email':'TEST_ONLY@example.invalid','password':'TEST_ONLY_PASSWORD'}
    assert c.post('/v2/auth/login',json=body).status_code==403
    assert c.post('/v2/auth/login',json=body,headers={'Origin':'https://attacker.invalid','X-FCC-Web':'1'}).status_code==403

def test_real_verifier_checks_revocation_and_project(monkeypatch):
    from app import security
    monkeypatch.setattr(security,'firebase_app',lambda:'TEST_ONLY_PROJECT')
    seen={}
    def verifier(token,app,check_revoked):seen.update(app=app,revoked=check_revoked);return {'uid':'TEST_ONLY_A','email_verified':True}
    monkeypatch.setattr(security.auth,'verify_id_token',verifier)
    assert security.verify_token('TEST_ONLY_TOKEN').uid=='TEST_ONLY_A';assert seen=={'app':'TEST_ONLY_PROJECT','revoked':True}
    def reject(*args,**kwargs):raise ValueError('sensitive TEST_ONLY')
    monkeypatch.setattr(security.auth,'verify_id_token',reject)
    with pytest.raises(HTTPException) as e:security.verify_token('TEST_ONLY_INVALID')
    assert e.value.status_code==401;assert 'sensitive' not in str(e.value.detail)

class FixtureIdentity:
    async def login(self,body,register=False):
        return {'ok':True,'idToken':'TEST_ONLY_ID','refreshToken':'TEST_ONLY_REFRESH_TOKEN',
                'expiresIn':3600,'user':{'uid':'TEST_ONLY_A','email':body.email,'emailVerified':not register,'displayName':body.displayName}}
    async def refresh(self,token):
        assert token=='TEST_ONLY_REFRESH_TOKEN'
        return {'ok':True,'idToken':'TEST_ONLY_NEW_ID','refreshToken':token,'expiresIn':3600,
                'user':{'uid':'TEST_ONLY_A','email':'a@example.invalid','emailVerified':True}}

def test_web_session_uses_http_only_cookie_and_native_returns_no_cookie(env):
    c,_,_=env;main.app.dependency_overrides[main.identity]=FixtureIdentity
    origin='https://fcc-api-322688211348.southamerica-east1.run.app'
    web={'Origin':origin,'X-FCC-Web':'1'};body={'email':'a@example.invalid','password':'TEST_ONLY_PASSWORD'}
    r=c.post('/v2/auth/login',headers=web,json=body);assert r.status_code==200
    assert 'refreshToken' not in r.json();assert r.json()['idToken']=='TEST_ONLY_ID'
    cookie=r.headers['set-cookie'];assert '__Host-fcc-refresh=' in cookie
    for flag in ['HttpOnly','Secure','SameSite=lax','Path=/']:assert flag in cookie
    r=c.post('/v2/auth/refresh',headers=web);assert r.json()['idToken']=='TEST_ONLY_NEW_ID';assert 'refreshToken' not in r.json()
    r=c.post('/v2/auth/native/login',json=body);assert r.json()['refreshToken']=='TEST_ONLY_REFRESH_TOKEN';assert 'set-cookie' not in r.headers
    assert c.post('/v2/auth/logout',headers=web).status_code==200
    assert c.post('/v2/auth/refresh',headers=web).status_code==401

def test_late_sync_cannot_resurrect_removed_or_replaced_league(env):
    c,repo,provider=env;lid=add(c,'A').json()['league']['id'];original=repo.get('TEST_ONLY_A',lid)
    async def removed(row,credentials=None):
        repo.remove('TEST_ONLY_A',lid)
        repo.create('TEST_ONLY_A',lid,{**original,'bindingVersion':'TEST_ONLY_NEW_BINDING'},30)
        return {'loaded':True,'name':'TEST_ONLY_OLD_PAYLOAD'}
    provider.fetch=removed
    r=c.post('/v2/leagues/'+lid+'/sync',headers=hdr())
    assert r.json()['status']=='removed'
    assert repo.get('TEST_ONLY_A',lid)['bindingVersion']=='TEST_ONLY_NEW_BINDING'
    assert repo.read_payload('TEST_ONLY_A',lid,{}) is None

def test_no_calendar_for_empty_account(env):
    c,repo,_=env
    r=c.get('/v2/nfl-schedule',headers=hdr());assert r.status_code==200;assert r.json()['weeks']==[]
