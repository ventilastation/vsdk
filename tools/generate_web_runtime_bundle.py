#!/usr/bin/env python3

import base64
import json
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
MANIFEST_PATH = ROOT_DIR / "web" / "runtime-manifest.json"
BUNDLE_PATH = ROOT_DIR / "web" / "runtime-bundle.json"


def main():
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    entries = []
    for relative_path in manifest["files"]:
      source_path = ROOT_DIR / relative_path
      if not source_path.is_file():
        raise FileNotFoundError(f"Missing runtime file: {relative_path}")
      encoded = base64.b64encode(source_path.read_bytes()).decode("ascii")
      entries.append({
        "path": relative_path,
        "base64": encoded,
      })

    bundle = {
      "version": 1,
      "files": entries,
    }
    BUNDLE_PATH.write_text(
      json.dumps(bundle, ensure_ascii=True, separators=(",", ":")),
      encoding="utf-8",
    )


if __name__ == "__main__":
    main()
