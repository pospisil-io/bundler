#!/usr/bin/env python3
"""
bundler.py — project file bundler with incremental change detection.

Usage:
    python bundler.py                        # full bundle
    python bundler.py -i                     # pack only changed files
    python bundler.py -i -d                  # dry-run: preview changed files, no archive
    python bundler.py --bump-version minor   # bump version in config, then full bundle
    python bundler.py -c path/to/other.yaml  # custom config location
"""

import argparse
import hashlib
import re
import sys
from datetime import datetime
from pathlib import Path

import py7zr
import yaml

DEFAULT_CONFIG = "bundle.yaml"
MANIFEST_FILE = ".bundle_manifest.yaml"

BUMP_LEVELS = ("major", "minor", "patch")
RELEASE_MANIFEST = "release_manifest.yaml"


# ---------------------------------------------------------------------------
# Config loading / version bumping
# ---------------------------------------------------------------------------

def load_config(config_path: Path) -> dict:
    with config_path.open("r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    required = ("project", "version", "output_dir", "include")
    missing = [k for k in required if k not in config]
    if missing:
        print(f"[error] Missing required config keys: {', '.join(missing)}")
        sys.exit(1)

    return config


def bump_version(version: str, level: str) -> str:
    """Increment a semver string at the given level, zeroing lower components."""
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)(.*)", version)
    if not match:
        print(f"[error] Cannot parse version '{version}' — expected MAJOR.MINOR.PATCH")
        sys.exit(1)
    major, minor, patch, suffix = int(match[1]), int(match[2]), int(match[3]), match[4]
    if level == "major":
        major, minor, patch = major + 1, 0, 0
    elif level == "minor":
        minor, patch = minor + 1, 0
    else:
        patch += 1
    return f"{major}.{minor}.{patch}{suffix}"


def write_version(config_path: Path, new_version: str) -> None:
    """Replace the version line in the YAML file in-place (preserves formatting)."""
    text = config_path.read_text(encoding="utf-8")
    updated = re.sub(
        r"^(version\s*:\s*)(.+)$",
        lambda m: f'{m.group(1)}"{new_version}"',
        text,
        flags=re.MULTILINE,
    )
    config_path.write_text(updated, encoding="utf-8")
    print(f"[ok] Version bumped to {new_version} in {config_path}")


# ---------------------------------------------------------------------------
# File resolution
# ---------------------------------------------------------------------------

def resolve_files(config: dict, base: Path) -> list[Path]:
    """Expand include globs then subtract exclude globs."""
    included: set[Path] = set()
    for pattern in config.get("include", []):
        included.update(p for p in base.glob(pattern) if p.is_file())

    excluded: set[Path] = set()
    for pattern in config.get("exclude", []):
        excluded.update(p for p in base.glob(pattern) if p.is_file())

    result = sorted(included - excluded)
    if not result:
        print("[warn] No files matched after applying include/exclude rules.")
    return result


# ---------------------------------------------------------------------------
# Hashing / manifest
# ---------------------------------------------------------------------------

def hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def build_manifest(files: list[Path], base: Path) -> dict[str, str]:
    return {str(p.relative_to(base)): hash_file(p) for p in files}


