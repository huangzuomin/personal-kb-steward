"""Quick LLM call test."""
import sys, json
sys.path.insert(0, r"C:\Users\zooma\.qclaw\workspace-agent-f731ab99")
from core.llm import call_chat_completion, LLMError
from core.config import config

cfg = config()

system_prompt = "You are a title generator. Return ONLY valid JSON with this structure: {\"items\":[{\"title\":\"...\",\"type\":\"seed-card\",\"status\":\"seed\",\"stage\":\"seed\",\"sources\":[\"test.md\"],\"summary\":\"...\",\"confidence\":\"medium\",\"review_required\":false}]}. Return exactly one item."

user_payload = {"task": "整理知识库", "documents": [{"title": "AI搜索工具对新闻发现的影响", "body": "本文探讨AI搜索工具如何改变记者的信息发现方式，以及对新闻业的影响。"}]}

try:
    result = call_chat_completion(cfg, system_prompt, user_payload)
    print("LLM call succeeded:")
    print(json.dumps(json.loads(result), ensure_ascii=False, indent=2))
except LLMError as e:
    print(f"LLM Error: {e}")
except Exception as e:
    print(f"Other error: {e}")
