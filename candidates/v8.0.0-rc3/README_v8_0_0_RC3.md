# Fantasy Command Center v8.0.0 RC3 — Entrar com Google

Esta versão acrescenta **Entrar com Google** à web e ao Android. A entrada e o cadastro por e-mail/senha continuam disponíveis. As ligas pertencem ao UID verificado do Firebase; a interface acompanha os cadastros reais, de zero a **seis ligas por conta**.

## Implementação

- Web: botão oficial Google Identity Services, em português, com seleção de conta. A credencial Google é enviada à API para validação e troca por uma sessão Firebase. O token de renovação fica em cookie Secure/HttpOnly; não é entregue ao JavaScript.
- Android: seletor do Credential Manager, acionado pelo botão na interface. O OAuth não é aberto na WebView. As credenciais são trocadas e cifradas no Android Keystore; o HTML recebe somente o perfil do usuário.
- API: valida assinatura, emissor, audiência, validade e nonce do token Google. O desafio expira em cinco minutos e é consumido numa transação do Firestore, uma única vez, com vínculo ao transporte e à finalidade.
- Conta existente: **Minha conta e ligas → Vincular conta Google** conecta o provedor ao UID autenticado. Não há migração de ligas por e-mail nem criação de dados substitutos. Conflitos entre contas são rejeitados.
- Saída da conta cancela o fluxo nativo e invalida respostas pendentes. Na web, a saída aguarda trocas de sessão em andamento para limpar o cookie depois da resposta.
- O cliente recebe o OAuth client ID público do servidor. Usuários finais não precisam informar API keys, client secrets ou cookies.

## Configuração e instalação

Siga [GOOGLE_LOGIN_SETUP_PT_BR.md](docs/GOOGLE_LOGIN_SETUP_PT_BR.md). É necessário ativar Google no Firebase, autorizar a origem web no cliente OAuth e registrar o pacote/SHA-1 do Android. O deploy lê automaticamente o client ID configurado no Firebase; não pede outra chave.

Atualize o backend primeiro. Depois aplique o patch ao projeto Android existente:

```powershell
.\apply_v8_0_0_RC3.ps1 -ProjectRoot "C:\caminho\FantasyCommandCenter" -ApiBase "https://fcc-api-v8-ybeye4a6la-rj.a.run.app"
```

O instalador cria backup, atualiza fontes, versão e dependências. Requer AndroidX, minSdk 26 e compileSdk 34 ou superior. Preserve a mesma assinatura para atualizar o app instalado.

## Validação e limites

Testes locais de backend, criptografia e interface usam fixtures isoladas `TEST_ONLY`. Nenhum dado de liga simulado é incluído como real. Consulte [REVIEW_PT_BR.md](docs/REVIEW_PT_BR.md) para os resultados finais.

Esta RC3 é um **patch Android e um backend para homologação**, sem APK ou projeto Gradle completo. Ainda requer deploy da RC3, configuração Google, login real e teste no aparelho. O serviço RC2 anterior respondeu a `/health` e `/app` com HTTP 200; isso não valida este fluxo novo. A referência de análise continua sendo v7.3.2 até validar ESPN/Sleeper reais.

As limitações de integração do RC2 permanecem: ESPN privada depende de autorização administrativa; planilhas legadas não são fallback compartilhado; o backend não oferece Web Push, notícias traduzidas nem toda a análise avançada do pipeline anterior.

## English

RC3 adds Google sign-in through the official web button and Android Credential Manager. The API validates Google ID tokens and exchanges them for Firebase sessions. Existing users can explicitly link Google while preserving their authenticated UID and registered leagues. The dynamic interface and maximum of six leagues per account are retained.

Local tests use isolated TEST_ONLY fixtures. Real Google/Firebase configuration, RC3 deployment, Android compilation/device checks and ESPN/Sleeper validation remain pending. This package contains an Android source patch and a backend, not an APK.
