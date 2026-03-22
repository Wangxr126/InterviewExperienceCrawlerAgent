# 打包上传到 PAI-DSW 的最小文件（train_lora + 数据 + dsw 配置）
# 用法: 在 PowerShell 中执行  cd ...\微调\dsw  ;  .\pack_for_dsw.ps1

$ErrorActionPreference = "Stop"
$DswDir = $PSScriptRoot
$FinetuneRoot = Split-Path -Parent $DswDir
$OutZip = Join-Path $DswDir "finetune_dsw_bundle.zip"

$TrainPy = Join-Path $FinetuneRoot "train_lora.py"
$DataJsonl = Join-Path $FinetuneRoot "training_data_alpaca.jsonl"

foreach ($p in @($TrainPy, $DataJsonl)) {
    if (-not (Test-Path -LiteralPath $p)) {
        Write-Error "缺少文件: $p"
    }
}

$staging = Join-Path $DswDir "_pack_staging"
if (Test-Path -LiteralPath $staging) {
    Remove-Item -LiteralPath $staging -Recurse -Force
}
$rootInStaging = Join-Path $staging "finetune"
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
    "对齐本地微调环境.txt"
)
foreach ($name in $copyNames) {
    $src = Join-Path $DswDir $name
    if (Test-Path -LiteralPath $src) {
        Copy-Item -LiteralPath $src -Destination (Join-Path $dswInStaging $name) -Force
    }
}

if (Test-Path -LiteralPath $OutZip) {
    Remove-Item -LiteralPath $OutZip -Force
}
Compress-Archive -Path (Join-Path $staging "finetune") -DestinationPath $OutZip -Force
Remove-Item -LiteralPath $staging -Recurse -Force

Write-Host "已生成: $OutZip"
$len = (Get-Item -LiteralPath $OutZip).Length / 1MB
Write-Host ("约 {0:N2} MB" -f $len)
