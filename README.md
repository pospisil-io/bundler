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

### bundler

```python
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

### unbundler

```python
# unpack a bundle in the current working directory
python unbundler.py myapp_1.2.0_full_20260318.7z

# unpack to a specified directory
python unbundler.py myapp_1.2.1_patch_20260318.7z /path/to/install

# dry-run: preview changed files
python unbundler.py myapp_1.2.1_patch_20260318.7z -d
```