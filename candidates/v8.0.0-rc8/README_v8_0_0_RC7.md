# Fantasy Command Center v8.0.0 RC7

A RC7 corrige confiabilidade, notícias, planejamento, confrontos e movimentações da RC6. Mantém conta Google, sessão/cache Android, ligas dinâmicas por usuário (até seis), dados públicos compartilhados e snapshots incrementais no Firestore. Nenhum usuário depende de uma planilha pessoal.

## Correções

- Notícias: nomes de jogadores, sobrenomes, times NFL e termos como RB1/IR são preservados. Frases reconhecidas recebem tradução contextual. O Android protege esses termos antes do ML Kit. Traduções antigas incorretas deixam de ser reutilizadas; títulos sem tradução confiável conservam o original.
- Planejamento: cada jogo NFL aparece uma vez por semana, inclusive com todas as ligas selecionadas. Os jogadores em BYE continuam individuais por liga. Jogos internacionais usam o mesmo formato e horário dos demais.
- Confrontos ESPN/Sleeper: diferença projetada e probabilidade usam a mesma lógica. Totais Sleeper com regras especiais ausentes são identificados como estimativa parcial. Se falta um titular, a probabilidade continua indisponível. Projeções parciais não entram no otimizador como completas.
- Histórico de decisões: não grava a W1 padrão durante o carregamento. Filtros/reconsultas iguais não duplicam registros. Registros antigos vazios e não validados são retirados; decisões reais da W1 são preservadas.
- Movimentações: identificam o time responsável, mostram horário/lance recebido e seguem a liga selecionada, em ordem temporal entre provedores.
- Auditoria adicional: erros de sincronização deixam de aparecer como sucesso; falhas de leitura Cloud preservam o cache; calendário parcial retém semanas válidas; jogadores sem time NFL definido não viram BYE/zero; percentuais de classificação não usam os limites da probabilidade; lembretes nativos não duplicam os do Cloud; conferências sem alteração atualizam o horário exibido.
- Confrontos usam o ID do time para distinguir equipes com nomes iguais. Ausência de dado e zero confirmado continuam separados.

O calendário, rosters, adversários, logos, resultados, movimentações, uso, snaps, draft e projeções permanecem no API/Cloud. Esta versão não habilita serviço pago adicional. [Fontes e limites](docs/PUBLIC_DATA_PT_BR.md).

## Atualizar o Cloud

Cole no Cloud Shell:

```bash
export FCC_PROJECT='fantasy-command-center-2026'
gcloud config set project "$FCC_PROJECT"
FCC_RC7_SOURCE="$(mktemp -d "$HOME/fcc-v8-rc7.XXXXXX")"
git clone --depth 1 https://github.com/douglasms98/Fantasy-Command-Center.git "$FCC_RC7_SOURCE"
cd "$FCC_RC7_SOURCE/candidates/v8.0.0-rc7"
if bash tools/deploy_v8.sh "$FCC_PROJECT" fcc-v8-firebase-api-key:latest southamerica-east1; then
  gcloud scheduler jobs run fcc-v8-sync --location=southamerica-east1 --project="$FCC_PROJECT"
fi
```

Reutiliza contas, segredo Firebase e ligas existentes. Aguarde o Scheduler e recarregue `/app`. `/health` deve informar `version=8.0.0-rc7`. A primeira carga pode demorar mais; as demais reutilizam os caches. **Atualizar minhas ligas** também sincroniza, respeitando o intervalo mínimo por liga.

## Atualizar o Android

Extraia o ZIP RC7 e execute **na pasta extraída**:

```powershell
.\apply_v8_0_0_RC7.ps1 -ProjectRoot "C:\Users\Douglas M\AndroidStudioProjects\FantasyCommandCenter"
$FCC_JAVA_DIR = Join-Path $env:ProgramFiles "Android\Android Studio\jbr"
if (!(Test-Path "$FCC_JAVA_DIR\bin\java.exe")) { throw "Java do Android Studio não encontrado." }
$env:JAVA_HOME = $FCC_JAVA_DIR
$env:Path = "$FCC_JAVA_DIR\bin;$env:Path"
Set-Location "C:\Users\Douglas M\AndroidStudioProjects\FantasyCommandCenter"
.\gradlew.bat assembleDebug
if ($LASTEXITCODE -ne 0) { throw "A compilação não terminou. Confira o erro acima." }
```

Instale `app\build\outputs\apk\debug\app-debug.apk` por cima do app existente com **a mesma assinatura**. O instalador faz backup e preserva seu keystore. Não é preciso abrir o Android Studio ou repetir Google/SHA-1 já configurado. Requer AndroidX, minSdk 26 e compileSdk 34 ou superior. Deploy Cloud não instala um novo APK no aparelho.

## Validação

92 testes Python e oito suítes JavaScript passaram. Análise de 23 fontes Python, 13 Java e sete XML, igualdade de assets Android/web, JSON de notícias e fragmento Google, e sintaxe Bash passaram. Leituras reais de uma liga ESPN pública e duas Sleeper confirmaram rosters, logos, adversários, resultados, movimentações com time responsável e projeções. Com os dados reais, o DOM mostrou os três confrontos com diferença/probabilidade e planejamento sem duplicações. [Revisão e cobertura](docs/REVIEW_PT_BR.md).

No perfil local DOM, inicialização levou cerca de 1,44 s e troca de telas 0,19–0,23 s. Não são medidas no aparelho ou na conexão do usuário. Depuração de armazenamento usa um double Firestore TEST_ONLY.

Deploy RC7, Firestore/Firebase real, PowerShell/Gradle, login, renderização visual e notificações no aparelho permanecem pendentes. Liga ESPN privada requer conexão individual autorizada. A probabilidade é uma estimativa do FCC, não um percentual oficial/calibrado do provedor. Campos sem publicação continuam ausentes; traduções desconhecidas podem ficar em inglês. O pacote contém fontes Android e backend, sem APK/projeto Gradle completo. v7.3.2 permanece a referência até homologação.

## English

RC7 fixes contextual NFL headlines, shared-game planning, partial Sleeper matchup estimates, loading-state decision logs and transaction actors. Additional reliability fixes cover failed synchronization reporting, Cloud snapshot reads, partial calendar retention, unknown-team BYEs, standings percentages, duplicate native reminders and unchanged-data freshness. Existing account isolation, six-league limit, Android session/cache and incremental storage remain.

92 Python tests, eight JavaScript suites and read-only checks of one public ESPN league and two Sleeper leagues passed. Cloud deployment, real Firestore integration, Windows/Android build and device validation remain pending. This is a source patch and backend, not an APK.
