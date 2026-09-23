$ErrorActionPreference = "Continue"
$work = "D:\dsh-pet\.work-assets"
$ff = "D:\dsh-pet\.venv\Lib\site-packages\imageio_ffmpeg\binaries\ffmpeg-win-x86_64-v7.1.exe"
$py = "D:\dsh-pet\.venv\Scripts\python.exe"
$target = $args[0]
if (-not $target) { $target = "$work\out\birthday.webm" }
$tag = [System.IO.Path]::GetFileNameWithoutExtension($target)

# 1) raw RGBA dump via the pet's own pipeline (-pix_fmt rgba over a pipe)
& $ff -hide_banner -loglevel error -i $target -f rawvideo -pix_fmt rgba -y "$work\out\$tag.rgba"
Write-Output "== alpha stats ($tag) =="
& $py "$work\alpha_stats.py" "$work\out\$tag.rgba"

# 2) one visible frame composited over a checkerboard
$filt = "[0:v]format=rgba[fg];color=c=0x2E2E2E:s=640x360:r=1,format=rgba,drawgrid=w=20:h=20:t=1:c=0x6E6E6E@1[bg];[bg][fg]overlay=format=auto,format=rgb24[out]"
& $ff -hide_banner -loglevel error -ss 5.0 -i $target -filter_complex $filt -frames:v 1 -y "$work\out\${tag}_check.png"
if (Test-Path "$work\out\${tag}_check.png") { Write-Output "checker_png=OK" } else { Write-Output "checker_png=FAIL" }
