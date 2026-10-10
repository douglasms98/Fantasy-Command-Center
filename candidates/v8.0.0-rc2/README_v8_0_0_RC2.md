# Fantasy Command Center v8.0.0 RC2 — interface dinâmica, até 6 ligas

Candidato com interface determinada pelas ligas que cada usuário cadastrou: com 1 liga aparece 1, com 2 aparecem 2, e assim por diante, até **6 ligas por conta**. A conta nova começa vazia. A lista de cadastro, os cartões da tela inicial e os filtros acompanham inclusões e remoções no Android e na web. Quantidades usadas em testes não criam configurações fixas para contas.

O código foi implementado e testado localmente. **Firebase/Firestore reais, publicação no Cloud Run, APK e testes no aparelho ainda estão pendentes.** v7.3.2 continua sendo a referência. Este ZIP contém um patch Android e um backend completo para homologação, não um APK nem um projeto Android completo com Gradle wrapper.

## O que mudou

- Limite fixo de **6 ligas por usuário**, conferido numa transação do servidor. A sétima inclusão é rejeitada, inclusive por chamada direta à API. Duplicatas não ocupam outra vaga; ligas pendentes contam no limite; remover libera uma vaga.
- Contador **X de 6 ligas cadastradas**, aviso ao atingir o limite e bloqueio do botão de cadastro. Só aparecem grupos de plataformas com ligas cadastradas; a conta vazia oferece **Cadastrar minha primeira liga**.
- Inclusões e remoções atualizam a tela mesmo quando outra sincronização está em andamento. Respostas antigas da lista não substituem uma lista mais recente.
- Cadastro por e-mail e senha, confirmação de e-mail, entrada, saída e recuperação de senha.
- Autenticação automática das chamadas com a sessão da conta. A interface não pede chave da API, token do Sync ou cookies.
- Ligas em `fcc_users/{uid}/leagues/{id}`. A API extrai o UID do token verificado; o cliente não escolhe o proprietário.
- Tela **Minha conta e ligas** para cadastrar, listar e remover liga pelo ID/link, temporada e time. No Sleeper, o nome de usuário pode selecionar o time público.
- Interface vazia para conta nova, sem ligas, elencos, notícias ou avatares pessoais embutidos. Filtros e armazenamento local são separados por UID.
- Tokens nativos cifrados com Android Keystore e fora do JavaScript. Na web, o token de renovação fica em cookie HttpOnly; o token de acesso fica em memória.
- Cache e notificações limpos na troca de conta. Respostas atrasadas de outra sessão são descartadas.
- Web servida pelo backend em `/app`, com chamadas na mesma origem. Calendário NFL consultado pelo Cloud para ambos os clientes, sem grade fixa ou temporada embutida.
- Atualização do servidor preparada a cada quatro horas com Cloud Scheduler e worker privado; Android usa WorkManager com rede disponível. Ao abrir, dados antigos podem provocar atualização automática, respeitando o intervalo mínimo.
- Mantidas as correções de lógica do RC2 para semanas, projeções, escalação, jogos internacionais, diagnóstico do roster e contraste.

## Preparação e uso

1. Configure e publique o ambiente de homologação seguindo [CLOUD_SETUP_PT_BR.md](docs/CLOUD_SETUP_PT_BR.md).
2. Abra `https://ORIGEM_DO_BACKEND_V8/app`. Crie a conta e confirme o e-mail.
3. Entre em **Minha conta e ligas** e cadastre de 1 a 6 ligas reais. Não há quantidade mínima nem ligas pré-cadastradas. Ao remover uma liga, os cartões, filtros e vagas disponíveis são atualizados.
4. Para o Android, aplique o patch ao projeto existente:

```powershell
.\apply_v8_0_0_RC2.ps1 -ProjectRoot "C:\caminho\FantasyCommandCenter" -ApiBase "https://ORIGEM_DO_BACKEND_V8"
```

O endereço é definido pelo desenvolvedor durante o build. O usuário final só faz login. Use o mesmo Firebase/backend para web e Android. O instalador adiciona WebKit, WorkManager e tradução ML Kit quando ausentes, cria backup e atualiza a versão; é necessário sincronizar o Gradle e compilar no Android Studio. Requer projeto compatível com Java, AndroidX, minSdk 26 e compileSdk compatível com as dependências.

## Limitações concretas desta revisão

- Nenhum recurso foi criado ou alterado no seu Google Cloud nesta sessão. O endereço do backend anterior não ganha `/v2` automaticamente. Publique o serviço novo antes de instalar este candidato.
- Suas ligas existentes não foram atribuídas a um UID desconhecido. Cadastre-as depois do login ou use o importador administrativo com um mapeamento aprovado; não há associação por suposição.
- A API pública do Sleeper permite acompanhar um time; o nome de usuário não autentica a conta Sleeper. Não implementamos alteração de escalação no provedor.
- ESPN privada fica com conexão pendente até aprovação no servidor, por usuário e liga. Este candidato não implementa OAuth/login direto no ESPN. Cookies pessoais nunca aparecem na interface nem no repositório.
- Os adaptadores normalizam roster, histórico, classificação e confronto disponíveis. Projeções ausentes permanecem desconhecidas. O pool de waivers, ranking, sugestões de trade e enriquecimento estatístico completos do pipeline anterior ainda precisam ser portados/validados. Não existem números substitutos para preencher essas lacunas.
- Planilhas/Sync legados não são usados como fallback compartilhado nesta API multiusuário. Uma conexão de planilha por conta ainda precisa de implementação própria.
- Notícias e tradução nativa mantêm o caminho Android do RC2, sujeito a download do modelo e teste no aparelho. O backend web deste RC não implementa feed/tradução de notícias nem Web Push.
- Atualização periódica não garante execução Android em um minuto exato, especialmente com restrições de bateria ou app forçado a parar. Atualização Cloud depende do Scheduler instalado.
- Os testes usam fixtures marcadas TEST_ONLY. Não houve validação ao vivo das suas ligas, do Firebase/Firestore, dos cookies privados, da implantação, do layout visual nem do APK.

## Validação reproduzível

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r backend/requirements-dev.txt
(cd backend && python -m pytest tests -q)
npm ci
npm test
python tools/check_sources.py
```

Ver [REVIEW_PT_BR.md](docs/REVIEW_PT_BR.md) para o diagnóstico, resultados e critérios de homologação.

## English

This release candidate adds Firebase email/password accounts, verified per-user league storage, league registration/removal, and account-specific Android/web screens. End users no longer paste API keys. Web refresh credentials use an HttpOnly cookie; Android credentials use encrypted Keystore-backed storage. New accounts have no seeded league data. Logout and account changes clear private caches and notifications.

The interface follows actual registrations: one registered league shows one, two show two, up to a fixed maximum of six per account. Home cards, platform groups and filters update after additions/removals. Both the UI and server enforce the maximum; pending leagues count, duplicates are idempotent, and removing a league frees a slot.

Local backend and JavaScript tests passed using isolated TEST_ONLY fixtures. Cloud configuration/deployment, real provider verification, Android build/device checks, private ESPN authorization and full legacy analytics parity remain pending. v7.3.2 stays the reference. This archive includes an Android source patch and a staging backend, not a ready APK.
