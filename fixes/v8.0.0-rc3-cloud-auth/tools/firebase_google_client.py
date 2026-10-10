"""Run in Cloud Shell. Read only the public OAuth client ID; never print secrets."""
import argparse
import json
import re
import subprocess
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


def firebase_error(error, project):
    """Return only known error codes and instructions; never echo Google's payload."""
    reasons=set()
    try:
        body=json.loads(error.read(65536))
        problem=body.get('error',{}) if isinstance(body,dict) else {}
        details=problem.get('details',[]) if isinstance(problem,dict) else []
        if isinstance(details,list):
            for detail in details:
                if isinstance(detail,dict) and detail.get('@type')=='type.googleapis.com/google.rpc.ErrorInfo':
                    reason=detail.get('reason')
                    if isinstance(reason,str):reasons.add(reason)
    except (ValueError,TypeError,OSError):
        pass
    if 'SERVICE_DISABLED' in reasons:
        return ('Firebase recusou a consulta: SERVICE_DISABLED. Execute: '
                'gcloud services enable identitytoolkit.googleapis.com --project='+project)
    if 'USER_PROJECT_DENIED' in reasons or 'SERVICE_USAGE_DENIED' in reasons:
        return ('Firebase recusou a consulta: USER_PROJECT_DENIED. A conta ativa precisa de '
                'serviceusage.services.use no projeto '+project+'. Confira a conta em gcloud auth list.')
    if 'ACCESS_TOKEN_SCOPE_INSUFFICIENT' in reasons:
        return ('Firebase recusou a consulta: ACCESS_TOKEN_SCOPE_INSUFFICIENT. '
                'Renove a autorizacao do Cloud Shell com a conta que administra o projeto.')
    if 'IAM_PERMISSION_DENIED' in reasons:
        return ('Firebase recusou a consulta: IAM_PERMISSION_DENIED. A conta ativa precisa de '
                'firebaseauth.configs.get; para autorizar o dominio, firebaseauth.configs.update. '
                'Confira o IAM do projeto '+project+'.')
    if error.code==401:
        return 'Sessao Google expirada ou invalida. Renove a autorizacao do Cloud Shell.'
    if error.code==404:
        return 'Ative Google em Firebase > Authentication > Metodos de login e tente novamente.'
    if error.code==403:
        return ('Firebase recusou a consulta (HTTP 403). O projeto de cota foi enviado: '+project+'. '
                'Confira gcloud auth list, a API identitytoolkit habilitada e as permissoes '
                'firebaseauth.configs.get/update e serviceusage.services.use da conta ativa.')
    return 'Nao foi possivel consultar/configurar Firebase (HTTP '+str(error.code)+'). Tente novamente.'


def configure(project, origin=''):
    if not re.fullmatch(r'[a-z][a-z0-9-]{4,28}[a-z0-9]', project):
        raise ValueError('Project ID invalido.')
    hostname=''
    if origin:
        parsed=urlsplit(origin)
        if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ('','/'):
            raise ValueError('Informe apenas a origem HTTPS do FCC.')
        hostname=parsed.hostname
    process=subprocess.run(['gcloud','auth','print-access-token','--project='+project],text=True,
                           stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30)
    if process.returncode or not process.stdout.strip():
        raise ValueError('Nao foi possivel autenticar. Execute no Cloud Shell da sua conta.')
    access_token=process.stdout.strip()

    def api(path, body=None):
        payload=json.dumps(body).encode() if body is not None else None
        request=Request('https://identitytoolkit.googleapis.com/admin/v2/projects/'+project+'/'+path,
                        data=payload,headers={'Authorization':'Bearer '+access_token,
                                              'Content-Type':'application/json','x-goog-user-project':project},
                        method='PATCH' if body is not None else 'GET')
        try:
            with urlopen(request,timeout=15) as response:return json.load(response)
        except HTTPError as error:
            raise ValueError(firebase_error(error,project)) from None
        except (URLError,ValueError):
            raise ValueError('Falha ao consultar Firebase. Tente novamente no Cloud Shell.') from None

    # This response can include clientSecret. Only clientId leaves this function.
    provider=api('defaultSupportedIdpConfigs/google.com')
    client_id=provider.get('clientId','')
    if provider.get('enabled') is not True or not re.fullmatch(r'[0-9]+-[A-Za-z0-9_-]+\.apps\.googleusercontent\.com',client_id):
        raise ValueError('Ative Google em Firebase > Authentication > Metodos de login e selecione o e-mail de suporte.')
    if hostname:
        config=api('config')
        domains=config.get('authorizedDomains',[])
        if not isinstance(domains,list) or any(not isinstance(domain,str) for domain in domains):
            raise ValueError('Configuracao de dominios inesperada; nao foi alterada.')
        if hostname not in domains:
            api('config?updateMask=authorizedDomains',{'authorizedDomains':domains+[hostname]})
            print('Dominio do FCC autorizado no Firebase: '+hostname,file=sys.stderr)
    return client_id


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--project',required=True)
    parser.add_argument('--authorize-origin',default='')
    args=parser.parse_args()
    try:print(configure(args.project,args.authorize_origin))
    except (ValueError,subprocess.SubprocessError):
        error=sys.exc_info()[1]
        print(str(error) if isinstance(error,ValueError) else 'Falha ao autenticar no Cloud Shell.',file=sys.stderr)
        raise SystemExit(1)
