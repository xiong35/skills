#!/usr/bin/env python3
"""检查自包含 GLB 几何及可配置的项目契约。

仅使用标准库，补充 Khronos Validator 和实际导入、渲染与运行时检查。
本脚本不修改输入资产。
"""
import argparse
import base64
import json
import math
from pathlib import Path
import struct
import sys
from urllib.parse import unquote_to_bytes


class InvalidGLB(ValueError):
    pass


class UnsupportedGLB(InvalidGLB):
    pass


def require(condition, message):
    if not condition:
        raise InvalidGLB(message)


def integer(value, label, minimum=0):
    require(type(value) is int and value >= minimum, f'{label}: invalid integer')
    return value


def reference(items, index, label):
    integer(index, label)
    require(index < len(items), f'{label}: index {index} out of range')
    return items[index]


def finite_json(value, path='json'):
    if isinstance(value, float):
        require(math.isfinite(value), f'{path}: non-finite JSON number')
    elif isinstance(value, dict):
        for key, child in value.items():
            finite_json(child, f'{path}.{key}')
    elif isinstance(value, list):
        for index, child in enumerate(value):
            finite_json(child, f'{path}[{index}]')


def vector(value, size, label):
    require(isinstance(value, list) and len(value) == size, f'{label}: expected {size} components')
    require(all(type(v) in (int, float) and math.isfinite(v) for v in value), f'{label}: invalid components')
    return value


def unit_interval(value, label):
    require(type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 1,
            f'{label}: must be finite and within [0, 1]')


def data_uri(uri, label):
    require(isinstance(uri, str) and uri.startswith('data:'), f'{label}: external resource is not self-contained')
    require(',' in uri, f'{label}: malformed data URI')
    header, encoded = uri.split(',', 1)
    try:
        return base64.b64decode(encoded, validate=True) if header.endswith(';base64') else unquote_to_bytes(encoded)
    except (ValueError, base64.binascii.Error) as exc:
        raise InvalidGLB(f'{label}: invalid embedded data') from exc


def read_glb(path):
    raw = Path(path).read_bytes()
    require(len(raw) >= 20, 'GLB header/JSON chunk is truncated')
    magic, version, length = struct.unpack_from('<4sII', raw)
    require(magic == b'glTF' and version == 2, 'not a GLB 2.0 container')
    require(length == len(raw), 'header length does not match file size')
    chunks, offset = [], 12
    while offset < length:
        require(offset + 8 <= length, 'truncated chunk header')
        size, kind = struct.unpack_from('<II', raw, offset)
        require(size % 4 == 0 and offset + 8 + size <= length, 'invalid chunk alignment/length')
        chunks.append((kind, raw[offset + 8:offset + 8 + size]))
        offset += 8 + size
    require(chunks and chunks[0][0] == 0x4E4F534A, 'first chunk must be JSON')
    require(sum(kind == 0x4E4F534A for kind, _ in chunks) == 1, 'duplicate JSON chunk')
    bins = [payload for kind, payload in chunks if kind == 0x004E4942]
    require(len(bins) <= 1, 'duplicate BIN chunk')
    if bins:
        require(len(chunks) > 1 and chunks[1][0] == 0x004E4942, 'BIN must follow JSON')
    try:
        doc = json.loads(chunks[0][1].decode('utf-8'))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise InvalidGLB('invalid UTF-8 JSON chunk') from exc
    require(isinstance(doc, dict), 'JSON root must be an object')
    finite_json(doc)
    require(doc.get('asset', {}).get('version') == '2.0', 'asset.version must be 2.0')
    return doc, bins[0] if bins else None, len(raw)


