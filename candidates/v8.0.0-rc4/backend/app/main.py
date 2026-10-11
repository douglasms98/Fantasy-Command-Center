from pathlib import Path
from hashlib import sha256
from functools import lru_cache
import asyncio
from fastapi import FastAPI, Depends, HTTPException, Request, Response
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict
from .config import settings
from .identity import Identity, Credentials, RefreshInput, EmailInput, GoogleChallengeInput, GoogleInput
from .security import principal, Principal, require_verified, web_origin
from .store import Store, now
from .providers import Providers, LeagueInput
from .service import Service, public, league_quota
from .calendar import Calendar

app=FastAPI(title='FCC contas e ligas',version='8.0.0-rc4')
s=settings()
app.add_middleware(CORSMiddleware,allow_origins=s.origins(),allow_credentials=True,allow_methods=['GET','POST','PUT','DELETE'],allow_headers=['Authorization','Content-Type','X-FCC-Web'])

def store():return Store()
@lru_cache
def providers():return Providers(Store())
def identity():return Identity()
def service(repo=Depends(store),provider=Depends(providers)):return Service(repo,provider)

@app.middleware('http')
async def headers(request,call_next):
    response=await call_next(request)
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['Referrer-Policy']='strict-origin-when-cross-origin'
    response.headers['Cross-Origin-Opener-Policy']='same-origin-allow-popups'
    response.headers['Cache-Control']='no-store'
    if request.url.path.startswith('/v2/'):
        response.headers['Pragma']='no-cache'
    return response

def limit(repo,key,maximum=30,seconds=900):
    if not repo.throttle(sha256(key.encode()).hexdigest(),maximum,seconds):raise HTTPException(429,'TRY_AGAIN_LATER')

def auth_limit(request,repo,email=''):
    peer=request.client.host if request.client else 'unknown'
    if s.FCC_TRUST_PROXY_HEADERS:peer=request.headers.get('x-forwarded-for',peer).split(',')[-1].strip()
    limit(repo,'auth-ip:'+peer,60)
    if email:limit(repo,'auth-email:'+email.strip().lower(),20)

COOKIE='__Host-fcc-refresh'
def web_session(response,result):
    response.set_cookie(COOKIE,result['refreshToken'],secure=s.FCC_COOKIE_SECURE,httponly=True,samesite='lax',path='/',max_age=30*86400)
    return {k:v for k,v in result.items() if k!='refreshToken'}

@app.get('/health')
def health():return {'ok':True,'version':'8.0.0-rc4','role':s.FCC_ROLE,'at':now(),'authConfigured':bool(s.FCC_GCP_PROJECT and s.FCC_FIREBASE_API_KEY),'googleConfigured':s.google_enabled()}

