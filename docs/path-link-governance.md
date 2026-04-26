# Path And Wikilink Governance

Phase 4 统一路径与 Obsidian 双链规则。

## 规则

- 所有内部路径都以知识库根目录为基准。
- 双链必须指向真实存在的文件。
- 双链必须使用规范相对路径，例如 `[[wiki/topics/xxx.md]]`。
- 不允许写 `[[topics/xxx]]`、`[[seeds/xxx]]` 这类省略 `wiki/` 的路径。
- 不存在的页面不得伪造成双链。

## 待创建链接

如果目标页面尚不存在，正文应写：

```markdown
## 待创建链接

- concepts/Patch实验.md
- topics/AI与新闻业.md
```

不要写：

```markdown
- [[concepts/Patch实验.md]]
- [[topics/AI与新闻业]]
```

## 运行时约束

`scripts/personal_kb_steward.py` 提供：

- `safe_wikilink(index, target)`：只有目标可解析时才生成 `[[...]]`。
- `safe_link_list(index, items)`：批量生成安全双链。
- `pending_link(target)`：目标不存在时写成 `待创建：target`。

## lint 输出

- `broken_links`：无法解析的双链。
- `noncanonical_links`：能解析，但写法不是规范相对路径的双链。

历史断链和非规范链接不自动修复，应进入 plan/apply 或人工确认流程。
