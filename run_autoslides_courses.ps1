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
$PreferredSlidegeist = Join-Path (Split-Path -Parent $ScriptDir) ".venv-slidegeist\Scripts\slidegeist.exe"
$PythonExe = "python"
$SlidegeistExe = "slidegeist"
if (Test-Path -LiteralPath $PreferredPython) {
    $PythonExe = $PreferredPython
}
if (Test-Path -LiteralPath $PreferredSlidegeist) {
    $SlidegeistExe = $PreferredSlidegeist
}

if ($Courses.Count -eq 0) {
    $Utf8 = [System.Text.Encoding]::UTF8
    $Courses = @(
        $Utf8.GetString([System.Convert]::FromBase64String("6K6h566X5py657uE5oiQ5LiO5L2T57O757uT5p6E")),
        $Utf8.GetString([System.Convert]::FromBase64String("6L2v5Lu25bel56iL5Z+656GA"))
    )
}

$IncludeArgs = foreach ($Course in $Courses) {
    @("--include-name", $Course)
}

$DryRunArgs = @()
if ($DryRun) {
    $DryRunArgs = @("--dry-run")
}

$SkipArgs = @()
if (-not $NoSkipExisting) {
    $SkipArgs = @("--skip-existing")
}

& $PythonExe $BatchScript `
    --input-dir $InputDir `
    --file-glob "screen_*.mp4" `
    --output-root $OutputRoot `
    --slidegeist-bin $SlidegeistExe `
    --dedupe-mode debounce `
    --dedupe-stable-seconds $DedupeStableSeconds `
    --asr $Asr `
    --optimize $Optimize `
    --notes $Notes `
    --local-asr-model $LocalAsrModel `
    --local-asr-device $LocalAsrDevice `
    --local-asr-compute-type $LocalAsrComputeType `
    @IncludeArgs `
    @DryRunArgs `
    @SkipArgs `
    @ExtraArgs
