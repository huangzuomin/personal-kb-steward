"""Issue #27: real renderer/executor, synthetic content, mocked model only."""
import hashlib
import importlib.util
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from jinja2 import UndefinedError

from core import jinja_renderer as renderer
from core.skill_executor import load_executor

ROOT = Path(__file__).resolve().parents[1]


def load_source_renderer():
    spec = importlib.util.spec_from_file_location('source_renderer_test', ROOT / 'skills/topic-research-compile/renderer.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def data(**kwargs):
    return {'source_rel': 'raw/example.md', 'source_title': '示例资料',
            'source_summary': '这份材料记录编辑部如何核对读者反馈。',
            'key_facts': ['编辑部记录来源并核对反馈。'],
            'topics': [{'title': '反馈核查', 'content': '核对流程与来源。'}],
            'quality_flags': [], 'analysis_mode': 'llm', **kwargs}


def test_missing_dependency_fails_instead_of_summary_only(monkeypatch):
    monkeypatch.setattr(renderer, '_JINJA2_AVAILABLE', False)
    error = ImportError('synthetic missing dependency')
    monkeypatch.setattr(renderer, '_JINJA2_IMPORT_ERROR', error)
    with pytest.raises(renderer.RendererDependencyError) as raised:
        load_source_renderer().render(data())
    assert raised.value.__cause__ is error


def test_executor_checks_renderer_before_spending_a_model_call(monkeypatch):
    monkeypatch.setattr(renderer, '_JINJA2_AVAILABLE', False)
    with patch('core.llm.call_chat_completion') as provider:
        execute = load_executor(ROOT, 'topic-research-compile')
        with pytest.raises(renderer.RendererDependencyError):
            execute({'notes': [{'rel': 'raw/example.md', 'title': '示例', 'body': '有效测试资料。'}], 'config': {}, 'use_llm': True})
    provider.assert_not_called()


def test_five_sections_and_structured_fields_are_preserved():
    page, = load_source_renderer().render(data(quality_flags=['来源时间待核。']))
    content = page['content']
    headings = [line for line in content.splitlines() if line.startswith('## ')]
    assert headings == ['## 原始来源', '## 核心摘要', '## 关键事实', '## 提取的专题', '## 质量标记']
    for value in ['编辑部记录来源并核对反馈。', '核对流程与来源。', '来源时间待核。', '分析模式：llm']:
        assert value in content
    assert page['quality_flags'] == ['来源时间待核。']
    assert page['review_required'] is True and page['confidence'] == 'low'
    assert 'status: manual_review' in content


@pytest.mark.parametrize('mode', ['heuristic', 'heuristic-fallback', 'unknown'])
def test_degraded_source_is_not_high_confidence(mode):
    page, = load_source_renderer().render(data(analysis_mode=mode))
    assert page['review_required'] is True
    assert page['confidence'] == 'low'
    assert 'stage: needs_context' in page['content']


def test_clean_single_source_is_allowed_without_truth_certification():
    page, = load_source_renderer().render(data())
    assert page['sources'] == ['raw/example.md']
    assert page['confidence'] == 'medium'
    assert page['review_required'] is False


def test_missing_fact_context_and_wrong_types_fail_loudly():
    with pytest.raises(UndefinedError):
        renderer.render_template('source_note.j2', {'title': 'Bad context'})
    with pytest.raises(ValueError, match='key_facts'):
        load_source_renderer().render(data(key_facts='not an array'))


def test_render_failure_is_not_relabelled_as_model_fallback():
    execute = load_executor(ROOT, 'topic-research-compile')
    body = '示例正文内容足够长，用于验证渲染失败不被降级为模型回退，并保持快照校验路径完整。'
    payload = json.dumps({'summary': '片段摘要。',
                          'key_statements': [{'text': '事实一', 'quote': '示例正文内容足够长',
                                              'kind': 'assertion'}],
                          'topics': [], 'limitations': [], 'quality_flags': []})
    note = {'rel': 'raw/example.md', 'title': '示例', 'body': body,
            'source_text': body, 'source_sha256': hashlib.sha256(body.encode('utf-8')).hexdigest()}
    # Patch the loaded executor globals: these are the functions it actually calls.
    with patch.dict(execute.__globals__, {
        'call_chat_completion': lambda *args: payload,
        'render': lambda *args: (_ for _ in ()).throw(UndefinedError('broken template')),
    }):
        with pytest.raises(UndefinedError):
            execute({'notes': [note], 'config': {}})


def test_missing_import_is_retained_without_failing_readonly_import():
    import builtins
    real_import = builtins.__import__
    def block_jinja(name, *args, **kwargs):
        if name == 'jinja2':
            raise ImportError('synthetic absent jinja2')
        return real_import(name, *args, **kwargs)
    spec = importlib.util.spec_from_file_location('isolated_jinja_renderer', ROOT / 'core/jinja_renderer.py')
    module = importlib.util.module_from_spec(spec)
    with patch('builtins.__import__', side_effect=block_jinja):
        spec.loader.exec_module(module)
    assert not module._JINJA2_AVAILABLE
    with pytest.raises(module.RendererDependencyError) as error:
        module.require_renderer()
    assert isinstance(error.value.__cause__, ImportError)


def test_source_checks_uncleaned_note_before_provider():
    from core.content_safety import SensitiveContentError
    with patch('core.llm.call_chat_completion') as provider:
        execute = load_executor(ROOT, 'topic-research-compile')
        with pytest.raises(SensitiveContentError):
            execute({'notes': [{'rel': 'raw/a.md', 'title': '示例', 'body': '# password=NotARealCredential9!Example'}], 'config': {}})
    provider.assert_not_called()
