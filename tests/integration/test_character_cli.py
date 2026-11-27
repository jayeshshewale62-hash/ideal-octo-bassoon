"""End-to-end tests of every ``studio character`` command (in-process CLI)."""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
import yaml

from studio.cli import main
from tests.conftest import CONFIG_DIR

CID = "chr_mira-vale"


def run(capsys, *args: str) -> tuple[int, str, str]:
    code = main(["--config-dir", str(CONFIG_DIR), *args])
    out, err = capsys.readouterr()
    return code, out, err


@pytest.fixture
def proj(capsys, tmp_path: Path) -> str:
    assert run(capsys, "new", "film", "--projects-dir", str(tmp_path))[0] == 0
    path = str(tmp_path / "film")
    code, out, _ = run(capsys, "character", "create", path, "Mira Vale", "--description", "test")
    assert code == 0, out
    return path


def test_templates(capsys) -> None:
    code, out, _ = run(capsys, "character", "templates")
    assert code == 0 and "biped" in out and "biped-minimal" in out
    assert {t["name"] for t in json.loads(run(capsys, "character", "templates", "--json")[1])} == {
        "biped",
        "biped-minimal",
    }


def test_create_output_and_files(capsys, proj: str) -> None:
    folder = Path(proj) / "characters" / CID
    assert (folder / "character.yaml").is_file() and (folder / "rig.yaml").is_file()
    code, out, _ = run(
        capsys,
        "character",
        "create",
        proj,
        "Bo",
        "--template",
        "biped-minimal",
        "--height-heads",
        "4",
    )
    assert code == 0 and "created character chr_bo" in out and "VALID" in out
    assert "no artwork was created" in out


def test_create_errors(capsys, proj: str) -> None:
    code, _, err = run(capsys, "character", "create", proj, "Mira Vale")
    assert code == 1 and "already exists" in err
    code, _, err = run(capsys, "character", "create", proj, "X", "--id", "bad id")
    assert code == 1 and "invalid character id" in err
    code, _, err = run(capsys, "character", "create", proj, "Yara", "--height-heads", "2")
    assert code == 1 and "no room for a torso" in err
    code, _, err = run(capsys, "character", "create", proj, "Zed", "--from", "chr_nobody")
    assert code == 1 and "no character" in err
    with pytest.raises(SystemExit) as exc:
        main(["character", "create", proj, "Q", "--template", "dragon"])
    assert exc.value.code == 2


def test_list_info_validate(capsys, proj: str) -> None:
    code, out, _ = run(capsys, "character", "list", proj)
    assert code == 0 and CID in out and "1 character(s)" in out
    rows = json.loads(run(capsys, "character", "list", proj, "--json")[1])
    assert rows[0]["parts"] == 21 and rows[0]["version"] == 1
    code, out, _ = run(capsys, "character", "info", proj, CID)
    assert code == 0 and "rig rig_mira_vale" in out and "upper_arm_l" in out
    info = json.loads(run(capsys, "character", "info", proj, CID, "--json")[1])
    assert info["rig"]["root"] == "root"
    code, out, _ = run(capsys, "character", "validate", proj)
    assert code == 0 and "VALID" in out
    data = json.loads(run(capsys, "character", "validate", proj, CID, "--json")[1])
    assert data["ok"] is True and data["errors"] == 0
    code, _, err = run(capsys, "character", "info", proj, "chr_ghost")
    assert code == 1 and "no character" in err


def test_validate_reports_errors(capsys, proj: str) -> None:
    rig = Path(proj) / "characters" / CID / "rig.yaml"
    data = yaml.safe_load(rig.read_text())
    data["bones"][5]["parent"] = "missing_bone"
    rig.write_text(yaml.safe_dump(data))
    code, out, _ = run(capsys, "character", "validate", proj, CID)
    assert code == 1 and "RIG004" in out and "INVALID" in out
    code, out, _ = run(capsys, "character", "rig", "validate", proj, CID)
    assert code == 1 and "RIG004" in out
    code, out, _ = run(capsys, "project", "validate", proj)  # M2 command includes characters
    assert code == 1 and "RIG004" in out


def test_rig_validate_fk_ik(capsys, proj: str) -> None:
    code, out, _ = run(capsys, "character", "rig", "validate", proj, CID)
    assert code == 0 and "VALID" in out
    code, out, _ = run(
        capsys,
        "character",
        "rig",
        "fk",
        proj,
        CID,
        "--rot",
        "forearm_l=200",
        "--parts",
        "--view",
        "side",
    )
    assert code == 0 and "CONSTRAINT forearm_l: requested 200 -> 150 (max)" in out
    assert "parts back-to-front" in out
    fk = json.loads(run(capsys, "character", "rig", "fk", proj, CID, "--json")[1])
    head = next(b for b in fk["bones"] if b["bone"] == "head")
    assert head["tip"] == [0.0, 0.0]
    code, out, _ = run(
        capsys, "character", "rig", "ik", proj, CID, "arm_l", "--target", "150", "400"
    )
    assert code == 0 and "reached" in out and "distance from end to target: 0.0" in out
    data = json.loads(
        run(
            capsys, "character", "rig", "ik", proj, CID, "leg_r", "--target", "-60", "900", "--json"
        )[1]
    )
    assert data["status"] == "reached" and data["error"] < 1e-6
    code, out, _ = run(
        capsys, "character", "rig", "ik", proj, CID, "arm_l", "--target", "2000", "0"
    )
    assert code == 3 and "too_far" in out
    code, out, _ = run(
        capsys, "character", "rig", "ik", proj, CID, "arm_l", "--target", "100", "260"
    )
    assert code == 3 and "joint limits applied" in out and "LIMIT" in out
    code, _, err = run(capsys, "character", "rig", "ik", proj, CID, "tail", "--target", "0", "0")
    assert code == 1 and "unknown IK chain" in err
    code, _, err = run(capsys, "character", "rig", "fk", proj, CID, "--rot", "wing=10")
    assert code == 1 and "unknown bones" in err
    code, _, err = run(capsys, "character", "rig", "fk", proj, CID, "--rot", "head")
    assert code == 1 and "BONE=DEGREES" in err