def load_manifest(manifest_path: Path) -> dict:
    """Return the full manifest document, or an empty dict if not found."""
    if not manifest_path.exists():
        return {}
    with manifest_path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def save_manifest(manifest_path: Path, file_hashes: dict[str, str], archive_name: str) -> None:
    """
    Persist the manifest, appending a history entry.

    Structure:
        files:
          rel/path: sha256
          ...
        history:
          - timestamp: "..."
            archive: "..."
            file_count: N
    """
    doc = load_manifest(manifest_path)
    history: list[dict] = doc.get("history", [])
    history.append({
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "archive": archive_name,
        "file_count": len(file_hashes),
    })
    doc = {"files": file_hashes, "history": history}
    with manifest_path.open("w", encoding="utf-8") as f:
        yaml.dump(doc, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


def find_changed(current: dict[str, str], previous_files: dict[str, str]) -> list[str]:
    """Return relative paths of files that are new or modified."""
    return sorted(
        rel for rel, digest in current.items()
        if previous_files.get(rel) != digest
    )


# ---------------------------------------------------------------------------
# Release manifest
# ---------------------------------------------------------------------------

def build_release_manifest(
    project: str,
    version: str,
    bundle_type: str,
    files_to_pack: list[Path],
    current_hashes: dict[str, str],
    previous_hashes: dict[str, str],
    base: Path,
) -> dict:
    """
    Build the release_manifest.yaml that will be embedded in the archive.

    For a full bundle every file is listed under 'changed'.
    For a patch bundle, files absent from previous_hashes are 'new',
    the rest are 'modified'. Files present in previous_hashes but absent
    from current_hashes are listed under 'deleted'.
    """
    rel_to_pack = {str(p.relative_to(base)) for p in files_to_pack}

    if bundle_type == "full":
        changed = sorted(rel_to_pack)
        deleted: list[str] = []
    else:
        changed = sorted(rel_to_pack)
        current_all = set(current_hashes.keys())
        previous_all = set(previous_hashes.keys())
        deleted = sorted(previous_all - current_all)

    return {
        "project": project,
        "version": version,
        "bundle_type": bundle_type,
        "created": datetime.now().isoformat(timespec="seconds"),
        "changed": changed,
        "deleted": deleted,
    }


def write_release_manifest(manifest: dict, path: Path) -> None:
    with path.open("w", encoding="utf-8") as f:
        yaml.dump(manifest, f, default_flow_style=False, allow_unicode=True, sort_keys=False)


# ---------------------------------------------------------------------------
# Archive creation
# ---------------------------------------------------------------------------

def make_archive_name(project: str, version: str, incremental: bool) -> str:
    date_str = datetime.now().strftime("%Y%m%d")
    bundle_type = "patch" if incremental else "full"
    return f"{project}_{version}_{bundle_type}_{date_str}.7z"


def create_archive(
    archive_path: Path,
    files: list[Path],
    base: Path,
    release_manifest: dict,
) -> None:
    # Write release manifest to a temp file next to the archive, then pack it
    manifest_tmp = archive_path.parent / RELEASE_MANIFEST
    write_release_manifest(release_manifest, manifest_tmp)
    try:
        with py7zr.SevenZipFile(archive_path, mode="w") as archive:
            for file_path in files:
                archive.write(file_path, arcname=str(file_path.relative_to(base)))
            archive.write(manifest_tmp, arcname=RELEASE_MANIFEST)
    finally:
        manifest_tmp.unlink(missing_ok=True)
    print(f"[ok] Archive created: {archive_path}  ({len(files)} file(s) + release manifest)")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Project file bundler with incremental change detection.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("-c", "--config", default=DEFAULT_CONFIG,
                        help="Path to bundle.yaml  (default: %(default)s)")
    parser.add_argument("-i", "--incremental", action="store_true",
                        help="Pack only files changed since the last bundle.")
    parser.add_argument("-d", "--dry-run", action="store_true",
                        help="Preview which files would be packed; create no archive.")
    parser.add_argument("-b", "--bump-version", metavar="LEVEL",
                        choices=BUMP_LEVELS,
                        help="Bump version in config before bundling: major | minor | patch")
    args = parser.parse_args()

    config_path = Path(args.config)
    if not config_path.exists():
        print(f"[error] Config file not found: {config_path}")
        sys.exit(1)

    base = config_path.parent.resolve()

    config = load_config(config_path)
    project  = config["project"]
    version  = config["version"]
    output_dir = (base / config["output_dir"]).resolve()

    manifest_path = base / MANIFEST_FILE
    manifest_doc  = load_manifest(manifest_path)
    previous_files: dict[str, str] = manifest_doc.get("files", {})

    # --- Resolve files -----------------------------------------------------
    all_files = resolve_files(config, base)
    if not all_files:
        sys.exit(0)

    current_manifest = build_manifest(all_files, base)

    # --- Determine which files to pack ------------------------------------
    if args.incremental:
        if not previous_files:
            print("[warn] No previous manifest found — falling back to full bundle.")
            args.incremental = False
            files_to_pack = all_files
        else:
            changed_rel = find_changed(current_manifest, previous_files)
            if not changed_rel:
                print("[info] No files changed since last bundle. Nothing to do.")
                sys.exit(0)
            files_to_pack = [base / p for p in changed_rel]
    else:
        files_to_pack = all_files

    # --- Report ------------------------------------------------------------
    bundle_type = "patch" if args.incremental else "full"
    print(f"[info] {bundle_type.capitalize()} bundle — {len(files_to_pack)} file(s):")
    for f in files_to_pack:
        print(f"       {f.relative_to(base)}")

    if args.dry_run:
        if args.bump_version:
            new_ver = bump_version(version, args.bump_version)
            print(f"[dry-run] Version would be bumped: {version} → {new_ver}")
        print("[dry-run] No archive written.")
        sys.exit(0)

    # --- Optional version bump (mutates the YAML file) ---------------------
    if args.bump_version:
        new_ver = bump_version(version, args.bump_version)
        write_version(config_path, new_ver)
        version = new_ver

    # --- Create release manifest, archive + update internal manifest -------
    output_dir.mkdir(parents=True, exist_ok=True)
    archive_name = make_archive_name(project, version, args.incremental)
    archive_path = output_dir / archive_name

    release_manifest = build_release_manifest(
        project=project,
        version=version,
        bundle_type=bundle_type,
        files_to_pack=files_to_pack,
        current_hashes=current_manifest,
        previous_hashes=previous_files,
        base=base,
    )

    create_archive(archive_path, files_to_pack, base, release_manifest)
    save_manifest(manifest_path, current_manifest, archive_name)
    print(f"[ok] Manifest updated: {manifest_path}")


if __name__ == "__main__":
    main()
