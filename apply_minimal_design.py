"""Validate and select a layout without rewriting application source or restoring stale backups."""
import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

PROJECT = Path(__file__).resolve().parent


def select(home, layout):
    # Prove that the complete window can initialize before persisting this preference.
    env = dict(os.environ, DOCUMENTASSISTANT_LAYOUT=layout, PYTHONDONTWRITEBYTECODE='1')
    try:
        checked = subprocess.run([sys.executable, str(PROJECT / 'validate_minimal_layout.py'),
                                  '--layout', layout], env=env, cwd=PROJECT, timeout=45)
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f'布局验证失败，未修改设置：{exc}', file=sys.stderr)
        return 1
    if checked.returncode:
        return checked.returncode
    home.mkdir(parents=True, exist_ok=True)
    target = home / 'ui-layout.json'
    # A unique temporary file prevents concurrent selectors from sharing a staging name.
    fd, name = tempfile.mkstemp(prefix='ui-layout-', suffix='.tmp', dir=home)
    temporary = Path(name)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            json.dump({'layout': layout}, handle)
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
    print(f'已选择 {layout} 布局，下次启动生效。原窗口与待处理队列保留。')
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--restore', action='store_true', help='下次启动使用原布局；不覆盖任何源码')
    parser.add_argument('--test', action='store_true', help='仅验证紧凑布局，不更改设置')
    parser.add_argument('--home', type=Path)
    args = parser.parse_args(argv)
    if args.test:
        return subprocess.call([sys.executable, str(PROJECT / 'validate_minimal_layout.py'), '--layout', 'minimal'])
    home = args.home or Path(os.environ.get('DOCUMENTASSISTANT_HOME', PROJECT.parent / 'DocumentAssistant-local'))
    return select(home, 'classic' if args.restore else 'minimal')


if __name__ == '__main__':
    raise SystemExit(main())
