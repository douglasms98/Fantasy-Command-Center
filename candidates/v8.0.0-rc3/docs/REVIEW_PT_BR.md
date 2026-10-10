# Revisão FCC v8.0.0 RC3

## Resultado

Login Google implementado na web, no Android e na API, com configuração descrita em [GOOGLE_LOGIN_SETUP_PT_BR.md](GOOGLE_LOGIN_SETUP_PT_BR.md). O fluxo por e-mail/senha foi preservado. Usuários finais não fornecem chaves; ligas continuam ligadas ao UID verificado, com interface de zero a seis cadastros reais.

## Testes locais

- Backend: **35 testes**. Incluem os testes anteriores de isolamento, limite de seis, concorrência de cadastros/sincronização e preservação de dados válidos.
- Google: cookie HttpOnly na web, credenciais apenas na resposta nativa, origem/CSRF, desafio com finalidade e transporte, expiração, consumo único, vínculo ao UID autenticado e rejeição de UID fornecido pelo cliente.
- Criptografia: o verificador Google real foi exercitado com uma chave efêmera e certificado TEST_ONLY, sem tráfego a Google. Tokens com assinatura alterada, audiência/emissor incorretos, prazo expirado e nonce divergente foram rejeitados.
- Configuração Cloud: consultas simuladas verificam leitura do client ID público, rejeição de provedor desativado/origem inválida, preservação dos domínios existentes e ausência de exposição do access token/client secret.
- JavaScript: quatro suítes cobrem lógica original, semanas dinâmicas, conta/ligas e Google. O novo fluxo cobre Google sem senha, vínculo, conflitos de conta, cancelamento nativo, ausência de OAuth JavaScript na WebView, callback atrasado e saída durante uma troca de cookie.
- Fonte: **15 Python, 13 Java e 7 XML** passam na análise sintática; os HTMLs Android/web e o fragmento de autenticação são idênticos. O shell passa em bash -n.
- Dependência Android: metadados oficiais do AAR credentials:1.3.0 confirmam minCompileSdk=34. As assinaturas utilizadas em Credential Manager/GetSignInWithGoogleOption foram conferidas na documentação oficial.

Todos os usuários, tokens e ligas das suítes são fixtures identificadas TEST_ONLY. Nenhum cadastro ou estatística de teste é colocado no payload do aplicativo.

## Pendente

Não foi executado login Google real, configuração administrativa Google/Firebase, deploy RC3, compilação Gradle/APK, execução PowerShell em Windows ou teste no aparelho. A análise sintática Java não substitui uma compilação Android. Não houve renderização visual nesta revisão; os testes DOM verificam comportamento.

O usuário publicou RC2 em 10/10/2026. Seus logs confirmam API, worker privado e Scheduler ativado. GETs públicos /health e /app responderam HTTP 200 com versão RC2 e authConfigured=true. Isso confirma implantação/configuração presente, sem validar login real, Firestore, provedores ou esta RC3.

Antes de promover, valide Google web/Android com a mesma conta, duas contas independentes, manutenção das ligas após vínculo, inclusão/remoção de até seis ligas e dados reais de ESPN/Sleeper. v7.3.2 segue a referência de análise até essa validação.

## Reprodução

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r backend/requirements-dev.txt
(cd backend && python -m pytest tests -q)
npm ci
npm test
python tools/check_sources.py
bash -n tools/deploy_v8.sh
```
