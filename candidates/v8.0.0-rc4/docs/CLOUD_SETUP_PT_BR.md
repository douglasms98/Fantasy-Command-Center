# Atualizar FCC Cloud para RC4

Projeto existente: **fantasy-command-center-2026**; região **southamerica-east1**. API, worker, contas de serviço e Scheduler já foram criados nos logs enviados por Douglas. Esta revisão não foi publicada no Cloud nesta sessão.

## Publicação no projeto existente

Cole o bloco completo no **Cloud Shell**:

```bash
export FCC_PROJECT='fantasy-command-center-2026'
gcloud config set project "$FCC_PROJECT"
FCC_RC4_SOURCE="$(mktemp -d "$HOME/fcc-v8-rc4.XXXXXX")"
git clone --depth 1 https://github.com/douglasms98/Fantasy-Command-Center.git "$FCC_RC4_SOURCE"
cd "$FCC_RC4_SOURCE/candidates/v8.0.0-rc4"
bash tools/deploy_v8.sh "$FCC_PROJECT" fcc-v8-firebase-api-key:latest southamerica-east1
```

O clone em pasta nova evita o erro `tools/deploy_v8.sh: No such file or directory` e preserva o checkout anterior. Não use `SEU_PROJECT_ID`: o ID correto já está preenchido.

O script:

1. Lê o client ID público Google do Firebase, com o projeto de cota explícito.
2. Resolve `latest` para uma versão numérica habilitada do segredo e confere o formato da `apiKey`, sem imprimir seu valor.
3. Publica a API **fcc-api-v8** e o worker **fcc-worker-v8** com a mesma imagem.
4. Atualiza a origem web e os domínios Firebase, preservando os anteriores.
5. Mantém o worker privado e o Scheduler **fcc-v8-sync**, a cada quatro horas, com IAM/OIDC.

Não recrie as contas de serviço ou os cadastros de usuário. Os vínculos existentes continuam no Firestore. Usuários finais não precisam informar chaves, client secrets ou credenciais Cloud.

## Se o segredo ainda estiver incorreto

`apiKey` e `appId` são campos diferentes. A chave Firebase começa com `AIza`; um valor como `1:...:web:...` é o identificador do aplicativo. O deploy RC4 recusa esse valor antes da publicação. A conferência do formato não garante que a chave esteja válida ou corretamente restrita no Firebase.

