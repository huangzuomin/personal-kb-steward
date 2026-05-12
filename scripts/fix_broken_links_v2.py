"""Fix broken links after topic stub renames.
Step 1: Update source notes to point to renamed topic stubs
Step 2: For unmatched sources, update links to best available stubs
Step 3: Write redirects for orphaned stubs
"""
import os, re

topics_dir = r'C:\Users\zooma\.qclaw\workspace\wiki\wiki\topics'
sources_dir = r'C:\Users\zooma\.qclaw\workspace\wiki\wiki\sources'

# After Step 1 renames: update source notes that were incorrectly updated
# to old filenames (before rename) to use the new filenames
post_rename_fixes = {
    # (source file, old target, new target)
    'source-topic-0240252e12.md': ('topic-topic-from-20260510-170640-0.md', 'topic-topic-from-2025年创新温州建设十大重大标志性成果出炉.md'),
    'source-ai.md': ('topic-topic-from-ai-20260510-170640-0.md', 'topic-topic-from-2025年创新温州建设十大重大标志性成果出炉.md'),
}

# For remaining unmatched sources, link to existing stubs
# We need to look at actual content to determine best match
remaining_updates = {
    # source -> (target stub filename, topic title)
    'source-topic-7ff881a931.md': ('topic-topic-from-ai-20260510-170641-0.md', '温州市揭牌成立全省首个人工智能局 加快建设人工智能创新发展先行市'),
    'source-topic-dc15ef1ed0.md': ('topic-topic-from-ai-20260510-170641-0.md', '温州市揭牌成立全省首个人工智能局 加快建设人工智能创新发展先行市'),
    'source-topic-ee44903047.md': ('topic-topic-from-ai-20260510-170641-0.md', '温州市揭牌成立全省首个人工智能局 加快建设人工智能创新发展先行市'),
    'source-topic-b8643c30be.md': ('topic-topic-from-ai-20260510-170640-0.md', '新晋万亿之城进击AI，"斜杠青年"温州下一站'),
    'source-topic-3273484d48.md': ('topic-topic-from-关于印发温州市加快人工智能创新发展的若干政策举措（2025—2027年）的通知.md', '关于印发温州市加快人工智能创新发展的若干政策举措（2025—2027年）的通知'),
    'source-topic-c8f00a2569.md': ('topic-topic-from-gdp-ai-20260510-170640-0.md', '冲刺万亿GDP的温州-全面注入AI动能'),
}

print('=== Step 1: Fix post-rename source updates ===')
for src_fname, (old_target, new_target) in post_rename_fixes.items():
    src_path = os.path.join(sources_dir, src_fname)
    if not os.path.exists(src_path):
        print(f'  SKIP (not found): {src_fname}')
        continue
    with open(src_path, encoding='utf-8') as f:
        content = f.read()
    new_link = f'[[wiki/topics/{new_target}|Topic from {new_target[18:-4]}]]'
    old_link_pattern = f'[[wiki/topics/{old_target}|Topic from '
    if old_link_pattern in content:
        # Find and replace just this link
        match = re.search(r'\[\[wiki/topics/[^\]]+\|Topic from [^\]]+\]\]', content)
        if match:
            current_link = match.group(0)
            new_content = content.replace(current_link, new_link)
            with open(src_path, 'w', encoding='utf-8') as f:
                f.write(new_content)
            print(f'  FIX: {src_fname} -> {new_target}')
    else:
        print(f'  ALREADY OK or no match: {src_fname}')

print()
print('=== Step 2: Update remaining source notes ===')
for src_fname, (target_stub, topic_title) in remaining_updates.items():
    src_path = os.path.join(sources_dir, src_fname)
    if not os.path.exists(src_path):
        print(f'  SKIP (not found): {src_fname}')
        continue
    with open(src_path, encoding='utf-8') as f:
        content = f.read()

    # Find current topic link
    match = re.search(r'\[\[wiki/topics/([^\]|]+)\|([^\]]+)\]\]', content)
    if match:
        current_target = match.group(1)
        current_title = match.group(2)
        new_link = f'[[wiki/topics/{target_stub}|{current_title}]]'
        if current_target != target_stub:
            new_content = content.replace(f'[[wiki/topics/{current_target}|{current_title}]]', new_link)
            with open(src_path, 'w', encoding='utf-8') as f:
                f.write(new_content)
            print(f'  UPDATE: {src_fname} -> {target_stub}')
        else:
            print(f'  ALREADY OK: {src_fname}')

print()
print('=== Summary of expected topic stubs ===')
# List all topic stubs that should exist
expected = [
    'topic-topic-from-2025年创新温州建设十大重大标志性成果出炉.md',
    'topic-topic-from-温州市数据局（市人工智能局）2025年工作总结和2026年工作思路.md',
    'topic-topic-from-关于印发温州市加快人工智能创新发展的若干政策举措（2025—2027年）的通知.md',
    'topic-topic-from-ai-20260510-170640-0.md',
    'topic-topic-from-ai-20260510-170641-0.md',
    'topic-topic-from-ai-21-20260510-170640-0.md',
    'topic-topic-from-gdp-ai-20260510-170640-0.md',
    'topic-topic-from-20260510-170640-0.md',
    'topic-topic-from-20260510-170641-0.md',
]
for e in expected:
    exists = os.path.exists(os.path.join(topics_dir, e))
    print(f'  {"EXISTS" if exists else "MISSING"}: {e}')
