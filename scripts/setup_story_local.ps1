param([switch]$ModelsOnly)
$ErrorActionPreference = 'Stop'
$workspace = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))

function Invoke-Checked {
    param([string]$Command, [string[]]$Arguments)
    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) { throw "$Command gagal (exit $LASTEXITCODE)." }
}

Push-Location $workspace
try {
    Invoke-Checked 'python' @('scripts/setup_story_image_models.py')
    Invoke-Checked 'python' @('scripts/download_story_speech.py')
    if ($ModelsOnly) { return }
    $envPath = Join-Path $workspace '.env'
    if (-not (Test-Path -LiteralPath $envPath -PathType Leaf)) {
        throw 'Buat .env dengan scripts/init_env.py terlebih dahulu.'
    }
    Invoke-Checked 'docker' @('compose', '-f', 'compose.yml', '-f', 'compose.gpu.yml', 'build', 'api', 'worker-heavy', 'web')
    $envText = [System.IO.File]::ReadAllText($envPath)
    foreach ($setting in @('STORY_MEDIA_PROVIDER=local', 'STORY_LOCAL_ENABLED=true')) {
        $settingName = $setting.Split('=')[0]
        $pattern = '(?m)^' + [regex]::Escape($settingName) + '=.*$'
        if ([regex]::IsMatch($envText, $pattern)) { $envText = [regex]::Replace($envText, $pattern, $setting) }
        else { $envText = $envText.TrimEnd() + "`n" + $setting + "`n" }
    }
    [System.IO.File]::WriteAllText($envPath, $envText, [System.Text.UTF8Encoding]::new($false))
    Invoke-Checked 'docker' @('compose', '-f', 'compose.yml', '-f', 'compose.gpu.yml', 'up', '-d', '--no-deps', '--wait', '--wait-timeout', '120', 'api', 'worker-heavy', 'worker-light', 'dispatcher', 'scheduler', 'publisher', 'web')
    Write-Output 'Story Studio lokal aktif. Buka Studio > Produksi. Model tidak mengunduh data saat generasi.'
}
finally { Pop-Location }
