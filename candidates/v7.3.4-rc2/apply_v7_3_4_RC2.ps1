param(
    [string]$ProjectRoot = (Join-Path $HOME "AndroidStudioProjects\FantasyCommandCenter")
)

$ErrorActionPreference = "Stop"
$PatchRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
if (!(Test-Path $ProjectRoot)) { throw "Projeto Android não encontrado: $ProjectRoot. Use -ProjectRoot para informar o caminho correto." }
$ProjectRoot = (Resolve-Path $ProjectRoot).Path
$Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$BackupRoot = Join-Path $ProjectRoot ("fcc_backup_v734_" + $Timestamp)
New-Item -ItemType Directory -Path $BackupRoot -Force | Out-Null

function Backup-File([string]$Destination) {
    if (!(Test-Path $Destination)) { return }
    $relative = ($Destination.Substring($ProjectRoot.Length) -replace '^[\\/]+','')
    $backup = Join-Path $BackupRoot $relative
    $parent = Split-Path -Parent $backup
    if (!(Test-Path $parent)) { New-Item -ItemType Directory -Path $parent -Force | Out-Null }
    Copy-Item $Destination $backup -Force
}

function Copy-PatchFile([string]$Source, [string]$Destination) {
    Backup-File $Destination
    $parent = Split-Path -Parent $Destination
    if (!(Test-Path $parent)) { New-Item -ItemType Directory -Path $parent -Force | Out-Null }
    Copy-Item $Source $Destination -Force
    $relative = ($Destination.Substring($ProjectRoot.Length) -replace '^[\\/]+','')
    Write-Host "OK   $relative" -ForegroundColor Green
}

Write-Host ""
Write-Host "Fantasy Command Center v7.3.4 RC2 — UI + BYE + NOTIFICAÇÕES + HISTÓRICO" -ForegroundColor Cyan
Write-Host "Projeto: $ProjectRoot"
Write-Host "Backup:  $BackupRoot"
Write-Host ""

$PatchMain = Join-Path $PatchRoot "app\src\main"
if (!(Test-Path $PatchMain)) { throw "Pacote incompleto: não encontrei $PatchMain" }
Get-ChildItem $PatchMain -Recurse -File | ForEach-Object {
    $relative = ($_.FullName.Substring($PatchRoot.Length) -replace '^[\\/]+','')
    $dst = Join-Path $ProjectRoot $relative
    Copy-PatchFile $_.FullName $dst
}

# Remove implementação Kotlin antiga se ainda existir e puder conflitar com Java.
$oldKt = Join-Path $ProjectRoot "app\src\main\java\com\douglas\fantasycommandcenter\FantasyNotificationScheduler.kt"
if (Test-Path $oldKt) {
    Backup-File $oldKt
    Remove-Item $oldKt -Force
    Write-Host "REM  app\src\main\java\com\douglas\fantasycommandcenter\FantasyNotificationScheduler.kt" -ForegroundColor Yellow
}

# Evita recursos duplicados PNG/WEBP em instalações vindas de patches antigos.
$resRoot = Join-Path $ProjectRoot "app\src\main\res"
if (Test-Path $resRoot) {
    Get-ChildItem $resRoot -Directory -Filter "mipmap-*" | ForEach-Object {
        foreach ($name in @("ic_launcher", "ic_launcher_round", "fcc_launcher_v724", "fcc_launcher_round_v724")) {
            $png = Join-Path $_.FullName ($name + ".png")
            $webp = Join-Path $_.FullName ($name + ".webp")
            if ((Test-Path $png) -and (Test-Path $webp)) {
                Backup-File $webp
                Remove-Item $webp -Force
                Write-Host "REM  $webp" -ForegroundColor Yellow
            }
        }
    }
}

function Update-GradleVersion([string]$Path, [bool]$Kts) {
    if (!(Test-Path $Path)) { return $false }
    Backup-File $Path
    $txt = Get-Content $Path -Raw
    $already = $txt -match 'versionName\s*(?:=\s*)?["'']7\.3\.4-rc2["'']'
    if ($Kts) {
        if ($txt -match 'versionName\s*=\s*"[^"]*"') {
            $txt = [regex]::Replace($txt, 'versionName\s*=\s*"[^"]*"', 'versionName = "7.3.4-rc2"', 1)
        } else { Write-Warning "versionName não encontrado em $Path" }
        if (!$already -and $txt -match 'versionCode\s*=\s*(\d+)') {
            $n = [int]$Matches[1] + 1
            $txt = [regex]::Replace($txt, 'versionCode\s*=\s*\d+', "versionCode = $n", 1)
        }
    } else {
        if ($txt -match 'versionName\s+["''][^"'']*["'']') {
            $txt = [regex]::Replace($txt, 'versionName\s+["''][^"'']*["'']', 'versionName "7.3.4-rc2"', 1)
        } else { Write-Warning "versionName não encontrado em $Path" }
        if (!$already -and $txt -match 'versionCode\s+(\d+)') {
            $n = [int]$Matches[1] + 1
            $txt = [regex]::Replace($txt, 'versionCode\s+\d+', "versionCode $n", 1)
        }
    }
    Set-Content -Path $Path -Value $txt -Encoding UTF8
    Write-Host "VER  app version -> 7.3.4-rc2" -ForegroundColor Cyan
    return $true
}

$done = Update-GradleVersion (Join-Path $ProjectRoot "app\build.gradle.kts") $true
if (!$done) { $done = Update-GradleVersion (Join-Path $ProjectRoot "app\build.gradle") $false }
if (!$done) { Write-Warning "build.gradle(.kts) não encontrado; ajuste versionName para 7.3.4-rc2 manualmente." }

# Translation runs on device with the official ML Kit model.
$GradlePath = Join-Path $ProjectRoot "app\build.gradle.kts"
$IsKts = Test-Path $GradlePath
if (!$IsKts) { $GradlePath = Join-Path $ProjectRoot "app\build.gradle" }
if (!(Test-Path $GradlePath)) { throw "Não encontrei o Gradle do módulo app." }
$GradleText = Get-Content $GradlePath -Raw
if ($GradleText -notmatch 'com\.google\.mlkit:translate:') {
    Backup-File $GradlePath
    $Dependency = if ($IsKts) { 'implementation("com.google.mlkit:translate:17.0.3")' } else { "implementation 'com.google.mlkit:translate:17.0.3'" }
    if ($GradleText -notmatch 'dependencies\s*\{') { throw "Bloco dependencies não encontrado em $GradlePath" }
    $GradleText = [regex]::Replace($GradleText, 'dependencies\s*\{', "dependencies {`n    $Dependency", 1)
    Set-Content $GradlePath -Value $GradleText -Encoding UTF8
}

$appBuild = Join-Path $ProjectRoot "app\build"
if (Test-Path $appBuild) {
    Remove-Item $appBuild -Recurse -Force
    Write-Host "CLEAN app\build" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "APLICAÇÃO CONCLUÍDA." -ForegroundColor Green
Write-Host "1) Android Studio: Sync Project with Gradle Files"
Write-Host "2) Build > Clean Project"
Write-Host "3) Build > Assemble Project (ou Generate APKs)"
Write-Host "4) Instale o APK/AAB por cima do app atual"
Write-Host "5) No app, abra Sincronização e confirme 'horário exato' para os alertas; se aparecer o botão, conceda a permissão."
Write-Host ""
Write-Host "RC2: testar agendamentos, atualização em segundo plano e tradução no Wi-Fi. Sem deploy Cloud Run." -ForegroundColor Cyan
