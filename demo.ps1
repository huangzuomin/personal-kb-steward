# demo.ps1 - End-to-end demo script for personal-kb-steward
$ErrorActionPreference = "Stop"

Write-Host "========================================================" -ForegroundColor Cyan
Write-Host "  Personal Knowledge Steward - Demo Initialization" -ForegroundColor Cyan
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host ""

Write-Host "[1/5] Initializing demo workspace targeting examples\mini-vault..." -ForegroundColor Yellow
python scripts\init_config.py --kb "examples\mini-vault"
Write-Host ""

Write-Host "[2/5] Running Task: 整理知识库 (Organize KB) [Dry Run]" -ForegroundColor Yellow
python scripts\personal_kb_steward.py task "整理知识库"
Write-Host ""

Write-Host "[3/5] Running Task: 准备写作素材 (Prepare Writing Materials) [Dry Run]" -ForegroundColor Yellow
python scripts\personal_kb_steward.py task "准备写作素材：地方媒体AI转型"
Write-Host ""

Write-Host "[4/5] Checking Manual Review Queue" -ForegroundColor Yellow
python scripts\personal_kb_steward.py review list
Write-Host ""

Write-Host "[5/5] Generating Visual Demo Report" -ForegroundColor Yellow
python scripts\generate_demo_report.py
Write-Host ""

Write-Host "========================================================" -ForegroundColor Cyan
Write-Host "Demo complete! Open 'demo_report.html' in your browser." -ForegroundColor Green
Write-Host "========================================================" -ForegroundColor Cyan
