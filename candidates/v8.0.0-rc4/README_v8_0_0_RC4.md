# Fantasy Command Center v8.0.0 RC4

Esta revisão mantém a sessão ao reabrir o Android, melhora a tela de entrada e recupera os dados de cada conta pelo FCC Cloud. **Nenhum usuário depende das planilhas de Douglas.** A interface acompanha seus próprios cadastros, de zero a **seis ligas**, com login Google ou e-mail/senha.

## Correções

- Sessão Android cifrada no Keystore; perfil e dados do próprio UID aparecem antes da renovação de rede. Uma indisponibilidade temporária mantém o cache; logout ou sessão realmente revogada exigem nova entrada. Dados de outra conta são rejeitados.
- Entrada com o ícone oficial FCC, Google em destaque, alternância entre entrar/cadastrar, exibição da senha e o texto **“Reúna todas suas ligas e faça as melhores decisões”**.
- ESPN: nomes/logos dos times e adversários, período atual explícito, placar ao vivo, histórico, projeções, jogadores livres e movimentações. O placar usa `totalPointsLive`; zero verdadeiro continua sendo zero.
- Sleeper: nomes/avatares, rosters de toda a liga, confrontos, histórico, jogadores livres e transações. Estatísticas públicas NFL são recalculadas com o scoring de cada liga; reservas e taxi também entram na verificação de disponibilidade.
- Histórico e rodada vêm das fontes. Ausências de dados são `null`, sem números fixos de W3/W4 ou projeções simuladas.
- Calendário NFL inclui jogos internacionais, byes e horários. Sugestões de escalação ficam disponíveis entre jogos; jogadores com kickoff passado permanecem bloqueados. Alertas futuros são gerados a partir dos jogos dos titulares, sem depender do teste de oito segundos.
- Notícias: o Cloud busca um feed público geral e filtra pelos jogadores dentro do servidor. Android traduz localmente com ML Kit; tradução dos títulos também na web pode ser habilitada no Cloud.
- Diagnóstico do roster compacto, mensagens de indisponibilidade legíveis no celular, botões principais com contraste e totais posicionais que não tratam projeções parciais como completas.
- API/worker mantêm a sincronização periódica no Cloud a cada quatro horas. Android usa WorkManager e reaproveita o cache quando o aplicativo retorna.

## Atualizar o Cloud

No Cloud Shell do projeto existente:

```bash
export FCC_PROJECT='fantasy-command-center-2026'
gcloud config set project "$FCC_PROJECT"
FCC_RC4_SOURCE="$(mktemp -d "$HOME/fcc-v8-rc4.XXXXXX")"
git clone --depth 1 https://github.com/douglasms98/Fantasy-Command-Center.git "$FCC_RC4_SOURCE"
cd "$FCC_RC4_SOURCE/candidates/v8.0.0-rc4"
bash tools/deploy_v8.sh "$FCC_PROJECT" fcc-v8-firebase-api-key:latest southamerica-east1
```

O script resolve a versão habilitada mais recente do segredo e verifica seu formato sem revelar o valor. Se o segredo ainda contiver um `appId` no lugar da `apiKey`, ele interrompe antes da publicação. Reutiliza as contas de serviço e a configuração Google existentes.

Para títulos traduzidos também na web, execute `export FCC_TRANSLATE_NEWS=true` **antes do deploy**. O script habilita Cloud Translation e concede o papel de tradução somente à API/worker. Esse serviço tem cobrança por uso; consulte [preços oficiais](https://cloud.google.com/products/translate/pricing). Sem essa opção, o Android ainda pode traduzir localmente e a web conserva o original quando não houver tradução disponível.

Detalhes: [CLOUD_SETUP_PT_BR.md](docs/CLOUD_SETUP_PT_BR.md) e [GOOGLE_LOGIN_SETUP_PT_BR.md](docs/GOOGLE_LOGIN_SETUP_PT_BR.md).

## Atualizar o Android

Extraia o ZIP RC4, abra o PowerShell na pasta extraída e execute:

```powershell
.\apply_v8_0_0_RC4.ps1 -ProjectRoot "C:\Users\Douglas M\AndroidStudioProjects\FantasyCommandCenter" -ApiBase "https://fcc-api-v8-ybeye4a6la-rj.a.run.app"
$FCC_JAVA_DIR = Join-Path $env:ProgramFiles "Android\Android Studio\jbr"
if (!(Test-Path "$FCC_JAVA_DIR\bin\java.exe")) { throw "Java do Android Studio não encontrado." }
$env:JAVA_HOME = $FCC_JAVA_DIR
$env:Path = "$FCC_JAVA_DIR\bin;$env:Path"
Set-Location "C:\Users\Douglas M\AndroidStudioProjects\FantasyCommandCenter"
.\gradlew.bat assembleDebug
```

O instalador faz backup e atualiza fontes/dependências/versão no projeto existente. Requer AndroidX, minSdk 26 e compileSdk 34 ou superior. Instale `app\build\outputs\apk\debug\app-debug.apk` por cima do aplicativo com **a mesma assinatura**, preservando seus dados. Reutilize o registro Firebase/SHA-1 dessa assinatura; ele não precisa ser recriado a cada versão.

## Validação e limites

**59 testes Python e cinco suítes JavaScript passaram.** As leituras reais de uma liga ESPN pública e duas Sleeper recuperaram logos, adversários, histórico, rosters, waivers, movimentações e projeções disponíveis, sem planilhas. Consulte [REVIEW_PT_BR.md](docs/REVIEW_PT_BR.md).

Este pacote contém **um patch de fontes Android e o backend completo**, sem APK ou projeto Gradle completo. Ainda faltam o deploy RC4, compilação no projeto Windows, login real e teste no aparelho, incluindo entrega das notificações com o aplicativo fechado. A revisão DOM não substitui renderização visual.

ESPN privada ainda precisa de uma conexão autorizada por conta no servidor. Certas regras especiais de pontuação Sleeper não podem ser calculadas a partir dos fatos públicos disponíveis; essas projeções aparecem indisponíveis. O app não substitui a pontuação da liga por PPR genérico. Notícias dependem de matérias reais recentes no feed. Web Push não foi implementado. v7.3.2 permanece a referência até a homologação completa.

## English

RC4 restores the encrypted Android session and account cache before network refresh, improves sign-in, and retrieves per-user league data through FCC Cloud without relying on personal spreadsheets. It fixes ESPN live-score fields, fetches team logos/opponents/history/free agents/transactions, and rescales public NFL facts using each Sleeper league's scoring rules. Registration remains dynamic with a six-league limit per account.

59 Python tests and five JavaScript suites passed; read-only checks covered one real public ESPN league and two Sleeper leagues. Cloud deployment, Windows/Android build, real sign-in, visual rendering and device notification delivery remain pending. This is an Android source patch plus a backend, not an APK. Unsupported scoring stays unavailable rather than being filled with simulated data.