if s.FCC_ROLE=='api':
    @app.get('/v2/auth/google/config')
    def google_config():
        return {'ok':True,'enabled':s.google_enabled(),
                'clientId':s.FCC_GOOGLE_CLIENT_ID if s.google_enabled() else ''}

    def google_owner(request,purpose):
        if purpose!='link':return None
        user=principal(request.headers.get('authorization'))
        require_verified(user)
        return user

    @app.post('/v2/auth/google/challenge')
    @app.post('/v2/auth/native/google/challenge')
    def google_challenge(body:GoogleChallengeInput,request:Request,repo=Depends(store)):
        native='/native/' in request.url.path
        if not native:web_origin(request)
        if not s.google_enabled():raise HTTPException(503,'GOOGLE_NOT_CONFIGURED')
        auth_limit(request,repo)
        user=google_owner(request,body.purpose)
        challenge=repo.google_challenge('native' if native else 'web',body.purpose,user.uid if user else '')
        return {'ok':True,'clientId':s.FCC_GOOGLE_CLIENT_ID,**challenge}

    @app.post('/v2/auth/google')
    @app.post('/v2/auth/google/link')
    @app.post('/v2/auth/native/google')
    @app.post('/v2/auth/native/google/link')
    async def google_login(body:GoogleInput,request:Request,response:Response,repo=Depends(store),auth=Depends(identity)):
        native='/native/' in request.url.path
        if not native:web_origin(request)
        if not s.google_enabled():raise HTTPException(503,'GOOGLE_NOT_CONFIGURED')
        auth_limit(request,repo)
        purpose='link' if request.url.path.endswith('/link') else 'login'
        user=google_owner(request,purpose)
        challenge=repo.consume_google_challenge(body.challengeId,'native' if native else 'web',purpose,user.uid if user else '')
        if not challenge:raise HTTPException(401,'GOOGLE_CHALLENGE_EXPIRED')
        token=request.headers.get('authorization','')[7:] if user else None
        result=await auth.google(body.googleIdToken,challenge,token)
        repo.profile(result['user']['uid'],result['user']['email'])
        return result if native else web_session(response,result)

    @app.get('/app')
    @app.get('/')
    def html():
        path=Path(__file__).resolve().parents[1]/'static'/'index.html'
        if not path.exists():raise HTTPException(503,'WEB_BUILD_REQUIRED')
        return FileResponse(path,media_type='text/html')

    @app.post('/v2/auth/register')
    async def register(body:Credentials,request:Request,response:Response,repo=Depends(store),auth=Depends(identity)):
        web_origin(request);auth_limit(request,repo,body.email)
        result=await auth.login(body,register=True);repo.profile(result['user']['uid'],result['user']['email'])
        return web_session(response,result)

    @app.post('/v2/auth/login')
    async def login(body:Credentials,request:Request,response:Response,repo=Depends(store),auth=Depends(identity)):
        web_origin(request);auth_limit(request,repo,body.email)
        result=await auth.login(body);repo.profile(result['user']['uid'],result['user']['email'])
        return web_session(response,result)

    @app.post('/v2/auth/refresh')
    async def refresh(request:Request,response:Response,repo=Depends(store),auth=Depends(identity)):
        web_origin(request);auth_limit(request,repo)
        token=request.cookies.get(COOKIE)
        if not token:raise HTTPException(401,'LOGIN_REQUIRED')
        result=await auth.refresh(token)
        return web_session(response,result)

    @app.post('/v2/auth/logout')
    def logout(request:Request,response:Response):
        web_origin(request);response.delete_cookie(COOKIE,path='/',secure=s.FCC_COOKIE_SECURE,httponly=True,samesite='lax')
        return {'ok':True}

    @app.post('/v2/auth/native/register')
    @app.post('/v2/auth/native/login')
    async def native_login(body:Credentials,request:Request,repo=Depends(store),auth=Depends(identity)):
        # No cookie is read or issued on this bearer-only transport.
        auth_limit(request,repo,body.email)
        result=await auth.login(body,register=request.url.path.endswith('/register'))
        repo.profile(result['user']['uid'],result['user']['email'])
        return result

    @app.post('/v2/auth/native/refresh')
    async def native_refresh(body:RefreshInput,request:Request,repo=Depends(store),auth=Depends(identity)):
        auth_limit(request,repo)
        return await auth.refresh(body.refreshToken)

    @app.post('/v2/auth/reset')
    async def reset(body:EmailInput,request:Request,repo=Depends(store),auth=Depends(identity)):
        auth_limit(request,repo,body.email);await auth.reset(body.email)
        return {'ok':True,'message':'Se houver uma conta, você receberá as instruções por e-mail.'}

    @app.post('/v2/auth/verify-email')
    async def verify(request:Request,user:Principal=Depends(principal),repo=Depends(store),auth=Depends(identity)):
        limit(repo,'verify:'+user.uid,5,3600)
        await auth.verify_email(request.headers['authorization'][7:])
        return {'ok':True}

    @app.get('/v2/me')
    def me(user:Principal=Depends(principal),repo=Depends(store)):
        repo.profile(user.uid,user.email)
        return {'ok':True,'user':{'uid':user.uid,'email':user.email,'emailVerified':user.verified,'displayName':user.name,'provider':user.provider,'googleLinked':user.google_linked}}

    @app.get('/v2/leagues')
    def leagues(user:Principal=Depends(principal),repo=Depends(store)):
        require_verified(user)
        registered=[public(row) for row in repo.list_leagues(user.uid)]
        return {'ok':True,'leagues':registered,**league_quota(len(registered))}

    @app.post('/v2/leagues',status_code=201)
    async def add_league(body:LeagueInput,user:Principal=Depends(principal),svc=Depends(service)):
        require_verified(user);limit(svc.store,'add-league:'+user.uid,30,3600)
        row,created=await svc.add(user.uid,body)
        return {'ok':True,'created':created,'league':row}

    @app.get('/v2/leagues/{lid}')
    def league(lid:str,user:Principal=Depends(principal),svc=Depends(service)):
        require_verified(user);row=svc.owned(user.uid,lid)
        return {'ok':True,'league':public(row),'data':svc.store.read_payload(user.uid,lid,row)}

    @app.delete('/v2/leagues/{lid}')
    def remove_league(lid:str,user:Principal=Depends(principal),svc=Depends(service)):
        require_verified(user);svc.owned(user.uid,lid);svc.store.remove(user.uid,lid)
        return {'ok':True}

    @app.post('/v2/leagues/{lid}/sync')
    async def sync_league(lid:str,user:Principal=Depends(principal),svc=Depends(service)):
        require_verified(user);return await svc.sync(user.uid,lid)

    @app.post('/v2/sync')
    async def sync_all(user:Principal=Depends(principal),svc=Depends(service)):
        require_verified(user);limit(svc.store,'sync:'+user.uid,12,3600)
        semaphore=asyncio.Semaphore(2)
        async def sync_one(row):
            async with semaphore:return await svc.sync(user.uid,row['id'])
        results=await asyncio.gather(*(sync_one(row) for row in svc.store.list_leagues(user.uid)))
        return {'ok':True,'results':results}

    @app.get('/v2/app-payload')
    def payload(user:Principal=Depends(principal),svc=Depends(service)):
        require_verified(user);return svc.payload(user.uid)

    @app.get('/v2/nfl-schedule')
    async def nfl_schedule(user:Principal=Depends(principal),svc=Depends(service)):
        require_verified(user);limit(svc.store,'calendar:'+user.uid,60,3600)
        data=svc.payload(user.uid)['data']
        return await Calendar(svc.store).get(data['season'],int(data['meta']['sourceAnalysisWeek']))

    @app.get('/v1/{legacy:path}')
    def legacy_api(legacy:str):
        # No shared-key backdoor or global league endpoint in the multi-user service.
        raise HTTPException(410,'UPGRADE_TO_ACCOUNT_LOGIN')

if s.FCC_ROLE=='worker':
    @app.post('/internal/sync')
    async def worker(svc=Depends(service)):
        # Worker must be deployed with Cloud Run IAM; no unauthenticated access.
        count=0;failed=0;users=set()
        for uid,row in svc.store.enabled_bindings():
            result=await svc.sync(uid,row['id']);count+=1;failed+=not result['ok'];users.add(uid)
        for uid in users:
            data=svc.payload(uid)['data']
            try:await Calendar(svc.store).get(data['season'],int(data['meta']['sourceAnalysisWeek']))
            except HTTPException:failed+=1
        return {'ok':True,'processed':count,'failed':failed}
