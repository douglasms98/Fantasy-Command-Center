# Dados públicos e armazenamento na RC6

## Fontes

| Origem | Dados usados | Atualização no FCC |
| --- | --- | --- |
| [Sleeper API](https://docs.sleeper.com/) | Ligas, rosters, equipes/avatares, resultados, movimentações e diretório público | Diretório: cache de 24 h; ligas: Scheduler existente e atualização manual |
| Publicação semanal Sleeper | Estatísticas de projeção e presets publicados | Cache compartilhado; scoring e período conferidos por liga |
| ESPN | Dados da liga e jogadores; calendário e feed NFL público | Caches existentes e Scheduler; ligas privadas exigem autorização |
| [nflverse — jogadores](https://nflreadr.nflverse.com/reference/load_players.html) | IDs GSIS/ESPN/PFR, idade e draft NFL | Cache compartilhado de 24 h |
| [nflverse — estatísticas](https://nflreadr.nflverse.com/reference/load_player_stats.html) | Corridas, targets, recepções, jardas e passes tentados | Cache compartilhado de 4 h |
| [nflverse — snaps](https://nflreadr.nflverse.com/reference/load_snap_counts.html) | Snaps e participação ofensiva | Cache compartilhado de 4 h |

A disponibilidade depende da publicação pelo provedor. [Frequência dos dados nflverse](https://nflreadr.nflverse.com/articles/nflverse_data_schedule.html). O cache do FCC não transforma arquivos pós-jogo em dados ao vivo. Para volume recente, são usadas até três participações de semanas regulares **anteriores** à rodada analisada. Semanas atuais, pós-temporada e temporadas diferentes não entram nessa janela.

Os arquivos são baixados de releases públicos de [nflverse-data](https://github.com/nflverse/nflverse-data), por temporada, sem nomes/IDs selecionados a partir de rosters ou credenciais. ETag/Last-Modified permitem respostas 304; tamanho e schema são limitados. Os dados selecionados são cruzados dentro do Cloud por IDs confirmados e posição. Identidades ausentes/ambíguas ficam sem enriquecimento. Não há consulta externa por nome de jogador do roster.

Capital do draft é a escolha **NFL**, não a posição do draft fantasy da liga. Uso é uma medida de volume observada, não uma previsão de pontuação. Fantasy PPG, histórico e projeções continuam seguindo as regras ESPN/Sleeper da própria liga. Snaps não são convertidos em pontos fantasy. QB1 vem do diretório/depth chart público Sleeper quando há um único titular confirmado; ausência de relato de lesão não é uma confirmação médica.

## Um banco, ligas isoladas

O Firestore existente guarda `fcc_users/{uid}/leagues/{liga}`. O UID vem de um token verificado, não do formulário. Cada conta registra de zero a seis ligas, e a interface usa essa lista. Liga privada/pendente também ocupa uma vaga. Não são criados seis bancos Firestore físicos.

Estatísticas NFL públicas ficam em `fcc_public_cache` e são reutilizadas entre contas. Essa coleção não contém rosters, vínculos de usuário, cookies ESPN ou tokens Firebase. No teste com arquivos atuais, cada cache normalizado/comprimido ficou abaixo de 260 KB, dentro do limite adotado pelo backend.

Snapshots privados têm manifesto e blocos comprimidos imutáveis. Pools grandes usam 16 grupos por ID estável, preservando a ordem do provedor. A comparação ignora somente o horário de verificação do provedor. Uma reconsulta idêntica atualiza os metadados de conferência, sem duplicar o snapshot; uma mudança grava os blocos afetados e publica a nova revisão com verificação da geração do vínculo.

O namespace de blocos inclui a geração do vínculo. Uma sincronização antiga não pode publicar no cadastro removido/recriado. O cache privado em memória é limitado a 32 entradas/32 MiB comprimidos e usa UID, liga, geração e revisão; não substitui autenticação. Revisões recentes ficam disponíveis por um dia para leituras em andamento. A limpeza ocorre no máximo uma vez por dia, sem usar exclusões TTL faturáveis ou criar outro job.

Os dados no formato anterior continuam legíveis. A migração é automática na próxima sincronização válida e não apaga os registros de usuários ou ligas. A primeira gravação cria os blocos; consultas frias podem ler mais documentos do que o formato monolítico anterior. O ganho incremental depende da quantidade de dados que realmente mudou e do reaproveitamento de cache — não significa zero leituras/escritas.

## Limites de gratuidade

Não se adiciona uma assinatura paga de dados, chaves para nflverse, BigQuery, tradução Cloud ou novas tarefas do Scheduler. A implantação continua nos serviços já configurados. O intervalo automático segue em quatro horas e há intervalo mínimo de cinco minutos entre tentativas manuais por liga. Cloud Run é configurado para zero instâncias mínimas, com os limites de instâncias anteriores.

[Firestore: cotas](https://firebase.google.com/docs/firestore/quotas), [Cloud Run: preços](https://cloud.google.com/run/pricing) e [Cloud Scheduler: preços](https://cloud.google.com/scheduler/pricing) têm condições próprias. Tráfego de saída, região, número de usuários, builds, imagens e armazenamento podem gerar custo na conta existente. Alertas de orçamento não são um teto de cobrança. Usar fontes públicas gratuitas não permite garantir uma fatura Cloud de R$ 0. Direitos/termos dos publicadores também continuam aplicáveis.

Se uma fonte de enriquecimento falhar, usa-se sua última publicação válida com indicação de desatualização. Sem publicação anterior, a cobertura fica parcial. A sincronização ESPN/Sleeper pode continuar sem esses complementos; o backend nunca inventa volume, draft ou projeções para preencher a tela.
