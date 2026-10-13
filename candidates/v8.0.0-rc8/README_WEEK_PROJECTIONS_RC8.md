# FCC v8.0.0 RC8 — candidato de correção Sleeper W6

**STATUS: CANDIDATO NÃO HOMOLOGADO. NÃO PUBLICADO NO CLOUD, NEM TESTADO NO ANDROID.**

Esta cópia isolada da RC7 propõe correção da atribuição de projeções e do agrupamento de valores Sleeper; mantém o formato de payload do backend para o Android existente.

## Alteração funcional

- Padroniza códigos de times NFL ao cruzar jogos com jogadores; respeita aliases JAC/JAX e WSH/WAS.
- Em BYE, com calendário confirmado e completo: projeção numérica 0,0. Campos parciais ausentes são limpos.
- Em Sleeper, jogador com status **OUT** e jogo não iniciado: projeção 0,0; não transforma IR, QUESTIONABLE ou status indeterminado em zero. ESPN não tem regra nova de OUT.
- O cálculo de confronto e a soma dos titulares passam a aceitar esses zeros, sem converter ausência legítima de dados em zero.
- Não sobrescreve pontos de partidas em andamento ou encerradas.

## Validação pendente

1. Executar: `cd backend && python -m pytest -q tests/test_sleeper_week_coverage.py tests/test_reliability.py tests/test_providers.py`.
2. Comparar payloads reais Sleeper W6, regras específicas das duas ligas, disponibilidade de estatísticas e jogos completos.
3. Examinar valores de `injuryStatus`, `currentProjection`, `projectionWeek`, `projectionMissingStats`, `byeWeek` e `matchup.*ProjectionCoverage` de todos os titulares, em ambas as ligas, sem logar tokens pessoais.
4. Revisar a integração com mapa posicional, waivers, otimizador, alertas e pontuação ESPN, antes de deploy.
5. Atualizar inventários VERSIONS.md e versions.json, com checksums reais, antes de publicação de versão.

Nenhum valor foi simulado como dado de liga real. RC7 e v7.3.2 são preservadas.
