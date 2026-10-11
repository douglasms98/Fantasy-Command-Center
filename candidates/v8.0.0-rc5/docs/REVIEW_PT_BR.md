# Revisão FCC v8.0.0 RC5

## Resultado

A RC5 reduz os recálculos da interface e as leituras duplicadas da API, comprime o transporte Android/web e acrescenta projeções semanais publicadas pelo Sleeper. Preserva os dados recuperados na RC4: logos, nomes dos adversários, histórico, rosters, jogadores livres, movimentações, calendário, notícias e alertas. Cada conta usa seus próprios vínculos no Cloud, de zero a seis ligas, sem depender de planilhas pessoais.

## Desempenho medido

O gargalo principal estava no diagnóstico recalculado para cada candidato a waiver, no calendário recalculado milhares de vezes e no processamento repetido de snapshots sem mudanças. Os resultados agora são reutilizados dentro de uma atualização da interface e descartados ao final dela; a próxima atualização considera os novos dados e horários.

| Medida local | RC4 | RC5 |
| --- | ---: | ---: |
| Trocar telas, mesmos dados de três ligas | 2,56–2,84 s | 0,16–0,19 s |
| Inicialização, mesmos dados | 5,05 s | 1,31 s |
| Dados atualizados, teste DOM adicional | — | 0,16–0,19 s por tela |
| Reaplicar a mesma revisão de dados | — | 0,15 s |

Esses tempos foram medidos em Node/jsdom, não no aparelho ou no navegador do usuário. Demonstram a redução do trabalho da interface, sem garantir o mesmo tempo em outros dispositivos. No payload real atualizado de três ligas, a compressão gzip reduziu aproximadamente 2,07 MB para 179 KB, cerca de 91% menos bytes. A API mantém respostas de conta com `no-store`; somente o HTML público usa ETag/revalidação. A compressão também é decodificada pelo cliente Android.

Refreshes simultâneos compartilham uma leitura. Cadastros/status e calendário completos vêm no payload, evitando consultas repetidas. Snapshots com a mesma `dataVersion` não refazem a preparação pesada de trades; a interface ainda atualiza horários e bloqueios. Alterações de dados ou conta invalidam o reaproveitamento. Não foram aumentados memória, CPU, limites de instância ou frequência do Scheduler.

## Projeções Sleeper

O Cloud consulta a publicação pública semanal do Sleeper por temporada/rodada, sem enviar seleção privada de jogadores. Confere período, posição e publicação, rejeitando linhas que contêm somente ADP. O cache público é reaproveitado entre ligas e as regras de pontuação são aplicadas individualmente.

- Projeção completa: usada quando os fatos publicados cobrem as regras da liga. A alternativa ESPN já existente permanece disponível quando pode calcular o scoring completo.
- Valor publicado no preset Sleeper: aparece identificado como PPR padrão, Half PPR padrão ou Standard padrão, separado do resultado específico da liga.
- Regras especiais incompletas: aparece `≈` e `PARCIAL` quando há uma estimativa calculável. Esse valor não é apresentado como pontuação completa e não entra nas recomendações de escalação ou na probabilidade do confronto.
- Bye confirmado pelo calendário: recebe zero. Ausência de projeção não vira zero, nem uma soma parcial é apresentada como total completo.

## Testes executados

- **66 testes Python passaram**, incluindo isolamento por UID, quota de seis ligas, autenticação/sessão, sincronizações concorrentes, provedores reais normalizados, calendário, notícias, compressão, revalidação do HTML, contexto leve do calendário e projeções Sleeper por período/scoring completo ou parcial.
- **Seis suítes JavaScript passaram**: lógica, semanas dinâmicas, contas, Google, sessão e desempenho. Os novos checks conferem equivalência das recomendações com/sem memoização, invalidação após mudança de projeção, ausência de projeções parciais no otimizador, reaproveitamento de revisão e coalescência das chamadas.
- Conferência DOM com dados recém-consultados das três ligas: rosters, adversários, URLs dos logos, histórico, waivers, opções de trades e valores publicados Sleeper apareceram sem erros JavaScript. Não executou consultas externas por nomes selecionados dos rosters.
- Análise sintática: **20 arquivos Python, 13 Java e 7 XML**. Assets Android/web e fragmento Google idênticos. `bash -n tools/deploy_v8.sh` passou.

Fixtures automatizadas são identificadas `TEST_ONLY` e ficam nos testes isolados. Não são inseridas em produção. Parsing Java não substitui compilação Android; DOM não substitui renderização visual.

## Leituras reais em 11/10/2026 UTC

Consultas somente de leitura a uma liga ESPN pública e duas Sleeper cadastradas por Douglas. Nenhuma escalação, transação ou conta foi alterada. Payloads individuais brutos não acompanham o pacote e não foram enviados ao GitHub.

| Liga | Roster | URLs de logo | Histórico | Projeções completas/bye no roster | Valores publicados Sleeper | Estimativas parciais | Jogadores livres | Movimentações |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| ESPN · Cartola VK Serie A | 15 | 12 | 4 semanas | 15 | 0 | 0 | 876 | 46 |
| Sleeper · Paga PPR | 16 | 12 | 4 semanas | 13 | 13 | 2 | 706 | 95 |
| Sleeper · SUNDAY NIGHT FUMBLE | 26 | 12 | 4 semanas | 17 | 20 | 4 | 639 | 49 |

Todos os adversários atuais tinham nomes reais e URLs de logo. Contagens de valores publicados e estimativas podem se sobrepor com um bye confirmado; a interface prioriza o bye. As contagens variam com a coleta e não são configuração fixa. O período informado pelos provedores foi temporada 2026/rodada 5; temporadas e semanas continuam dinâmicas.

## Ainda pendente nesta RC5

- Deploy RC5 e integração real Firebase/Firestore/Secrets/Scheduler. Os logs enviados pelo usuário confirmaram o deploy da RC4 anterior.
- PowerShell no Windows, build Gradle/APK e instalação com a mesma assinatura do aplicativo existente.
- Login real, reabertura da conta/cache, desempenho no aparelho, logout/troca de usuário e renderização visual Android/web.
- Entrega nativa das notificações com aplicativo fechado ou telefone reiniciado.
- Liga ESPN privada: continua exigindo conexão individual autorizada no servidor. Google do FCC não autentica ESPN.
- Tradução Cloud real, opcional. As regras especiais Sleeper sem fatos suficientes continuam identificadas como incompletas.

Pacote de fontes Android e backend, sem APK ou projeto Gradle completo. Leituras dos provedores não validam um deploy completo. v7.3.2 permanece como referência até a homologação.

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
