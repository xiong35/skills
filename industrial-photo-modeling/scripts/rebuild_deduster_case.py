"""在新的输出目录重建包内已验收的 0.6.2 模型。

仅使用 Python 标准库，由调用者指定已有 Blender，不自动安装。
从源代码生成几何，不将已有 GLB 或 .blend 作为输入。
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

SKILL = Path(__file__).resolve().parents[1]
CASE = SKILL / 'assets/ring-pulsating-deduster-v062'


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def verify_snapshot(folder):
    """按 LF 规范化文本指纹，兼容 Git 在不同系统上的换行转换。"""
    case = Path(folder).resolve()
    snapshot = read_json(case / 'source-snapshot.json')
    if snapshot.get('hashNormalization') != 'utf8-lf':
        raise ValueError('Unsupported snapshot hash normalization')
    for item in snapshot['files']:
        source = (case / item['file']).resolve()
        if source.parent != case or not source.is_file():
            raise ValueError('Invalid or missing case file: ' + item['file'])
        digest = hashlib.sha256(source.read_bytes().replace(b'\r\n', b'\n')).hexdigest()
        if digest != item['sha256']:
            raise ValueError('Snapshot changed: ' + item['file'] + '. Reassess and version the case before claiming reproduction.')
    return snapshot


def compare_json(expected, actual, path='$'):
    """仅容许浮点舍入误差，键、名称与顺序必须一致。"""
    if isinstance(expected, dict) and isinstance(actual, dict):
        if expected.keys() != actual.keys():
            raise ValueError(f'{path}: different keys')
        for key, value in expected.items():
            compare_json(value, actual[key], path + '.' + key)
    elif isinstance(expected, list) and isinstance(actual, list):
        if len(expected) != len(actual):
            raise ValueError(f'{path}: different lengths')
        for index, (left, right) in enumerate(zip(expected, actual)):
            compare_json(left, right, f'{path}[{index}]')
    elif (type(expected) in (int, float) and type(actual) in (int, float)):
        if not (math.isfinite(actual) and abs(expected - actual) <= 1e-5):
            raise ValueError(f'{path}: numeric mismatch {expected!r} / {actual!r}')
    elif type(expected) is not type(actual) or expected != actual:
        raise ValueError(f'{path}: value mismatch')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--blender', required=True, help='Existing Blender executable or PATH command')
    parser.add_argument('--out', required=True, help='New, nonexistent output directory; never a project asset folder')
    parser.add_argument('--render', action='store_true')
    parser.add_argument('--draft', action='store_true', help='1000x700 preview instead of 1600x1000')
    parser.add_argument('--shots', default='front,rear,gearbox-rear,gearbox-side,circular-housing,motor-front')
    parser.add_argument('--samples', type=int, default=32)
    args = parser.parse_args()
    out = Path(args.out).resolve()
    if out.exists():
        parser.error('Output already exists. Choose a new directory; existing artifacts will not be replaced.')
    if out == SKILL or SKILL in out.parents or out in SKILL.parents:
        parser.error('Output must be separate from the Skill source.')
    if args.samples < 1:
        parser.error('Samples must be positive.')
    executable = shutil.which(args.blender)
    if not executable:
        parser.error('Blender was not found. Supply an existing executable; this tool does not install one.')
    try:
        snapshot = verify_snapshot(CASE)
    except (OSError, ValueError, KeyError) as error:
        parser.error(str(error))
    allowed_shots = {'front', 'rear', 'gearbox-rear', 'gearbox-front', 'rear-orthographic', 'platform',
                     'motor-rear', 'motor-front', 'gearbox-side', 'circular-inlet', 'circular-housing'}
    if not set(args.shots.split(',')) <= allowed_shots:
        parser.error('Unsupported render view.')
    out.mkdir(parents=True)
    logs = out / 'logs'
    logs.mkdir()
    runtime = out / 'runtime'
    env = os.environ.copy()
    env.update({'PYTHONDONTWRITEBYTECODE': '1', 'PYTHONUTF8': '1'})
    for key, folder in [('BLENDER_USER_CONFIG', 'config'), ('BLENDER_USER_SCRIPTS', 'scripts'),
                        ('BLENDER_USER_DATAFILES', 'datafiles'), ('TEMP', 'temp'), ('TMP', 'temp')]:
        destination = runtime / folder
        destination.mkdir(parents=True, exist_ok=True)
        env[key] = str(destination)
    result = {'ok': False, 'caseVersion': snapshot['caseVersion'], 'commands': [],
              'input': 'Bundled source snapshot and parameters only; no existing binary model.',
              'limits': snapshot['limits']}

    def run(name, command):
        print('RUN ' + name, flush=True)
        started = time.monotonic()
        with (logs / (name + '.log')).open('w', encoding='utf-8') as log:
            process = subprocess.run(command, cwd=SKILL, env=env, stdout=log, stderr=subprocess.STDOUT, check=False)
        result['commands'].append({'name': name, 'argv': command, 'exitCode': process.returncode,
                                   'seconds': round(time.monotonic() - started, 3)})
        if process.returncode:
            raise RuntimeError(f'{name} exited {process.returncode}; see logs/{name}.log')

    try:
        run('blender-version', [executable, '--version'])
        command = [executable, '--factory-startup', '-b', '--python-exit-code', '1',
                   '--python-expr', 'import sys; sys.dont_write_bytecode = True',
                   '--python', str(CASE / 'build_model.py'), '--',
                   '--config', str(CASE / 'parameters.json'), '--out', str(out), '--bake-ao']
        if args.render:
            command += ['--render', '--shots', args.shots, '--samples', str(args.samples)]
        if args.draft:
            command += ['--draft']
        run('build-export-import-render', command)
        glb = out / 'ring-pulsating-deduster.glb'
        run('check-glb', [sys.executable, '-X', 'utf8', '-B', str(SKILL / 'scripts/check_glb.py'), str(glb),
                          '--contract', str(CASE / 'glb-contract.json'), '--report', str(out / 'glb-check.json')])
        if args.render:
            # 原配方的背面相机会裁切外侧圆形壳体。
            # 保留原有几何源，另生成适配完整模型的背面视图。
            rear = [executable, '--factory-startup', '-b', '--python-exit-code', '1',
                    '--python-expr', 'import sys; sys.dont_write_bytecode = True',
                    '--python', str(SKILL / 'scripts/render_deduster_rear.py'), '--',
                    '--glb', str(glb), '--image', str(out / 'ring-pulsating-deduster-rear-full.png'),
                    '--samples', str(args.samples)]
            if args.draft:
                rear += ['--draft']
            run('render-complete-rear', rear)
        compare_json(read_json(CASE / 'accepted-model.json'), read_json(out / 'ring-pulsating-deduster.manifest.json'))
        compare_json(read_json(CASE / 'accepted-sensors.json'), read_json(out / 'sensors.json'))
        qa = read_json(out / 'ring-pulsating-deduster.qa.json')
        if (qa['triangles'], qa['meshes']) != (snapshot['baselineAsset']['triangles'], snapshot['baselineAsset']['meshCount']):
            raise ValueError('Rebuilt topology counts differ from the accepted baseline.')
        result.update({'ok': True, 'blender': qa['blender'], 'triangles': qa['triangles'], 'meshes': qa['meshes'],
                       'anchors': len(qa['anchors']), 'manifestMatches': True, 'sensorsMatch': True,
                       'glbSha256': hashlib.sha256(glb.read_bytes()).hexdigest(),
                       'binaryHashIdentical': hashlib.sha256(glb.read_bytes()).hexdigest() == snapshot['baselineAsset']['sha256']})
        print(json.dumps({key: result[key] for key in ['ok', 'blender', 'triangles', 'meshes', 'anchors', 'binaryHashIdentical']}), flush=True)
    except Exception as error:
        result['error'] = str(error)
        print(str(error), file=sys.stderr)
    finally:
        (out / 'replay-result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