class Inspector:
    COMPONENTS = {5120: ('b', 1), 5121: ('B', 1), 5122: ('h', 2),
                  5123: ('H', 2), 5125: ('I', 4), 5126: ('f', 4)}
    SHAPES = {'SCALAR': (1, 1), 'VEC2': (1, 2), 'VEC3': (1, 3), 'VEC4': (1, 4),
              'MAT2': (2, 2), 'MAT3': (3, 3), 'MAT4': (4, 4)}

    def __init__(self, doc, binary):
        self.doc, self.buffers, self.cache = doc, [], {}
        for key in ('buffers', 'bufferViews', 'accessors', 'nodes', 'meshes', 'materials', 'images', 'textures', 'scenes'):
            require(isinstance(doc.get(key, []), list), f'{key}: expected array')
        used = doc.get('extensionsUsed', [])
        if any(name in used for name in ('KHR_draco_mesh_compression', 'EXT_meshopt_compression')):
            raise UnsupportedGLB('compressed geometry requires a decoder; this checker cannot certify it')
        for index, item in enumerate(doc.get('buffers', [])):
            size = integer(item.get('byteLength'), f'buffers[{index}].byteLength', 1)
            if 'uri' in item:
                payload = data_uri(item['uri'], f'buffers[{index}]')
            else:
                require(index == 0 and binary is not None, 'only buffer 0 may use the BIN chunk')
                payload = binary
                require(len(payload) - size <= 3, 'BIN padding exceeds three bytes')
            require(len(payload) >= size, f'buffers[{index}]: truncated payload')
            self.buffers.append(payload[:size])
        for index, item in enumerate(doc.get('bufferViews', [])):
            payload = reference(self.buffers, item.get('buffer'), f'bufferViews[{index}].buffer')
            offset = integer(item.get('byteOffset', 0), 'bufferView.byteOffset')
            size = integer(item.get('byteLength'), 'bufferView.byteLength', 1)
            require(offset + size <= len(payload), f'bufferViews[{index}]: outside buffer')
            if 'byteStride' in item:
                stride = integer(item['byteStride'], 'bufferView.byteStride', 4)
                require(stride <= 252 and stride % 4 == 0, 'invalid bufferView.byteStride')

    def elements(self, view_index, offset, count, component, shape, packed=False):
        view = reference(self.doc.get('bufferViews', []), view_index, 'accessor.bufferView')
        require(component in self.COMPONENTS and shape in self.SHAPES, 'invalid accessor component/type')
        fmt, size = self.COMPONENTS[component]
        columns, rows = self.SHAPES[shape]
        column_size = ((rows * size + 3) // 4) * 4 if columns > 1 else rows * size
        element_size = columns * column_size
        stride = element_size if packed else view.get('byteStride', element_size)
        integer(offset, 'accessor.byteOffset')
        require(offset % size == 0 and view.get('byteOffset', 0) % size == 0, 'misaligned accessor')
        require(stride >= element_size and stride % size == 0, 'accessor stride overlaps elements')
        require(offset + (count - 1) * stride + element_size <= view['byteLength'], 'accessor exceeds bufferView')
        payload = self.buffers[view['buffer']]
        start = view.get('byteOffset', 0) + offset
        offsets = [column * column_size + row * size for column in range(columns) for row in range(rows)]
        result = []
        for index in range(count):
            values = tuple(struct.unpack_from('<' + fmt, payload, start + index * stride + pos)[0] for pos in offsets)
            require(all(math.isfinite(v) for v in values), 'non-finite binary accessor value')
            result.append(values)
        return result

    def accessor(self, index):
        if index in self.cache:
            return self.cache[index]
        item = reference(self.doc.get('accessors', []), index, 'accessor')
        count = integer(item.get('count'), f'accessors[{index}].count', 1)
        require(count <= 10000000, 'accessor exceeds this checker inspection budget (10 million elements)')
        component, shape = item.get('componentType'), item.get('type')
        require(component in self.COMPONENTS and shape in self.SHAPES, 'invalid accessor component/type')
        require(not item.get('normalized') or component not in (5125, 5126), 'invalid normalized accessor type')
        if 'bufferView' in item:
            values = self.elements(item['bufferView'], item.get('byteOffset', 0), count, component, shape)
        else:
            require(item.get('byteOffset', 0) == 0, 'accessor without bufferView has byteOffset')
            columns, rows = self.SHAPES[shape]
            values = [(0,) * (columns * rows)] * count
        if 'sparse' in item:
            sparse = item['sparse']
            n = integer(sparse.get('count'), 'sparse.count', 1)
            require(n <= count, 'sparse count exceeds accessor count')
            indices = sparse['indices']
            require(indices.get('componentType') in (5121, 5123, 5125), 'invalid sparse index type')
            slots = self.elements(indices['bufferView'], indices.get('byteOffset', 0), n, indices['componentType'], 'SCALAR', True)
            replacement = sparse['values']
            data = self.elements(replacement['bufferView'], replacement.get('byteOffset', 0), n, component, shape, True)
            previous = -1
            for (slot,), row in zip(slots, data):
                require(previous < slot < count, 'sparse indices must increase and remain in range')
                values[slot] = row
                previous = slot
        self.cache[index] = values
        return values

    def geometry(self):
        triangles = 0
        for index in range(len(self.doc.get('accessors', []))):
            self.accessor(index)
        for mesh_index, mesh in enumerate(self.doc.get('meshes', [])):
            require(mesh.get('primitives'), f'meshes[{mesh_index}]: no primitives')
            for primitive in mesh['primitives']:
                attributes = primitive.get('attributes', {})
                require('POSITION' in attributes, 'mesh primitive has no POSITION accessor')
                position_id = attributes['POSITION']
                position = reference(self.doc['accessors'], position_id, 'POSITION')
                require(position['type'] == 'VEC3', 'POSITION is not VEC3')
                count = len(self.accessor(position_id))
                for attribute_id in attributes.values():
                    require(len(self.accessor(attribute_id)) == count, 'primitive attribute counts differ')
                if 'indices' in primitive:
                    item = reference(self.doc['accessors'], primitive['indices'], 'primitive.indices')
                    require(item['type'] == 'SCALAR' and item['componentType'] in (5121, 5123, 5125) and not item.get('normalized'), 'invalid index accessor')
                    indices = self.accessor(primitive['indices'])
                    require(all(0 <= value[0] < count for value in indices), 'primitive index outside vertex range')
                    count = len(indices)
                mode = primitive.get('mode', 4)
                require(type(mode) is int and 0 <= mode <= 6, 'invalid primitive mode')
                if mode == 4:
                    require(count % 3 == 0, 'TRIANGLES element count is not divisible by three')
                    triangles += count // 3
                elif mode in (5, 6):
                    require(count >= 3, 'triangle strip/fan has fewer than three vertices')
                    triangles += count - 2
                if 'material' in primitive:
                    reference(self.doc.get('materials', []), primitive['material'], 'primitive.material')
                for target in primitive.get('targets', []):
                    for accessor_id in target.values():
                        require(len(self.accessor(accessor_id)) == len(self.accessor(position_id)), 'morph target count differs')
        return triangles

    def nodes(self):
        nodes = self.doc.get('nodes', [])
        parents = {}
        for index, node in enumerate(nodes):
            if 'mesh' in node:
                reference(self.doc.get('meshes', []), node['mesh'], 'node.mesh')
            for key, size in [('translation', 3), ('rotation', 4), ('scale', 3), ('matrix', 16)]:
                if key in node:
                    vector(node[key], size, f'nodes[{index}].{key}')
            require(not ('matrix' in node and any(key in node for key in ('translation', 'rotation', 'scale'))), 'node mixes matrix and TRS')
            if 'rotation' in node:
                require(abs(sum(v*v for v in node['rotation']) - 1) < .001, 'node rotation quaternion is not normalized')
            for child in node.get('children', []):
                reference(nodes, child, 'node.children')
                require(child not in parents, 'node has multiple parents or duplicate child reference')
                parents[child] = index
        active, visited = set(), set()
        def visit(index):
            require(index not in active, 'node hierarchy contains a cycle')
            if index in visited:
                return
            active.add(index)
            for child in nodes[index].get('children', []):
                visit(child)
            active.remove(index)
            visited.add(index)
        for index in range(len(nodes)):
            visit(index)
        for scene in self.doc.get('scenes', []):
            for index in scene.get('nodes', []):
                reference(nodes, index, 'scene.nodes')
                require(index not in parents, 'scene references a non-root node')
        if 'scene' in self.doc:
            reference(self.doc.get('scenes', []), self.doc['scene'], 'scene')

    def resources_materials(self):
        for index, image in enumerate(self.doc.get('images', [])):
            require(('uri' in image) != ('bufferView' in image), f'images[{index}]: expected one embedded source')
            if 'uri' in image:
                require(bool(data_uri(image['uri'], f'images[{index}]')), 'empty embedded image')
            else:
                reference(self.doc.get('bufferViews', []), image['bufferView'], 'image.bufferView')
                require(isinstance(image.get('mimeType'), str), 'bufferView image requires mimeType')
        for texture in self.doc.get('textures', []):
            if 'source' in texture:
                reference(self.doc.get('images', []), texture['source'], 'texture.source')
            for extension in texture.get('extensions', {}).values():
                if isinstance(extension, dict) and 'source' in extension:
                    reference(self.doc.get('images', []), extension['source'], 'texture extension source')
        for index, material in enumerate(self.doc.get('materials', [])):
            pbr = material.get('pbrMetallicRoughness', {})
            for value in vector(pbr.get('baseColorFactor', [1, 1, 1, 1]), 4, 'baseColorFactor'):
                unit_interval(value, 'baseColorFactor')
            for key in ('metallicFactor', 'roughnessFactor'):
                unit_interval(pbr.get(key, 1), key)
            def texture_refs(obj):
                if isinstance(obj, dict):
                    for key, value in obj.items():
                        if key.endswith('Texture') and isinstance(value, dict) and 'index' in value:
                            reference(self.doc.get('textures', []), value['index'], f'materials[{index}].{key}')
                        texture_refs(value)
                elif isinstance(obj, list):
                    for child in obj:
                        texture_refs(child)
            texture_refs(material)

    def contract(self, contract, triangles):
        nodes, materials = self.doc.get('nodes', []), self.doc.get('materials', [])
        def node_index(name):
            matches = [i for i, node in enumerate(nodes) if node.get('name') == name]
            require(len(matches) == 1, f'required node {name!r}: expected once, found {len(matches)}')
            return matches[0]
        for name in contract.get('required_nodes', []) + contract.get('anchors', []):
            node_index(name)
        require(triangles >= contract.get('min_triangles', 0), 'triangle count below contract minimum')
        require(triangles <= contract.get('max_triangles', math.inf), 'triangle count exceeds contract maximum')
        for name, expected in contract.get('materials', {}).items():
            matches = [m for m in materials if m.get('name') == name]
            require(len(matches) == 1, f'required material {name!r}: expected once, found {len(matches)}')
            actual = matches[0].get('pbrMetallicRoughness', {})
            expected = dict(expected)
            if 'baseColorSRGB' in expected:
                color = expected.pop('baseColorSRGB')
                require(isinstance(color, str) and len(color) == 7 and color.startswith('#'), 'baseColorSRGB requires #rrggbb')
                channels = [int(color[i:i+2], 16)/255 for i in (1, 3, 5)]
                expected['baseColorFactor'] = [v/12.92 if v <= .04045 else ((v+.055)/1.055)**2.4 for v in channels] + [1]
            for key, value in expected.items():
                found = actual.get(key, [1, 1, 1, 1] if key == 'baseColorFactor' else 1)
                left, right = (found, value) if isinstance(value, list) else ([found], [value])
                require(len(left) == len(right) and all(abs(a-b) <= .00001 for a, b in zip(left, right)), f'material {name!r} differs at {key}')
        shared = set(contract.get('allowed_shared_materials', []))
        used_groups = {}
        def collect(index):
            node = nodes[index]
            found = set()
            if 'mesh' in node:
                for primitive in self.doc['meshes'][node['mesh']]['primitives']:
                    material_id = primitive.get('material')
                    if material_id is not None and materials[material_id].get('name') not in shared:
                        found.add(material_id)
            for child in node.get('children', []):
                found.update(collect(child))
            return found
        for name in contract.get('independent_paint_groups', []):
            used = collect(node_index(name))
            require(bool(used), f'paint group {name!r} has no independent materials')
            for previous, previous_used in used_groups.items():
                require(not used.intersection(previous_used), f'paint groups {previous!r} and {name!r} share materials')
            used_groups[name] = used


def inspect(path, contract=None):
    doc, binary, size = read_glb(path)
    inspector = Inspector(doc, binary)
    inspector.resources_materials()
    inspector.nodes()
    triangles = inspector.geometry()
    inspector.contract(contract or {}, triangles)
    return {'ok': True, 'bytes': size, 'triangles': triangles, 'nodes': len(doc.get('nodes', [])),
            'meshes': len(doc.get('meshes', [])), 'materials': len(doc.get('materials', [])),
            'materialNames': [item.get('name', '') for item in doc.get('materials', [])],
            'checkedAnchors': (contract or {}).get('anchors', []), 'embeddedResources': True,
            'extensionsUsed': doc.get('extensionsUsed', []),
            'scope': 'structural asset/contract check; visual fidelity and runtime monitoring require separate verification'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('glb', type=Path)
    parser.add_argument('--contract', type=Path)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    code = 0
    try:
        contract = json.loads(args.contract.read_text(encoding='utf-8-sig')) if args.contract else None
        require(contract is None or isinstance(contract, dict), 'contract must be a JSON object')
        if contract:
            finite_json(contract, 'contract')
        report = inspect(args.glb, contract)
    except UnsupportedGLB as exc:
        report, code = {'ok': False, 'unsupported': str(exc)}, 2
    except (InvalidGLB, OSError, ValueError, KeyError, TypeError, struct.error, RecursionError) as exc:
        report, code = {'ok': False, 'error': str(exc)}, 1
    output = json.dumps(report, ensure_ascii=True, indent=2)
    if args.report:
        require(args.report.resolve() != args.glb.resolve(), 'report path must not overwrite GLB')
        args.report.write_text(output + '\n', encoding='utf-8')
    print(output)
    return code


if __name__ == '__main__':
    sys.exit(main())
