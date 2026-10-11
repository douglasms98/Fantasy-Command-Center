# Fantasy Command Center v8.0.0 RC5

A RC5 corrige recálculos que deixavam Android/web lentos e inclui as projeções publicadas pelo Sleeper. Logos, adversários, histórico, rosters, waivers, movimentações e calendário continuam vindo da API/Cloud, sem depender de planilhas pessoais. Login persistente e interface dinâmica de zero a seis ligas por conta são preservados.

## Mudanças

- Reutiliza diagnóstico/waivers/calendário durante cada renderização, sem conservar cálculos antigos após uma atualização de dados.
- Evita consultas simultâneas duplicadas e refazer trades quando o snapshot não mudou. Cadastros/status e calendário chegam no payload da conta.
- Comprime o transporte API/Android/web e revalida o HTML público com ETag. Dados de usuário mantêm `no-store` e isolamento por UID.
- Consulta a publicação semanal Sleeper e calcula o valor conforme o scoring de cada liga. Mostra separadamente o valor publicado no preset padrão.
- Quando faltam estatísticas de regras especiais, mostra a estimativa como `≈`/`PARCIAL` e não a utiliza no otimizador ou na probabilidade do confronto. Zero só é usado quando confirmado, inclusive por bye.
- Preserva sessão Android cifrada, identidade Google, notícias por feed geral, calendário internacional, sugestões entre jogos e alertas futuros. Não altera assinatura ou frequência do Scheduler.

## Atualizar o Cloud

No Cloud Shell:

```bash
export FCC_PROJECT='fantasy-command-center-2026'
gcloud config set project "$FCC_PROJECT"
FCC_RC5_SOURCE="$(mktemp -d "$HOME/fcc-v8-rc5.XXXXXX")"
git clone --depth 1 https://github.com/douglasms98/Fantasy-Command-Center.git "$FCC_RC5_SOURCE"
cd "$FCC_RC5_SOURCE/candidates/v8.0.0-rc5"
if bash tools/deploy_v8.sh "$FCC_PROJECT" fcc-v8-firebase-api-key:latest southamerica-east1; then
  gcloud scheduler jobs run fcc-v8-sync --location=southamerica-east1 --project="$FCC_PROJECT"
fi
```

Reutiliza o segredo Firebase correto e as identidades existentes. Não recrie usuários/ligas ou chaves. A execução manual do Scheduler solicita a atualização dos snapshots antigos; aguarde a conclusão e use **Atualizar minhas ligas**. Depois recarregue a web em `/app`. `/health` deve informar `version=8.0.0-rc5`.

Tradução Cloud de notícias continua opcional, conforme [CLOUD_SETUP_PT_BR.md](docs/CLOUD_SETUP_PT_BR.md). Esta revisão não exige habilitar serviços pagos adicionais. Google já configurado continua usando a mesma origem e certificado, conforme [GOOGLE_LOGIN_SETUP_PT_BR.md](docs/GOOGLE_LOGIN_SETUP_PT_BR.md).

## Atualizar o Android

Extraia o ZIP RC5 e execute na pasta extraída:

```powershell
.\apply_v8_0_0_RC5.ps1 -ProjectRoot "C:\Users\Douglas M\AndroidStudioProjects\FantasyCommandCenter" -ApiBase "https://fcc-api-v8-ybeye4a6la-rj.a.run.app"
$FCC_JAVA_DIR = Join-Path $env:ProgramFiles "Android\Android Studio\jbr"
if (!(Test-Path "$FCC_JAVA_DIR\bin\java.exe")) { throw "Java do Android Studio não encontrado." }
$env:JAVA_HOME = $FCC_JAVA_DIR
$env:Path = "$FCC_JAVA_DIR\bin;$env:Path"
Set-Location "C:\Users\Douglas M\AndroidStudioProjects\FantasyCommandCenter"
.\gradlew.bat assembleDebug
```

O instalador cria backup e atualiza fontes/dependências/versão no projeto existente. Requer AndroidX, minSdk 26 e compileSdk 34 ou superior. Instale `app\build\outputs\apk\debug\app-debug.apk` por cima do app com **a mesma assinatura**. Não é preciso recadastrar a mesma SHA-1 no Firebase.

## Validação

**66 testes Python e seis suítes JavaScript passaram**, mais parsing de 20 Python/13 Java/7 XML e igualdade dos HTMLs. Leituras reais de uma liga ESPN pública e duas Sleeper confirmaram adversários, URLs de logos, histórico, rosters, jogadores livres e movimentações; 13 e 20 valores publicados Sleeper chegaram ao roster dessas duas ligas.

No teste local DOM, trocar telas passou de aproximadamente 2,6 s para 0,17 s. Um payload real de aproximadamente 2,07 MB caiu para 179 KB com gzip. Os tempos não medem o aparelho ou a conexão do usuário. [Resultados e limites](docs/REVIEW_PT_BR.md).

Este pacote é um patch Android e backend completo, sem APK/projeto Gradle completo. Deploy RC5, build Windows/Android, login real, renderização visual e entrega nativa de notificações permanecem pendentes. ESPN privada exige conexão autorizada por conta. Regras especiais sem fatos suficientes continuam incompletas; nenhum valor simulado é usado em produção. v7.3.2 permanece a referência até a homologação completa.

## English

RC5 reduces repeated roster/waiver/calendar calculations, coalesces API reads, reuses unchanged snapshots and compresses Android/web data transfer. It adds published weekly Sleeper projections and applies each league's scoring rules, while retaining cloud-backed logos, opponents, history, free agents and transactions. Published standard presets and incomplete custom estimates are labeled separately; partial estimates are excluded from lineup recommendations and matchup probabilities.

66 Python tests, six JavaScript suites and read-only checks of one public ESPN league and two Sleeper leagues passed. Local DOM tab changes fell from roughly 2.6 s to 0.17 s, and gzip reduced a real payload by about 91%. These are local measurements. RC5 deployment, Android build, real sign-in, visual rendering and device notification delivery remain pending. This package contains source patches and a backend, not an APK.
