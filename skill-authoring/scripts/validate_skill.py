#!/usr/bin/env python3
"""只读且无额外依赖的 Skill 检查器，不是完整的 YAML/Markdown 解析器。"""

import argparse
import json
import re
import unicodedata
from pathlib import Path
from urllib.parse import unquote, urlsplit

PROFILE = 'portable-flat-v1'
FIELDS = {'name', 'description', 'license', 'compatibility', 'allowed-tools'}


class Unsupported(ValueError):
    pass


def scalar(value):
    if value.startswith('"'):
        try:
            result = json.loads(value)
        except ValueError as exc:
            raise Unsupported('Double quotes require the JSON string subset') from exc
        if not isinstance(result, str):
            raise Unsupported('Only string scalars are checked')
        return result
    if value.startswith("'"):
        if not re.fullmatch(r"'(?:[^']|'')*'", value):
            raise Unsupported('Unsupported single-quoted scalar')
        return value[1:-1].replace("''", "'")
    if (not value or value[0] in '|>!&*[{%@`:?' or re.search(r':(?:\s|$)', value) or '#' in value
            or value.lower() in {'null', '~', 'true', 'false', 'yes', 'no', 'on', 'off'}
            or re.match(r'^[+\-.0-9]', value)):
        raise Unsupported('Use an unambiguous single-line string or a complete YAML validator')
    return value


def frontmatter(text):
    lines = text.splitlines()
    if not lines or lines[0] != '---':
        raise ValueError('SKILL.md must start with a YAML frontmatter delimiter (UTF-8, no BOM)')
    try:
        end = lines.index('---', 1)
    except ValueError as exc:
        raise ValueError('Missing closing frontmatter delimiter') from exc
    data = {}
    for line in lines[1:end]:
        if not line.strip() or line.startswith('#'):
            continue
        match = re.fullmatch(r'([a-z][a-z-]*):[ \t]*(.*)', line)
        if not match:
            raise Unsupported('Only a flat mapping of single-line strings is checked')
        key, value = match.groups()
        if key in data:
            raise ValueError(f'Duplicate frontmatter key: {key}')
        if key not in FIELDS:
            raise Unsupported(f'Field {key!r} requires another validator; preserve it')
        data[key] = scalar(value)
    return data, '\n'.join(lines[end + 1:])


def prose(text):
    """跳过围栏代码示例，不将示例中的演示链接作为真实资源。"""
    result, fence = [], None
    for line in text.splitlines():
        mark = re.match(r'^\s*(`{3,}|~{3,})(.*)$', line)
        if mark:
            token, rest = mark.groups()
            if fence is None:
                fence = token
            elif token[0] == fence[0] and len(token) >= len(fence) and not rest.strip():
                fence = None
        elif fence is None:
            result.append(line)
    return '\n'.join(result)


def heading_ids(text):
    result, counts = set(), {}
    for title in re.findall(r'^#{1,6}\s+(.+?)\s*#*$', prose(text), re.MULTILINE):
        title = title.lower().strip().replace('`', '')
        slug = ''.join(ch for ch in title
                       if ch in '-_ ' or unicodedata.category(ch)[0] not in 'PS').replace(' ', '-')
        count = counts.get(slug, 0)
        counts[slug] = count + 1
        result.add(slug if count == 0 else f'{slug}-{count}')
    return result


def validate(folder, allow_reference_roots=()):
    root = Path(folder).resolve()
    allowed = [root, *(Path(path).resolve() for path in allow_reference_roots)]
    report = {'profile': PROFILE, 'path': str(root), 'ok': False,
              'errors': [], 'unsupported': [], 'warnings': [], 'local_links_checked': 0,
              'limits': ['Flat string frontmatter only; not complete YAML or Markdown',
                         'No script execution, secret scanning, behavioral or host validation']}

    def issue(kind, code, message, path=None):
        report[kind].append({'code': code, 'message': message,
                             'file': str(path) if path else 'SKILL.md'})

    entry = root / 'SKILL.md'
    if not root.is_dir() or not entry.is_file():
        issue('errors', 'entry', 'Target must be a skill folder containing SKILL.md')
        return report
    try:
        if not entry.resolve().is_relative_to(root):
            raise ValueError('SKILL.md resolves outside the target folder')
        text = entry.read_text(encoding='utf-8')
        data, body = frontmatter(text)
        for key in ('name', 'description'):
            if key not in data or not data[key].strip():
                issue('errors', 'required', f'{key} must be a non-empty string')
        name = data.get('name', '')
        if (not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', name) or len(name) > 64):
            issue('errors', 'name', 'Use 1-64 lowercase letters, digits and single hyphens')
        if name != root.name:
            issue('errors', 'directory', 'name must match the skill directory')
        if len(data.get('description', '')) > 1024:
            issue('errors', 'description', 'description exceeds 1024 characters')
        if 'compatibility' in data and not 1 <= len(data['compatibility']) <= 500:
            issue('errors', 'compatibility', 'compatibility must contain 1-500 characters')
        if not body.strip():
            issue('errors', 'body', 'Instructions are empty')
        if re.search(r'^\s*\[TODO:[^\n]*\]\s*$', prose(body), re.MULTILINE):
            issue('errors', 'scaffold', 'Unfinished instruction placeholder')
        if len(body.splitlines()) > 500:
            issue('warnings', 'long-entry', 'Consider moving conditional detail to references')
    except Unsupported as exc:
        issue('unsupported', 'frontmatter-profile', str(exc))
    except (OSError, UnicodeError, ValueError) as exc:
        issue('errors', 'entry', str(exc))

    try:
        documents = sorted(root.rglob('*.md')) if root.is_dir() else []
        for document in documents:
            if not document.resolve().is_relative_to(root):
                issue('errors', 'resource-scope', 'Markdown resource resolves outside skill', document)
                continue
            try:
                content = prose(document.read_text(encoding='utf-8'))
                targets = re.findall(r'(?<!!)\[[^\]\n]*\]\(([^\)\n]+)\)', content)
                targets += re.findall(r'^\s*\[[^\]\n]+\]:\s*(\S+)\s*$', content, re.MULTILINE)
                for target in targets:
                    parsed = urlsplit(target)
                    if parsed.scheme in {'http', 'https', 'mailto'}:
                        continue
                    if parsed.scheme or parsed.netloc:
                        issue('unsupported', 'link-syntax', f'Unsupported link: {target}', document)
                        continue
                    dest = ((document.parent / unquote(parsed.path)).resolve()
                            if parsed.path else document.resolve())
                    report['local_links_checked'] += 1
                    if not any(dest.is_relative_to(base) for base in allowed):
                        issue('errors', 'reference-scope', f'Outside allowed roots: {target}', document)
                    elif not dest.exists():
                        issue('errors', 'missing-reference', f'Missing reference: {target}', document)
                    elif parsed.fragment and dest.suffix.lower() == '.md':
                        if unquote(parsed.fragment) not in heading_ids(dest.read_text(encoding='utf-8')):
                            issue('errors', 'heading', f'Missing heading: {target}', document)
            except (OSError, UnicodeError, ValueError) as exc:
                issue('errors', 'reference-read', str(exc), document)
    except OSError as exc:
        issue('errors', 'resource-read', str(exc))
    report['ok'] = not report['errors'] and not report['unsupported']
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('skill', type=Path)
    parser.add_argument('--allow-reference-root', action='append', default=[], type=Path,
                        help='Explicit additional read root for project policy links')
    args = parser.parse_args()
    report = validate(args.skill, args.allow_reference_root)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if report['errors'] else 2 if report['unsupported'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
