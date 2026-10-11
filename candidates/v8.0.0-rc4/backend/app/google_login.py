"""Google ID tokens are checked on the server before the Firebase exchange."""
import hmac
from requests import Session
from google.auth import exceptions
from google.auth.transport.requests import Request
from google.oauth2 import id_token
from fastapi import HTTPException
from .config import settings


class BoundedRequest(Request):
    def __call__(self, url, method='GET', body=None, headers=None, timeout=None, **kwargs):
        return super().__call__(url, method=method, body=body, headers=headers,
                                timeout=10, **kwargs)


def verify_google_token(token, nonce):
    config = settings()
    if not config.google_enabled():
        raise HTTPException(503, 'GOOGLE_NOT_CONFIGURED')
    try:
        with Session() as session:
            request = BoundedRequest(session=session)
            claims = id_token.verify_oauth2_token(token, request, config.FCC_GOOGLE_CLIENT_ID)
    except exceptions.TransportError:
        raise HTTPException(503, 'AUTH_UNAVAILABLE') from None
    except Exception:
        raise HTTPException(401, 'GOOGLE_AUTH_FAILED') from None
    actual_nonce = claims.get('nonce')
    if not isinstance(actual_nonce, str) or not hmac.compare_digest(actual_nonce, nonce):
        raise HTTPException(401, 'GOOGLE_AUTH_FAILED')
    if not claims.get('sub') or not claims.get('email') or claims.get('email_verified') is not True:
        raise HTTPException(401, 'GOOGLE_AUTH_FAILED')
    return claims
