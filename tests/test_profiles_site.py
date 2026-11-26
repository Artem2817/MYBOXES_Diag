"""Hardware snapshots and packaged PC profiles must remain consistent."""
from pathlib import Path
import json
import hashlib
ROOT = Path(__file__).resolve().parents[1]


def test_profiles_match_sources_and_pin_functions_are_unique():
    for path in (ROOT / "profiles").glob("*.json"):
        data = json.loads(path.read_text())
        source = ROOT / "hardware" / data["id"] / "hwdef.dat"
        assert hashlib.sha256(source.read_bytes()).hexdigest() == data["hwdef_sha256"]
        assert len({v["pin"] for v in data["pins"]}) == len(data["pins"])
        assert len(data["outputs"]) == (14 if data["index"] == 0 else 13)
        assert [v["channel"] for v in data["outputs"]] == list(range(1, len(data["outputs"]) + 1))
        assert len(data["imus"]) == (2 if data["index"] == 2 else 1)
        assert data == json.loads((ROOT / "pc/mybox_diag/profiles" / path.name).read_text())


def test_hardware_snapshot_has_exact_recorded_provenance():
    source = json.loads((ROOT / "hardware/SOURCE.json").read_text())
    for item in source["files"]:
        assert hashlib.sha256((ROOT / item["path"]).read_bytes()).hexdigest() == item["sha256"]
    assert source["platform_commit"] == json.loads((ROOT / "release.json").read_text())["platform_commit"]
