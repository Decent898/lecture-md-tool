# Process one lecture video. Usage:
#   .\scripts\run_one.ps1 -Video "C:\path\to\video.mp4" -OutputRoot ".\out" [extra args]
param(
    [Parameter(Mandatory = $true)]
    [string]$Video,
    [Parameter(Mandatory = $true)]
    [string]$OutputRoot,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ExtraArgs
)

$ErrorActionPreference = "Stop"

python -m lecture_md process --video $Video --output-root $OutputRoot @ExtraArgs
