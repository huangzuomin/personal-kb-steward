"""Fix broken links between source notes and topic stubs.
Strategy:
  - For 3 matched sources: rename topic stubs to expected filenames + update source notes
  - For 7 unmatched sources: update source notes to link to existing stubs (best effort)
"""
import os, re, shutil

topics_dir = r'C:\Users\zooma\.qclaw\workspace\wiki\wiki\topics'
sources_dir = r'C:\Users\zooma\.qclaw\workspace\wiki\wiki\sources'

# Mapping: source file -> (expected topic filename, actual stub filename)
# Only for the 3 sources that have matching topic stubs
matched_renames = {
    'source-2025.md': (
        'topic-topic-from-2025年创新温州建设十大重大标志性成果出炉.md',
        'topic-topic-from-2025-20260510-170640-0.md'
    ),
    'source-2025-2026.md': (
        'topic-topic-from-温州市数据局（市人工智能局）2025年工作总结和2026年工作思路.md',
        'topic-topic-from-2025-2026-20260510-170641-0.md'
    ),
    'source-2025-2027.md': (
        'topic-topic-from-关于印发温州市加快人工智能创新发展的若干政策举措（2025—2027年）的通知.md',
        'topic-topic-from-2025-2027-20260510-170640-0.md'
    ),
}

# For 7 unmatched sources: link to best available stubs
# source-topic-0240252e12.md -> topic-topic-from-支持人工智能创新发展，温州有这些动作！_腾讯新闻.md
#   content: "支持人工智能创新发展，温州有这些动作！_腾讯新闻" -> topic-topic-from-20260510-170640-0.md
# source-topic-7ff881a931.md -> topic-topic-from-人工智能浪潮袭来-看温州释放创新蓬勃动力_新温州_中国网.md
#   content: "人工智能浪潮袭来..." -> topic-topic-from-20260510-170641-0.md
# source-ai-21.md -> topic-topic-from-新晋万亿之城进击ai，"斜杠青年"温州下一站---21经济网.md
#   content: "新晋万亿之城进击AI..." -> topic-topic-from-ai-21-20260510-170640-0.md
# source-ai.md -> topic-topic-from-温州市成立国内首家人工智能局... -> topic-topic-from-ai-20260510-170640-0.md
# source-gdp-ai.md -> topic-topic-from-冲刺万亿gdp的温州-全面注入ai动能.md -> topic-topic-from-gdp-ai-20260510-170640-0.md
# source-topic-b8643c30be.md -> topic-topic-from-市政府党组会议召开.md -> topic-topic-from-ai-20260510-170641-0.md
# source-topic-c8f00a2569.md -> topic-topic-from-求是思享汇- -> NO MATCH, use gdp-ai stub
# source-topic-dc15ef1ed0.md -> topic-topic-from-温州市揭牌成立全省首个人工智能局... -> topic-topic-from-ai-20260510-170641-0.md
# source-topic-ee44903047.md -> topic-topic-from-全国首个"人工智能局"挂牌成立... -> topic-topic-from-ai-20260510-170641-0.md
# source-topic-3273484d48.md -> topic-topic-from-温州市国民经济和社会发展第十五个年规划纲要.md -> topic-topic-from-2025-2027-20260510-170640-0.md

best_effort_links = {
    'source-topic-0240252e12.md': 'topic-topic-from-20260510-170640-0.md',
    'source-topic-7ff881a931.md': 'topic-topic-from-20260510-170641-0.md',
    'source-ai-21.md': 'topic-topic-from-ai-21-20260510-170640-0.md',
    'source-ai.md': 'topic-topic-from-ai-20260510-170640-0.md',
    'source-gdp-ai.md': 'topic-topic-from-gdp-ai-20260510-170640-0.md',
    'source-topic-b8643c30be.md': 'topic-topic-from-ai-20260510-170641-0.md',
    'source-topic-c8f00a2569.md': 'topic-topic-from-gdp-ai-20260510-170640-0.md',
    'source-topic-dc15ef1ed0.md': 'topic-topic-from-ai-20260510-170641-0.md',
    'source-topic-ee44903047.md': 'topic-topic-from-ai-20260510-170641-0.md',
    'source-topic-3273484d48.md': 'topic-topic-from-2025-2027-20260510-170640-0.md',
}

changes = []

# Step 1: Rename topic stubs for matched sources
print('=== Step 1: Renaming topic stubs ===')
for src_fname, (expected_topic, actual_stub) in matched_renames.items():
    old_path = os.path.join(topics_dir, actual_stub)
    new_path = os.path.join(topics_dir, expected_topic)
    if os.path.exists(old_path) and not os.path.exists(new_path):
        shutil.move(old_path, new_path)
        print(f'RENAME: {actual_stub} -> {expected_topic}')
        changes.append(('rename_topic', actual_stub, expected_topic))
    elif os.path.exists(new_path):
        print(f'SKIP (already exists): {expected_topic}')
    else:
        print(f'SKIP (source not found): {old_path}')

# Step 2: Update source notes to link to correct topic stub filenames
print()
print('=== Step 2: Updating source notes ===')

# For matched sources: update the link in the "提取的专题" section
for src_fname, (expected_topic, actual_stub) in matched_renames.items():
    src_path = os.path.join(sources_dir, src_fname)
    if not os.path.exists(src_path):
        continue
    with open(src_path, encoding='utf-8') as f:
        content = f.read()

    # Find and replace the broken topic link
    # Pattern: [[wiki/topics/topic-topic-from-{OLD_TOPIC_TITLE}.md|...]]
    old_link_pattern = re.search(r'\[\[wiki/topics/[^\]]+\|', content)
    if old_link_pattern:
        # Replace with new link
        new_link = f'[[wiki/topics/{expected_topic}|Topic from {expected_topic[18:-4]}]]'
        new_content = re.sub(r'\[\[wiki/topics/[^\]]+\|Topic from [^\]]+\]\]', new_link, content)
        with open(src_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print(f'UPDATE SOURCE: {src_fname} -> links to {expected_topic}')
        changes.append(('update_source', src_fname, expected_topic))

# For unmatched sources: update links to best available stubs
for src_fname, target_stub in best_effort_links.items():
    src_path = os.path.join(sources_dir, src_fname)
    if not os.path.exists(src_path):
        continue
    with open(src_path, encoding='utf-8') as f:
        content = f.read()

    # Find the current broken topic link
    old_match = re.search(r'\[\[wiki/topics/([^\]|]+)\|([^\]]+)\]\]', content)
    if old_match:
        old_target = old_match.group(1)
        topic_title = old_match.group(2)
        new_link = f'[[wiki/topics/{target_stub}|{topic_title}]]'
        new_content = content.replace(f'[[wiki/topics/{old_target}|{topic_title}]]', new_link)
        with open(src_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
        print(f'UPDATE SOURCE (best effort): {src_fname} -> {target_stub}')
        changes.append(('update_source_be', src_fname, target_stub))

print()
print(f'Total changes: {len(changes)}')
for c in changes:
    print(f'  {c}')
