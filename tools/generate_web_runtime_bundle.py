#!/usr/bin/env python3

import base64
import json
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
MANIFEST_PATH = ROOT_DIR / "web" / "runtime-manifest.json"
BUNDLE_PATH = ROOT_DIR / "web" / "runtime-bundle.json"


def iter_workspace_image_sources():
    for root_name in ("games", "system"):
        root_dir = ROOT_DIR / root_name
        if not root_dir.is_dir():
            continue
        for path in root_dir.rglob("*"):
            if not path.is_file():
                continue
            relative_path = path.relative_to(ROOT_DIR).as_posix()
            if root_name == "games" and path.name == "menu.png" and len(path.relative_to(root_dir).parts) == 3:
                yield relative_path
                continue
            if "/images/" not in relative_path:
                continue
            if path.name == "__images__.yaml" or path.suffix.lower() == ".png":
                yield relative_path


def build_manifest_file_list(existing_files):
    ordered = []
    seen = set()

    for relative_path in existing_files:
        normalized = Path(relative_path).as_posix()
        if not (ROOT_DIR / normalized).is_file():
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        ordered.append(normalized)

    for relative_path in sorted(iter_workspace_image_sources()):
        if relative_path in seen:
            continue
        seen.add(relative_path)
        ordered.append(relative_path)

    return ordered


def main():
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    manifest["files"] = build_manifest_file_list(manifest["files"])
    MANIFEST_PATH.write_text(
      json.dumps(manifest, ensure_ascii=True, indent=2) + "\n",
      encoding="utf-8",
    )

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
