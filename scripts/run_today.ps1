# Process all videos modified today in a folder. Usage:
#   .\scripts\run_today.ps1 -InputDir "$env:USERPROFILE\Downloads" -OutputRoot ".\out" [extra args]
param(
    [string]$InputDir = "$env:USERPROFILE\Downloads",
    [string]$OutputRoot = ".\lecture_md_out",
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ExtraArgs
)

$ErrorActionPreference = "Stop"

python -m lecture_md process --input-dir $InputDir --today --output-root $OutputRoot --skip-existing @ExtraArgs
