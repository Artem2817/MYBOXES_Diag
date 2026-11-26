#!/usr/bin/env python3
"""Export existing verified diagnostic artifacts; never build or overwrite the website."""
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def export(index_path, output, source_archive=False):
    index_path, output = Path(index_path).resolve(), Path(output).resolve()
    index = json.loads(index_path.read_text(encoding="utf-8"))
    config = json.loads((ROOT / "release.json").read_text())
    if index["version"] != config["application_version"]:
        raise ValueError("diagnostic application version mismatch")
    if len(index["profiles"]) != 3 or len({p["profile"] for p in index["profiles"]}) != 3:
        raise ValueError("expected exactly three board profiles")
    inputs = [(row["file"], row["sha256"]) for row in index["profiles"]]
    inputs.append((index["windows_exe"], index["windows_sha256"]))
    checked = []
    for name, checksum in inputs:
        source = (index_path.parent / name).resolve()
        if index_path.parent not in source.parents or not source.is_file():
            raise ValueError("unsafe or missing diagnostic asset")
        if digest(source) != checksum:
            raise ValueError("diagnostic checksum mismatch: " + source.name)
        checked.append(source)
    # Refuse overlapping directories so exporting cannot mutate the input site.
    if output == index_path.parent or output in index_path.parents or index_path.parent in output.parents:
        raise ValueError("release output must be separate from the input site")
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise ValueError("use an empty release directory")
    for source in checked:
        shutil.copy2(source, output / source.name)
    version = config["application_version"]
    base = f'https://github.com/{config["repository"]}/releases/download/v{version}/'
    for row in index["profiles"]:
        row["file"] = base + Path(row["file"]).name
    index["windows_exe"] = base + Path(index["windows_exe"]).name
    index["repository"] = config["repository"]
    index["release_url"] = f'https://github.com/{config["repository"]}/releases/tag/v{version}'
    index["sources_url"] = f'https://github.com/{config["repository"]}/tree/v{version}'
    (output / "diagnostic-index.json").write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n")
    commit = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True).strip()
    if source_archive:
        name = f"MYBOXES_Diag-v{version}-sources.zip"
        subprocess.run(["git", "-C", str(ROOT), "archive", "--format=zip", "-o", str(output / name), "HEAD"],
                       check=True)
    files = sorted(p for p in output.iterdir() if p.is_file())
    manifest = dict(schema=1, version=version, source_commit=commit, platform_commit=config["platform_commit"],
                    files=[dict(name=p.name, size=p.stat().st_size, sha256=digest(p)) for p in files])
    manifest_path = output / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    files.append(manifest_path)
    (output / "SHA256SUMS.txt").write_text("".join(f"{digest(p)}  {p.name}\n" for p in sorted(files)))
    return index


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--index", type=Path, required=True, help="existing diagnostic-index.json")
    parser.add_argument("--output", type=Path, default=ROOT / "dist/release")
    parser.add_argument("--source-archive", action="store_true")
    args = parser.parse_args()
    export(args.index, args.output, args.source_archive)
    print("Verified diagnostic release exported; website source unchanged")


if __name__ == "__main__":
    main()
