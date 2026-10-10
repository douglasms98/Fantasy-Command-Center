from dataclasses import dataclass
from functools import lru_cache
from fastapi import Header, HTTPException, Request
from firebase_admin import auth, initialize_app
from .config import settings

@lru_cache
def firebase_app():
    project = settings().FCC_GCP_PROJECT
    if not project:
        raise HTTPException(503, 'AUTH_NOT_CONFIGURED')
    return initialize_app(options={'projectId': project}, name='fcc-v8')

@dataclass(frozen=True)
class Principal:
    uid: str
    email: str
    verified: bool
    name: str = ''

def verify_token(token: str) -> Principal:
    try:
        claims = auth.verify_id_token(token, app=firebase_app(), check_revoked=True)
        uid = claims['uid']
        if not uid or '/' in uid:
            raise ValueError('uid')
        return Principal(uid, claims.get('email', ''), claims.get('email_verified') is True, claims.get('name',''))
    except HTTPException:
        raise
    except Exception:
        # Do not return provider tokens, exception text, cookies or credentials.
        raise HTTPException(401, 'SESSION_EXPIRED')

def principal(authorization: str | None = Header(default=None)) -> Principal:
    if not authorization or not authorization.startswith('Bearer '):
        raise HTTPException(401, 'LOGIN_REQUIRED')
    return verify_token(authorization[7:])

def require_verified(user: Principal):
    if not user.verified:
        raise HTTPException(403, 'EMAIL_VERIFICATION_REQUIRED')

def web_origin(request: Request):
    # Required on cookie-bearing mutations, including login, to stop login CSRF.
    if request.headers.get('origin', '').rstrip('/') not in settings().origins():
        raise HTTPException(403, 'ORIGIN_NOT_ALLOWED')
    if request.headers.get('x-fcc-web') != '1':
        raise HTTPException(403, 'CSRF_HEADER_REQUIRED')
