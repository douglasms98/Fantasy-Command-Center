"""Ephemeral TEST_ONLY signing key. Nothing is saved or sent to a provider."""
import time
from datetime import datetime, timezone, timedelta
import pytest
from fastapi import HTTPException
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from google.auth import jwt, crypt
from app import google_login
from app.config import Settings

def test_real_google_verifier_rejects_signature_audience_issuer_expiry_and_nonce(monkeypatch):
    client='123456789-TEST_ONLY.apps.googleusercontent.com'
    monkeypatch.setattr(google_login,'settings',lambda:Settings(FCC_GCP_PROJECT='test-only',FCC_FIREBASE_API_KEY='TEST_ONLY',FCC_GOOGLE_CLIENT_ID=client))
    private=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'TEST_ONLY')])
    instant=datetime.now(timezone.utc)
    cert=x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(private.public_key()).serial_number(1).not_valid_before(instant-timedelta(days=1)).not_valid_after(instant+timedelta(days=1)).sign(private,hashes.SHA256())
    pem=private.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption())
    signer=crypt.RSASigner.from_string(pem,key_id='TEST_ONLY_KID')
    monkeypatch.setattr(google_login.id_token,'_fetch_certs',lambda request,url:{'TEST_ONLY_KID':cert.public_bytes(serialization.Encoding.PEM).decode()})
    claims={'iss':'accounts.google.com','aud':client,'sub':'TEST_ONLY_SUB','email':'test@example.invalid',
            'email_verified':True,'nonce':'TEST_ONLY_NONCE','iat':int(time.time())-10,'exp':int(time.time())+200}
    def token(extra=None):return jwt.encode(signer,{**claims,**(extra or {})}).decode()
    assert google_login.verify_google_token(token(),'TEST_ONLY_NONCE')['sub']=='TEST_ONLY_SUB'
    for extra in ({'aud':'TEST_ONLY_OTHER_CLIENT'},{'iss':'https://attacker.invalid'},{'exp':int(time.time())-10},{'nonce':'TEST_ONLY_WRONG'}):
        with pytest.raises(HTTPException) as error:google_login.verify_google_token(token(extra),'TEST_ONLY_NONCE')
        assert error.value.status_code==401 and error.value.detail=='GOOGLE_AUTH_FAILED'
    valid=token();header,payload,signature=valid.split('.')
    tampered=header+'.'+payload+'.'+('A' if signature[0]!='A' else 'B')+signature[1:]
    with pytest.raises(HTTPException) as error:google_login.verify_google_token(tampered,'TEST_ONLY_NONCE')
    assert error.value.status_code==401
