param(
    [int]$Interval = 5,
    [int]$Rounds = 720
)

Set-Location -Path (Split-Path -Parent $PSScriptRoot)
python scripts\mt5_tls_probe.py --interval $Interval --rounds $Rounds
