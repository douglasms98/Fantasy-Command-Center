# Ativar Google no FCC RC3

Projeto usado nesta sessão: `fantasy-command-center-2026`. A API RC2 está publicada; este guia atualiza os mesmos serviços para RC3. O Secret Manager já contém `fcc-v8-firebase-api-key:1`. Não recrie esse segredo nem envie seu valor ao chat.

## 1. Habilitar o provedor

Abra [Firebase Authentication](https://console.firebase.google.com/project/fantasy-command-center-2026/authentication/providers). Em **Métodos de login**, ative **Google**, escolha o e-mail de suporte do projeto e salve. E-mail/senha pode continuar habilitado.

## 2. Autorizar a versão web

Abra [Google Auth Platform → Clientes](https://console.cloud.google.com/auth/clients?project=fantasy-command-center-2026). Edite o cliente **Aplicativo da Web** usado pelo provedor Google do Firebase. Em **Origens JavaScript autorizadas**, acrescente:

```text
https://fcc-api-v8-ybeye4a6la-rj.a.run.app
```

Use a origem sem `/app`, sem caminho e sem barra final. Não substitua as origens existentes. Caso abra outra URL do serviço, essa origem também precisa estar autorizada e aceita pela API; prefira o endereço acima.

Para identificar o cliente exato, após baixar o RC3, execute no Cloud Shell:

```bash
python3 tools/firebase_google_client.py --project fantasy-command-center-2026
```

Esse comando imprime somente o client ID público. Ele não exibe API keys, access tokens ou client secrets. O deploy também inclui o domínio do FCC em **Domínios autorizados** do Firebase, preservando os demais.

Confira **Público-alvo** e o status do aplicativo OAuth. Quando o projeto estiver em teste, use uma conta autorizada para teste. A liberação para os demais usuários segue a configuração do projeto Google; o código não remove essa exigência.

## 3. Atualizar o Cloud

No clone usado no Cloud Shell:

```bash
cd /home/douglasmsvg98/fcc-v8-rc2.9d5ue5
git pull --ff-only
cd candidates/v8.0.0-rc3
bash tools/deploy_v8.sh fantasy-command-center-2026 fcc-v8-firebase-api-key:1 southamerica-east1
```

O script interrompe antes do deploy se Google estiver desativado ou sem client ID válido. Ele lê a configuração do Firebase pela conta autenticada do Cloud Shell, publica API/worker e preserva o agendamento a cada quatro horas. Não usa um client secret na aplicação.

Abra `/health`: `version` deve ser `8.0.0-rc3` e `googleConfigured` deve ser `true`. Esses campos conferem a presença da configuração; faça o login real para validá-la.

Os desafios expiram em cinco minutos mesmo sem TTL. Para limpar os documentos expirados, configure TTL em `fcc_auth_challenges.expiresAt`, como em `fcc_rate_limits.expiresAt`. Incorpore a regra de bloqueio de `fcc_auth_challenges` às regras do Firestore; regras amplas existentes podem permitir acesso apesar de outro bloco conter `false`.

## 4. Registrar a assinatura Android

Abra [Configurações gerais do Firebase](https://console.firebase.google.com/project/fantasy-command-center-2026/settings/general). Se ainda não houver aplicativo Android, cadastre o pacote **`com.douglas.fantasycommandcenter`**. Confira o `applicationId` no Gradle do seu projeto: use o valor real se ele for diferente.

No terminal PowerShell, na raiz do projeto Android:

```powershell
.\gradlew.bat signingReport
```

Cadastre no Firebase a **SHA-1** da assinatura usada pelo APK. Debug e release podem usar certificados diferentes; o APK instalado precisa corresponder ao certificado cadastrado. Preserve sua assinatura anterior para instalar por cima do app atual. O instalador RC3 não altera o keystore.

Este cliente usa Credential Manager e troca a credencial pelo backend REST. Não adiciona FirebaseAuth SDK nem exige colar uma API key ou um client ID no Android. O client ID é recebido da API; o registro Android/SHA-1 continua necessário.

Depois aplique `apply_v8_0_0_RC3.ps1`, sincronize o Gradle, compile e teste no aparelho. São incluídas `androidx.credentials:credentials:1.3.0`, `credentials-play-services-auth:1.3.0` e `googleid:1.1.1`. Credential Manager requer compileSdk 34 ou superior neste pacote.

## 5. Conferência funcional

Teste a entrada Google na web e no Android com a mesma conta: ambos devem receber o mesmo UID e a mesma lista de ligas. Confirme cadastro de uma e duas ligas, limite de seis, remoção e troca de conta. Para uma conta já criada por senha, entre por senha e use **Vincular conta Google**; confira suas ligas antes e depois.

Feche o seletor sem escolher conta: o app deve mostrar cancelamento e permitir tentar novamente. Verifique também a saída durante um fluxo de entrada e o retorno de uma outra conta, sem reaparecerem dados do usuário anterior.

## Fontes

- [Google no Firebase Android](https://firebase.google.com/docs/auth/android/google-signin)
- [Origens JavaScript e cliente web](https://developers.google.com/identity/gsi/web/guides/get-google-api-clientid)
- [Google Identity Services e nonce](https://developers.google.com/identity/gsi/web/reference/js-reference)
- [Firebase Authentication REST](https://firebase.google.com/docs/reference/rest/auth)
- [Configuração do provedor Google](https://docs.cloud.google.com/identity-platform/docs/reference/rest/v2/projects.defaultSupportedIdpConfigs/get)
