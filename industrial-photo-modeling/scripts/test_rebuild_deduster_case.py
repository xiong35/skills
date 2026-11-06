"""验证实际案例在 Git 换行转换后的可重建输入检查。"""
import json
from pathlib import Path
import tempfile
import unittest

from rebuild_deduster_case import CASE, verify_snapshot


class SnapshotTests(unittest.TestCase):
    def make_case(self, directory, ending):
        folder = Path(directory) / 'case'
        folder.mkdir()
        snapshot = json.loads((CASE / 'source-snapshot.json').read_text(encoding='utf-8'))
        (folder / 'source-snapshot.json').write_text(json.dumps(snapshot), encoding='utf-8')
        for item in snapshot['files']:
            data = (CASE / item['file']).read_bytes().replace(b'\r\n', b'\n')
            (folder / item['file']).write_bytes(data.replace(b'\n', ending))
        return folder, snapshot

    def test_actual_sources_accept_lf_and_crlf(self):
        for ending in [b'\n', b'\r\n']:
            with self.subTest(ending=ending), tempfile.TemporaryDirectory() as directory:
                folder, snapshot = self.make_case(directory, ending)
                self.assertEqual(verify_snapshot(folder), snapshot)

    def test_real_content_change_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            folder, _ = self.make_case(directory, b'\n')
            path = folder / 'parameters.json'
            path.write_bytes(path.read_bytes() + b' ')
            with self.assertRaisesRegex(ValueError, 'Snapshot changed'):
                verify_snapshot(folder)

    def test_outside_source_cannot_be_read(self):
        with tempfile.TemporaryDirectory() as directory:
            folder, snapshot = self.make_case(directory, b'\n')
            (Path(directory) / 'outside.py').write_text('pass', encoding='utf-8')
            snapshot['files'][0]['file'] = '../outside.py'
            (folder / 'source-snapshot.json').write_text(json.dumps(snapshot), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'Invalid or missing'):
                verify_snapshot(folder)

    def test_unknown_hash_mode_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            folder, snapshot = self.make_case(directory, b'\n')
            snapshot['hashNormalization'] = 'ignore-all-changes'
            (folder / 'source-snapshot.json').write_text(json.dumps(snapshot), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'Unsupported snapshot'):
                verify_snapshot(folder)


if __name__ == '__main__':
    unittest.main()
