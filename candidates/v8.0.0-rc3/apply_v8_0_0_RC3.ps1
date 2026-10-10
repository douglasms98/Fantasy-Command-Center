param(
    [string]$ProjectRoot = (Join-Path $HOME "AndroidStudioProjects\FantasyCommandCenter"),
    [Parameter(Mandatory=$true)][string]$ApiBase
)

$ErrorActionPreference = "Stop"
$PatchRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ApiUri = $null
if (![Uri]::TryCreate($ApiBase, [UriKind]::Absolute, [ref]$ApiUri) -or $ApiUri.Scheme -ne "https" -or $ApiUri.AbsolutePath -ne "/" -or $ApiUri.Query -or $ApiUri.Fragment -or $ApiUri.UserInfo) {
    throw "ApiBase precisa ser a origem HTTPS do backend v8 publicado, sem caminho, usuário, query ou fragmento."
}
$ApiBase = $ApiBase.TrimEnd('/')
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
if (!(Test-Path $ProjectRoot)) { throw "Projeto Android não encontrado: $ProjectRoot. Use -ProjectRoot para informar o caminho correto." }
$ProjectRoot = (Resolve-Path $ProjectRoot).Path
$Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$BackupRoot = Join-Path $ProjectRoot ("fcc_backup_v800rc3_" + $Timestamp)
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
Write-Host "Fantasy Command Center v8.0.0 RC3 — LOGIN GOOGLE, CONTAS E LIGAS NO CLOUD" -ForegroundColor Cyan
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

# Configure once at build time; end users never enter this address or a key.
$AccountPath = Join-Path $ProjectRoot "app\src\main\java\com\douglas\fantasycommandcenter\AccountRepository.java"
$AccountText = [IO.File]::ReadAllText($AccountPath)
$BasePattern = [regex]::new('public static final String BASE="[^"]+";')
if (!$BasePattern.IsMatch($AccountText)) { throw "BASE do cliente de conta não encontrada." }
$AccountText = $BasePattern.Replace($AccountText, ('public static final String BASE="' + $ApiBase + '";'), 1)
[IO.File]::WriteAllText($AccountPath, $AccountText, $Utf8NoBom)

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
    $already = $txt -match 'versionName\s*(?:=\s*)?["'']8\.0\.0-rc3["'']'
    if ($Kts) {
        if ($txt -match 'versionName\s*=\s*"[^"]*"') {
            $txt = ([regex]::new('versionName\s*=\s*"[^"]*"')).Replace($txt, 'versionName = "8.0.0-rc3"', 1)
        } else { Write-Warning "versionName não encontrado em $Path" }
        if (!$already -and $txt -match 'versionCode\s*=\s*(\d+)') {
            $n = [int]$Matches[1] + 1
            $txt = ([regex]::new('versionCode\s*=\s*\d+')).Replace($txt, "versionCode = $n", 1)
        }
    } else {
        if ($txt -match 'versionName\s+["''][^"'']*["'']') {
            $txt = ([regex]::new('versionName\s+["''][^"'']*["'']')).Replace($txt, 'versionName "8.0.0-rc3"', 1)
        } else { Write-Warning "versionName não encontrado em $Path" }
        if (!$already -and $txt -match 'versionCode\s+(\d+)') {
            $n = [int]$Matches[1] + 1
            $txt = ([regex]::new('versionCode\s+\d+')).Replace($txt, "versionCode $n", 1)
        }
    }
    [IO.File]::WriteAllText($Path, $txt, $Utf8NoBom)
    Write-Host "VER  app version -> 8.0.0-rc3" -ForegroundColor Cyan
    return $true
}

$done = Update-GradleVersion (Join-Path $ProjectRoot "app\build.gradle.kts") $true
if (!$done) { $done = Update-GradleVersion (Join-Path $ProjectRoot "app\build.gradle") $false }
if (!$done) { Write-Warning "build.gradle(.kts) não encontrado; ajuste versionName para 8.0.0-rc3 manualmente." }

# Dependencies needed by this complete source patch.
$GradlePath = Join-Path $ProjectRoot "app\build.gradle.kts"
$IsKts = Test-Path $GradlePath
if (!$IsKts) { $GradlePath = Join-Path $ProjectRoot "app\build.gradle" }
if (!(Test-Path $GradlePath)) { throw "Não encontrei o Gradle do módulo app." }
$GradleText = [IO.File]::ReadAllText($GradlePath)
foreach ($Coordinate in @("androidx.webkit:webkit:1.12.1", "androidx.work:work-runtime:2.9.1", "com.google.mlkit:translate:17.0.3", "androidx.credentials:credentials:1.3.0", "androidx.credentials:credentials-play-services-auth:1.3.0", "com.google.android.libraries.identity.googleid:googleid:1.1.1")) {
    $Family = $Coordinate.Substring(0, $Coordinate.LastIndexOf(':')) + ':'
    if ($GradleText.Contains($Family)) {
        if ($Coordinate.StartsWith("androidx.credentials:") -or $Coordinate.StartsWith("com.google.android.libraries.identity.googleid:")) {
            $ExistingPattern = [regex]::new([regex]::Escape($Family) + '(\d+\.\d+\.\d+)(?![\d.])')
            $Existing = $ExistingPattern.Match($GradleText)
            $Minimum = [version]($Coordinate.Substring($Coordinate.LastIndexOf(':') + 1))
            if ($Existing.Success -and [version]($Existing.Groups[1].Value) -lt $Minimum) {
                $GradleText = $ExistingPattern.Replace($GradleText, $Coordinate)
            }
        }
        continue
    }
    $Dependency = if ($IsKts) { 'implementation("' + $Coordinate + '")' } else { "implementation '" + $Coordinate + "'" }
    $DependenciesPattern = [regex]::new('dependencies\s*\{')
    if (!$DependenciesPattern.IsMatch($GradleText)) { throw "Bloco dependencies não encontrado." }
    $GradleText = $DependenciesPattern.Replace($GradleText, "dependencies {`n    $Dependency", 1)
}
[IO.File]::WriteAllText($GradlePath, $GradleText, $Utf8NoBom)

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
Write-Host "5) Use Entrar com Google ou e-mail/senha. Abra Minha conta e ligas para cadastrar suas ligas."
Write-Host "Google no Android: cadastre o pacote e a SHA-1 da assinatura no mesmo projeto Firebase."
Write-Host "Para consultar a SHA-1, execute .\gradlew.bat signingReport na raiz do projeto."
Write-Host "Credential Manager requer compileSdk 34 ou superior; este pacote nao troca sua assinatura."
Write-Host ""
Write-Host "RC3: testar Entrar com Google, Firebase/Firestore reais, ESPN/Sleeper e Android. Backend v8 deve estar publicado antes da instalação." -ForegroundColor Cyan
