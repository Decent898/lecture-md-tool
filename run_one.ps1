param(
    [Parameter(Mandatory = $true)]
    [string]$Video,
    [Parameter(Mandatory = $true)]
    [string]$OutputRoot
)

$ErrorActionPreference = "Stop"

if (-not $env:MIMO_API_KEY) {
    throw "MIMO_API_KEY is not set"
}

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
python (Join-Path $ScriptDir "lecture_md_batch.py") --video $Video --output-root $OutputRoot

