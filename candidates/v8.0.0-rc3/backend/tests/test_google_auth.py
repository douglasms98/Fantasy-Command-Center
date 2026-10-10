"""TEST_ONLY fixtures: no live users, credentials, or league statistics."""
from datetime import datetime, timezone, timedelta
from copy import deepcopy
import hashlib
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from app import main, identity, google_login
from app.config import Settings
from app.security import Principal
from test_accounts import Memory

GOOGLE_TOKEN='TEST_ONLY_HEADER.TEST_ONLY_PAYLOAD.TEST_ONLY_SIGNATURE'
CLIENT='123456789-TEST_ONLY.apps.googleusercontent.com'
ORIGIN='https://fcc-api-322688211348.southamerica-east1.run.app'
WEB={'Origin':ORIGIN,'X-FCC-Web':'1'}

class GoogleMemory(Memory):
    def __init__(self):super().__init__();self.challenges={};self.sequence=0
    def google_challenge(self,transport,purpose,owner_uid=''):
        self.sequence+=1
        cid=hashlib.sha256(('TEST_ONLY_'+str(self.sequence)).encode()).hexdigest()
        self.challenges[cid]={'transport':transport,'purpose':purpose,'ownerUid':owner_uid,
            'nonce':'TEST_ONLY_NONCE_'+str(self.sequence),'expiresAt':datetime.now(timezone.utc)+timedelta(minutes=5)}
        return {'challengeId':cid,'nonce':self.challenges[cid]['nonce'],'expiresIn':300}
    def consume_google_challenge(self,cid,transport,purpose,owner_uid=''):
        row=self.challenges.get(cid)
        if not row or row['transport']!=transport or row['purpose']!=purpose or row['ownerUid']!=owner_uid or row['expiresAt']<=datetime.now(timezone.utc):return None
        return self.challenges.pop(cid)

class GoogleIdentity:
    async def google(self,token,challenge,firebase_token=None):
        assert token==GOOGLE_TOKEN
        self.calls.append((deepcopy(challenge),firebase_token))
        uid=challenge['ownerUid'] or 'TEST_ONLY_GOOGLE'
        return {'ok':True,'idToken':'TEST_ONLY_FIREBASE_ID','refreshToken':'TEST_ONLY_FIREBASE_REFRESH',
            'expiresIn':3600,'user':{'uid':uid,'email':'google@example.invalid',
            'emailVerified':True,'displayName':'TEST_ONLY','provider':'google.com'}}

@pytest.fixture
def google_env(monkeypatch):
    config=Settings(FCC_GCP_PROJECT='test-only-project',FCC_FIREBASE_API_KEY='TEST_ONLY_KEY',FCC_GOOGLE_CLIENT_ID=CLIENT,FCC_PUBLIC_ORIGIN=ORIGIN)
    monkeypatch.setattr(main,'s',config)
    monkeypatch.setattr(google_login,'settings',lambda:config)
    monkeypatch.setattr(identity,'settings',lambda:config)
    repo=GoogleMemory();auth=GoogleIdentity();auth.calls=[]
    main.app.dependency_overrides[main.store]=lambda:repo
    main.app.dependency_overrides[main.identity]=lambda:auth
    def principal(header):
        if header not in ('Bearer TEST_ONLY_A','Bearer TEST_ONLY_B','Bearer TEST_ONLY_UNVERIFIED'):raise HTTPException(401,'LOGIN_REQUIRED')
        uid=header.split()[-1]
        return Principal(uid,uid+'@example.invalid',uid!='TEST_ONLY_UNVERIFIED')
    monkeypatch.setattr(main,'principal',principal)
    with TestClient(main.app,base_url=ORIGIN) as client:yield client,repo,auth,config
    main.app.dependency_overrides.clear()

def challenge(client,native=False,purpose='login',owner=''):
    headers={} if native else dict(WEB)
    if owner:headers['Authorization']='Bearer TEST_ONLY_'+owner
    response=client.post('/v2/auth/'+('native/' if native else '')+'google/challenge',headers=headers,json={'purpose':purpose})
    assert response.status_code==200,response.text
    return response.json()

def body(row):return {'challengeId':row['challengeId'],'googleIdToken':GOOGLE_TOKEN}

def test_google_public_config_and_health(google_env):
    client,_,_,_=google_env
    response=client.get('/v2/auth/google/config')
    assert response.json()=={'ok':True,'enabled':True,'clientId':CLIENT}
    assert 'TEST_ONLY_KEY' not in response.text
    health=client.get('/health')
    assert health.json()['googleConfigured'] is True and health.json()['version']=='8.0.0-rc3'
    assert health.headers['cross-origin-opener-policy']=='same-origin-allow-popups'

