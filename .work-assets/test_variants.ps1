$ErrorActionPreference = "Continue"
$work = "D:\dsh-pet\.work-assets"
$ff = "D:\dsh-pet\.venv\Lib\site-packages\imageio_ffmpeg\binaries\ffmpeg-win-x86_64-v7.1.exe"
$py = "D:\dsh-pet\.venv\Scripts\python.exe"

Write-Output "== 对照：官方素材用桌宠的解码器（-c:v libvpx-vp9）解 alpha =="
& $ff -hide_banner -loglevel error -c:v libvpx-vp9 -i "D:\dsh-pet\assets\characters\shenshen\videos\idle\待机呼吸休闲.webm" -frames:v 1 -f rawvideo -pix_fmt rgba -y "$work\out\ref1.rgba"
& $py "$work\alpha_stats.py" "$work\out\ref1.rgba"

$key = "[0:v]fps=24,drawbox=x=50:y=36:w=182:h=48:color=0x89A67C@1:t=fill,colorkey=0x89A67C:0.02:0,scale=658:370[fg0];color=c=black@0.0:s=640x360:r=24,format=rgba[bg];[bg][fg0]overlay=x=-14:y=11:format=auto[fg];[fg]split=2[fgA][fgB];"
$fa = $key + "[fgA]alphaextract[m];color=c=black:s=640x360:r=24,format=rgba[blk];[blk][fgB]overlay=format=auto[rgb];[rgb][m]alphamerge,format=yuva420p[out]"
$fb = $key + "[fgA]alphaextract,lut=y='if(gt(val,0),255,0)',format=rgba[m];color=c=black@0.0:s=640x360:r=24,format=rgba[blk];[blk][fgB][m]maskedmerge,format=yuva420p[out]"

foreach ($v in @(@("A", $fa), @("B", $fb))) {
  $name = $v[0]; $filt = $v[1]
  $out = "$work\out\t$name.webm"
  if (Test-Path $out) { Remove-Item $out -Force }
  $sw = [System.Diagnostics.Stopwatch]::StartNew()
  & $ff -hide_banner -loglevel error -ss 5 -t 1 -i "$work\src\source.mp4" `
    -filter_complex $filt -map "[out]" -an `
    -c:v libvpx-vp9 -pix_fmt yuva420p -auto-alt-ref 0 `
    -row-mt 1 -threads 8 -deadline good -cpu-used 6 `
    -crf 28 -b:v 700k -colorspace bt709 -color_primaries bt709 -color_trc bt709 -y $out
  $sw.Stop()
  if (Test-Path $out) {
    Write-Output ("VARIANT {0}: {1} KB  编码 {2:N0}s" -f $name, [math]::Round((Get-Item $out).Length / 1KB), $sw.Elapsed.TotalSeconds)
    & $ff -hide_banner -loglevel error -c:v libvpx-vp9 -i $out -frames:v 1 -f rawvideo -pix_fmt rgba -y "$work\out\t$name.rgba"
    & $py "$work\alpha_stats.py" "$work\out\t$name.rgba"
    & $ff -hide_banner -loglevel error -ss 0.5 -c:v libvpx-vp9 -i $out -filter_complex "[0:v]format=rgba[fg];color=c=0x2E2E2E:s=640x360:r=1,format=rgba,drawgrid=w=20:h=20:t=1:c=0x6E6E6E@1[bg];[bg][fg]overlay=format=auto,format=rgb24[o]" -map "[o]" -frames:v 1 -y "$work\out\t${name}_check.png"
  } else {
    Write-Output ("VARIANT {0}: FAILED" -f $name)
  }
}
