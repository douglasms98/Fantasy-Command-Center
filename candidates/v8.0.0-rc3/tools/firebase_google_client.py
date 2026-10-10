"""Run in Cloud Shell. Read only the public OAuth client ID; never print secrets."""
import argparse
import json
import re
import subprocess
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


def configure(project, origin=''):
    if not re.fullmatch(r'[a-z][a-z0-9-]{4,28}[a-z0-9]', project):
        raise ValueError('Project ID invalido.')
    hostname=''
    if origin:
        parsed=urlsplit(origin)
        if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ('','/'):
            raise ValueError('Informe apenas a origem HTTPS do FCC.')
        hostname=parsed.hostname
    process=subprocess.run(['gcloud','auth','print-access-token'],text=True,
                           stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30)
    if process.returncode or not process.stdout.strip():
        raise ValueError('Nao foi possivel autenticar. Execute no Cloud Shell da sua conta.')
    access_token=process.stdout.strip()

    def api(path, body=None):
        payload=json.dumps(body).encode() if body is not None else None
        request=Request('https://identitytoolkit.googleapis.com/admin/v2/projects/'+project+'/'+path,
                        data=payload,headers={'Authorization':'Bearer '+access_token,'Content-Type':'application/json'},
                        method='PATCH' if body is not None else 'GET')
        try:
            with urlopen(request,timeout=15) as response:return json.load(response)
        except HTTPError as error:
            if error.code==404:
                raise ValueError('Ative Google em Firebase > Authentication > Metodos de login e tente novamente.') from None
            raise ValueError('Nao foi possivel consultar/configurar Firebase (HTTP '+str(error.code)+'). Confira acesso ao projeto.') from None
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
