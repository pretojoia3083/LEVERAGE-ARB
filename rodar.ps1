# ==========================================================
#  LEVERAGE ARB - rodar 24/7 neste PC
#  - reinicia sozinho se o servidor cair
#  - grava tudo em servidor.log (com troca de arquivo)
#  - para com PARAR.bat ou fechando a janela
# ==========================================================
$ErrorActionPreference = 'Continue'
$raiz = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $raiz

$log    = Join-Path $raiz 'servidor.log'
$limite = 5MB

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
