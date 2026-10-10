"""Cloud configuration helpers use TEST_ONLY HTTP responses and credentials."""
import importlib.util
import io
import json
import os
import shlex
import shutil
import subprocess
import sys
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
        # Reproduce the client-based API refusing CLI user credentials without a quota project.
        if request.get_header('X-goog-user-project')!='test-only-project':
            raise helper.HTTPError(request.full_url,403,'Forbidden',{},io.BytesIO(json.dumps({'error':{
                'details':[{'@type':'type.googleapis.com/google.rpc.ErrorInfo','reason':'USER_PROJECT_DENIED'}]
            }}).encode()))
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


@pytest.mark.parametrize('reason,expected',[
    ('SERVICE_DISABLED','gcloud services enable identitytoolkit.googleapis.com --project=test-only-project'),
    ('USER_PROJECT_DENIED','serviceusage.services.use'),
    ('ACCESS_TOKEN_SCOPE_INSUFFICIENT','Renove a autorizacao'),
    ('IAM_PERMISSION_DENIED','firebaseauth.configs.get'),
    ('TEST_ONLY_PRIVATE_SECRET','HTTP 403'),
])
def test_cloud_helper_reports_actionable_errors_without_private_payload(monkeypatch,reason,expected):
    monkeypatch.setattr(helper.subprocess,'run',lambda *args,**kwargs:SimpleNamespace(returncode=0,stdout='TEST_ONLY_ACCESS_TOKEN',stderr=''))
    def denied(request,timeout):
        error={'error':{'message':'TEST_ONLY_PRIVATE_SECRET TEST_ONLY_ACCESS_TOKEN','clientSecret':'TEST_ONLY_PRIVATE_SECRET',
                        'details':[{'@type':'type.googleapis.com/google.rpc.ErrorInfo','reason':reason,
                                    'metadata':{'private':'TEST_ONLY_PRIVATE_SECRET'}}]}}
        raise helper.HTTPError(request.full_url,403,'Forbidden',{},io.BytesIO(json.dumps(error).encode()))
    monkeypatch.setattr(helper,'urlopen',denied)
    with pytest.raises(ValueError) as caught:helper.configure('test-only-project')
    assert expected in str(caught.value)
    assert 'TEST_ONLY_PRIVATE_SECRET' not in str(caught.value) and 'TEST_ONLY_ACCESS_TOKEN' not in str(caught.value)


def test_cloud_helper_malformed_error_is_safe(monkeypatch):
    monkeypatch.setattr(helper.subprocess,'run',lambda *args,**kwargs:SimpleNamespace(returncode=0,stdout='TEST_ONLY_ACCESS_TOKEN',stderr=''))
    def denied(request,timeout):
        raise helper.HTTPError(request.full_url,403,'Forbidden',{},io.BytesIO(b'TEST_ONLY_PRIVATE_SECRET'))
    monkeypatch.setattr(helper,'urlopen',denied)
    with pytest.raises(ValueError,match='HTTP 403') as caught:helper.configure('test-only-project')
    assert 'TEST_ONLY_PRIVATE_SECRET' not in str(caught.value)


@pytest.mark.parametrize('helper_fails',[False,True])
def test_deploy_wrapper_uses_original_rc3_and_stops_before_deploy_on_auth_failure(tmp_path,helper_fails):
    fix=tmp_path/'fixes/v8.0.0-rc3-cloud-auth/tools';fix.mkdir(parents=True)
    source=tmp_path/'candidates/v8.0.0-rc3/backend';source.mkdir(parents=True)
    (source/'Dockerfile').write_text('# TEST_ONLY')
    script=fix/'deploy_v8.sh'
    shutil.copy(Path(__file__).resolve().parents[2]/'tools/deploy_v8.sh',script)
    commands=tmp_path/'bin';commands.mkdir();log=tmp_path/'commands.log';helper_log=tmp_path/'helper.log'
    (commands/'gcloud').write_text('''#!/usr/bin/env bash
printf '%s\\n' "$*" >> "$FCC_TEST_COMMAND_LOG"
if [[ "$*" == *'value(status.url)'* ]]; then
  printf 'https://fcc.example.invalid\\n'
elif [[ "$*" == *'value(spec.template.spec.containers[0].image)'* ]]; then
  printf 'test-only/image:rc3\\n'
elif [[ "$*" == *'get-iam-policy'* ]]; then
  printf '{"bindings":[]}\\n'
fi
''')
    (commands/'python3').write_text('''#!/usr/bin/env bash
if [[ "$1" == '-c' ]]; then
  exec '''+shlex.quote(sys.executable)+''' "$@"
fi
printf '%s\\n' "$*" >> "$FCC_TEST_HELPER_LOG"
if [[ "$FCC_TEST_HELPER_FAILS" == 'true' ]]; then exit 1; fi
printf '123456789-TEST_ONLY.apps.googleusercontent.com\\n'
''')
    for binary in commands.iterdir():binary.chmod(0o755)
    env={**os.environ,'PATH':str(commands)+os.pathsep+os.environ['PATH'],
         'FCC_TEST_COMMAND_LOG':str(log),'FCC_TEST_HELPER_LOG':str(helper_log),
         'FCC_TEST_HELPER_FAILS':'true' if helper_fails else 'false'}
    result=subprocess.run(['bash',str(script),'test-only-project','test-key:1','southamerica-east1'],
                          env=env,capture_output=True,text=True,timeout=30)
    helpers=helper_log.read_text().splitlines()
    assert all(str(fix/'firebase_google_client.py') in line for line in helpers)
    if helper_fails:
        assert result.returncode!=0 and not log.exists()
    else:
        assert result.returncode==0,result.stderr
        assert '--source '+str(source) in log.read_text()
        assert 'FCC_GOOGLE_CLIENT_ID='+CLIENT in log.read_text()
        assert len(helpers)==2 and '--authorize-origin https://fcc.example.invalid' in helpers[1]
