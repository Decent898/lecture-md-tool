param(
    [string]$InputDir = "E:\AutoSlides",
    [string]$OutputRoot = "$env:USERPROFILE\Documents\lecture_md_runs\autoslides_courses",
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

if (($Asr -eq "api" -or $Optimize -eq "api" -or $Notes -eq "api") -and -not $env:MIMO_API_KEY) {
    throw "Set MIMO_API_KEY first, or run with -Asr local -Optimize none -Notes none."
}

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$BatchScript = Join-Path $ScriptDir "lecture_md_batch.py"
$PreferredPython = Join-Path (Split-Path -Parent $ScriptDir) ".venv-slidegeist\Scripts\python.exe"
$PythonExe = "python"
if (Test-Path -LiteralPath $PreferredPython) {
    $PythonExe = $PreferredPython
}

$FfmpegCandidates = @(
    "C:\Users\12776\anaconda3\envs\cosyvoice\Library\bin",
    "$env:USERPROFILE\anaconda3\envs\cosyvoice\Library\bin",
    "$env:USERPROFILE\scoop\shims",
    "$env:LOCALAPPDATA\Microsoft\WinGet\Packages"
)

foreach ($Candidate in $FfmpegCandidates) {
    if ($Candidate -and (Test-Path -LiteralPath (Join-Path $Candidate "ffmpeg.exe"))) {
        $env:PATH = "$Candidate;$env:PATH"
        break
    }
}

$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

if ($Courses.Count -eq 0) {
    $Utf8 = [System.Text.Encoding]::UTF8
    $Courses = @(
        $Utf8.GetString([System.Convert]::FromBase64String("6K6h566X5py657uE5oiQ5LiO5L2T57O757uT5p6E")),
        $Utf8.GetString([System.Convert]::FromBase64String("6L2v5Lu25bel56iL5Z+656GA"))
    )
}

$BatchArgs = @(
    $BatchScript,
    "--input-dir", $InputDir,
    "--file-glob", "screen_*.mp4",
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

& $PythonExe @BatchArgs
