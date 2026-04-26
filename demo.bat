@echo off
chcp 65001 >nul
echo ========================================================
echo   Personal Knowledge Steward - Demo Initialization
echo ========================================================
echo.

echo [1/5] Initializing demo workspace targeting examples\mini-vault...
python scripts\init_config.py --kb "examples\mini-vault"
echo.

echo [2/5] Running Task: 整理知识库 (Organize KB) [Dry Run]
python scripts\personal_kb_steward.py task "整理知识库"
echo.

echo [3/5] Running Task: 准备写作素材 (Prepare Writing Materials) [Dry Run]
python scripts\personal_kb_steward.py task "准备写作素材：地方媒体AI转型"
echo.

echo [4/5] Checking Manual Review Queue
python scripts\personal_kb_steward.py review list
echo.

echo [5/5] Generating Visual Demo Report
python scripts\generate_demo_report.py
echo.

echo ========================================================
echo Demo complete! Open 'demo_report.html' in your browser.
echo ========================================================
