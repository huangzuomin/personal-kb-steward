"""Issue #25: synthetic examples only; never load a user's vault or credentials."""
import json
from unittest.mock import patch

import pytest

from core.content_safety import SensitiveContentError, assert_safe_content, sensitive_reason
from core.seed_quality import signal_sentences
from core.signal_extraction import signal_excerpts
from core.llm import call_chat_completion

SAFE = '编辑部需要记录事实来源，并根据读者反馈调整服务流程。'
FAKE_SECRET = 'NotARealCredential9!Example'


@pytest.mark.parametrize('delimiter', ['```', '~~~', '````', '~~~~'])
def test_fenced_content_stays_out_and_duplicate_uses_actual_outside_line(delimiter):
    body = f'{delimiter}\n{SAFE}\n{delimiter}\n{SAFE}\n'
    assert signal_sentences(f'{delimiter}\n{SAFE}\n{delimiter}') == []
    assert [(s.text, s.body_line) for s in signal_excerpts(body)] == [(SAFE, 4)]


@pytest.mark.parametrize('inner', ['~~~', '```', '````python', '```` extra'])
def test_short_wrong_or_info_bearing_fence_cannot_close_outer(inner):
    body = f'````\n{inner}\n内部哨兵文本不能成为知识信号。\n````\n{SAFE}'
    assert signal_sentences(body) == [SAFE]


@pytest.mark.parametrize('body', [f'> ```\n> {SAFE}\n> ```', f'- ```\n  {SAFE}\n  ```', f'```\n{SAFE}'])
def test_quoted_list_and_unclosed_fences_do_not_leak(body):
    assert signal_sentences(body) == []


@pytest.mark.parametrize('line', [
    'sudo nano /etc/nginx/sites-available/example', 'curl http://192.0.2.1',
    'acme.sh --issue -d example.invalid -w /var/www/html', 'network=devnet',
    'make run addr=not-a-real-address', 'screen -S ExampleSession',
    'utm_source=example&utm_medium=note', '.iZExample12345678',
    '192.0.2.1', '2001:db8::1', 'image-2026.png', '[参考资料](https://example.invalid)',
    '`docker compose up`', 'proxy_pass http://127.0.0.1:80;', FAKE_SECRET,
    f'password={FAKE_SECRET}',
])
def test_bare_operations_references_and_credentials_are_not_signals(line):
    assert signal_sentences(line + '\n' + SAFE) == [SAFE]


@pytest.mark.parametrize('line', [
    '服务流程应当可以复核。', 'curl 是一种传输工具，不应据此推导业务结论。',
    'git improves collaboration by recording the history of changes.',
    '使用 `git diff` 核对修改范围，再决定是否批准。',
    '接口文档位于 https://example.invalid ，尚需检查版本。',
])
def test_short_facts_technical_prose_and_inline_code_are_preserved(line):
    assert signal_sentences(line) == [line]


def test_limit_is_not_a_side_effect_of_filtering():
    assert signal_sentences(SAFE, limit=0) == []
    assert signal_sentences('network=devnet\n' + SAFE, limit=1) == [SAFE]


@pytest.mark.parametrize('value', [f'password={FAKE_SECRET}', {'notes': [{'password': FAKE_SECRET}]},
                                   f'```\n-----BEGIN PRIVATE KEY-----\n{FAKE_SECRET}\n```',
                                   {'title': f'api_key="{FAKE_SECRET}"'}, {'password': 123456}])
def test_checker_never_echoes_sensitive_value(value):
    with pytest.raises(SensitiveContentError) as error:
        assert_safe_content(value)
    assert FAKE_SECRET not in str(error.value)


@pytest.mark.parametrize('text', ['password=<REDACTED>', 'api_key=${MY_KEY}', 'token=$MY_TOKEN',
                                  'secret=...', 'https://example.invalid/192.0.2.1',
                                  'ExampleModel-v3.13', 'a39261384433d6b2ba35a323653733ab4ae33f57'])
def test_placeholders_versions_hashes_and_public_endpoints_are_not_credentials(text):
    assert_safe_content(text)
    assert sensitive_reason(text) is None


def test_model_boundary_blocks_before_any_network_or_key_lookup(monkeypatch):
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    with patch('urllib.request.urlopen') as network:
        with pytest.raises(SensitiveContentError):
            call_chat_completion({}, 'Summarize this note.', {'text': f'password={FAKE_SECRET}'})
    network.assert_not_called()


def test_normal_content_uses_auth_but_sensitive_response_is_not_returned(monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY', 'test-transport-auth-only')
    monkeypatch.setenv('OPENAI_MODEL', 'test-model')
    response = {'choices': [{'message': {'content': f'password={FAKE_SECRET}'}}]}
    with patch('urllib.request.urlopen') as network:
        network.return_value.__enter__.return_value.read.return_value = json.dumps(response).encode()
        with pytest.raises(SensitiveContentError) as error:
            call_chat_completion({}, 'Summarize.', {'text': SAFE})
    assert FAKE_SECRET not in str(error.value)
    request = network.call_args.args[0]
    assert SAFE in json.loads(request.data)['messages'][1]['content']
    assert 'test-transport-auth-only' not in request.data.decode()


def test_clustering_does_not_swallow_security_block_as_heuristic_fallback():
    from core.clustering import ClusterInput, cluster_inputs
    with patch('core.llm.call_chat_completion', side_effect=SensitiveContentError('blocked')):
        with pytest.raises(SensitiveContentError):
            cluster_inputs([ClusterInput('quicknote/a.md', '观察', SAFE)], cfg={'llm': {}})
