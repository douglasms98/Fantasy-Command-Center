# Revisão do FCC — v8.0.0 RC2

O problema estrutural era um app baseado em um conjunto global de ligas e configuração manual de chave. A revisão estabelece um contrato de conta: toda liga, cache pessoal e conexão privada pertence a um UID Firebase confirmado. Não foi feita associação automática de suas ligas sem identificar e validar sua conta.

## Achados e alterações

| Área | Achado | Alteração no candidato | Validação pendente |
| --- | --- | --- | --- |
| Cadastro | Não havia fluxo de conta no backend legado | Cadastro, confirmação de e-mail, login, renovação e recuperação por Firebase Auth | Projeto Firebase e e-mails reais |
| Autenticação | Chaves globais e possibilidade de configuração vazia no legado | API v2 exige token Firebase; v1 não oferece acesso ao serviço multiusuário | IAM e configuração Cloud reais |
| Ligas | Lista global e dados pessoais embutidos; limite configurável de 30 no RC1 | Interface cresce de 0 a 6 conforme os cadastros; limite fixo por conta no servidor; contador, bloqueio da sétima liga e remoção que libera vaga | Migrar os seus vínculos aprovados e validar com Firestore real |
| Interface dinâmica | Grupos vazios de plataformas e risco de atualização ignorada durante sync | Cartões/filtros exatamente para os vínculos registrados; plataformas sem liga ocultas; atualizações sequenciais e descarte de listas antigas | Render visual e cadastro no aparelho |
| Acesso entre usuários | Dados globais podiam aparecer para todas as instalações | UID verificado no servidor, vínculo por conta e 404 para vínculo alheio | Verificação integrada com Firestore real |
| Troca de conta | Cache, UI e alarmes podiam sobreviver | Limpeza nativa, armazenamento web por UID, descarte de respostas atrasadas, alarmes com UID | Dois usuários no aparelho |
| API na web | HTML local e acesso a outro domínio dependiam de CORS/configuração manual | `/app` e API na mesma origem, cookie HttpOnly, origem exata, calendário no servidor | Publicação HTTPS |
| Semanas e BYEs | Grade 2026 e avanço por data fixa podiam continuar governando planejamento | Temporada de dados, semanas do provedor e calendário confirmado; BYE inferido apenas em semana completa | Calendário real e virada de temporada |
| Notificações | Permissão permitia o teste, mas não criava eventos automaticamente | Eventos a partir de horários confirmados, cache da conta e times do roster; remoção cancela agendamentos | Entrega Android com app fechado/reiniciado |
| Escalação | Pausa por rodada inteira | Mantida lógica RC2 de jogos ao vivo, bloqueio de quem já começou e reabertura entre jogos | Quinta, domingo, segunda e slots reais |
| Notícias | Manchetes originais em inglês | Mantida tradução Android ML Kit do RC2 e proteção por conta | Modelo/dispositivo; feed e tradução web ainda ausentes |
| Segundo plano | Leitura dependia do app aberto | Worker Cloud a cada quatro horas, WorkManager Android, atualização de fonte antiga ao abrir | Deploy Scheduler, bateria e aparelho |
| Diagnóstico/comparação | Cartões muito altos e botão sem contraste | Mantido grid móvel e contraste do RC2 | Render visual e aparelho |
| Estatísticas ausentes | Risco de tratar falta de dado como zero | Adaptadores preservam `null`; zero real é preservado; projeção antiga não vira atual | Paridade completa do enriquecimento/waivers/trades anterior |

## Testes executados

- **21 testes Python passaram**, com dados TEST_ONLY: quantidade dinâmica de 0 a 6 por usuário, bloqueio da sétima liga, duplicata no limite, pendência contando como cadastro, limite que não aumenta por variável de ambiente, remoção que libera vaga, até 6 em cada conta independentemente, inclusão idempotente, isolamento de leitura/sync/delete, e-mail confirmado, URLs seguras, preservação do último dado válido, intervalo de sync, ocultação de secrets, CORS, origem de login, verificação de revogação, cookies web, transporte nativo, remoção durante sync, calendário, internacional, histórico dinâmico e zero versus ausência.
- **Testes de lógica JavaScript passaram**: escalação entre jogos, pausa ao vivo, jogador já iniciado, kickoff desconhecido, datas de notificações, deduplicação, internacional sem jogador do roster, semana por calendário confirmado e regras de layout/contraste no CSS.
- **Testes de semanas passaram**: avanço W4→W6, origem da projeção, histórico até W5, limites de confirmação, overlay e migração de ordenação legada.
- **Teste da página inteira em jsdom passou**: cadastros reais na interface de teste de 0→1→2→6, contagem idêntica nos cartões/lista/filtros, ausência de grupos vazios, limite na interface e na API, remoção que libera vaga, contas independentes, inclusão durante sincronização, descarte de lista atrasada, limite atingido em outro dispositivo, cadastro com confirmação e entrada, logout, storage por UID, dados carregados, nomes tratados como texto, jogador com apóstrofo, watchlist e resposta de sessão atrasada.
- Parsing dos fontes Java, Python e XML e igualdade entre HTML Android/web foram conferidos. Parsing não verifica as classes/bibliotecas Android nem produz APK.

As fixtures ficam exclusivamente nos testes. O app entregue não recebe dados dessas fixtures.

## O que falta para considerar a revisão validada

Firebase/Firestore/IAM reais, deploy Cloud Run/Scheduler, cadastro e entrega dos e-mails, vínculo aprovado das suas ligas, ESPN privada quando necessária, paridade dos dados avançados, build Android e teste de notificações/tradução/layout no aparelho. Não foram executados testes com as suas ligas reais. O Chromium não ficou disponível para renderização nesta sessão; jsdom não valida aparência ou dimensões.

Por isso o pacote é **release candidate** e v7.3.2 permanece como referência. O candidato não deve substituir a produção antes de homologação. Esta revisão de código não significa que o endereço da API antiga já passou a aceitar contas.
