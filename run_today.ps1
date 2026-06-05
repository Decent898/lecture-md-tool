param(
    [string]$InputDir = "$env:USERPROFILE\Downloads",
    [string]$OutputRoot = ".\batch_mimo_today"
)

$ErrorActionPreference = "Stop"

if (-not $env:MIMO_API_KEY) {
    throw "MIMO_API_KEY is not set"
}

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
python (Join-Path $ScriptDir "lecture_md_batch.py") --input-dir $InputDir --today --output-root $OutputRoot --skip-existing