def test_google_disabled_does_not_use_an_unverified_identity(google_env):
    client,repo,auth,config=google_env;config.FCC_GOOGLE_CLIENT_ID=''
    assert client.get('/v2/auth/google/config').json()['enabled'] is False
    assert client.post('/v2/auth/native/google/challenge',json={}).status_code==503
    assert client.post('/v2/auth/native/google',json={'challengeId':'a'*64,'googleIdToken':GOOGLE_TOKEN}).status_code==503
    assert not repo.profiles and not auth.calls

def test_google_web_csrf_required(google_env):
    client,repo,auth,_=google_env
    for headers in ({},{'Origin':ORIGIN},{'Origin':'https://attacker.invalid','X-FCC-Web':'1'}):
        assert client.post('/v2/auth/google/challenge',headers=headers,json={}).status_code==403
    row=challenge(client)
    assert client.post('/v2/auth/google',json=body(row)).status_code==403
    assert row['challengeId'] in repo.challenges and not auth.calls

def test_google_web_cookie_and_replay_rejection(google_env):
    client,repo,auth,_=google_env;row=challenge(client)
    result=client.post('/v2/auth/google',headers=WEB,json=body(row))
    assert result.status_code==200,result.text
    assert result.json()['user']['uid']=='TEST_ONLY_GOOGLE' and 'refreshToken' not in result.json()
    for flag in ('HttpOnly','Secure','SameSite=lax','Path=/'):assert flag in result.headers['set-cookie']
    assert client.post('/v2/auth/google',headers=WEB,json=body(row)).json()['detail']=='GOOGLE_CHALLENGE_EXPIRED'
    assert len(auth.calls)==1 and list(repo.profiles)==['TEST_ONLY_GOOGLE']

def test_challenge_transport_and_expiration(google_env):
    client,repo,auth,_=google_env;web=challenge(client)
    assert client.post('/v2/auth/native/google',json=body(web)).status_code==401
    native=challenge(client,True)
    assert client.post('/v2/auth/google',headers=WEB,json=body(native)).status_code==401
    repo.challenges[native['challengeId']]['expiresAt']=datetime.now(timezone.utc)-timedelta(seconds=1)
    assert client.post('/v2/auth/native/google',json=body(native)).status_code==401
    assert not auth.calls

def test_native_session_issues_no_browser_cookie(google_env):
    client,_,_,_=google_env;row=challenge(client,True)
    result=client.post('/v2/auth/native/google',json=body(row))
    assert result.status_code==200 and result.json()['refreshToken']=='TEST_ONLY_FIREBASE_REFRESH'
    assert 'set-cookie' not in result.headers

def test_link_keeps_uid_and_leagues_and_rejects_another_uid(google_env):
    client,repo,auth,_=google_env
    repo.rows[('TEST_ONLY_A','TEST_ONLY_LEAGUE')]={'name':'TEST_ONLY_A_LEAGUE'}
    row=challenge(client,False,'link','A')
    result=client.post('/v2/auth/google/link',headers={**WEB,'Authorization':'Bearer TEST_ONLY_A'},json=body(row))
    assert result.status_code==200 and result.json()['user']['uid']=='TEST_ONLY_A'
    assert list(repo.rows)==[('TEST_ONLY_A','TEST_ONLY_LEAGUE')] and auth.calls[0][1]=='TEST_ONLY_A'
    row=challenge(client,True,'link','A')
    assert client.post('/v2/auth/native/google/link',headers={'Authorization':'Bearer TEST_ONLY_B'},json=body(row)).status_code==401
    assert client.post('/v2/auth/native/google',json=body(row)).status_code==401
    assert row['challengeId'] in repo.challenges

def test_link_requires_verified_user_and_client_cannot_set_uid(google_env):
    client,repo,auth,_=google_env
    assert client.post('/v2/auth/google/challenge',headers=WEB,json={'purpose':'link'}).status_code==401
    assert client.post('/v2/auth/native/google/challenge',headers={'Authorization':'Bearer TEST_ONLY_UNVERIFIED'},json={'purpose':'link'}).status_code==403
    assert client.post('/v2/auth/native/google/challenge',json={'purpose':'login','ownerUid':'TEST_ONLY_A'}).status_code==422
    assert client.post('/v2/auth/native/google',json={'challengeId':'a'*64,'googleIdToken':GOOGLE_TOKEN,'uid':'TEST_ONLY_A'}).status_code==422
    assert not repo.challenges and not auth.calls

