import httpx
from fastapi import HTTPException
from pydantic import BaseModel, Field, ConfigDict, field_validator
import re
from urllib.parse import urlencode
from starlette.concurrency import run_in_threadpool
from .config import settings
from .security import verify_token
from .google_login import verify_google_token

class GoogleChallengeInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    purpose: str = Field(default='login', pattern=r'^(login|link)$')

class GoogleInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    challengeId: str = Field(pattern=r'^[a-f0-9]{64}$')
    googleIdToken: str = Field(min_length=20, max_length=8192,
                               pattern=r'^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$')

class Credentials(BaseModel):
    model_config=ConfigDict(extra='forbid')
    email: str = Field(max_length=254)
    password: str = Field(min_length=8, max_length=256)
    displayName: str = Field(default='', max_length=80)
    @field_validator('email')
    @classmethod
    def email_check(cls,v):
        v=v.strip().lower()
        if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',v):raise ValueError('E-mail inválido')
        return v

class RefreshInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    refreshToken: str = Field(min_length=10, max_length=8192)

class EmailInput(BaseModel):
    model_config=ConfigDict(extra='forbid')
    email: str = Field(min_length=3, max_length=254)

class Identity:
    def key(self):
        key=settings().FCC_FIREBASE_API_KEY
        if not key or not settings().FCC_GCP_PROJECT:raise HTTPException(503,'AUTH_NOT_CONFIGURED')
        return key

    async def call(self,method,body,google=False):
        key=self.key()
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                r=await client.post(f'https://identitytoolkit.googleapis.com/v1/accounts:{method}',params={'key':key},json=body)
        except httpx.HTTPError:raise HTTPException(503,'AUTH_UNAVAILABLE') from None
        if not r.is_success:
            if google:
                try:code=r.json().get('error',{}).get('message','').split(' : ')[0]
                except (ValueError,AttributeError):code=''
                if code=='OPERATION_NOT_ALLOWED':raise HTTPException(503,'GOOGLE_NOT_CONFIGURED')
                if code in ('EMAIL_EXISTS','FEDERATED_USER_ID_ALREADY_LINKED'):
                    raise HTTPException(409,'GOOGLE_ACCOUNT_LINK_REQUIRED')
                raise HTTPException(401,'GOOGLE_AUTH_FAILED')
            raise HTTPException(401,'AUTH_FAILED')
        return r.json()

    async def google(self,token,challenge,firebase_token=None):
        await run_in_threadpool(verify_google_token,token,challenge['nonce'])
        body={'postBody':urlencode({'id_token':token,'providerId':'google.com'}),
              'requestUri':settings().FCC_PUBLIC_ORIGIN.rstrip('/')+'/app',
              'returnSecureToken':True,'returnIdpCredential':False}
        if firebase_token:body['idToken']=firebase_token
        result=await self.call('signInWithIdp',body,google=True)
        if result.get('needConfirmation'):
            raise HTTPException(409,'GOOGLE_ACCOUNT_LINK_REQUIRED')
        if result.get('providerId')!='google.com' or not result.get('idToken') or not result.get('refreshToken'):
            raise HTTPException(401,'GOOGLE_AUTH_FAILED')
        user=verify_token(result['idToken'])
        if challenge.get('ownerUid') and user.uid!=challenge['ownerUid']:
            raise HTTPException(401,'ACCOUNT_CHANGED')
        return self.session(result,user)

    async def login(self,credentials,register=False):
        body={'email':credentials.email,'password':credentials.password,'returnSecureToken':True}
        if register and credentials.displayName:body['displayName']=credentials.displayName
        result=await self.call('signUp' if register else 'signInWithPassword',body)
        if register and credentials.displayName:
            updated=await self.call('update',{'idToken':result['idToken'],'displayName':credentials.displayName,'returnSecureToken':True})
            result.update({k:v for k,v in updated.items() if k in ('idToken','refreshToken','expiresIn')})
        user=verify_token(result['idToken'])
        return self.session(result,user)

    def session(self,result,user):
        return {'ok':True,'idToken':result['idToken'],'refreshToken':result['refreshToken'],
                'expiresIn':int(result.get('expiresIn') or 3600),'user':{'uid':user.uid,'email':user.email,'emailVerified':user.verified,'displayName':user.name,'provider':user.provider,'googleLinked':user.google_linked}}

    async def refresh(self,token):
        key=self.key()
        try:
            async with httpx.AsyncClient(timeout=20) as c:
                r=await c.post('https://securetoken.googleapis.com/v1/token',params={'key':key},data={'grant_type':'refresh_token','refresh_token':token})
        except httpx.HTTPError:raise HTTPException(503,'AUTH_UNAVAILABLE') from None
        if not r.is_success:raise HTTPException(401,'SESSION_EXPIRED')
        raw=r.json();user=verify_token(raw['id_token'])
        return self.session({'idToken':raw['id_token'],'refreshToken':raw['refresh_token'],'expiresIn':raw['expires_in']},user)

    async def verify_email(self,id_token):
        await self.call('sendOobCode',{'requestType':'VERIFY_EMAIL','idToken':id_token})

    async def reset(self,email):
        # Generic response prevents account enumeration through password reset.
        try:await self.call('sendOobCode',{'requestType':'PASSWORD_RESET','email':email})
        except HTTPException as e:
            if e.status_code==503:raise
