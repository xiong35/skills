"""仅用标准库验证 portable-flat-v1 检查器的行为、命令行及反例。"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from validate_skill import validate


class SkillChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='skill-check-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / 'demo-skill'
        self.root.mkdir()
        self.entry = self.root / 'SKILL.md'
        self.good = '---\nname: demo-skill\ndescription: "处理测量记录；用于核对表格。"\n---\n\n# 核对\n交付实际结果。\n'
        self.entry.write_text(self.good, encoding='utf-8')

    def codes(self, result, kind='errors'):
        return {item['code'] for item in result[kind]}

    def test_minimal_unicode_skill_and_cli_are_read_only(self):
        before = self.entry.read_bytes()
        run = subprocess.run([sys.executable, '-B', str(Path(__file__).with_name('validate_skill.py')),
                              str(self.root)], capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertTrue(json.loads(run.stdout)['ok'])
        self.assertEqual(self.entry.read_bytes(), before)
        self.assertEqual({p.name for p in self.root.iterdir()}, {'SKILL.md'})

    def test_empty_required_values_do_not_pass(self):
        self.entry.write_text('---\nname: ""\ndescription: ""\n---\n内容\n', encoding='utf-8')
        self.assertIn('required', self.codes(validate(self.root)))

    def test_wrong_target_does_not_scan_unrelated_documents(self):
        wrong = self.root / 'other-folder'
        wrong.mkdir()
        (wrong / 'unrelated.md').write_bytes(b'\xff')
        report = validate(wrong)
        self.assertEqual(self.codes(report), {'entry'})
        self.assertEqual(report['local_links_checked'], 0)

    def test_directory_identity_and_names_are_checked(self):
        self.entry.write_text(self.good.replace('name: demo-skill', 'name: other-skill'), encoding='utf-8')
        self.assertIn('directory', self.codes(validate(self.root)))
        self.entry.write_text(self.good.replace('name: demo-skill', 'name: demo--skill'), encoding='utf-8')
        self.assertIn('name', self.codes(validate(self.root)))

    def test_duplicate_keys_are_not_silently_overwritten(self):
        self.entry.write_text(self.good.replace('name: demo-skill', 'name: demo-skill\nname: other'), encoding='utf-8')
        self.assertIn('entry', self.codes(validate(self.root)))

    def test_multiline_or_metadata_report_unsupported_exit_two(self):
        self.entry.write_text(self.good.replace('---\n\n#', 'metadata:\n  version: "1"\n---\n\n#'), encoding='utf-8')
        run = subprocess.run([sys.executable, '-B', str(Path(__file__).with_name('validate_skill.py')),
                              str(self.root)], capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(run.returncode, 2)
        self.assertFalse(json.loads(run.stdout)['ok'])
        self.assertIn('frontmatter-profile', self.codes(validate(self.root), 'unsupported'))
        self.entry.write_text(self.good.replace('description: "处理测量记录；用于核对表格。"',
                                               'description: >\n  Folded content'), encoding='utf-8')
        self.assertFalse(validate(self.root)['ok'])

    def test_malformed_encoding_or_delimiters_fail(self):
        self.entry.write_bytes(b'\xff\xfe')
        self.assertIn('entry', self.codes(validate(self.root)))
        self.entry.write_text('---\nname: demo-skill\n', encoding='utf-8')
        self.assertIn('entry', self.codes(validate(self.root)))

    def test_ambiguous_plain_yaml_is_not_approved(self):
        for value in ('content:', 'content:\titem', '?', 'true', '0.5'):
            with self.subTest(value=value):
                self.entry.write_text(self.good.replace('"处理测量记录；用于核对表格。"', value), encoding='utf-8')
                self.assertFalse(validate(self.root)['ok'])

    def test_missing_real_reference_and_heading_fail(self):
        self.entry.write_text(self.good + '[细节](references/details.md#注意事项)\n', encoding='utf-8')
        self.assertIn('missing-reference', self.codes(validate(self.root)))
        (self.root / 'references').mkdir()
        detail = self.root / 'references/details.md'
        detail.write_text('# 其他内容\n', encoding='utf-8')
        self.assertIn('heading', self.codes(validate(self.root)))
        detail.write_text('# 注意事项\n', encoding='utf-8')
        self.assertTrue(validate(self.root)['ok'])

    def test_reference_definitions_are_checked_but_examples_are_not(self):
        self.entry.write_text(self.good + '\n```markdown\n[example](missing-example.md)\n```\n', encoding='utf-8')
        self.assertTrue(validate(self.root)['ok'])
        self.entry.write_text(self.good + '\n[细节][ref]\n[ref]: missing.md\n', encoding='utf-8')
        self.assertIn('missing-reference', self.codes(validate(self.root)))

    def test_external_policy_needs_explicit_read_root(self):
        outside = Path(self.temp.name) / 'policy.md'
        outside.write_text('# Policy\n', encoding='utf-8')
        self.entry.write_text(self.good + '[政策](../policy.md)\n', encoding='utf-8')
        self.assertIn('reference-scope', self.codes(validate(self.root)))
        self.assertTrue(validate(self.root, [Path(self.temp.name)])['ok'])

    def test_empty_body_and_unfinished_scaffold_fail(self):
        self.entry.write_text(self.good.split('# 核对')[0], encoding='utf-8')
        self.assertIn('body', self.codes(validate(self.root)))
        self.entry.write_text(self.good + '[TODO: fill workflow]\n', encoding='utf-8')
        self.assertIn('scaffold', self.codes(validate(self.root)))

    def test_description_limit_is_checked(self):
        self.entry.write_text(self.good.replace('处理测量记录；用于核对表格。', 'a' * 1025), encoding='utf-8')
        self.assertIn('description', self.codes(validate(self.root)))


if __name__ == '__main__':
    unittest.main()
