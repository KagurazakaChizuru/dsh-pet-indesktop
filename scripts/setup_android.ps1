param(
    [string]$ToolsRoot = "$env:LOCALAPPDATA/dsh-pet-android",
    [switch]$WithEmulator
)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
New-Item -ItemType Directory -Force -Path $ToolsRoot | Out-Null

function Get-VerifiedArchive([string]$Uri, [string]$Destination, [string]$Sha256, [string]$Fallback = '') {
    if (!(Test-Path -LiteralPath $Destination) -or
        (Get-FileHash -LiteralPath $Destination -Algorithm SHA256).Hash -ne $Sha256) {
        Write-Host "Downloading $Uri"
        try { Invoke-WebRequest -Uri $Uri -OutFile $Destination -TimeoutSec 180 }
        catch {
            if (!$Fallback) { throw }
            Write-Host "Using checksum-verified mirror: $Fallback"
            Invoke-WebRequest -Uri $Fallback -OutFile $Destination -TimeoutSec 180
        }
    }
    if ((Get-FileHash -LiteralPath $Destination -Algorithm SHA256).Hash -ne $Sha256) {
        throw "SHA-256 mismatch: $Destination"
    }
}

$jdk = Get-ChildItem -LiteralPath $ToolsRoot -Directory -Filter 'jdk-17*' | Select-Object -First 1
if (!$jdk) {
    $jdkUri = 'https://aka.ms/download-jdk/microsoft-jdk-17.0.20.1-windows-x64.zip'
    $hashResponse = Invoke-WebRequest "$jdkUri.sha256sum.txt" -TimeoutSec 30
    $hashText = if ($hashResponse.Content -is [byte[]]) {
        [Text.Encoding]::UTF8.GetString($hashResponse.Content)
    } else { [string]$hashResponse.Content }
    $expectedHash = ($hashText -split '\s+')[0]
    if ($expectedHash -notmatch '^[0-9a-fA-F]{64}$') { throw 'Invalid JDK checksum.' }
    $archive = Join-Path $ToolsRoot 'jdk17.zip'
    Get-VerifiedArchive $jdkUri $archive $expectedHash
    Expand-Archive -LiteralPath $archive -DestinationPath $ToolsRoot -Force
    $jdk = Get-ChildItem -LiteralPath $ToolsRoot -Directory -Filter 'jdk-17*' | Select-Object -First 1
}
if (!$jdk) { throw 'JDK 17 was not installed.' }
$env:JAVA_HOME = $jdk.FullName
$env:JAVA_TOOL_OPTIONS = "$env:JAVA_TOOL_OPTIONS -Djavax.net.ssl.trustStoreType=Windows-ROOT"
$env:ANDROID_HOME = Join-Path $ToolsRoot 'sdk'
$env:PATH = "$env:JAVA_HOME/bin;$env:ANDROID_HOME/platform-tools;$env:PATH"
$manager = Join-Path $env:ANDROID_HOME 'cmdline-tools/latest/bin/sdkmanager.bat'
if (!(Test-Path -LiteralPath $manager)) {
    $archive = Join-Path $ToolsRoot 'commandlinetools.zip'
    Get-VerifiedArchive 'https://dl.google.com/android/repository/commandlinetools-win-15859902_latest.zip' $archive '90ae805d20434428bffcb699c290860f19bb5f66a67e6b330067e3de801fb04a'
    $unpack = Join-Path $ToolsRoot 'sdk-unpack'
    Expand-Archive -LiteralPath $archive -DestinationPath $unpack -Force
    New-Item -ItemType Directory -Force -Path "$env:ANDROID_HOME/cmdline-tools/latest" | Out-Null
    Copy-Item -Path "$unpack/cmdline-tools/*" -Destination "$env:ANDROID_HOME/cmdline-tools/latest" -Recurse -Force
}
# Installation was explicitly authorized; sdkmanager records the SDK licenses.
1..100 | ForEach-Object { 'y' } | & $manager "--sdk_root=$env:ANDROID_HOME" --licenses
if ($LASTEXITCODE -ne 0) { throw 'Android SDK license setup failed.' }
$packages = @('platform-tools', 'platforms;android-36', 'build-tools;35.0.0')
if ($WithEmulator) { $packages += @('emulator', 'system-images;android-35;google_apis;x86_64') }
& $manager "--sdk_root=$env:ANDROID_HOME" @packages
if ($LASTEXITCODE -ne 0) { throw 'Android SDK package installation failed.' }
& "$env:JAVA_HOME/bin/java.exe" -version
& "$env:ANDROID_HOME/platform-tools/adb.exe" devices -l
$gradleArchive = Join-Path $ToolsRoot 'gradle-8.11.1-bin.zip'
Get-VerifiedArchive 'https://downloads.gradle.org/distributions/gradle-8.11.1-bin.zip' $gradleArchive 'f397b287023acdba1e9f6fc5ea72d22dd63669d59ed4a289a29b1a76eee151c6' 'https://repo.huaweicloud.com/gradle/gradle-8.11.1-bin.zip'
$gradleUser = if ($env:GRADLE_USER_HOME) { $env:GRADLE_USER_HOME } else { Join-Path $env:USERPROFILE '.gradle' }
# The cache key is Gradle Wrapper's hash of the pinned distribution URL.
$gradleCache = Join-Path $gradleUser 'wrapper/dists/gradle-8.11.1-bin/1cz1qd87tzpd0obqxmzf16lxg'
New-Item -ItemType Directory -Force -Path $gradleCache | Out-Null
if (!(Test-Path -LiteralPath "$gradleCache/gradle-8.11.1-bin.zip.ok")) {
    Copy-Item -LiteralPath $gradleArchive -Destination "$gradleCache/gradle-8.11.1-bin.zip" -Force
}
Write-Host "JAVA_HOME=$env:JAVA_HOME"
Write-Host "ANDROID_HOME=$env:ANDROID_HOME"
