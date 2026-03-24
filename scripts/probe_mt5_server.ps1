param(
    [int]$Interval = 5,
    [string]$Output = "C:\\temp\\mt5_probe_server.log"
)

$dir = Split-Path -Parent $Output
if (-not (Test-Path $dir)) {
    New-Item -ItemType Directory -Path $dir | Out-Null
}

while ($true) {
    $t = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    try {
        $r = Invoke-WebRequest -Uri "https://127.0.0.1:2000/api/auth/start?version=3470&agent=AstralWGateway&login=1015&type=manager" -UseBasicParsing -TimeoutSec 8
        "$t OK $($r.StatusCode)" | Out-File -FilePath $Output -Append -Encoding utf8
    } catch {
        "$t FAIL $($_.Exception.Message)" | Out-File -FilePath $Output -Append -Encoding utf8
    }
    Start-Sleep -Seconds $Interval
}
