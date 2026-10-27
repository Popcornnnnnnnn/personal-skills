#!/usr/bin/env python3
"""Run installed LinkGet and retain evidence of its managed Photos checks."""
import argparse
from datetime import datetime, timezone
import importlib
import json
from pathlib import Path
import re
import shutil
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url")
    parser.add_argument("--expected", type=int, required=True)
    parser.add_argument("--kind", choices=["image", "video"], required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    if args.expected < 1:
        parser.error("Expected media count must be positive")
    receipt = args.receipt.expanduser().resolve()
    if receipt.exists() or receipt.with_suffix(".linkget.json").exists():
        parser.error("Receipt already exists: inspect/reconcile it before retrying")
    executable = shutil.which("linkget")
    if not executable:
        parser.error("LinkGet is unavailable")
    launcher = Path(executable).resolve().read_text()
    match = re.search(r'"([^"\n]+/libexec/linkget/cli.py)"', launcher)
    if not match:
        parser.error("Installed LinkGet launcher changed: inspect before adapting")
    sys.path.insert(0, str(Path(match.group(1)).parent.parent))
    cli = importlib.import_module("linkget.cli")
    photos = importlib.import_module("linkget.photos")
    media = importlib.import_module("linkget.media")
    receipt.parent.mkdir(parents=True, exist_ok=True)
    result = {"source": media.reference(args.url), "expected_count": args.expected,
              "kind": args.kind, "started_at": datetime.now(timezone.utc).isoformat(),
              "linkget_version": cli.VERSION, "managed_originals_verified": False}
    original_import, original_verify = cli.import_photos, cli.verify_library_copies

    def save():
        temporary = receipt.with_suffix(".tmp")
        temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
        temporary.chmod(0o600)
        temporary.replace(receipt)

    def verify(files, identifiers):
        original_verify(files, identifiers)
        library = photos.library_directory().resolve()
        records = []
        for source, identifier in zip(files, identifiers):
            asset = identifier.split("/")[0].upper()
            digest = photos.digest(source, fresh=True)
            matches = [p for p in (library / "originals" / asset[0]).glob(asset + ".*")
                       if p.is_file() and not p.is_symlink()
                       and photos.digest(p, fresh=True) == digest]
            if not matches:
                raise RuntimeError("Managed Photos original missing after LinkGet verification")
            records.append({"asset_id": identifier, "sha256": digest,
                            "bytes": source.stat().st_size, "managed_path": str(matches[0])})
        by_content = {(record["sha256"], record["bytes"]): record for record in records}
        source_assets = []
        for index, source in enumerate(result.get("source_media", []), 1):
            asset = by_content.get((source["sha256"], source["bytes"]))
            if asset is None:
                raise RuntimeError("A source media item has no verified Photos original")
            source_assets.append({"index": index, "asset_id": asset["asset_id"],
                                  "sha256": source["sha256"], "bytes": source["bytes"]})
        if len(source_assets) != args.expected:
            raise RuntimeError("Photos verification did not cover the full source count")
        result.update(managed_originals_verified=True, library=str(library), assets=records,
                      source_assets=source_assets, unique_asset_count=len(records))
        save()

    def checked_import(files, date_now, live_pairs=None):
        inspected = media.inspect_files(files)
        if len(files) != args.expected or any(r["kind"] != args.kind or not r["probe_ok"] for r in inspected):
            raise RuntimeError("Source count/type or decoded media did not match: import stopped")
        result["media"] = inspected
        result["source_media"] = [{"sha256": photos.digest(source, fresh=True), "bytes": source.stat().st_size}
                                  for source in files]
        save()
        return original_import(files, date_now, live_pairs)

    cli.verify_library_copies, cli.import_photos = verify, checked_import
    save()
    try:
        code = cli.main([args.url, "--photos", "--browser", "none", "--report",
                         str(receipt.with_suffix(".linkget.json"))])
        result["exit_code"] = code
        result["complete"] = (code == 0 and result["managed_originals_verified"]
                              and len(result.get("source_assets", [])) == args.expected)
        save()
        return 0 if result["complete"] else 1
    finally:
        cli.verify_library_copies, cli.import_photos = original_verify, original_import


if __name__ == "__main__":
    raise SystemExit(main())
