"""Generate G14-A backup manifest for an existing PostgreSQL dump."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from phigraph.recovery.manifest import build_backup_manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("backup")
    parser.add_argument("snapshot")
    parser.add_argument("--output")
    parser.add_argument("--runtime-version")
    args = parser.parse_args()

    snapshot = json.loads(Path(args.snapshot).read_text(encoding="utf-8"))
    governance = snapshot.get("schema_governance")
    manifest = build_backup_manifest(
        backup_path=args.backup,
        schema_governance=governance,
        integrity_snapshot=snapshot,
        runtime_version=args.runtime_version,
    )
    output = json.dumps(manifest.to_dict(), sort_keys=True, indent=2) + "\n"
    if args.output:
        Path(args.output).write_text(output, encoding="utf-8")
    else:
        print(output, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
