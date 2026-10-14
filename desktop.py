"""Entry point shared by the standalone executable and source builds."""
import argparse
import json
import os
import sys
from pathlib import Path


def run():
    parser = argparse.ArgumentParser(description='DocumentAssistant')
    parser.add_argument('--home', type=Path)
    parser.add_argument('--tray', action='store_true')
    parser.add_argument('--extract', type=Path, help=argparse.SUPPRESS)
    parser.add_argument('--output', type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.extract:
        if not args.output:
            parser.error('--extract requires --output')
        from document_assistant.extractor import extract
        args.output.write_text(json.dumps(extract(args.extract), ensure_ascii=True), encoding='utf-8')
        return 0
    if args.output:
        parser.error('--output requires --extract')
    location = Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent
    home = (args.home or Path(os.environ.get('DOCUMENTASSISTANT_HOME', location.parent / 'DocumentAssistant-local'))).resolve()
    home.mkdir(parents=True, exist_ok=True)
    temporary = home / 'tmp'
    temporary.mkdir(exist_ok=True)
    os.environ.update(DOCUMENTASSISTANT_HOME=str(home), TEMP=str(temporary), TMP=str(temporary),
                      PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1')
    from document_assistant.gui import main
    return main(start_in_tray=args.tray)


if __name__ == '__main__':
    raise SystemExit(run())
