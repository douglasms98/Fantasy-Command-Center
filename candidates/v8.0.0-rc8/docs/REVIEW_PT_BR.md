# Revisão FCC v8.0.0 RC7

## Escopo e referência

Esta revisão parte da RC6 e compara as funções de confrontos, planejamento, notícias, movimentações e histórico com o HTML arquivado da v7.3.2. Preserva o cálculo por regras da liga, semanas variáveis, isolamento por UID, seis ligas, Google e sessão/cache. Dados e datas fixas da versão antiga não são copiados para produção. Os defeitos corrigidos abrangem parte da lógica antiga e a integração com os novos dados normalizados.

## Falhas reproduzidas e corrigidas

| Problema | Correção e limite |
| --- | --- |
| Jogos repetidos por time/liga | Chave por semana e par NFL; um horário para cada jogo. BYEs dos jogadores mantidos por liga. |
| Formato distinto de jogo internacional | Mesmo formato AWAY @ HOME e horário; sem rótulo/local adicional. |
| Sleeper tinha totais parciais, mas não diferença/probabilidade | Mesma função para ambas as plataformas; parcial identificado e cobertura de todos os titulares exigida. |
| Nomes iguais misturavam rosters | Identificação por teamId; nome somente para compatibilidade anterior. |
| W1 e decisões vazias ao carregar | Fonte carregada e semana real exigidas; remoção de registros vazios antigos, preservação dos válidos. |
| Filtros duplicavam histórico | Comparação estável do conjunto completo de decisões, independente do filtro da tela. |
| Movimentos sem time e fora de ordem | Team/Owner/User normalizados, IDs mantidos, ordenação global por timestamp e filtro por liga. |
| Tradução literal/time traduzido | Templates contextualizados e proteção de nomes/termos antes da tradução; cache de tradução versionado. Original mantido se a tradução não for confiável. |
| Erro de sync aparecia como sucesso/cache normal | Resultado de falhas preservado, contador de falhas e aviso visual; calendário público não mascara falha das ligas no worker Android. |
| Falha de leitura Cloud parecia liga vazia | Resposta 503 específica; o cliente mantém o cache anterior. |
| Falha parcial de calendário apagava semanas | Semanas válidas retidas e marcadas desatualizadas; semanas ausentes são identificadas. |
| Time NFL desconhecido recebia BYE/projeção zero | BYE inferido somente para uma das 32 equipes NFL num calendário completo. |
| Percentuais da classificação eram limitados como probabilidade | Funções separadas para fração de classificação e percentual estimado. |
| Android criava lembrete além do fornecido pelo Cloud | Derivação local apenas quando não há lembretes de kickoff do Cloud. |
| Conferência idêntica mantinha horário antigo na tela | Metadados de conferência atualizados sem substituir o snapshot pesado. |

Regra especial desconhecida não vira zero. Estatísticas esparsas comuns podem representar zero; intervalos mutuamente exclusivos são usados somente quando o provedor publicou um desses intervalos. Faixas de field goals não são divididas artificialmente. Jogo NFL encerrado usa pontos reais; ausência de pontos reais não vira zero. Parcial não alimenta o otimizador como projeção completa. A probabilidade FCC é heurística, identificada como estimativa e indisponível quando falta cobertura de titulares. Caches antigos sem cobertura de projeção parcial não geram percentual até a nova sincronização.

## Verificações automatizadas

- **92 testes Python**: autenticação/Google, isolamento/quota, scoring/períodos/IDs, parcial versus ausente/zero, cache, armazenamento incremental, remoção/re-cadastro, erro de sync, leitura de snapshot, calendário parcial e linguagem NFL.
- **Oito suítes JavaScript**: lógica, semanas, contas, Google, restauração da sessão, desempenho, dados NFL e confiabilidade. Incluem filtros, loading W1, histórico estável, movimentações, percentuais e aviso de falha.
- **23 Python, 13 Java e sete XML** analisados sintaticamente. HTML e JSON de notícias Android/web e fragmento Google iguais; sintaxe Bash aprovada. Parsing Java não substitui build Android.
- Fixtures TEST_ONLY são testes isolados, não dados de produção. Nenhuma liga real foi alterada.

## Leituras reais em 11/10/2026 UTC

As ligas existentes foram consultadas somente para leitura. Os campos abaixo são resultados da coleta, não constantes do app. Dados privados brutos não acompanham o ZIP/GitHub.

| Fonte | Roster | Logos | Semanas anteriores | Jogadores livres | Movimentos / time informado | Projeções completas / parciais no roster |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Sleeper 1 | 16 | 12 | 4 | 701 | 97 / 97 | 13 / 2 |
| Sleeper 2 | 26 | 12 | 4 | 634 | 51 / 51 | 18 / 3 |
| ESPN pública | 15 | 12 | 4 | 876 | 56 / 56 | 15 / 0 |

Os adversários estavam identificados nas três ligas. Nas duas Sleeper, os 10 titulares de cada lado tinham projeção completa ou parcial e os confrontos apresentaram diferença e probabilidade identificadas como estimativa parcial. Regras especiais pendentes foram mantidas na cobertura. Uso recente: 14/15 e 23/25 elegíveis Sleeper, 13/14 ESPN. Contexto QB de WR/TE: 9/9, 14/14 e 7/7. Lacunas de dados pessoais continuam ausentes.

O DOM dos três payloads reais verificou os três confrontos, chaves únicas por jogo/semana e ausência de histórico W1 vazio. Inicialização local: cerca de 1,44 s; telas: 0,19–0,23 s; reaplicação da mesma revisão: 0,24 s. Mede Node/jsdom, não navegador/aparelho/rede reais.

## Pendências

Deploy RC7 e integração Firestore/Firebase/Secrets/Scheduler real; PowerShell/Gradle e APK Windows; login/reabertura/logout e visual no aparelho/navegador; entrega de notificações com app fechado/reiniciado. A web pública consultada nesta revisão ainda informou RC6. Logo publicado não garante que toda URL externa de imagem sempre responda.

Liga ESPN privada requer autorização individual. Google do FCC não autentica ESPN. Tradução Cloud permanece desabilitada por padrão; ML Kit precisa do modelo e pode falhar. Original em inglês é preservado quando necessário. Power Ranking/editoriais só aparecem quando publicados pela fonte; o FCC não inventa os valores para preencher lacunas. Fontes públicas podem atrasar/mudar schema. A RC7 não promete dados completos em todos os campos nem custo Cloud zero.

As otimizações incrementais da RC6 são preservadas: consultas idênticas não duplicam blocos/snapshots, uma alteração isolada regrava o bloco correspondente, cache privado por UID/geração/revisão, migração antiga e limpeza segura. A validação de Firestore usou double TEST_ONLY. Consulte [fontes e armazenamento](PUBLIC_DATA_PT_BR.md).

O pacote é um patch Android com backend completo, sem APK/projeto Gradle completo. v7.3.2 permanece a referência até homologação completa.

## Reproduzir testes

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
