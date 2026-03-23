# 第二套上传包：文件名带时间戳，不覆盖 finetune_dsw_bundle.zip，便于并行实验
# 用法: cd E:\Agent\AgentProject\wxr_agent\微调\dsw
#       .\pack_for_dsw_parallel.ps1
#       .\pack_for_dsw_parallel.ps1 -RunId v100-8192

param(
    [string]$RunId = ""
)

$ErrorActionPreference = "Stop"
$DswDir = $PSScriptRoot
$FinetuneRoot = Split-Path -Parent $DswDir

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$suffix = if ($RunId) { "_$RunId" } else { "" }
$OutZip = Join-Path $DswDir "finetune_dsw_bundle_${stamp}${suffix}.zip"

$TrainPy = Join-Path $FinetuneRoot "train_lora.py"
$DataJsonl = Join-Path $FinetuneRoot "training_data_alpaca.jsonl"

foreach ($p in @($TrainPy, $DataJsonl)) {
    if (-not (Test-Path -LiteralPath $p)) {
        Write-Error "缺少文件: $p"
    }
}

$staging = Join-Path $DswDir "_pack_staging_parallel"
if (Test-Path -LiteralPath $staging) {
    Remove-Item -LiteralPath $staging -Recurse -Force
}
$rootInStaging = Join-Path $staging "finetune_run2"
$dswInStaging = Join-Path $rootInStaging "dsw"
New-Item -ItemType Directory -Path $dswInStaging -Force | Out-Null

Copy-Item -LiteralPath $TrainPy -Destination (Join-Path $rootInStaging "train_lora.py") -Force
Copy-Item -LiteralPath $DataJsonl -Destination (Join-Path $rootInStaging "training_data_alpaca.jsonl") -Force

$copyNames = @(
    "requirements-dsw.txt",
    "setup_dsw.sh",
    "install_venv_dsw.sh",
    "env_dsw.example",
    "README_DSW.txt",
    "对齐本地微调环境.txt",
    "run_second_instance.sh"
)
foreach ($name in $copyNames) {
    $src = Join-Path $DswDir $name
    if (Test-Path -LiteralPath $src) {
        Copy-Item -LiteralPath $src -Destination (Join-Path $dswInStaging $name) -Force
    }
}

Compress-Archive -Path (Join-Path $staging "finetune_run2") -DestinationPath $OutZip -Force
Remove-Item -LiteralPath $staging -Recurse -Force

Write-Host "已生成（与 finetune_dsw_bundle.zip 不同名，可并存上传）:"
Write-Host "  $OutZip"
$len = (Get-Item -LiteralPath $OutZip).Length / 1MB
Write-Host ("约 {0:N2} MB" -f $len)
Write-Host ""
Write-Host "远程解压目录建议: /mnt/workspace/TEMP-FILE-STATION/finetune_run2"
Write-Host "详见同目录 dsw/run_second_instance.sh"
