# Fantasy Command Center v8.0.0 RC6

A RC6 acrescenta fatos públicos do nflverse e sincronização incremental no Firestore. Cada usuário mantém suas próprias ligas (até seis), sem depender de planilhas pessoais. Os dados NFL públicos são compartilhados entre as contas; rosters, vínculos e credenciais continuam isolados por UID.

## O que muda

- Volume recente, targets, recepções, corridas, passes tentados, snaps e capital do draft NFL complementam os dados ESPN/Sleeper.
- O diagnóstico e a análise de jogadores usam o volume e o contexto do quarterback. O detalhe do jogador mostra as medidas recebidas e a qualidade dos dados mostra a cobertura.
- ESPN/Sleeper continuam responsáveis pelas ligas, rosters, adversários, logos, resultados, movimentações e projeções conforme as regras da liga. nflverse não é um serviço de projeções fantasy.
- O Cloud compara os dados: uma consulta sem mudanças mantém o mesmo snapshot; quando algo muda, grava apenas os blocos afetados. Os snapshots antigos são lidos e migrados na próxima sincronização bem-sucedida.
- Cache público por temporada, cache privado por UID/liga/revisão, downloads condicionais e limpeza diária dos blocos retirados. Mantém o Scheduler a cada quatro horas.
- Login/cache Android, Google, semanas dinâmicas, otimizador entre jogos, calendário internacional e desempenho da RC5 são preservados.

As fontes consultadas não exigem uma assinatura de API paga. Não são habilitados novos serviços pagos, tradução Cloud ou tarefas extras. A conta Google Cloud existente continua sujeita às cotas e à cobrança de uso, inclusive tráfego, builds e armazenamento; esta versão não promete uma fatura de R$ 0. [Fontes, arquitetura e limites](docs/PUBLIC_DATA_PT_BR.md).

## Atualizar o Cloud

Cole no Cloud Shell:

```bash
export FCC_PROJECT='fantasy-command-center-2026'
gcloud config set project "$FCC_PROJECT"
FCC_RC6_SOURCE="$(mktemp -d "$HOME/fcc-v8-rc6.XXXXXX")"
git clone --depth 1 https://github.com/douglasms98/Fantasy-Command-Center.git "$FCC_RC6_SOURCE"
cd "$FCC_RC6_SOURCE/candidates/v8.0.0-rc6"
if bash tools/deploy_v8.sh "$FCC_PROJECT" fcc-v8-firebase-api-key:latest southamerica-east1; then
  gcloud scheduler jobs run fcc-v8-sync --location=southamerica-east1 --project="$FCC_PROJECT"
fi
```

Reutiliza o segredo Firebase correto, as contas e os vínculos existentes. Não recrie usuários/ligas ou chaves. O comando do Scheduler solicita a sincronização; aguarde sua conclusão e recarregue a web em `/app`. `/health` deve informar `version=8.0.0-rc6`. A primeira carga pública pode demorar mais; as próximas usam os caches. **Atualizar minhas ligas** também executa a sincronização, respeitando o intervalo mínimo.

## Atualizar o Android

Extraia o ZIP RC6 e execute **na pasta extraída**:

```powershell
.\apply_v8_0_0_RC6.ps1 -ProjectRoot "C:\Users\Douglas M\AndroidStudioProjects\FantasyCommandCenter" -ApiBase "https://fcc-api-v8-ybeye4a6la-rj.a.run.app"
$FCC_JAVA_DIR = Join-Path $env:ProgramFiles "Android\Android Studio\jbr"
if (!(Test-Path "$FCC_JAVA_DIR\bin\java.exe")) { throw "Java do Android Studio não encontrado." }
$env:JAVA_HOME = $FCC_JAVA_DIR
$env:Path = "$FCC_JAVA_DIR\bin;$env:Path"
Set-Location "C:\Users\Douglas M\AndroidStudioProjects\FantasyCommandCenter"
.\gradlew.bat assembleDebug
if ($LASTEXITCODE -ne 0) { throw "A compilação não terminou. Confira o erro acima." }
```

Instale `app\build\outputs\apk\debug\app-debug.apk` por cima do app com **a mesma assinatura**. O instalador faz backup e preserva seu keystore. Não é preciso repetir a configuração Google/SHA-1 que já funciona. O pacote requer AndroidX, minSdk 26 e compileSdk 34 ou superior.

## Validação e pendências

84 testes Python e sete suítes JavaScript passaram; 22 fontes Python, 13 Java e sete XML foram analisadas. Leituras reais de uma liga ESPN pública e duas Sleeper confirmaram os dados e o enriquecimento. Alterar um jogador entre 800 waivers gravou um bloco; uma reconsulta sem mudanças não criou snapshot/blocos. Na medição local DOM com dados reais, telas levaram aproximadamente 0,17–0,21 s; isso não mede o aparelho ou a rede. [Revisão completa](docs/REVIEW_PT_BR.md).

Deploy RC6 e integração real Firestore/Firebase/Scheduler, build Windows/Android, login e notificações no aparelho permanecem pendentes. Liga ESPN privada precisa de conexão individual autorizada; Google do FCC não autentica ESPN. Dados ausentes permanecem ausentes e projeções parciais Sleeper continuam identificadas e excluídas do otimizador. Este é um patch de fontes Android com backend completo, sem APK/projeto Gradle completo. v7.3.2 continua a referência até a homologação.

## English

RC6 adds shared public nflverse facts (recent usage, snaps and NFL draft capital), quarterback context and incremental Firestore snapshots. It retains per-user league isolation, a six-league limit, existing registrations, Android session/cache and each league's ESPN/Sleeper scoring. Only changed snapshot blocks are stored; unchanged data retains its revision. Existing snapshots migrate on successful sync. Public sources do not require a paid API subscription, but existing Google Cloud usage is subject to quotas and billing.

84 Python tests, seven JavaScript suites and read-only checks of one public ESPN league and two Sleeper leagues passed. Deployment, real Firestore integration, Windows/Android build and device validation remain pending. This package contains source patches and a backend, not an APK.
