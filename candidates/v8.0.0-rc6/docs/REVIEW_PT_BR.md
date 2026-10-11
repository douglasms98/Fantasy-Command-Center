# Revisão FCC v8.0.0 RC6

## Resultado

A RC6 complementa as ligas ESPN/Sleeper com dados NFL públicos do nflverse e usa snapshots incrementais no Firestore. Preserva cadastros, conta Google, sessão/cache Android, isolamento por UID, limite de seis ligas e otimizações da RC5. Dados de cada liga vêm da API/Cloud; uma planilha pessoal não é requisito para outros usuários.

Uso recente e contexto do quarterback entram no diagnóstico/análise já existentes. A ficha do jogador mostra volume observado, snaps e draft NFL. A qualidade dos dados informa cobertura e publicação parcial/desatualizada. Os pontos e projeções fantasy continuam respeitando a pontuação de cada liga; estatísticas genéricas nflverse não são injetadas como PPG/projeção fantasy.

## Armazenamento incremental

- Um snapshot idêntico mantém a revisão e atualiza somente os metadados de conferência.
- Pools grandes são divididos em 16 grupos por ID estável. Mudanças regravam os blocos afetados; os demais são reutilizados. Ordem e entradas duplicadas são reconstruídas corretamente.
- Em teste isolado com 800 waivers, alterar a projeção de um jogador gravou um bloco e o novo manifesto. Reconsultar os mesmos dados, com outro horário, não gravou snapshot/blocos.
- A publicação da revisão verifica a geração do vínculo; remover/recriar uma liga não permite que uma sincronização anterior publique sobre a nova.
- Snapshots antigos continuam legíveis e migram na próxima sincronização. Leituras em andamento mantêm revisões recentes; a coleta de blocos retirados ocorre diariamente. Falha na limpeza não invalida os novos dados.
- Cache privado limitado por bytes/entradas, por UID/liga/geração/revisão. O cache público contém somente fatos NFL genéricos. Caches e hashes não substituem a autenticação.

A primeira gravação cria vários blocos. Uma consulta fria pode exigir mais leituras Firestore do que o antigo snapshot monolítico; reaproveitamento e economia dependem das mudanças reais e do cache. Testes de armazenamento usam um double Firestore identificado `TEST_ONLY`, não uma base Cloud real.

## Validação executada

**84 testes Python** e **sete suítes JavaScript** passaram. Cobrem login/Google, conta/quota, semanas, calendar/lineup, notícias, scoring Sleeper completo/parcial, compressão, sessão, desempenho e os novos casos de cache público, IDs/períodos, ausência versus zero, alteração isolada, snapshot idêntico, migração, contas e re-cadastro. No detalhe DOM, volume zero confirmado aparece; uma medida ausente não vira zero.

Análise sintática: **22 Python, 13 Java, sete XML**. Assets Android/web e fragmento Google idênticos; `bash -n tools/deploy_v8.sh` passou. Parsing Java não substitui compilação Android. Fixtures automatizadas ficam nos testes e não são dados de produção.

## Leituras reais em 11/10/2026 UTC

Uma liga ESPN pública e duas Sleeper existentes foram consultadas somente para leitura. Nenhuma conta, escalação ou movimentação foi alterada. Três arquivos NFL públicos foram baixados e normalizados pelo novo módulo: 8.682 registros de jogadores ofensivos, 4.512 linhas de estatísticas e 6.064 linhas de snaps da temporada. Os dados de uso usados nesta rodada vieram das semanas anteriores à W5.

| Liga consultada | Roster | Uso recente | Snaps | Draft conhecido | Contexto QB de WR/TE | URLs de logos | Resultados anteriores |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Sleeper 1 | 16 | 14/15 elegíveis | 14/15 | 14/15 | 9/9 | 12 | 4 semanas |
| Sleeper 2 | 26 | 23/25 elegíveis | 23/25 | 20/25 | 14/14 | 12 | 4 semanas |
| ESPN pública | 15 | 13/14 elegíveis | 13/14 | 12/14 | 7/7 | 12 | 4 semanas |

As três ligas tinham nomes dos adversários. Jogadores livres: 706, 639 e 876, respectivamente; movimentações: 95, 49 e 46. Projeções completas/bye no roster: 13, 17 e 15; valores publicados Sleeper: 13 e 20. Números são resultados de uma coleta, não configurações fixas. DEF não entra no denominador dos dados pessoais NFL; jogadores sem participação/ID conhecido podem ficar sem complemento.

Cada snapshot real precisou de 39–40 blocos, e o maior bloco comprimido ficou abaixo de 6,3 KB. A reconstrução desses snapshots reproduziu todos os dados, exceto o horário que é apresentado pelos metadados de conferência. Cada arquivo público normalizado/comprimido ficou abaixo de 260 KB. Dados brutos das ligas não acompanham o pacote nem foram publicados no GitHub.

## Desempenho local

Com os três payloads reais enriquecidos, a inicialização DOM levou aproximadamente 1,55 s; trocar telas levou 0,17–0,21 s. Reaplicar a mesma revisão levou cerca de 0,20 s, sem repetir a preparação pesada de trades. O payload ficou maior com os novos fatos, mas mantém compressão API/Android/web e caches limitados. Os tempos medem Node/jsdom local e não o aparelho, a conexão ou o Cloud.

O transporte de conta continua `no-store`. Somente o HTML público usa ETag. Atualizações do calendário que mudam apenas o horário de coleta não invalidam a revisão da conta; mudança real de jogo/placar/bloqueio invalida. Cloud Run usa zero instâncias mínimas; primeira carga/cold start podem demorar mais.

## Pendências e limites

- Deploy RC6 e validação real Firestore/Firebase/Secrets/Scheduler. O deploy da RC4 anterior foi confirmado pelos logs do usuário; isso não valida RC6.
- Execução PowerShell/Gradle no Windows, APK e instalação com a mesma assinatura.
- Login/reabertura/logout/troca de usuário e desempenho/renderização no aparelho e navegador reais.
- Entrega nativa de notificações com aplicativo fechado/reiniciado.
- ESPN privada: conexão individual autorizada; login Google do FCC não autentica ESPN.
- Tradução Cloud real continua opcional; regras especiais Sleeper sem fatos suficientes continuam parciais e não entram no otimizador/probabilidade.
- Fontes públicas podem atrasar, mudar schema ou ficar indisponíveis; o último dado válido é identificado, e lacunas não são inventadas. Elas não garantem todos os campos/editoriais das planilhas.
- Fontes sem assinatura paga não garantem custo Cloud zero. [Fontes e condições](PUBLIC_DATA_PT_BR.md).

Este pacote é um patch de fontes Android e backend completo, sem APK/projeto Gradle completo. v7.3.2 permanece a referência até homologação completa.

## Reprodução

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r backend/requirements-dev.txt
PYTHONPATH=backend python -m pytest backend/tests -q
npm ci
npm test
python tools/check_sources.py
bash -n tools/deploy_v8.sh
```
