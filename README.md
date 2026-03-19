# bundler

## installation

1. (install Python)
2. `python -m venv .venv` to initialize virtual environment
3. `.venv\Scripts\activate` to activate the virtual environment
4. `pip install py7zr pyyaml` to install dependencies

## usage

### bundle.yaml

```yaml
project: app_name
version: "1.0.0"
output_dir: ./dist

include:
  - "**"

exclude:
  - .git/**
  - .venv/**
  - dist/**
  - .bundle_manifest.yaml

```

### bundler.py [-h] [-i] [-d] [-b LEVEL] [config]

Project file bundler with incremental change detection

```powershell
positional arguments:
  config                      path to bundle.yaml (default: bundle.yaml)

options:
  -h, --help                  show this help message and exit
  -i, --incremental           pack only files changed since the last bundle
  -d, --dry-run               preview which files would be packed; create no archive
  -b, --bump-version LEVEL    bump version in config before bundling: major | minor | patch

# create full bundle, uses ./bundle.yaml
python bundler.py

# full bundle, explicit config
python bundler.py other.yaml

# pack only changed files
python bundler.py -i

# dry-run: preview changed files, no archive
python bundler.py -i -d

# bump version in config, then full bundle
python bundler.py -b minor

# explicit config, incremental, bump patch
python bundler.py other.yaml -i -b patch
```

### unbundler.py [-h] [-d] archive [target]

Unpack a project bundle and apply it to an install directory

```powershell
positional arguments:
  archive        path to the .7z bundle archive
  target         directory to apply the bundle to (default: cwd)

options:
  -h, --help     show this help message and exit
  -d, --dry-run  preview changes without writing or deleting anything

# unpack a bundle in the current working directory
python unbundler.py myapp_1.2.0_full_20260318.7z

# unpack to a specified directory
python unbundler.py myapp_1.2.1_patch_20260318.7z /path/to/install

# dry-run: preview changed files
python unbundler.py myapp_1.2.1_patch_20260318.7z -d
```