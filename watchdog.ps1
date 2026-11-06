# 自动交付守卫: 监控迭代进度, 跑满后自动执行最终分析
$ErrorActionPreference = 'Continue'
$py = "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe"
$prog = 'C:\Users\LZY20\Desktop\量化回测\iteration\progress.json'
$out  = 'C:\Users\LZY20\Desktop\量化回测\iteration\交付报告.txt'

Write-Output "[watchdog] 开始监控迭代进度..."
while ($true) {
    Start-Sleep -Seconds 20
    if (-not (Test-Path $prog)) { Write-Output "[watchdog] progress.json 不存在, 继续等待"; continue }
    try {
        $p = Get-Content $prog -Raw | ConvertFrom-Json
    } catch { continue }
    if ($p.elapsed_sec -ge $p.total_sec) {
        Write-Output "[watchdog] 迭代已跑满 ($($p.elapsed_sec)s/$($p.total_sec)s), 等 10 秒让最终文件落盘..."
        Start-Sleep -Seconds 10
        break
    }
}
Set-Location 'C:\Users\LZY20\Desktop\harness\quant'
Write-Output "[watchdog] 执行最终分析..."
& $py final_analysis.py 2>&1 | Out-File $out -Encoding utf8
Write-Output "[watchdog] 交付报告已生成: $out"
