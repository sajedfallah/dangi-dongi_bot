param(
    [string]$ProjectDir = "C:\dangi-dongi"
)

$ErrorActionPreference = "Stop"

function Assert-Admin {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw "Run PowerShell as Administrator."
    }
}

function Remove-ServiceIfExists {
    param(
        [string]$ServiceName,
        [string]$NssmExe
    )

    $existing = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
    if (-not $existing) {
        return
    }

    if ($existing.Status -ne 'Stopped') {
        try {
            Stop-Service -Name $ServiceName -Force -ErrorAction Stop
            $existing.WaitForStatus('Stopped', [TimeSpan]::FromSeconds(20))
        }
        catch {
            Write-Warning "Could not stop $ServiceName cleanly: $($_.Exception.Message)"
        }
    }

    & $NssmExe remove $ServiceName confirm | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to remove existing service $ServiceName."
    }

    for ($i = 0; $i -lt 20; $i++) {
        if (-not (Get-Service -Name $ServiceName -ErrorAction SilentlyContinue)) {
            break
        }
        Start-Sleep -Milliseconds 500
    }
}

Assert-Admin

$python = Join-Path $ProjectDir ".venv\Scripts\python.exe"
$envFile = Join-Path $ProjectDir ".env"
$logsDir = Join-Path $ProjectDir "logs"
$nssmDir = Join-Path $ProjectDir "tools\nssm"
$nssmExe = Join-Path $nssmDir "nssm.exe"

if (-not (Test-Path $python)) {
    throw "Virtual environment Python not found at $python"
}
if (-not (Test-Path $envFile)) {
    throw ".env not found at $envFile"
}

New-Item -ItemType Directory -Force -Path $logsDir | Out-Null
New-Item -ItemType Directory -Force -Path $nssmDir | Out-Null

if (-not (Test-Path $nssmExe)) {
    $zip = Join-Path $env:TEMP "nssm-2.24.zip"
    $extract = Join-Path $env:TEMP "nssm-2.24"
    Invoke-WebRequest -Uri "https://nssm.cc/release/nssm-2.24.zip" -OutFile $zip
    if (Test-Path $extract) { Remove-Item -Recurse -Force $extract }
    Expand-Archive -Path $zip -DestinationPath $extract -Force
    $source = Join-Path $extract "nssm-2.24\win64\nssm.exe"
    if (-not (Test-Path $source)) {
        throw "NSSM executable was not found after extraction."
    }
    Copy-Item $source $nssmExe -Force
}

$apiService = "DangiDongi-API"
$botService = "DangiDongi-Bot"

Remove-ServiceIfExists -ServiceName $botService -NssmExe $nssmExe
Remove-ServiceIfExists -ServiceName $apiService -NssmExe $nssmExe

& $nssmExe install $apiService $python "-m uvicorn app.main:app --host 127.0.0.1 --port 8000"
if ($LASTEXITCODE -ne 0) { throw "Failed to install $apiService." }
& $nssmExe set $apiService AppDirectory $ProjectDir
& $nssmExe set $apiService Start SERVICE_AUTO_START
& $nssmExe set $apiService AppExit Default Restart
& $nssmExe set $apiService AppRestartDelay 5000
& $nssmExe set $apiService AppStdout (Join-Path $logsDir "api.out.log")
& $nssmExe set $apiService AppStderr (Join-Path $logsDir "api.err.log")
& $nssmExe set $apiService AppRotateFiles 1
& $nssmExe set $apiService AppRotateOnline 1
& $nssmExe set $apiService AppRotateBytes 10485760

& $nssmExe install $botService $python "run_bot.py"
if ($LASTEXITCODE -ne 0) { throw "Failed to install $botService." }
& $nssmExe set $botService AppDirectory $ProjectDir
& $nssmExe set $botService Start SERVICE_AUTO_START
& $nssmExe set $botService AppExit Default Restart
& $nssmExe set $botService AppRestartDelay 5000
& $nssmExe set $botService DependOnService $apiService
& $nssmExe set $botService AppStdout (Join-Path $logsDir "bot.out.log")
& $nssmExe set $botService AppStderr (Join-Path $logsDir "bot.err.log")
& $nssmExe set $botService AppRotateFiles 1
& $nssmExe set $botService AppRotateOnline 1
& $nssmExe set $botService AppRotateBytes 10485760

Start-Service $apiService
Start-Sleep -Seconds 3
Start-Service $botService

Write-Host ""
Write-Host "Dangi-Dongi services installed and started."
Get-Service $apiService, $botService | Format-Table Status, Name, DisplayName -AutoSize
Write-Host ""
Write-Host "Logs: $logsDir"
