$ErrorActionPreference = "Continue"
$work = "D:\dsh-pet\.work-assets"
$ff = "D:\dsh-pet\.venv\Lib\site-packages\imageio_ffmpeg\binaries\ffmpeg-win-x86_64-v7.1.exe"
$out = "$work\out\birthday.webm"
if (Test-Path $out) { Remove-Item $out -Force }

$filt = "[0:v]fps=24,drawbox=x=50:y=36:w=182:h=48:color=0x89A67C@1:t=fill,colorkey=0x89A67C:0.02:0,scale=658:370:flags=bicubic[fg];color=c=black@0.0:s=640x360:r=24,format=rgba[bg];[bg][fg]overlay=x=-14:y=11:format=auto,format=yuva420p[out]"

$sw = [System.Diagnostics.Stopwatch]::StartNew()
& $ff -hide_banner -loglevel warning -i "$work\src\source.mp4" `
  -filter_complex $filt -map "[out]" -an `
  -c:v libvpx-vp9 -pix_fmt yuva420p -auto-alt-ref 0 `
  -row-mt 1 -threads 8 -deadline good -cpu-used 4 `
  -crf 28 -b:v 700k `
  -colorspace bt709 -color_primaries bt709 -color_trc bt709 `
  -y $out
$code = $LASTEXITCODE
$sw.Stop()
Write-Output ("exit={0} elapsed={1:N1}s" -f $code, $sw.Elapsed.TotalSeconds)
if (Test-Path $out) {
  $kb = [math]::Round((Get-Item $out).Length / 1KB)
  Write-Output ("OUTPUT_KB={0}" -f $kb)
  & $ff -hide_banner -i $out 2>&1 | Select-String -Pattern "Duration|Stream|ALPHA_MODE" | ForEach-Object { "  " + $_.Line.Trim() }
} else {
  Write-Output "SIZE_FAIL no output"
}
