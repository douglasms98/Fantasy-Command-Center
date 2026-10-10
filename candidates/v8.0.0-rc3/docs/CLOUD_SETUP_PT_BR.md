> Para Google na RC3, siga primeiro [GOOGLE_LOGIN_SETUP_PT_BR.md](GOOGLE_LOGIN_SETUP_PT_BR.md). O deploy agora lê automaticamente o client ID do Google habilitado no Firebase.

# Ativação do FCC v8 no Cloud

Este guia acompanha código de homologação. Os comandos não foram executados neste projeto Cloud. A sessão não possui uma conexão administrativa com seu Google Cloud/Firebase nem `gcloud` autenticado. Use o Cloud Shell do projeto correto.

## 1. Firebase e banco

No [Firebase Console](https://console.firebase.google.com/), adicione Firebase ao projeto Google Cloud escolhido. Em **Authentication → Sign-in method**, habilite **Email/Password**. Configure os modelos de confirmação de e-mail e recuperação de senha. Mantenha habilitada a proteção contra enumeração de e-mails quando disponível.

Crie ou selecione o Firestore em modo Native. O código usa `(default)`; outro banco exige `FCC_FIRESTORE_DATABASE` nos dois serviços. Nenhuma migração apaga as coleções do backend antigo.

A API key do Firebase é configuração do servidor, obtida nas configurações do projeto Firebase. Salve uma vez no Secret Manager com um nome como `fcc-v8-firebase-api-key`. Escolha uma versão numérica do secret para o deploy. Nenhum usuário do aplicativo precisa vê-la ou colá-la. Não crie nem baixe JSON de conta de serviço para colocar no APK; Cloud Run usa a identidade do serviço.

As regras de [firestore-v8.rules](../backend/firestore-v8.rules) bloqueiam acesso direto dos clientes às coleções FCC. Integre-as às regras existentes após revisar as outras aplicações do projeto. Uma regra ampla que permite acesso a todos os documentos também permitiria FCC: um `deny` específico não sobrepõe outros `allow`. O acesso deste backend passa pelo Admin SDK e pela validação da conta na API.

## 2. Identidades e permissões

Defina o ID real do projeto, sem usar o número do projeto como substituto:

```bash
export FCC_PROJECT='SEU_PROJECT_ID'
gcloud config set project "$FCC_PROJECT"
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com firestore.googleapis.com secretmanager.googleapis.com cloudscheduler.googleapis.com identitytoolkit.googleapis.com
gcloud iam service-accounts create fcc-v8-api --display-name='FCC v8 API'
gcloud iam service-accounts create fcc-v8-worker --display-name='FCC v8 Worker'
gcloud iam service-accounts create fcc-v8-build --display-name='FCC v8 Build'
gcloud iam service-accounts create fcc-v8-scheduler --display-name='FCC v8 Scheduler'
gcloud projects add-iam-policy-binding "$FCC_PROJECT" --member="serviceAccount:fcc-v8-api@$FCC_PROJECT.iam.gserviceaccount.com" --role=roles/datastore.user
gcloud projects add-iam-policy-binding "$FCC_PROJECT" --member="serviceAccount:fcc-v8-api@$FCC_PROJECT.iam.gserviceaccount.com" --role=roles/firebaseauth.viewer
gcloud projects add-iam-policy-binding "$FCC_PROJECT" --member="serviceAccount:fcc-v8-worker@$FCC_PROJECT.iam.gserviceaccount.com" --role=roles/datastore.user
gcloud projects add-iam-policy-binding "$FCC_PROJECT" --member="serviceAccount:fcc-v8-build@$FCC_PROJECT.iam.gserviceaccount.com" --role=roles/run.builder
gcloud secrets add-iam-policy-binding fcc-v8-firebase-api-key --member="serviceAccount:fcc-v8-api@$FCC_PROJECT.iam.gserviceaccount.com" --role=roles/secretmanager.secretAccessor
```

O operador que publica precisa de permissão para criar/alterar Cloud Run, Scheduler e IAM, e atuar como as contas de serviço usadas. As permissões do build e do operador estão na [documentação de deploy por código-fonte](https://docs.cloud.google.com/run/docs/deploying-source-code). Não conceda Owner/Editor às identidades de execução. Se as contas já existem, reutilize-as depois de revisar seus papéis.

Para evitar acúmulo dos contadores de limitação, habilite TTL no campo `expiresAt` do grupo de coleção `fcc_rate_limits`, pelo painel de TTL do Firestore. Snapshots recentes das ligas são mantidos por pelo menos 24 horas e versões antigas são retiradas durante sincronizações posteriores.

## 3. Publicar homologação

Na pasta deste pacote, execute com a versão real do secret:

```bash
bash tools/deploy_v8.sh "$FCC_PROJECT" fcc-v8-firebase-api-key:1 southamerica-east1
```

O script publica **fcc-api-v8** e **fcc-worker-v8**, mantendo o serviço antigo separado. Define a origem web após obter a URL do Cloud Run, reutiliza a mesma imagem para o worker e cria/atualiza o Scheduler a cada quatro horas. O worker exige IAM/OIDC. A API tem entrada pública no Cloud Run, mas toda rota de ligas exige uma sessão Firebase válida e e-mail confirmado.

O script é para um piloto pequeno. Para muitos usuários, distribua a sincronização por fila/ligas em vez de um único processamento sequencial. Cloud Run, Firestore, build, Secrets e Scheduler seguem a cobrança do projeto.

O resultado mostra a URL web `/app` e o `ApiBase` para compilar o Android. Adicione o domínio efetivo às configurações de domínios autorizados do Firebase. Se usar domínio próprio, ajuste `FCC_PUBLIC_ORIGIN` para essa origem e sirva `/app` por ela. `FCC_WEB_ORIGINS` pode listar origens HTTPS adicionais, mas o login web deste RC usa cookie na mesma origem: não publique o HTML separado da API sem adaptar esse transporte.

Não habilite origem `null` nem CORS `*`. O arquivo HTML aberto por `file://` não é a versão web autenticada. A web deve ser aberta na URL publicada.

## 4. Conta e ligas existentes

Crie sua conta FCC, confirme o e-mail e use **Minha conta e ligas**. Sleeper aceita link/ID e username público ou roster ID. ESPN pública precisa de liga e team ID. Os IDs são conferidos no provedor antes de marcar a liga como carregada.

Cada conta começa sem ligas e pode cadastrar até **6**. Uma liga cadastrada produz um cartão e uma opção de filtro; duas produzem duas, e assim por diante. A API informa `registeredCount`, `maxLeagues=6` e `remainingSlots` em `/v2/leagues` e nos metadados de `/v2/app-payload`. Ligação privada pendente ocupa uma vaga. Duplicatas não aumentam a contagem e remover libera uma vaga. O limite do servidor é transacional e fixo; a variável antiga `FCC_MAX_LEAGUES` não o altera.

Para migrar várias ligas com operador autorizado, prepare um JSON local com uma lista de objetos `LeagueInput`: `platform`, `leagueId`, `teamId`, `season`, e opcionalmente `username`/`name`. Os valores precisam ser reais e aprovados pelo titular. O arquivo não pode conter UID, chaves ou cookies. Não o envie ao GitHub.

```bash
export FCC_GCP_PROJECT="$FCC_PROJECT"
python tools/import_approved_leagues.py --uid UID_FIREBASE_CONFIRMADO --input approved-bindings.local.json
python tools/import_approved_leagues.py --uid UID_FIREBASE_CONFIRMADO --input approved-bindings.local.json --apply
```

O primeiro comando apenas inspeciona. O segundo grava os vínculos no UID especificado, depois de conferir que a conta existe e confirmou o e-mail. O importador não copia automaticamente configurações globais antigas para todas as contas.

## 5. ESPN privada

Este candidato não oferece OAuth ESPN. Uma liga privada permanece pendente até existir conexão autorizada para o titular. Se houver autorização e credenciais válidas já administradas no Cloud, coloque-as em um secret **exclusivo** `fcc-espn-UID_FIREBASE-ID_DO_VINCULO_FCC`, contendo `SWID` e `espn_s2`. Não use o ID externo da liga no lugar do ID de vínculo retornado por `/v2/leagues`.

Conceda `roles/secretmanager.secretAccessor` sobre esse secret às identidades `fcc-v8-api` e `fcc-v8-worker`. Valide o vínculo com o comando administrativo:

```bash
python tools/bind_private_espn.py --uid UID_FIREBASE --league ID_VINCULO_FCC --secret NOME_SECRET
python tools/bind_private_espn.py --uid UID_FIREBASE --league ID_VINCULO_FCC --secret NOME_SECRET --apply
```

Os valores dos cookies não são argumentos do comando nem respostas da API. O script testa o provedor antes de aprovar o vínculo. Nenhum endpoint público permite escolher `credentialSecret` ou usar a conexão de outra conta. Um login FCC não concede automaticamente autorização para ler ESPN privada.

## 6. Verificar antes de promover

Abra `/health` e confira a versão e `authConfigured=true`. Isso confirma presença da configuração, não disponibilidade real de Firebase/Firestore. Crie uma conta e faça o fluxo completo de cadastro/confirmação/login/recuperação.

Valide o cadastro progressivo de 0, 1, 2 e 6 ligas, inclusive no Android e na web. Cartões e filtros devem corresponder aos vínculos reais, sem lugares reservados. Confirme que a sétima inclusão retorna 409 `LEAGUE_LIMIT_REACHED`, que remover libera uma vaga e que outra conta tem suas próprias vagas. Teste duas inclusões simultâneas quando há apenas uma vaga. Confirme 401 sem sessão, 404 para vínculo de outro usuário e ausência de dados da conta anterior após logout. Confirme que o worker rejeita chamada sem credencial IAM e que o Scheduler registra execução bem-sucedida.

Compare roster, temporada, histórico, projeções e confrontos com os provedores reais. Teste calendário internacional, sugestões entre quinta/domingo/segunda, notificações após fechar/reiniciar o app e tradução no Wi-Fi. Estatísticas ausentes devem aparecer indisponíveis, nunca preenchidas com fixtures.

Só depois desses testes decida o corte para produção. O serviço `/v1` anterior não é migrado por este script e as versões antigas podem continuar usando-o até o corte revisado.

## Referências oficiais

- [Validação de ID tokens Firebase](https://firebase.google.com/docs/auth/admin/verify-id-tokens)
- [Firebase Authentication REST](https://firebase.google.com/docs/reference/rest/auth)
- [Condições nas regras Firestore](https://firebase.google.com/docs/firestore/security/rules-conditions)
- [API pública Sleeper](https://docs.sleeper.com/)
- [Segredos no Cloud Run](https://docs.cloud.google.com/run/docs/configuring/services/secrets)
- [Cloud Scheduler com Cloud Run](https://docs.cloud.google.com/run/docs/triggering/using-scheduler)
- [Android Keystore](https://developer.android.com/privacy-and-security/keystore)
- [WebViewAssetLoader](https://developer.android.com/develop/ui/views/layout/webapps/load-local-content)
