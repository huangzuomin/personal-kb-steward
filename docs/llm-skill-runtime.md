# LLM Skill Runtime

Phase 10 introduces a runtime path that can load `skills/<skill-name>/SKILL.md` as an execution contract and ask an OpenAI-compatible LLM to return structured JSON.

## Commands

Dry-run with a real provider:

```powershell
python scripts\personal_kb_steward.py plan --llm "整理知识库"
```

Dry-run with mock output for tests and classroom demos:

```powershell
python scripts\personal_kb_steward.py plan --mock-llm "整理知识库"
```

`--llm` and `--mock-llm` currently affect dry-run plans only. `--apply` still uses the existing deterministic runtime until the MVP Skill executors are rewritten.

## Provider Config

`config.json` contains:

```json
{
  "llm": {
    "provider": "openai-compatible",
    "base_url": "https://api.openai.com/v1",
    "model": "",
    "api_key_env": "OPENAI_API_KEY",
    "temperature": 0.2,
    "timeout_seconds": 60
  }
}
```

Set these environment variables for a real call:

```powershell
$env:OPENAI_API_KEY="..."
$env:OPENAI_MODEL="..."
```

## Runtime Boundary

The LLM is allowed to understand, classify, extract, and propose. Python remains responsible for:

- loading the Skill contract;
- forcing JSON output;
- validating required fields;
- rejecting legacy `source`;
- checking that `sources` are concrete provided files;
- rendering Markdown previews;
- putting validation issues into `manual_review`;
- keeping all writes behind dry-run / apply.

## Current Scope

The runtime is wired into product entries through their primary Skill. It is ready for Phase 12, where the first three MVP Skills can get dedicated schemas and renderers:

- `mindseed-grow`
- `topic-insight-miner`
- `writing-material-pack`
