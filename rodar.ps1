# ==========================================================
#  LEVERAGE ARB - rodar 24/7 neste PC
#  - reinicia sozinho se o servidor cair
#  - grava tudo em servidor.log (com troca de arquivo)
#  - so uma instancia por vez (trava por mutex)
#  - para com PARAR.bat ou fechando a janela
# ==========================================================
$ErrorActionPreference = 'Continue'
$raiz = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $raiz

$log    = Join-Path $raiz 'servidor.log'
$limite = 5MB

# ------------------------------------------------------------
# TRAVA DE INSTANCIA UNICA
# Sem isso, abrir o .bat duas vezes cria duas rotinas de
# reinicio que brigam pela porta 8800 e derrubam o servidor.
# ------------------------------------------------------------
$mutex = New-Object System.Threading.Mutex($false, 'Global\LEVERAGE_ARB_UNICO_8800')
$liberado = $false
try {
    $liberado = $mutex.WaitOne(0, $false)
} catch [System.Threading.AbandonedMutexException] {
    $liberado = $true
}
if (-not $liberado) {
    Write-Host ""
    Write-Host "  [LEVERAGE ARB] JA ESTA RODANDO em outra janela."
    Write-Host "  Nao abra de novo. Para ver os logs, veja a outra janela."
    Write-Host ""
    Start-Sleep -Seconds 4
    exit
}

# nao deixa o log crescer pra sempre
if ((Test-Path $log) -and (Get-Item $log).Length -gt $limite) {
    Move-Item $log "$log.1" -Force
}

function Escrever([string]$texto) {
    $linha = "[$(Get-Date -Format 'dd/MM HH:mm:ss')] $texto"
    Write-Host $linha
    Add-Content -Path $log -Value $linha -Encoding utf8
}

Escrever "============================================"
Escrever " LEVERAGE ARB iniciando"
Escrever " Dashboard: http://localhost:8800"
Escrever " Para parar: feche esta janela ou rode PARAR.bat"
Escrever "============================================"

$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'

try {
    while ($true) {
        Escrever "iniciando servidor..."
        try {
            # via cmd /c para o PowerShell nao transformar a saida do uvicorn
            # (que vai para stderr) em "erro" e poluir o log.
            # o filtro remove o laco de "GET /api/..." que nao ajuda em nada.
            & cmd /c "py -m uvicorn server:app --host 0.0.0.0 --port 8800 --timeout-keep-alive 30 2>&1" |
                Where-Object { $_ -notmatch '"\s*(GET|POST|PUT|DELETE)\s+/' } |
                Tee-Object -FilePath $log -Append
        } catch {
            Escrever "erro ao iniciar: $($_.Exception.Message)"
        }
        Escrever "servidor parou - reiniciando em 10 segundos..."
        Start-Sleep -Seconds 10
    }
} finally {
    # so libera a trava se este processo for o dono dela
    if ($liberado) { $mutex.ReleaseMutex() | Out-Null }
}
