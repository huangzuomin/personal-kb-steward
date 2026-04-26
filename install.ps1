param(
  [string]$KnowledgeBase = ""
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host "personal-kb-steward install"

if (-not (Test-Path (Join-Path $Root "config.json"))) {
  Copy-Item -LiteralPath (Join-Path $Root "config.example.json") -Destination (Join-Path $Root "config.json")
}

if ($KnowledgeBase -ne "") {
  python (Join-Path $Root "scripts\init_config.py") --kb $KnowledgeBase
}

python (Join-Path $Root "scripts\validate_config.py")
python (Join-Path $Root "scripts\personal_kb_steward.py") status

Write-Host "Done. Next: python scripts\personal_kb_steward.py plan `"整理知识库`""