Abra [Secret Manager](https://console.cloud.google.com/security/secret-manager?project=fantasy-command-center-2026), selecione **fcc-v8-firebase-api-key → Nova versão** e cole apenas o valor do campo `apiKey` das [configurações do aplicativo web Firebase](https://console.firebase.google.com/project/fantasy-command-center-2026/settings/general). Salve e execute novamente o deploy com `:latest`. Não cole o bloco JavaScript no Bash. A versão antiga permanece registrada; o script não volta automaticamente para `:1`.

## Notícias em português também na web

Para habilitar a tradução dos títulos públicos no servidor, antes do comando de deploy:

```bash
export FCC_TRANSLATE_NEWS=true
bash tools/deploy_v8.sh "$FCC_PROJECT" fcc-v8-firebase-api-key:latest southamerica-east1
```

Essa opção habilita **Cloud Translation** e concede `roles/cloudtranslate.user` à API e ao worker. Usa a identidade do Cloud Run, sem outra chave. Os títulos do feed geral são traduzidos antes de filtrar por elenco; nenhum publisher recebe a seleção privada de jogadores da conta. Traduções são reaproveitadas em cache e nomes NFL/siglas protegidos são conferidos.

Cloud Translation possui [cobrança por uso](https://cloud.google.com/products/translate/pricing). A opção padrão do script é `false`. Android conserva a tradução local ML Kit; o primeiro download do modelo precisa de conexão compatível com a configuração de Wi-Fi. Se não houver tradução válida, exibe o título original e sua fonte.

## Google, banco e permissões existentes

Confira [GOOGLE_LOGIN_SETUP_PT_BR.md](GOOGLE_LOGIN_SETUP_PT_BR.md). O Google precisa continuar habilitado no Firebase, com a origem web e o pacote/certificado Android corretos. Use a URL `/app` servida pela própria API, nunca um HTML aberto por `file://`.

O Firestore usado é Native, banco `(default)`. Outro banco exige `FCC_FIRESTORE_DATABASE` nos dois serviços. As regras [firestore-v8.rules](../backend/firestore-v8.rules) bloqueiam acesso direto de clientes às coleções FCC; incorpore-as às regras existentes sem apagar as de outros aplicativos. Um bloqueio não cancela um `allow` amplo de outro bloco. A API usa Admin SDK e verifica o UID autenticado.

As identidades existentes precisam destes papéis:

| Identidade | Papel/escopo |
| --- | --- |
| fcc-v8-api | `roles/datastore.user`, `roles/firebaseauth.viewer`; `roles/secretmanager.secretAccessor` no segredo Firebase |
| fcc-v8-worker | `roles/datastore.user`; acesso apenas aos segredos privados de ligas autorizadas |
| fcc-v8-build | `roles/run.builder` |
| fcc-v8-scheduler | `roles/run.invoker` somente no worker |
| API e worker, com tradução habilitada | `roles/cloudtranslate.user` |

O operador precisa poder publicar Cloud Run e atuar como essas contas. O script reutiliza as identidades; não concede Owner/Editor. Configuração de um projeto novo deve seguir a [documentação oficial de deploy por código-fonte](https://docs.cloud.google.com/run/docs/deploying-source-code).

TTL em `fcc_rate_limits.expiresAt` e `fcc_auth_challenges.expiresAt` limpa registros expirados. Os desafios já expiram logicamente mesmo sem TTL. O cache público de NFL/notícias fica separado dos snapshots de cada UID.

## Cadastro e atualização das ligas

Abra **Minha conta e ligas** na web ou no Android. Sleeper aceita link/ID e username público ou roster ID; ESPN pública recebe liga e team ID. Cada usuário começa sem ligas e cadastra até **seis**. Uma inclusão gera um cartão; duas geram dois. Duplicatas não consomem outra vaga, liga pendente ocupa vaga e remoção libera uma. A API impõe o limite de forma transacional.

Rosters, logos, adversários, resultados, waivers e transações vêm dos provedores no Cloud. O calendário NFL orienta rodada, byes, kickoff e jogos internacionais. Projeções públicas NFL são recalculadas conforme a liga Sleeper; regras especiais sem fatos suficientes ficam indisponíveis. Nenhuma planilha pessoal é usada como fallback para outras contas.

O Cloud atualiza dados mesmo quando o telefone está fechado. WorkManager também atualiza o cache Android periodicamente quando o sistema permite; não fornece horário exato. Depois do deploy, use **Atualizar minhas ligas** para substituir o snapshot anterior e conferir os novos campos.

Importações administrativas opcionais continuam em `tools/import_approved_leagues.py`: JSON local aprovado pelo titular, UID confirmado e modo de inspeção antes de `--apply`. Não envie configurações privadas ou snapshots ao GitHub.

## ESPN privada

O login Google do FCC não autentica a conta ESPN. Uma liga privada permanece pendente até existir conexão autorizada para seu titular. O candidato ainda não oferece OAuth ESPN.

Com autorização e credenciais válidas administradas no Cloud, use um segredo exclusivo `fcc-espn-UID_FIREBASE-ID_VINCULO_FCC`, contendo `SWID` e `espn_s2`. O ID de vínculo é o retornado por `/v2/leagues`, não o ID externo da liga. Conceda acesso somente às identidades API/worker responsáveis e confira:

```bash
export FCC_GCP_PROJECT='fantasy-command-center-2026'
python3 tools/bind_private_espn.py --uid UID_FIREBASE --league ID_VINCULO_FCC --secret NOME_SECRET
python3 tools/bind_private_espn.py --uid UID_FIREBASE --league ID_VINCULO_FCC --secret NOME_SECRET --apply
```

Os argumentos acima descrevem identificadores administrativos; substitua-os pelos valores confirmados dessa conexão. Cookies não são argumentos, respostas da API ou conteúdo do APK. A conexão não pode ser compartilhada automaticamente com outra conta.

## Conferência após atualizar

Abra a URL web mostrada no deploy. `/health` deve informar `version=8.0.0-rc4`, `authConfigured=true` e `googleConfigured=true`; isso confirma configuração presente, não um login completo. Entre, atualize as ligas e compare os dados com ESPN/Sleeper.

No Android, instale o APK da RC4 com a mesma assinatura. Entre uma vez, feche e reabra: deve recuperar a própria conta/cache e atualizar os dados. Teste logout/troca de conta, notificações futuras, reinicialização do telefone e sugestões entre jogos. Confira a execução real do Scheduler; a agenda configurada sozinha não prova sincronização bem-sucedida.

As leituras reais e os testes locais estão em [REVIEW_PT_BR.md](REVIEW_PT_BR.md). Deploy, Firestore real, compilação Windows/Android e entrega no aparelho ainda precisam dessa conferência. O script não altera `/v1` nem migra contas globais do sistema antigo.
