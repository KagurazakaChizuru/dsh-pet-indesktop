param(
    [string]$ToolsRoot = "$env:LOCALAPPDATA/dsh-pet-android",
    [string]$Python = '',
    [string[]]$Tasks = @('testDebugUnitTest', 'lintDebug', 'assembleDebug')
)
$ErrorActionPreference = 'Stop'
$repository = Split-Path $PSScriptRoot -Parent
if (!$Python) {
    $Python = Join-Path $repository '.venv/Scripts/python.exe'
    if (!(Test-Path -LiteralPath $Python)) { $Python = 'python' }
}
if (!$env:JAVA_HOME) {
    $jdk = Get-ChildItem -LiteralPath $ToolsRoot -Directory -Filter 'jdk-17*' | Select-Object -First 1
    if (!$jdk) { throw 'Run scripts/setup_android.ps1 first or set JAVA_HOME.' }
    $env:JAVA_HOME = $jdk.FullName
}
if (!$env:ANDROID_HOME) { $env:ANDROID_HOME = Join-Path $ToolsRoot 'sdk' }
$env:PYTHONUTF8 = '1'
# Use the host's trusted roots, including locally managed network certificates.
$env:JAVA_TOOL_OPTIONS = "$env:JAVA_TOOL_OPTIONS -Djavax.net.ssl.trustStoreType=Windows-ROOT"
$env:PATH = "$env:JAVA_HOME/bin;$env:ANDROID_HOME/platform-tools;$env:PATH"
Push-Location (Join-Path $repository 'android')
try {
    & ./gradlew.bat @Tasks "-PpetPython=$Python" --console=plain
    if ($LASTEXITCODE -ne 0) { throw "Android build failed: $LASTEXITCODE" }
    if ($Tasks -contains 'assembleDebug') {
        $destination = Join-Path $repository 'dist-android'
        New-Item -ItemType Directory -Force -Path $destination | Out-Null
        $metadata = Get-Content -LiteralPath 'app/build/outputs/apk/debug/output-metadata.json' -Raw | ConvertFrom-Json
        $output = $metadata.elements[0]
        $apk = Join-Path $destination "dsh-pet-android-$($output.versionName)-debug.apk"
        Copy-Item -LiteralPath (Join-Path 'app/build/outputs/apk/debug' $output.outputFile) -Destination $apk -Force
        $digest = Get-FileHash -LiteralPath $apk -Algorithm SHA256
        "$($digest.Hash.ToLowerInvariant())  $(Split-Path $apk -Leaf)" |
            Set-Content -LiteralPath (Join-Path $destination 'SHA256SUMS.txt') -Encoding ascii
        $digest | Format-List
    }
} finally { Pop-Location }
