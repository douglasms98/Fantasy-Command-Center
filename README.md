# Fantasy Command Center (FCC)

## Português (BR)

Aplicativo Android em desenvolvimento para centralizar a gestão de ligas de fantasy football da NFL, com integração planejada com ESPN, Sleeper e Google Cloud. Reúne elencos, estatísticas, resultados, notícias e apoio às decisões de escalação, waivers e trocas, com suporte às pontuações Standard e PPR.

## English

An Android application under development to centralize NFL fantasy football league management, with planned ESPN, Sleeper, and Google Cloud integrations. It brings together rosters, statistics, results, news, and support for lineup, waiver, and trade decisions, with Standard and PPR scoring.

## Histórico / History

Este repositório preserva os pacotes e previews recuperados do projeto. Os nomes originais são mantidos. A presença no histórico não significa que uma versão foi validada.

- **v8.0.0 RC2:** [interface dinâmica e limite de 6 ligas por conta](candidates/v8.0.0-rc2/README_v8_0_0_RC2.md). Uma liga cadastrada mostra uma, duas mostram duas, até seis. Inclusão/remoção atualizam cartões e filtros; interface e servidor bloqueiam a sétima. Testes locais passaram; Cloud e Android pendentes.
- **v8.0.0 RC1:** [contas e ligas por usuário](candidates/v8.0.0-rc1/README_v8_0_0_RC1.md), com cadastro/login Firebase, ligação das ligas ao UID e interface Android/web sem chave manual. Testes locais passaram; ativação Cloud, provedores reais e Android pendentes. É candidato, não APK pronto.
- **v7.3.4 RC2:** [semanas dinâmicas](candidates/v7.3.4-rc2/README_v7_3_4_RC2.md), com proveniência das projeções e histórico por fonte. Testes de lógica passaram; build Android, dispositivo e API web pendentes.
- **v7.3.4 RC1:** [candidato de correção](candidates/v7.3.4-rc1/README_v7_3_4_RC1.md) para notificações, escalação, planner, tradução e interface. Testes de lógica passaram; build Android e dispositivo pendentes. É um patch, não um APK.
- **v7.3.2:** referência atual; ainda exige validação das integrações e testes no dispositivo.
- **v7.3.3 ALLIGATORS_PPR_PREP:** descartada pelo autor por utilizar dados simulados. Arquivada apenas para preservar o histórico. Não instalar nem implantar como versão válida.
- Demais versões: histórico de desenvolvimento, patches e previews; sem nova validação funcional durante o arquivamento.

The repository preserves recovered project packages and previews. Original filenames are retained. Archival does not imply validation. v7.3.2 is the current reference. v7.3.3 ALLIGATORS_PPR_PREP was rejected because it used simulated data and must not be installed or deployed as a valid release.

## Estrutura / Structure

- `archive/candidates/`: candidatos ainda não validados no Android.
- `candidates/v8.0.0-rc2/`: interface dinâmica, quota de 6 por usuário, patch Android, backend e testes.
- `candidates/v8.0.0-rc1/`: patch Android, backend de contas, testes e guia Cloud.
- `candidates/v7.3.4-rc2/`: patch, código e testes com semanas dinâmicas.
- `candidates/v7.3.4-rc1/`: código, instalador e testes do patch RC1.
- `archive/packages/`: pacotes Android, backend e patches.
- `archive/previews/`: previews HTML.
- `archive/discarded/`: versões explicitamente descartadas.
- `VERSIONS.md`: índice de arquivos.
- `versions.json`: inventário com tamanho, data e SHA-256.

As integrações estão em validação. Dados simulados não devem ser apresentados como dados reais das ligas. / Integrations are being validated. Simulated data must not be presented as real league data.

