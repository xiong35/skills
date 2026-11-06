#!/usr/bin/env python3
"""使用小型生成资产验证 check_glb 的实际行为，不依赖额外包。"""
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

from check_glb import inspect, InvalidGLB, UnsupportedGLB


def fixture():
    payload = struct.pack('<9f', 0, 0, 0, 1, 0, 0, 0, 1, 0) + struct.pack('<3H', 0, 1, 2)
    doc = {'asset': {'version': '2.0'}, 'buffers': [{'byteLength': len(payload)}],
           'bufferViews': [{'buffer': 0, 'byteLength': 36}, {'buffer': 0, 'byteOffset': 36, 'byteLength': 6}],
           'accessors': [{'bufferView': 0, 'componentType': 5126, 'count': 3, 'type': 'VEC3'},
                         {'bufferView': 1, 'componentType': 5123, 'count': 3, 'type': 'SCALAR'}],
           'materials': [{'name': 'paint', 'pbrMetallicRoughness': {'baseColorFactor': [1, 0, 0, 1],
                           'metallicFactor': .7, 'roughnessFactor': .4}}],
           'meshes': [{'primitives': [{'attributes': {'POSITION': 0}, 'indices': 1, 'material': 0}]}],
           'nodes': [{'name': 'Machine', 'mesh': 0, 'children': [1]}, {'name': 'Anchor_end'}],
           'scenes': [{'nodes': [0]}], 'scene': 0}
    return doc, payload


def encode(doc, payload):
    text = json.dumps(doc, separators=(',', ':')).encode('utf-8')
    text += b' ' * (-len(text) % 4)
    payload += b'\0' * (-len(payload) % 4)
    body = struct.pack('<II', len(text), 0x4E4F534A) + text
    body += struct.pack('<II', len(payload), 0x004E4942) + payload
    return struct.pack('<4sII', b'glTF', 2, len(body) + 12) + body


class GLBChecks(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='photo-model-glb-')
        self.folder = Path(self.temporary.name)
        self.doc, self.payload = fixture()

    def tearDown(self):
        self.temporary.cleanup()

    def asset(self, doc=None, payload=None):
        path = self.folder / 'asset.glb'
        path.write_bytes(encode(self.doc if doc is None else doc, self.payload if payload is None else payload))
        return path

    def test_valid_geometry_and_configurable_contract(self):
        result = inspect(self.asset(), {'anchors': ['Anchor_end'], 'required_nodes': ['Machine'],
                        'max_triangles': 2, 'materials': {'paint': {'baseColorSRGB': '#ff0000'}}})
        self.assertEqual(result['triangles'], 1)
        self.assertEqual(result['nodes'], 2)

    def test_bad_header_cli_exits_nonzero(self):
        path = self.folder / 'invalid.glb'
        path.write_bytes(b'not-a-glb')
        result = subprocess.run([sys.executable, str(Path(__file__).with_name('check_glb.py')), str(path)],
                                capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 1)
        self.assertFalse(json.loads(result.stdout)['ok'])

    def test_declared_length_mismatch(self):
        path = self.asset()
        path.write_bytes(path.read_bytes()[:-1])
        with self.assertRaisesRegex(InvalidGLB, 'length'):
            inspect(path)

    def test_binary_nan_rejected(self):
        data = struct.pack('<f', float('nan')) + self.payload[4:]
        with self.assertRaisesRegex(InvalidGLB, 'non-finite binary'):
            inspect(self.asset(payload=data))

    def test_vertex_index_range_rejected(self):
        data = self.payload[:36] + struct.pack('<3H', 0, 1, 99)
        with self.assertRaisesRegex(InvalidGLB, 'vertex range'):
            inspect(self.asset(payload=data))

    def test_accessor_out_of_bounds_rejected(self):
        self.doc['accessors'][0]['count'] = 4
        with self.assertRaisesRegex(InvalidGLB, 'exceeds bufferView'):
            inspect(self.asset())

    def test_external_resource_rejected(self):
        self.doc['images'] = [{'uri': 'company-texture.png'}]
        with self.assertRaisesRegex(InvalidGLB, 'external resource'):
            inspect(self.asset())

    def test_missing_duplicate_anchor_and_wrong_material_rejected(self):
        path = self.asset()
        for contract in [{'anchors': ['missing']}, {'materials': {'paint': {'roughnessFactor': .8}}}, {'max_triangles': 0}]:
            with self.subTest(contract=contract), self.assertRaises(InvalidGLB):
                inspect(path, contract)
        self.doc['nodes'].append({'name': 'Anchor_end'})
        with self.assertRaisesRegex(InvalidGLB, 'expected once'):
            inspect(self.asset(), {'anchors': ['Anchor_end']})

    def test_cycle_rejected(self):
        self.doc['nodes'][1]['children'] = [0]
        with self.assertRaisesRegex(InvalidGLB, 'cycle'):
            inspect(self.asset())

    def test_independent_paint_contract_rejects_shared_material(self):
        self.doc['nodes'][0]['children'].append(2)
        self.doc['nodes'].append({'name': 'Second', 'mesh': 0})
        with self.assertRaisesRegex(InvalidGLB, 'share materials'):
            inspect(self.asset(), {'independent_paint_groups': ['Machine', 'Second']})

    def test_compressed_asset_is_not_misreported_as_checked(self):
        self.doc['extensionsUsed'] = ['KHR_draco_mesh_compression']
        with self.assertRaises(UnsupportedGLB):
            inspect(self.asset())

    def test_interleaved_vertices(self):
        self.doc['bufferViews'][0]['byteStride'] = 16
        self.doc['bufferViews'][0]['byteLength'] = 48
        self.doc['bufferViews'][1]['byteOffset'] = 48
        data = b''.join(struct.pack('<4f', *vertex, 42) for vertex in [(0, 0, 0), (1, 0, 0), (0, 1, 0)])
        data += struct.pack('<3H', 0, 1, 2)
        self.doc['buffers'][0]['byteLength'] = len(data)
        self.assertEqual(inspect(self.asset(payload=data))['triangles'], 1)

    def test_sparse_accessor_values_are_read_and_checked(self):
        # 稀疏替换会移动顶点 1，其数值也必须为有限值。
        self.doc['bufferViews'].extend([{'buffer': 0, 'byteOffset': 42, 'byteLength': 1},
                                       {'buffer': 0, 'byteOffset': 44, 'byteLength': 12}])
        self.doc['accessors'][0]['sparse'] = {'count': 1,
            'indices': {'bufferView': 2, 'componentType': 5121},
            'values': {'bufferView': 3}}
        data = self.payload + b'\1\0' + struct.pack('<3f', 2, 0, 0)
        self.doc['buffers'][0]['byteLength'] = len(data)
        self.assertTrue(inspect(self.asset(payload=data))['ok'])
        data = data[:-12] + struct.pack('<3f', float('nan'), 0, 0)
        with self.assertRaisesRegex(InvalidGLB, 'non-finite binary'):
            inspect(self.asset(payload=data))


if __name__ == '__main__':
    unittest.main()
