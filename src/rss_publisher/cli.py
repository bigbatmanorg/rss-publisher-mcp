from __future__ import annotations

import argparse
import json
from pathlib import Path
from .config import Settings
from .service import PublisherService


def main() -> None:
    parser = argparse.ArgumentParser(prog="rss-publisher")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("validate")
    sub.add_parser("audit")
    sub.add_parser("rebuild")
    p = sub.add_parser("export-state")
    p.add_argument("--output")
    args = parser.parse_args()
    service = PublisherService(Settings.from_env())
    if args.command == "validate":
        result = service.validate_feed()
    elif args.command == "audit":
        result = service.audit_feed()
    elif args.command == "rebuild":
        service.rebuild_public()
        result = service.validate_feed()
    elif args.command == "export-state":
        result = service.export_state()
        if args.output:
            Path(args.output).write_text(json.dumps(result, indent=2, ensure_ascii=False))
            print(args.output)
            return
    print(json.dumps(result, indent=2, ensure_ascii=False))
