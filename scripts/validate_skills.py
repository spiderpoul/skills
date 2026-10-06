#!/usr/bin/env python3
"""Validate this repository's one-line metadata convention and local links.

Uses only the standard library. This is not a general YAML parser or an audit
of model behavior. Full Skill specifications may permit additional formats.
"""

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

NAME = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
LINK = re.compile(r"!?\[[^\]]*\]\(([^\s)]+)(?:\s+\"[^\"]*\")?\)")


def scalar(value):
    value = value.strip()
    if not value:
        raise ValueError("empty value")
    if value.startswith('"'):
        parsed = json.loads(value)
        if not isinstance(parsed, str):
            raise ValueError("expected string")
        return parsed
    if value.startswith("'"):
        if not value.endswith("'") or len(value) < 2:
            raise ValueError("unclosed single quote")
        return value[1:-1].replace("''", "'")
    if ': ' in value or value.startswith(('|', '>', '[', '{', '&', '*', '!')):
        raise ValueError("use a quoted one-line string")
    return value


def validate(root):
    errors = []
    skills = sorted((root / 'skills').glob('*/SKILL.md'))
    if not skills:
        errors.append('No skills/<name>/SKILL.md files found')
    names = set()
    for path in skills:
        rel = path.relative_to(root)
        lines = path.read_text(encoding='utf-8').splitlines()
        if not lines or lines[0] != '---' or '---' not in lines[1:]:
            errors.append(f'{rel}: missing YAML frontmatter delimiters')
            continue
        fields = {}
        end = lines.index('---', 1)
        for line in lines[1:end]:
            if not line.strip():
                continue
            key, sep, value = line.partition(':')
            if not sep or key not in ('name', 'description') or key in fields:
                errors.append(f'{rel}: use unique one-line name and description fields')
                continue
            try:
                fields[key] = scalar(value)
            except (ValueError, json.JSONDecodeError) as exc:
                errors.append(f'{rel}: {key}: {exc}')
        for key in ('name', 'description'):
            if not fields.get(key):
                errors.append(f'{rel}: missing {key}')
        name = fields.get('name', '')
        if not NAME.fullmatch(name) or len(name) > 64 or path.parent.name != name:
            errors.append(f'{rel}: name must match folder and use lowercase hyphens')
        if name in names:
            errors.append(f'{rel}: duplicate skill name {name}')
        names.add(name)
        metadata = path.parent / 'agents/openai.yaml'
        if metadata.exists():
            content = metadata.read_text(encoding='utf-8')
            for key in ('display_name', 'short_description', 'default_prompt'):
                match = re.search(rf'^  {key}: (.+)$', content, re.MULTILINE)
                try:
                    val = scalar(match[1]) if match else ''
                    if not val:
                        raise ValueError('missing value')
                    if key == 'default_prompt' and f'${name}' not in val:
                        raise ValueError('must mention the skill as $<name>')
                    if key == 'short_description' and not 25 <= len(val) <= 64:
                        raise ValueError('must have 25–64 characters')
                except ValueError as exc:
                    errors.append(f'{metadata.relative_to(root)}: {key}: {exc}')
    for path in sorted(root.rglob('*.md')):
        if any(part in ('.git', 'node_modules') for part in path.relative_to(root).parts):
            continue
        for target in LINK.findall(path.read_text(encoding='utf-8')):
            if target.startswith('#') or urlsplit(target).scheme:
                continue
            target = unquote(target.split('#', 1)[0])
            resolved = (path.parent / target).resolve()
            if not resolved.is_relative_to(root) or not resolved.exists():
                errors.append(f'{path.relative_to(root)}: broken local link: {target}')
            if path.is_relative_to(root / 'skills') and path.parent.name != 'skills':
                skill_root = next((p.parent for p in skills if path.is_relative_to(p.parent)), None)
                if skill_root and not resolved.is_relative_to(skill_root):
                    errors.append(f'{path.relative_to(root)}: skill link leaves its standalone folder: {target}')
    return skills, errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    skills, errors = validate(args.root.resolve())
    if errors:
        for error in errors:
            print(f'ERROR: {error}', file=sys.stderr)
        return 1
    print(f'Validated {len(skills)} skill(s), interface metadata and local Markdown links.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
