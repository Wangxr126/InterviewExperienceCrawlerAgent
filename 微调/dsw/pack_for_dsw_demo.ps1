# 打包「推理对比演示」所需文件到 DSW
# 包含：infer_server.py + demo_cases.json + dsw 配置文件
# 用法：cd 微调\dsw  ;  .\pack_for_dsw_demo.ps1

$ErrorActionPreference = "Stop"
$DswDir      = $PSScriptRoot
$FinetuneRoot = Split-Path -Parent $DswDir
$OutZip      = Join-Path $DswDir "finetune_dsw_demo_bundle.zip"

# ── 必须文件 ──────────────────────────────────────────────────────────
$InferServerPy = Join-Path $FinetuneRoot "infer_server.py"
$DemoCasesJson = Join-Path $FinetuneRoot "demo_cases.json"

foreach ($p in @($InferServerPy, $DemoCasesJson)) {
    if (-not (Test-Path -LiteralPath $p)) {
        Write-Error "缺少文件: $p"
    }
}

# ── 暂存目录 ──────────────────────────────────────────────────────────
$staging       = Join-Path $DswDir "_demo_staging"
if (Test-Path -LiteralPath $staging) {
    Remove-Item -LiteralPath $staging -Recurse -Force
}
$rootInStaging = Join-Path $staging "finetune"
$dswInStaging  = Join-Path $rootInStaging "dsw"
New-Item -ItemType Directory -Path $dswInStaging -Force | Out-Null

# ── 复制核心文件 ──────────────────────────────────────────────────────
Copy-Item -LiteralPath $InferServerPy -Destination (Join-Path $rootInStaging "infer_server.py") -Force
Copy-Item -LiteralPath $DemoCasesJson -Destination (Join-Path $rootInStaging "demo_cases.json") -Force

# ── 复制 dsw 配置文件 ────────────────────────────────────────────────
$copyNames = @(
    "requirements-dsw.txt",
    "setup_dsw.sh",
    "install_venv_dsw.sh",
    "env_dsw.example",
    "README_DSW.txt"
)
foreach ($name in $copyNames) {
    $src = Join-Path $DswDir $name
    if (Test-Path -LiteralPath $src) {
        Copy-Item -LiteralPath $src -Destination (Join-Path $dswInStaging $name) -Force
    }
}

# ── adapter 权重（若本地存在则一并打包）────────────────────────────────
$adapterSrc = Join-Path $FinetuneRoot "adapter"
if (Test-Path -LiteralPath $adapterSrc) {
    Write-Host "找到 adapter 目录，一并打包…"
    Copy-Item -LiteralPath $adapterSrc -Destination (Join-Path $rootInStaging "adapter") -Recurse -Force
} else {
    Write-Host "未找到 adapter 目录（DSW 上已有权重文件夹时可忽略）"
}

# ── 打包 ──────────────────────────────────────────────────────────────
if (Test-Path -LiteralPath $OutZip) {
    Remove-Item -LiteralPath $OutZip -Force
}
Compress-Archive -Path (Join-Path $staging "finetune") -DestinationPath $OutZip -Force
Remove-Item -LiteralPath $staging -Recurse -Force

Write-Host ""
Write-Host "===== 打包完成 ====="
Write-Host "输出文件: $OutZip"
$len = (Get-Item -LiteralPath $OutZip).Length / 1MB
Write-Host ("约 {0:N2} MB" -f $len)
Write-Host ""
Write-Host "DSW 上操作步骤："
Write-Host "  1. 上传 finetune_dsw_demo_bundle.zip 到 DSW"
Write-Host "  2. unzip -o finetune_dsw_demo_bundle.zip -d /mnt/workspace/TEMP-FILE-STATION/"
Write-Host "  3. cd /mnt/workspace/TEMP-FILE-STATION/finetune"
Write-Host "  4. 确认 adapter/ 权重文件夹已在此目录（或 DSW 上已有，跳过）"
Write-Host "  5. conda activate 或 source .venv_finetune/bin/activate"
Write-Host "  6. python infer_server.py"
Write-Host "  7. 在 DSW 控制台开启端口 8899 转发"
