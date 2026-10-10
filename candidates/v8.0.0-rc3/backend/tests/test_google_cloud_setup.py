"""Cloud configuration helpers use TEST_ONLY HTTP responses and credentials."""
import importlib.util
import io
import json
from pathlib import Path
from types import SimpleNamespace
import pytest

spec=importlib.util.spec_from_file_location('firebase_google_client',Path(__file__).resolve().parents[2]/'tools/firebase_google_client.py')
helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
CLIENT='123456789-TEST_ONLY.apps.googleusercontent.com'

def test_cloud_helper_reads_public_client_and_preserves_domains(monkeypatch,capsys):
    requests=[]
    monkeypatch.setattr(helper.subprocess,'run',lambda *args,**kwargs:SimpleNamespace(returncode=0,stdout='TEST_ONLY_ACCESS_TOKEN',stderr=''))
    def fetch(request,timeout):
        requests.append(request)
        if request.full_url.endswith('google.com'):body={'enabled':True,'clientId':CLIENT,'clientSecret':'TEST_ONLY_PRIVATE_SECRET'}
        elif request.method=='PATCH':body={}
        else:body={'authorizedDomains':['test-only.firebaseapp.com','existing.example.invalid']}
        return io.BytesIO(json.dumps(body).encode())
    monkeypatch.setattr(helper,'urlopen',fetch)
    assert helper.configure('test-only-project','https://fcc.example.invalid')==CLIENT
    patch=requests[-1];assert patch.method=='PATCH'
    assert json.loads(patch.data)=={'authorizedDomains':['test-only.firebaseapp.com','existing.example.invalid','fcc.example.invalid']}
    output=capsys.readouterr();assert 'TEST_ONLY_ACCESS_TOKEN' not in output.out+output.err and 'TEST_ONLY_PRIVATE_SECRET' not in output.out+output.err

def test_cloud_helper_disabled_google_stops_and_invalid_origin_is_rejected(monkeypatch):
    monkeypatch.setattr(helper.subprocess,'run',lambda *args,**kwargs:SimpleNamespace(returncode=0,stdout='TEST_ONLY_ACCESS_TOKEN',stderr=''))
    monkeypatch.setattr(helper,'urlopen',lambda *args,**kwargs:io.BytesIO(json.dumps({'enabled':False,'clientId':CLIENT,'clientSecret':'TEST_ONLY_PRIVATE_SECRET'}).encode()))
    with pytest.raises(ValueError,match='Ative Google'):helper.configure('test-only-project')
    for origin in ('http://fcc.example.invalid','https://user@fcc.example.invalid','https://fcc.example.invalid/app'):
        with pytest.raises(ValueError,match='origem HTTPS'):helper.configure('test-only-project',origin)
