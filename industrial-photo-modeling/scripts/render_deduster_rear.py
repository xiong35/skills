"""在 Blender 中生成完整设备的背面检查图。

独立于已冻结的几何源，不修改网格或材质。
"""
import argparse
import json
from pathlib import Path
import runpy
import sys

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--glb', type=Path, required=True)
    parser.add_argument('--image', type=Path, required=True)
    parser.add_argument('--samples', type=int, default=32)
    parser.add_argument('--draft', action='store_true')
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
    if args.image.exists():
        raise ValueError('Review image already exists; choose a new path.')
    if args.samples < 1:
        raise ValueError('Samples must be positive.')
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(args.glb.resolve()))
    root = bpy.data.objects['MachineRoot']
    vertices = [obj.matrix_world @ vertex.co for obj in root.children_recursive
                if obj.type == 'MESH' for vertex in obj.data.vertices]
    if not vertices:
        raise ValueError('No model vertices to frame.')
    case = Path(__file__).resolve().parents[1] / 'assets/ring-pulsating-deduster-v062'
    api = runpy.run_path(str(case / 'build_model.py'))
    api['setup_render'].__globals__['ROOT'] = root
    camera = api['setup_render'](args.image.parent, args.draft)
    scene = bpy.context.scene
    scene.cycles.samples = args.samples
    scene.cycles.seed = 0
    low = Vector(tuple(min(v[i] for v in vertices) for i in range(3)))
    high = Vector(tuple(max(v[i] for v in vertices) for i in range(3)))
    target = (low + high) / 2
    direction = Vector((-8.3, 12, 4.98)).normalized()
    camera.rotation_euler = (-direction).to_track_quat('-Z', 'Y').to_euler()
    rotation = camera.rotation_euler.to_matrix()
    right, up = rotation @ Vector((1, 0, 0)), rotation @ Vector((0, 1, 0))
    projected = [((v - target).dot(right), (v - target).dot(up)) for v in vertices]
    min_x, max_x = min(v[0] for v in projected), max(v[0] for v in projected)
    min_y, max_y = min(v[1] for v in projected), max(v[1] for v in projected)
    target += right * ((min_x + max_x) / 2) + up * ((min_y + max_y) / 2)
    camera.location = target + direction * 24
    aspect = scene.render.resolution_x / scene.render.resolution_y
    camera.data.ortho_scale = max(max_x - min_x, (max_y - min_y) * aspect) * 1.12
    bpy.context.view_layer.update()
    uv = [world_to_camera_view(scene, camera, v) for v in vertices]
    bounds = {'left': min(p.x for p in uv), 'right': max(p.x for p in uv),
              'bottom': min(p.y for p in uv), 'top': max(p.y for p in uv), 'minDepth': min(p.z for p in uv)}
    if not (0 < bounds['left'] < bounds['right'] < 1 and 0 < bounds['bottom'] < bounds['top'] < 1 and bounds['minDepth'] > 0):
        raise RuntimeError('Model is not fully inside review camera frame.')
    args.image.parent.mkdir(parents=True, exist_ok=True)
    scene.render.filepath = str(args.image.resolve())
    bpy.ops.render.render(write_still=True)
    args.image.with_suffix('.framing.json').write_text(json.dumps({
        'ok': True, 'input': str(args.glb.resolve()), 'verticesChecked': len(vertices),
        'normalizedFrameBounds': bounds, 'camera': list(camera.location), 'target': list(target),
        'orthoScale': camera.data.ortho_scale, 'samples': args.samples,
        'resolution': [scene.render.resolution_x, scene.render.resolution_y],
        'scope': 'Review camera only; geometry/materials/anchors untouched.'}, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
