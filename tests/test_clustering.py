import unittest
from pathlib import Path

from core.clustering import ClusterInput, cluster_inputs


ROOT = Path(__file__).resolve().parents[1]


class DynamicClusteringTests(unittest.TestCase):
    def test_clusters_without_fixed_theme_rules(self):
        source = (ROOT / "scripts" / "personal_kb_steward.py").read_text(encoding="utf-8")
        self.assertNotIn("THEME_RULES", source)
        self.assertNotIn("classify_theme", source)

    def test_dynamic_cluster_uses_current_inputs(self):
        clusters, low = cluster_inputs([
            ClusterInput("quicknote/a.md", "Cursor 课堂演示", "用 Cursor 做 AI 编程课堂 demo"),
            ClusterInput("quicknote/b.md", "Cursor 项目复盘", "Cursor 帮助重构脚本和测试"),
            ClusterInput("quicknote/c.md", "地方媒体案例", "地方媒体 AI 使用出现流程问题"),
        ], max_clusters=3)
        self.assertGreaterEqual(len(clusters), 1)
        self.assertLessEqual(len(clusters), 3)
        all_sources = {src for cluster in clusters for src in cluster["sources"]}
        self.assertIn("quicknote/a.md", all_sources)
        self.assertIsInstance(low, list)


if __name__ == "__main__":
    unittest.main()
