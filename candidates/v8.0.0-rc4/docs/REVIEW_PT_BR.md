# Revisão FCC v8.0.0 RC4

## Resultado

Sessão Android restaurada a partir do cache próprio e cifrado, nova entrada com o ícone FCC e dados enriquecidos no Cloud por conta, sem planilhas pessoais. API pública ESPN e Sleeper fornecem dados reais; notícias são filtradas dentro do Cloud a partir de feed geral. A interface continua dinâmica, limitada a seis ligas por UID.

## Testes executados

- **59 testes Python passaram**: isolamento entre contas, quota transacional, sincronizações concorrentes, sessão/Google/nonce/criptografia, leitura de configuração com projeto de cota, erros temporários de renovação sem apagar login, normalização dos provedores, scoring por liga, disponibilidade/ownership de waivers, calendário, alertas e cache comprimido.
- Notícias: consultas externas usam apenas o feed geral; troca de roster não muda a requisição ao publisher. IDs Sleeper sem mapeamento não são tratados como atletas ESPN. Testes de tradução verificam nomes/siglas protegidos e rejeitam traduções que os alteram.
- **Cinco suítes JavaScript passaram**: lógica original, semanas dinâmicas, cadastro de 0→1→2→6 ligas, rejeição da sétima, remoção/troca de conta, races de refresh, Google web/nativo, cache antes de rede, modo offline, rejeição do UID errado, bloqueio por kickoff e totais posicionais completos.
- Conferência DOM adicional com payloads reais das três ligas: cartões independentes, imagens com URLs dos times/adversários, histórico, waivers e seleção de adversários para trades apareceram sem erros JavaScript. Não executou consultas externas por nomes de jogadores.
- Análise sintática: **19 arquivos Python, 13 Java e 7 XML**. Assets Android/web e fragmento Google idênticos. `bash -n tools/deploy_v8.sh` passou.

Fixtures automatizadas são identificadas `TEST_ONLY`, em testes isolados. Não são inseridas no payload de produção. A análise sintática Java não substitui o build Android.

## Leituras reais em 11/10/2026 UTC

Consultas somente de leitura às ligas públicas cadastradas por Douglas, sem alterar escalações, transações ou contas. Dados individuais brutos não acompanham o pacote nem foram enviados ao GitHub.

| Liga | Roster | URLs de logo | Histórico | Projeções no roster | Jogadores livres | Movimentações | Adversário atual |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| ESPN · Cartola VK Serie A | 15 | 12 | 4 semanas | 15 | 876 | 46 | Nome real conferido |
| Sleeper · Paga PPR | 16 | 12 | 4 semanas | 13 | 706 | 93 | Nome real conferido |
| Sleeper · SUNDAY NIGHT FUMBLE | 26 | 12 | 4 semanas | 17 | 639 | 49 | Nome real conferido |

Os provedores informaram temporada 2026/rodada 5 nessa coleta; esses valores não são fixados no aplicativo. Histórico confirmado W1–W4 vem da fonte. ESPN apresentou placar vivo 12,0 × 0,0: a implementação anterior lia outro campo e mostrava zero. A nova leitura usa `totalPointsLive` e projeção correspondente ao período atual.

Jogadores em bye recebem zero apenas quando o calendário confirma o bye. Projeções especiais ausentes permanecem indisponíveis; a soma de uma escalação incompleta não é mostrada como total completo. Disponibilidade exclui jogadores de todos os rosters, IR/taxi e ownership do provedor. As contagens de waivers/transações variam com a coleta e não são valores de configuração.

As três ligas retornaram nomes e URLs dos logos de adversários reais. Foram gerados alertas futuros de jogos confirmados a partir do calendário. Notícias recentes correspondentes aos rosters apareceram no feed geral, sem consulta externa por nomes privados selecionados. Tradução Cloud real não foi executada: depende da opção administrativa.

## Ainda pendente

- Deploy RC4 e integração real com Firebase/Firestore/Secrets/Scheduler.
- Login real Google/e-mail, preservação da sessão no aparelho após fechar, logout/troca de conta e atualização sobre o app atual.
- PowerShell em Windows e compilação Gradle/APK no projeto Android existente.
- Renderização visual e entrega nativa de notificações com o aplicativo fechado ou telefone reiniciado.
- Liga ESPN privada, que ainda necessita conexão individual autorizada no servidor.
- Regras especiais Sleeper sem fatos suficientes, especialmente algumas bonificações de defesa/retorno e passes longos; não são substituídas por scoring de outra liga.

O pacote é um patch Android e backend, sem APK/projeto Gradle completo. Leituras de provedores não validam um deploy completo nem autorizam promover automaticamente a RC4; v7.3.2 permanece como referência até a homologação.

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