def test_turnaround_validate(capsys, proj: str) -> None:
    code, out, _ = run(capsys, "character", "turnaround", "validate", proj, CID)
    assert code == 0 and "TRN003" in out
    path = Path(proj) / "characters" / CID / "character.yaml"
    data = yaml.safe_load(path.read_text())
    data["turnaround"]["views"] = [v for v in data["turnaround"]["views"] if v["view"] != "back"]
    path.write_text(yaml.safe_dump(data))
    code, out, _ = run(capsys, "character", "turnaround", "validate", proj, CID)
    assert code == 1 and "TRN002" in out and "'back'" in out


def test_assets_and_compare(capsys, proj: str, samples) -> None:
    code, out, _ = run(
        capsys,
        "asset",
        "register",
        proj,
        str(samples["svg"]),
        "--name",
        "Mira head",
        "--category",
        "character",
    )
    asset_id = out.split()[1]
    code, out, _ = run(capsys, "character", "set-part-asset", proj, CID, "head", asset_id)
    assert code == 0 and "v2" in out
    code, out, _ = run(
        capsys, "character", "set-part-asset", proj, CID, "head", asset_id, "--view", "side"
    )
    assert code == 0 and "view side" in out
    code, out, _ = run(capsys, "character", "set-view-artwork", proj, CID, "front", asset_id)
    assert code == 0 and "v4" in out
    code, _, err = run(
        capsys, "character", "set-part-asset", proj, CID, "head", "ast_0000000000000000"
    )
    assert code == 1 and "no asset" in err
    code, out, _ = run(capsys, "character", "compare", proj, CID, "--version", "1")
    assert code == 0 and "no identity differences" in out and "CONSISTENT" in out  # art only
    run(capsys, "character", "create", proj, "Tomas")
    code, out, _ = run(capsys, "character", "compare", proj, CID, "--with", "chr_tomas")
    assert code == 1 and "INCONSISTENT" in out and "name" in out
    data = json.loads(
        run(capsys, "character", "compare", proj, CID, "--with", "chr_tomas", "--json")[1]
    )
    assert data["consistent"] is False
    code, _, err = run(capsys, "character", "compare", proj, CID)
    assert code == 1 and "--version" in err


def test_preview(capsys, proj: str, tmp_path: Path) -> None:
    code, out, _ = run(
        capsys, "character", "preview", proj, CID, "--view", "side", "--ik", "arm_l", "150", "400"
    )
    assert code == 0 and "not artwork and not animation" in out
    target = Path(proj) / "renders" / "previews" / f"{CID}-side-diagnostic.svg"
    root = ET.fromstring(target.read_text())
    assert root.tag.endswith("svg")
    out_file = tmp_path / "diag.svg"
    assert run(capsys, "character", "preview", proj, CID, "--out", str(out_file))[0] == 0
    code, _, err = run(capsys, "character", "preview", proj, CID, "--out", str(out_file))
    assert code == 1 and "--force" in err
    assert run(capsys, "character", "preview", proj, CID, "--out", str(out_file), "--force")[0] == 0
    code, _, err = run(capsys, "character", "preview", proj, CID, "--ik", "arm_l", "x", "1")
    assert code == 1 and "two numbers" in err


def test_preview_never_overwrites_assets(capsys, proj: str, samples) -> None:
    run(
        capsys,
        "asset",
        "register",
        proj,
        str(samples["svg"]),
        "--name",
        "Mira head",
        "--category",
        "character",
    )
    asset_path = Path(proj) / "assets" / "characters" / "mira-head.v1.svg"
    before = asset_path.read_bytes()
    code, _, err = run(
        capsys, "character", "preview", proj, CID, "--out", str(asset_path), "--force"
    )
    assert code == 1 and "registered asset" in err
    assert asset_path.read_bytes() == before


def test_schema_exports(capsys) -> None:
    for name in (
        "character_definition",
        "rig",
        "bone",
        "joint_constraint",
        "ik_chain",
        "character_part",
        "turnaround_view",
        "turnaround",
        "character_identity_profile",
        "character",
    ):
        code, out, _ = run(capsys, "schema", "export", name)
        assert code == 0 and "properties" in json.loads(out)[name], name


def test_milestone_2_commands_still_work(capsys, proj: str) -> None:
    for args in (
        ("version",),
        ("modules",),
        ("providers", "list"),
        ("config", "validate"),
        ("project", "info", proj),
        ("asset", "list", proj),
        ("asset", "validate", proj),
    ):
        assert run(capsys, *args)[0] == 0, args
    code, out, _ = run(capsys, "project", "validate", proj)
    assert code == 0 and "VALID" in out
