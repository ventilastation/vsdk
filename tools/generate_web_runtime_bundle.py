#!/usr/bin/env python3

import base64
import json
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
MANIFEST_PATH = ROOT_DIR / "web" / "runtime-manifest.json"
BUNDLE_PATH = ROOT_DIR / "web" / "runtime-bundle.json"


def iter_python_sources():
    """Auto-discover the Python files the browser runtime needs, so nobody
    has to hand-edit the manifest when a module is added, moved, or removed."""
    yield "apps/micropython/main.py"
    yield "apps/micropython/manifest.py"
    package_dir = ROOT_DIR / "apps" / "micropython" / "ventilastation"
    for path in sorted(package_dir.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        yield path.relative_to(ROOT_DIR).as_posix()
    for root_name in ("games", "system"):
        root_dir = ROOT_DIR / root_name
        if not root_dir.is_dir():
            continue
        for path in sorted(root_dir.rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            yield path.relative_to(ROOT_DIR).as_posix()


def iter_workspace_asset_sources():
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
            if "/images/" in relative_path and (path.name == "__images__.yaml" or path.suffix.lower() == ".png"):
                yield relative_path
                continue
            if "/sounds/" in relative_path:
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

    for relative_path in iter_python_sources():
        if relative_path in seen:
            continue
        seen.add(relative_path)
        ordered.append(relative_path)

    for relative_path in sorted(iter_workspace_asset_sources()):
        if relative_path in seen:
            continue
        seen.add(relative_path)
        ordered.append(relative_path)

    return ordered


def should_include_in_bundle(relative_path):
    normalized = Path(relative_path).as_posix()
    suffix = Path(normalized).suffix.lower()
    if suffix in {".png", ".yaml", ".yml", ".mp3", ".wav", ".ogg"}:
        return False
    return True


def main():
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    manifest["files"] = build_manifest_file_list(manifest["files"])
    MANIFEST_PATH.write_text(
      json.dumps(manifest, ensure_ascii=True, indent=2) + "\n",
      encoding="utf-8",
    )

    entries = []
    for relative_path in manifest["files"]:
      if not should_include_in_bundle(relative_path):
        continue
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
