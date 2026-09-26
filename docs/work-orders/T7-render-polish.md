# T7 rendering handoff polish

Same topic owner and restrictions as T7-last-corrections.md. No other module changes.

Astra inspected the refreshed actual Markdown: gaps and actions are concatenated into a single line (`...）- ...`) because inline Jinja if/end blocks eat newlines under trim_blocks. Correct topic_page.j2 so two gaps/actions are separate real Markdown lines; add a narrow renderer regression (not a string check of the template). Regenerate both evidence samples and reports. Remove stale previous mock-topic-stub.md or replace with clearly marked pointer/updated content so no misleading old sample remains. Do not label malformed negative output as clean sample.

Update stale module doc text saying tensions require supports vs contradicts from two distinct sources; this conflicts with the corrected two compiled sides rule. Remove the bare empty '-' in report under 分歧语义. Review generated visible text for list formatting, Chinese and unsupported overclaiming (e.g. say records/reported effect, not proof of causal effectiveness).

Run topic generation + claim_evidence focused tests and provide report/log. Do not change core/claims or other generators. Handoff when finished.
