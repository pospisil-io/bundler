#!/usr/bin/env python3
"""
unbundler.py — unpack a project bundle and apply it to an install directory.

Reads the release_manifest.yaml embedded in the archive to know which files
to overwrite and which to delete, then applies the changes to the target
directory.

Usage:
    python unbundler.py myapp_1.2.0_full_20260318.7z
    python unbundler.py myapp_1.2.0_full_20260318.7z /path/to/install
    python unbundler.py myapp_1.2.0_full_20260318.7z /path/to/install -d
"""

import argparse
import sys
import tempfile
from pathlib import Path

import py7zr
import yaml

RELEASE_MANIFEST = "release_manifest.yaml"


# ---------------------------------------------------------------------------
# Archive reading
# ---------------------------------------------------------------------------

def read_release_manifest(archive_path: Path) -> dict:
    """Extract and parse release_manifest.yaml from the archive without
    fully unpacking it."""
    with py7zr.SevenZipFile(archive_path, mode="r") as archive:
        names = archive.getnames()
        if RELEASE_MANIFEST not in names:
            print(f"[error] Archive does not contain '{RELEASE_MANIFEST}'. "
                  "Was it created with bundler.py?")
            sys.exit(1)
        data = archive.read(targets=[RELEASE_MANIFEST])
        raw = data[RELEASE_MANIFEST].read()
        return yaml.safe_load(raw)


def extract_archive(archive_path: Path, dest: Path) -> None:
    """Extract all files from the archive into dest."""
    with py7zr.SevenZipFile(archive_path, mode="r") as archive:
        archive.extractall(path=dest)


# ---------------------------------------------------------------------------
# Apply changes
# ---------------------------------------------------------------------------

def apply_bundle(
    archive_path: Path,
    target: Path,
    manifest: dict,
    dry_run: bool,
) -> None:
    changed: list[str] = manifest.get("changed", [])
    deleted: list[str] = manifest.get("deleted", [])
    bundle_type: str    = manifest.get("bundle_type", "?")
    version: str        = manifest.get("version", "?")
    project: str        = manifest.get("project", "?")

    print(f"[info] Project : {project}")
    print(f"[info] Version : {version}")
    print(f"[info] Type    : {bundle_type}")
    print(f"[info] Changes : {len(changed)} file(s) to write, "
          f"{len(deleted)} file(s) to delete")

    # --- Deletions ---------------------------------------------------------
    if deleted:
        print()
        print("[info] Files to delete:")
        for rel in deleted:
            target_file = target / rel
            suffix = "" if target_file.exists() else "  (not found, will skip)"
            print(f"       {rel}{suffix}")

    # --- Extraction into temp dir, then copy to target ---------------------
    if changed:
        print()
        print("[info] Files to write:")
        for rel in changed:
            print(f"       {rel}")

    if dry_run:
        print()
        print("[dry-run] No files written or deleted.")
        return

    for rel in deleted:
        target_file = target / rel
        if not target_file.exists():
            continue
        target_file.unlink()
        # Clean up empty parent directories
        for parent in target_file.parents:
            if parent == target:
                break
            try:
                parent.rmdir()   # only succeeds if empty
            except OSError:
                break

    with tempfile.TemporaryDirectory() as tmp_str:
        tmp = Path(tmp_str)
        extract_archive(archive_path, tmp)

        for rel in changed:
            src = tmp / rel
            dst = target / rel
            if not src.exists():
                print(f"[warn] '{rel}' listed in manifest but not found in archive — skipping.")
                continue
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(src.read_bytes())

    print()
    print(f"[ok] Applied {len(changed)} file(s) to {target}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Unpack a project bundle and apply it to an install directory.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("archive",
                        help="Path to the .7z bundle archive.")
    parser.add_argument("target", nargs="?", default=".",
                        help="Directory to apply the bundle to.  (default: cwd)")
    parser.add_argument("-d", "--dry-run", action="store_true",
                        help="Preview changes without writing or deleting anything.")
    args = parser.parse_args()

    archive_path = Path(args.archive)
    if not archive_path.exists():
        print(f"[error] Archive not found: {archive_path}")
        sys.exit(1)
    if not archive_path.suffix == ".7z":
        print(f"[warn] File does not have a .7z extension: {archive_path}")

    target = Path(args.target).resolve()
    if not target.exists():
        print(f"[error] Target directory does not exist: {target}")
        sys.exit(1)

    manifest = read_release_manifest(archive_path)
    apply_bundle(archive_path, target, manifest, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