def test_google_verifier_audience_nonce_and_signed_email(google_env,monkeypatch):
    config=google_env[3];seen={}
    claims={'sub':'TEST_ONLY_SUB','email':'google@example.invalid','email_verified':True,'nonce':'TEST_ONLY_NONCE'}
    def verify(token,request,audience):seen.update(token=token,audience=audience);return deepcopy(claims)
    monkeypatch.setattr(google_login.id_token,'verify_oauth2_token',verify)
    assert google_login.verify_google_token(GOOGLE_TOKEN,'TEST_ONLY_NONCE')['sub']=='TEST_ONLY_SUB'
    assert seen['audience']==config.FCC_GOOGLE_CLIENT_ID
    for bad in ({'nonce':'TEST_ONLY_WRONG'},{'nonce':None},{'email_verified':False},{'sub':''}):
        original=deepcopy(claims);claims.update(bad)
        with pytest.raises(HTTPException) as error:google_login.verify_google_token(GOOGLE_TOKEN,'TEST_ONLY_NONCE')
        assert error.value.detail=='GOOGLE_AUTH_FAILED';claims.clear();claims.update(original)
    def invalid(*args):raise ValueError('TEST_ONLY_TOKEN_DETAIL')
    monkeypatch.setattr(google_login.id_token,'verify_oauth2_token',invalid)
    with pytest.raises(HTTPException) as error:google_login.verify_google_token(GOOGLE_TOKEN,'TEST_ONLY_NONCE')
    assert error.value.status_code==401 and 'TOKEN_DETAIL' not in error.value.detail

@pytest.mark.anyio
async def test_firebase_exchange_and_link_uid(google_env,monkeypatch):
    from urllib.parse import parse_qs
    monkeypatch.setattr(identity,'verify_google_token',lambda token,nonce:None)
    user=Principal('TEST_ONLY_A','a@example.invalid',True,'TEST_ONLY','google.com')
    monkeypatch.setattr(identity,'verify_token',lambda token:user)
    result={'providerId':'google.com','idToken':'TEST_ONLY_ID','refreshToken':'TEST_ONLY_REFRESH','expiresIn':'3600',
            'oauthIdToken':'TEST_ONLY_PROVIDER_TOKEN','rawUserInfo':'TEST_ONLY_PRIVATE'}
    auth=identity.Identity();seen={}
    async def call(method,body,google=False):seen.update(method=method,body=body,google=google);return deepcopy(result)
    monkeypatch.setattr(auth,'call',call)
    session=await auth.google(GOOGLE_TOKEN,{'nonce':'TEST_ONLY_NONCE','ownerUid':'TEST_ONLY_A'},'TEST_ONLY_FIREBASE_CURRENT')
    assert session['user']['uid']=='TEST_ONLY_A' and 'oauthIdToken' not in session and 'rawUserInfo' not in session
    assert seen['method']=='signInWithIdp' and seen['google'] is True and seen['body']['idToken']=='TEST_ONLY_FIREBASE_CURRENT'
    assert parse_qs(seen['body']['postBody'])=={'id_token':[GOOGLE_TOKEN],'providerId':['google.com']}
    with pytest.raises(HTTPException) as error:await auth.google(GOOGLE_TOKEN,{'nonce':'TEST_ONLY_NONCE','ownerUid':'TEST_ONLY_B'},'TEST_ONLY_FIREBASE_CURRENT')
    assert error.value.detail=='ACCOUNT_CHANGED'
    result['needConfirmation']=True
    with pytest.raises(HTTPException) as error:await auth.google(GOOGLE_TOKEN,{'nonce':'TEST_ONLY_NONCE'})
    assert error.value.detail=='GOOGLE_ACCOUNT_LINK_REQUIRED'

@pytest.fixture
def anyio_backend():return 'asyncio'

def test_linked_google_identity_survives_later_password_login(monkeypatch):
    from app import security
    monkeypatch.setattr(security,'firebase_app',lambda:'TEST_ONLY_APP')
    monkeypatch.setattr(security.auth,'verify_id_token',lambda *args,**kwargs:{
        'uid':'TEST_ONLY_A','email_verified':True,
        'firebase':{'sign_in_provider':'password','identities':{'google.com':['TEST_ONLY_GOOGLE_SUB']}}})
    user=security.verify_token('TEST_ONLY_FIREBASE_TOKEN')
    assert user.provider=='password' and user.google_linked is True
