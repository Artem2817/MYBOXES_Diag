import importlib.util
import json
import hashlib
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("package_release", ROOT / "tools/package_release.py")
package = importlib.util.module_from_spec(spec)
spec.loader.exec_module(package)


def test_release_export_preserves_bytes_and_never_replaces_site(tmp_path):
    site = tmp_path / "site"
    (site / "diagnostics").mkdir(parents=True)
    index = dict(version="0.2.2", profiles=[])
    for i in range(3):
        name = f"diagnostics/board{i}.hex"
        data = f"test fixture {i}".encode()
        (site / name).write_bytes(data)
        index["profiles"].append(dict(profile=f"board{i}", file=name, sha256=hashlib.sha256(data).hexdigest()))
    data = b"application fixture"
    (site / "diagnostics/app.exe").write_bytes(data)
    index.update(windows_exe="diagnostics/app.exe", windows_sha256=hashlib.sha256(data).hexdigest())
    path = site / "diagnostic-index.json"
    path.write_text(json.dumps(index))
    before = path.read_bytes()
    result = package.export(path, tmp_path / "release")
    assert path.read_bytes() == before
    assert result["windows_exe"].startswith("https://github.com/Artem2817/MYBOXES_Diag/releases/")
    sums = (tmp_path / "release/SHA256SUMS.txt").read_text().splitlines()
    for line in sums:
        digest, name = line.split("  ", 1)
        assert hashlib.sha256((tmp_path / "release" / name).read_bytes()).hexdigest() == digest
    with pytest.raises(ValueError, match="separate"):
        package.export(path, site / "nested")
    (site / "diagnostics/app.exe").write_bytes(b"corruption")
    with pytest.raises(ValueError, match="checksum mismatch"):
        package.export(path, tmp_path / "other")
