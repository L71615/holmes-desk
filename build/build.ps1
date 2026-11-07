# JudgeDee 打包脚本：生成 dist\JudgeDee.exe（单文件、免安装、带图标）
# 用法：pwsh -File build\build.ps1
$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

Write-Host "==> 检查依赖" -ForegroundColor Cyan
python -c "import PyInstaller, requests" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "缺依赖，先装：python -m pip install pyinstaller requests" -ForegroundColor Yellow
    exit 1
}

$icon = Join-Path $root "judgedee\assets\judgedee-app.ico"

Write-Host "==> PyInstaller 打包" -ForegroundColor Cyan
python -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --windowed `
    --name JudgeDee `
    --icon $icon `
    --add-data "judgedee\assets;judgedee\assets" `
    --add-data "judgedee\data;judgedee\data" `
    --collect-submodules judgedee `
    judgedee\__main__.py

if ($LASTEXITCODE -ne 0) {
    Write-Host "打包失败" -ForegroundColor Red
    exit 1
}

$exe = Join-Path $root "dist\JudgeDee.exe"
if (Test-Path $exe) {
    $size = [math]::Round((Get-Item $exe).Length / 1MB, 1)
    Write-Host "==> 完成：$exe（$size MB）" -ForegroundColor Green
} else {
    Write-Host "没有找到产物" -ForegroundColor Red
    exit 1
}
