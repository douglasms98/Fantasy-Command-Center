# FCC v7.3.4 RC1

Candidato de correção sobre v7.3.2. Não usa nem incorpora v7.3.3 ALLIGATORS_PPR_PREP.

## Alterações
- Otimizador reabre entre jogos; bloqueia jogadores após kickoff e pausa por liga quando jogadores do roster estão ao vivo. Horários desconhecidos impedem sugestões para esses jogadores.
- Listas vazias ou inválidas não apagam os alertas válidos. Calendário NFL confirmado gera lembretes 30 min antes dos horários de kickoff; configurações confirmadas de waivers geram lembretes 1 h antes e no horário previsto do processamento.
- Diagnóstico mostra eventos recebidos, rejeitados e motivo da ausência de agendamentos.
- WorkManager atualiza API principal, backup configurado e calendário NFL a cada 4 h, sujeito à conectividade e às restrições do Android. Cache é reaplicado ao retornar ao app. Não garante execução quando o usuário força a parada do aplicativo.
- Planner mostra os jogos internacionais identificados pelo país do estádio, inclusive sem titulares do roster nesses jogos; remove o limite de 12 times da visão consolidada.
- Tradução de títulos inglês → português no aparelho via ML Kit, preservando nomes identificados e IR/NFL/ESPN/PPR/BYE/DNP. Primeiro download do modelo usa Wi-Fi. Se indisponível, conserva o título original e tenta novamente depois; não fabrica uma tradução.
- Diagnóstico do roster em 2 colunas no celular e botão Comparar ligas com contraste explícito.

## Instalar no projeto existente
1. Extraia este ZIP em uma pasta separada.
2. No PowerShell, execute: .\apply_v7_3_4_RC1.ps1 -ProjectRoot "C:\caminho\do\FantasyCommandCenter"
3. O script faz backup dos arquivos substituídos, atualiza versionName e adiciona com.google.mlkit:translate:17.0.3 ao módulo app.
4. Android Studio: Sync Project with Gradle Files, depois assembleDebug ou Build APK(s).
5. Instale por cima do aplicativo existente. Abra, conecte ao Wi-Fi, sincronize e verifique agendamentos futuros. Permita horário exato se necessário.

O pacote é um patch para o projeto Android existente, não um projeto Gradle autônomo.

## Validação
Passaram testes automatizados de sintaxe JavaScript, bloqueio de jogadores com jogo iniciado, reabertura entre jogos, pausa ao vivo, proteção para horários desconhecidos, geração/deduplicação de eventos, preservação de programação em lista vazia e planner internacional.
Regras CSS foram verificadas no código. Não foi possível renderizar a interface em Chromium neste ambiente, nem compilar Android ou executar WorkManager, AlarmManager e ML Kit em dispositivo. Ainda faltam build e validação com dados reais e no celular. v7.3.2 permanece a referência até essa validação.

As fixtures dos testes são isoladas, identificadas como TEST_ONLY e não são incorporadas aos dados do app.

Referências técnicas:
- https://developer.android.com/develop/background-work/services/alarms
- https://developer.android.com/develop/background-work/background-tasks/persistent/getting-started/define-work
- https://developers.google.com/ml-kit/language/translation/android
