param(
    [string]$InputDir = "$env:USERPROFILE\Downloads",
    [string]$OutputRoot = ".\batch_mimo_today",
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ExtraArgs
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
python (Join-Path $ScriptDir "lecture_md_batch.py") --input-dir $InputDir --today --output-root $OutputRoot --skip-existing @ExtraArgs
