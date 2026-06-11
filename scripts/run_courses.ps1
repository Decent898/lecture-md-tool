# Batch-process recurring course recordings (e.g. AutoSlides screen captures).
# Generic example: pass your own input folder, filename glob, and course-name filters.
#
# Examples:
#   .\scripts\run_courses.ps1 -InputDir "E:\AutoSlides" -DryRun
#   .\scripts\run_courses.ps1 -InputDir "E:\AutoSlides" -Courses "计算机组成","软件工程"
#   .\scripts\run_courses.ps1 -InputDir "D:\Recordings" -FileGlob "*.mp4" -Asr local -Optimize none -Notes none
param(
    [Parameter(Mandatory = $true)]
    [string]$InputDir,
    [string]$OutputRoot = "$env:USERPROFILE\Documents\lecture_md_runs\courses",
    [string]$FileGlob = "screen_*.mp4",
    [string[]]$Courses = @(),
    [ValidateSet("api", "local")]
    [string]$Asr = "local",
    [ValidateSet("api", "none")]
    [string]$Optimize = "api",
    [ValidateSet("api", "none")]
    [string]$Notes = "api",
    [string]$LocalAsrModel = "small",
    [string]$LocalAsrDevice = "cpu",
    [string]$LocalAsrComputeType = "int8",
    [string]$SceneThreshold = "0.01",
    [string]$MinSceneLen = "20",
    [double]$DedupeStableSeconds = 6.0,
    [switch]$DryRun,
    [switch]$NoSkipExisting,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ExtraArgs
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $InputDir)) {
    throw "Input directory not found: $InputDir"
}

if (($Asr -eq "api" -or $Optimize -eq "api" -or $Notes -eq "api") -and
    -not ($env:LECTURE_MD_API_KEY -or $env:OPENAI_API_KEY -or $env:MIMO_API_KEY)) {
    throw "Set LECTURE_MD_API_KEY (or OPENAI_API_KEY) first, or run with -Asr local -Optimize none -Notes none."
}

$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

$BatchArgs = @(
    "-m", "lecture_md", "process",
    "--input-dir", $InputDir,
    "--file-glob", $FileGlob,
    "--output-root", $OutputRoot,
    "--scene-threshold", $SceneThreshold,
    "--min-scene-len", $MinSceneLen,
    "--dedupe-mode", "debounce",
    "--dedupe-stable-seconds", "$DedupeStableSeconds",
    "--asr", $Asr,
    "--optimize", $Optimize,
    "--notes", $Notes,
    "--local-asr-model", $LocalAsrModel,
    "--local-asr-device", $LocalAsrDevice,
    "--local-asr-compute-type", $LocalAsrComputeType
)

foreach ($Course in $Courses) {
    $BatchArgs += @("--include-name", $Course)
}

if ($DryRun) {
    $BatchArgs += "--dry-run"
}

if (-not $NoSkipExisting) {
    $BatchArgs += "--skip-existing"
}

$BatchArgs += $ExtraArgs

python @BatchArgs
