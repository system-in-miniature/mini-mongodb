import unittest
from pathlib import Path


class DocumentationHomepageTest(unittest.TestCase):
    def test_homepages_are_language_separated(self) -> None:
        english = Path("docs/index.md").read_text(encoding="utf-8")
        chinese = Path("docs/zh/index.md").read_text(encoding="utf-8")
        self.assertNotRegex(english, r"[\u4e00-\u9fff]")
        self.assertIn("Learning modes", english)
        self.assertIn("学习模式", chinese)

    def test_evidence_package_and_final_stage_are_indexed(self) -> None:
        protocol = Path("bench/PROTOCOL.md").read_text()
        results = Path("bench/results/2026-08-10/results.json").read_text()
        goal = Path("journey/stages/08-executable-domain-labs/goal.md").read_text()
        self.assertNotRegex(protocol, r"[\u4e00-\u9fff]")
        self.assertIn('"work_reduction": 100.0', results)
        self.assertIn("100x", goal)
        self.assertIn("100 倍", Path("README.zh-CN.md").read_text())


if __name__ == "__main__":
    unittest.main()
