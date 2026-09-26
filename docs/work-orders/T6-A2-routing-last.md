# A2 final routing correction

Resume the same integration session. Own router.json, tests/test_router.py or existing A2 routing tests, and checkpoint-A2 report only. Others are editing source executor and typed_card_updates; preserve their changes. No private data, live calls, installs, subagents, commits.

Root independently verified A2 (82 passed, 10 subtests) and all four original probes now pass. One introduced regression remains: route('检查案例卡质量') now returns case-story-bank-builder because case_bank is first. Restore healthcheck priority while placing case_bank before generic work-memory. Keep case generation reachable for '生成案例卡' and '生成项目案例卡', and existing entry routes unchanged. Add focused routing assertions; no NL router redesign. Run routing + A2 integration tests, update report to supersede FIRST placement claim, then STOP. B1 waits typed update acceptance; do not start B1.
