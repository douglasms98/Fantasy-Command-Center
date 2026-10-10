# FCC RC3 — correção da autenticação no deploy Cloud

O log recebido confirma atualização do clone para `0f44ff2` e interrupção antes do deploy com HTTP 403 na consulta administrativa ao Firebase. A mensagem antiga ocultava o motivo específico; ela não confirma falta de permissão IAM.

O helper antigo usava um access token da conta ativa do gcloud sem enviar `x-goog-user-project`. A correção informa explicitamente o projeto escolhido como projeto de cota em todas as consultas e alterações. Esse é o mecanismo documentado pelo Google para chamadas REST com credenciais de usuário. Se outra configuração causar o 403, o helper agora distingue API desativada, cota recusada, escopo insuficiente e permissão IAM recusada, quando o Google envia esse código. Nunca imprime access tokens, client secrets ou a resposta bruta do provedor.

## Aplicar no Cloud Shell

O provedor Google ainda precisa estar habilitado no Firebase. A origem web e a assinatura Android continuam seguindo o [guia da RC3](../../candidates/v8.0.0-rc3/docs/GOOGLE_LOGIN_SETUP_PT_BR.md).

```bash
cd /home/douglasmsvg98/fcc-v8-rc2.9d5ue5
git pull --ff-only

gcloud config set project fantasy-command-center-2026
gcloud config set billing/quota_project fantasy-command-center-2026
gcloud services enable identitytoolkit.googleapis.com --project=fantasy-command-center-2026

bash fixes/v8.0.0-rc3-cloud-auth/tools/deploy_v8.sh \
  fantasy-command-center-2026 \
  fcc-v8-firebase-api-key:1 \
  southamerica-east1
```

O wrapper usa o backend original em `candidates/v8.0.0-rc3`, sem alterar fontes nem ZIP da RC3. Para usar o ZIP desta correção fora do clone, extraia-o e forneça o diretório do pacote RC3 como quarto argumento do script. Esta correção contém apenas scripts Cloud, testes e documentação; não é um pacote Android e não exige reaplicar o PowerShell.

## Se o acesso ainda for recusado

- `SERVICE_DISABLED`: habilite `identitytoolkit.googleapis.com` no projeto informado.
- `USER_PROJECT_DENIED`: confira `gcloud auth list` e se a conta ativa tem `serviceusage.services.use` no projeto. O projeto de cota já é enviado pelo script.
- `ACCESS_TOKEN_SCOPE_INSUFFICIENT` ou HTTP 401: renove a autorização do Cloud Shell com a conta que administra o projeto.
- `IAM_PERMISSION_DENIED`: a conta que executa o script precisa de `firebaseauth.configs.get` para consultar e `firebaseauth.configs.update` para adicionar o domínio. Isso se aplica ao operador do Cloud Shell, não exige ampliar as permissões dos serviços API/worker.
- HTTP 403 sem código específico: a mensagem original não permite apontar a causa. Confira conta ativa, API habilitada e as permissões acima antes de tentar novamente.

O helper não altera IAM nem habilita o provedor Google automaticamente. A leitura bem-sucedida do client ID não substitui o teste de login real.

## Validação

Dez testes Python com fixtures TEST_ONLY reproduzem a recusa sem projeto de cota, conferem preservação dos domínios e validam diagnóstico sem expor credenciais. O wrapper é executado com comandos Cloud falsos: usa o backend original da RC3 e não inicia deploy quando a autenticação falha. Parsing Python e sintaxe Bash conferidos. Execução administrativa real no projeto, novo deploy e login Google permanecem pendentes.

## Fontes oficiais

- [Projeto de cota e header REST](https://docs.cloud.google.com/docs/quotas/set-quota-project)
- [Consulta do provedor Google e permissão Firebase](https://docs.cloud.google.com/identity-platform/docs/reference/rest/v2/projects.defaultSupportedIdpConfigs/get)
- [Atualização da configuração do projeto](https://docs.cloud.google.com/identity-platform/docs/reference/rest/v2/projects/updateConfig)
