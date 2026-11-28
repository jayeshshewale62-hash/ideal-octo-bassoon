"""End-to-end tests of every ``studio animation`` command (in-process CLI)."""

from __future__ import annotations

import json
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
import yaml

from studio.cli import main
from tests.conftest import CONFIG_DIR, REPO_ROOT

CID = "chr_mira-vale"
ALIGNMENT = REPO_ROOT / "docs" / "examples" / "chr_mira-vale" / "hello.alignment.json"


def run(capsys, *args: str) -> tuple[int, str, str]:
    code = main(["--config-dir", str(CONFIG_DIR), *args])
    out, err = capsys.readouterr()
    return code, out, err


@pytest.fixture
def proj(capsys, tmp_path: Path) -> str:
    run(capsys, "new", "film", "--projects-dir", str(tmp_path))
    path = str(tmp_path / "film")
    run(capsys, "character", "create", path, "Mira Vale")
    run(capsys, "face", "create", path, CID)
    return path


def anim_dir(proj: str) -> Path:
    return Path(proj) / "characters" / CID / "animations"


def test_generate_list_info(capsys, proj: str) -> None:
    for kind in ("walk", "run", "idle", "wave", "point", "nod"):
        code, out, err = run(capsys, "animation", "cycles", "generate", proj, CID, kind)
        assert code == 0 and f"generated {kind}" in out, err
    code, out, _ = run(capsys, "animation", "cycles", "list")
    assert code == 0 and "walk" in out and "nod" in out
    code, out, _ = run(capsys, "animation", "list", proj, CID)
    assert code == 0 and "6 clip(s)" in out
    data = json.loads(run(capsys, "animation", "list", proj, CID, "--json")[1])
    assert {c["id"] for c in data["clips"]} == {"walk", "run", "idle", "wave", "point", "nod"}
    code, out, _ = run(capsys, "animation", "info", proj, CID, "walk")
    assert code == 0 and "cycle walk: facing left" in out and "track ik:leg_l" in out
    info = json.loads(run(capsys, "animation", "info", proj, CID, "run", "--json")[1])
    assert "ik:leg_r.x" in info["channels"]
    code, _, err = run(capsys, "animation", "cycles", "generate", proj, CID, "walk")
    assert code == 1 and "--replace" in err
    code, out, _ = run(
        capsys, "animation", "cycles", "generate", proj, CID, "walk", "--speed", "500", "--replace"
    )
    assert code == 0 and "walk v2" in out and "speed 500" in out
    assert (
        Path(proj) / "characters" / CID / "history" / "animations" / "clips" / "walk.v1.yaml"
    ).is_file()
    code, _, err = run(
        capsys,
        "animation",
        "cycles",
        "generate",
        proj,
        CID,
        "walk",
        "--id",
        "w2",
        "--speed",
        "2000",
    )
    assert code == 1 and err.startswith("error:")
    code, _, err = run(
        capsys,
        "animation",
        "cycles",
        "generate",
        proj,
        CID,
        "walk",
        "--id",
        "w3",
        "--param",
        "wobble=2",
    )
    assert code == 1 and "unknown cycle parameter" in err


def test_create_keys_events_versions(capsys, proj: str) -> None:
    code, out, _ = run(
        capsys, "animation", "create", proj, CID, "greet", "--duration", "2", "--fps", "30"
    )
    assert code == 0
    steps = [
        ("bone:neck", "--frame", "15", "--set", "rotation=10", "--interp", "ease_in_out"),
        ("bone:neck", "--time", "0", "--set", "rotation=0"),
        ("expression", "--time", "0", "--expression", "neutral"),
        (
            "expression",
            "--time",
            "1",
            "--expression",
            "happy",
            "--weight",
            "0.8",
            "--interp",
            "smooth",
        ),
        ("face", "--time", "1.4", "--set", "eye_l.blink=0"),
        ("face", "--time", "1.5", "--set", "eye_l.blink=1"),
        ("part:hair", "--time", "1", "--set", "rotation=5", "--set", "visible=true"),
        ("root", "--time", "1", "--set", "x=20"),
        (
            "ik:arm_l",
            "--time",
            "1",
            "--set",
            "x=150",
            "--set",
            "y=400",
            "--interp",
            "bezier",
            "--bezier",
            "0.25",
            "0.1",
            "0.25",
            "1",
        ),
    ]
    for i, (target, *rest) in enumerate(steps):
        code, out, err = run(capsys, "animation", "key", "set", proj, CID, "greet", target, *rest)
        assert code == 0, (target, err)
        assert f"v{i + 2}" in out
    code, _, err = run(
        capsys,
        "animation",
        "key",
        "set",
        proj,
        CID,
        "greet",
        "bone:neck",
        "--frame",
        "15",
        "--set",
        "rotation=4",
    )
    assert code == 1 and "already has a key" in err
    assert (
        run(
            capsys,
            "animation",
            "key",
            "set",
            proj,
            CID,
            "greet",
            "bone:neck",
            "--frame",
            "15",
            "--set",
            "rotation=4",
            "--replace",
        )[0]
        == 0
    )
    code, _, err = run(
        capsys,
        "animation",
        "key",
        "set",
        proj,
        CID,
        "greet",
        "bone:neck",
        "--time",
        "9",
        "--set",
        "rotation=4",
    )
    assert code == 1 and "after the clip end" in err
    code, _, err = run(capsys, "animation", "key", "set", proj, CID, "greet", "wing", "--time", "0")
    assert code == 1 and "unknown target" in err
    code, _, err = run(
        capsys,
        "animation",
        "key",
        "set",
        proj,
        CID,
        "greet",
        "bone:neck",
        "--time",
        "0.1",
        "--set",
        "rotation=1",
        "--interp",
        "bezier",
        "--bezier",
        "0.2",
        "-1",
        "0.5",
        "1",
    )
    assert code == 1 and "overshoot" in err
    code, out, _ = run(
        capsys, "animation", "key", "remove", proj, CID, "greet", "bone:neck", "--time", "0"
    )
    assert code == 0 and "removed key" in out
    code, out, _ = run(
        capsys,
        "animation",
        "events",
        "add",
        proj,
        CID,
        "greet",
        "--kind",
        "expression_change",
        "--name",
        "smile",
        "--time",
        "1",
    )
    assert code == 0
    rows = json.loads(run(capsys, "animation", "events", "list", proj, CID, "greet", "--json")[1])
    assert rows == [{"time": 1.0, "kind": "expression_change", "name": "smile", "data": {}}]
    code, out, _ = run(capsys, "animation", "validate", proj, CID)
    assert code == 0 and "VALID" in out


def test_evaluate_preview_blend(capsys, proj: str, tmp_path: Path) -> None:
    for kind in ("walk", "run", "idle"):
        run(capsys, "animation", "cycles", "generate", proj, CID, kind)
    code, out, _ = run(
        capsys, "animation", "evaluate", proj, CID, "--clip", "walk", "--time", "0", "--time", "0.6"
    )
    assert (
        code == 0
        and "IK leg_l" in out
        and "reached" in out
        and "event foot_contact contact_l" in out
    )
    states = json.loads(
        run(
            capsys,
            "animation",
            "evaluate",
            proj,
            CID,
            "--clip",
            "walk",
            "--sample",
            "0.25",
            "--json",
            "--parts",
        )[1]
    )
    assert len(states) == 5 and states[0]["layers"][0]["phase"] == 0 and "parts" in states[0]
    code, out, _ = run(
        capsys, "animation", "preview", proj, CID, "--clip", "run", "--sample", "0.1"
    )
    assert code == 0 and "still diagnostics" in out
    sheet = Path(proj) / "renders" / "previews" / f"{CID}-anim-run.svg"
    root = ET.fromstring(sheet.read_text())
    ns = "{http://www.w3.org/2000/svg}"
    assert "not animation" in root.find(f"{ns}title").text
    assert len(root.findall(f".//{ns}g[@class='frame']")) == 8
    assert root.findall(f".//{ns}line[@class='key']") and root.findall(
        f".//{ns}path[@class='event']"
    )
    code, out, _ = run(
        capsys,
        "animation",
        "blend",
        proj,
        CID,
        "walk",
        "run",
        "--weight",
        "0.3",
        "--time",
        "0.1",
        "--out",
        str(tmp_path / "b.svg"),
    )
    assert (
        code == 0
        and "normalized weights walk=0.7 run=0.3" in out
        and (tmp_path / "b.svg").is_file()
    )
    code, _, err = run(capsys, "animation", "blend", proj, CID, "walk", "run", "--weight", "1.5")
    assert code == 1 and "within [0, 1]" in err
    code, _, err = run(capsys, "animation", "evaluate", proj, CID, "--clip", "walk")
    assert code == 1 and "--time" in err
    code, _, err = run(capsys, "animation", "evaluate", proj, CID, "--clip", "zz", "--time", "0")
    assert code == 1 and "no clip" in err


def test_sets_lipsync_springs_meshes(capsys, proj: str) -> None:
    for kind in ("walk", "idle"):
        run(capsys, "animation", "cycles", "generate", proj, CID, kind)
    track = Path(proj) / "audio" / "hello.lipsync.yaml"
    track.parent.mkdir(exist_ok=True)
    assert run(capsys, "face", "phonemes", "map", str(ALIGNMENT), "--out", str(track))[0] == 0
    code, out, _ = run(
        capsys,
        "animation",
        "mesh",
        "create",
        proj,
        CID,
        "torso",
        "--part",
        "upper_torso",
        "--grid",
        "3x2",
        "--bones",
        "spine,upper_arm_l",
    )
    assert code == 0 and "12 vertices" in out
    assert run(capsys, "animation", "mesh", "validate", proj, CID)[0] == 0
    assert "triangles" in run(capsys, "animation", "mesh", "show", proj, CID, "torso")[1]
    code, _, err = run(
        capsys,
        "animation",
        "mesh",
        "create",
        proj,
        CID,
        "bad",
        "--part",
        "upper_torso",
        "--grid",
        "x",
    )
    assert code == 1 and "--grid" in err
    code, out, err = run(
        capsys,
        "animation",
        "set",
        "create",
        proj,
        CID,
        "perf",
        "--layer",
        "walk",
        "--layer",
        "idle:0.5:additive:upper_body",
        "--lipsync-path",
        "audio/hello.lipsync.yaml",
        "--springs",
        "--mesh",
        "torso",
    )
    assert code == 0 and "springs=3" in out, err
    code, out, _ = run(capsys, "animation", "evaluate", proj, CID, "--set", "perf", "--time", "0.3")
    assert code == 0 and "lipsync: segment l" in out and "mesh torso" in out
    code, out, _ = run(capsys, "animation", "validate", proj, CID, "perf")
    assert code == 0
    # path traversal in a lip-sync path is refused
    code, _, err = run(
        capsys,
        "animation",
        "set",
        "create",
        proj,
        CID,
        "evil",
        "--layer",
        "walk",
        "--lipsync-path",
        "../../etc/passwd",
    )
    assert code == 1 and "'..'" in err
    code, _, err = run(
        capsys, "animation", "set", "create", proj, CID, "bad", "--layer", "walk:1:override:wings"
    )
    assert code == 1 and "SET005" in err


def test_lipsync_from_registered_asset(capsys, proj: str, tmp_path: Path) -> None:
    run(capsys, "animation", "cycles", "generate", proj, CID, "idle")
    track = tmp_path / "hello.lipsync.yaml"
    run(capsys, "face", "phonemes", "map", str(ALIGNMENT), "--out", str(track))
    _, out, _ = run(
        capsys,
        "asset",
        "register",
        proj,
        str(track),
        "--name",
        "hello lipsync",
        "--category",
        "voice",
    )
    asset = out.split()[1]
    code, out, err = run(
        capsys,
        "animation",
        "set",
        "create",
        proj,
        CID,
        "talk",
        "--layer",
        "idle",
        "--lipsync-asset",
        asset,
        "--lipsync-start",
        "0.5",
    )
    assert code == 0, err
    code, out, _ = run(
        capsys,
        "animation",
        "evaluate",
        proj,
        CID,
        "--set",
        "talk",
        "--time",
        "0.2",
        "--time",
        "0.8",
    )
    assert code == 0 and out.count("lipsync:") == 1  # silent before the start offset


def test_validation_reports_broken_files(capsys, proj: str, settings) -> None:
    run(capsys, "animation", "cycles", "generate", proj, CID, "walk")
    path = anim_dir(proj) / "clips" / "walk.yaml"
    data = yaml.safe_load(path.read_text())
    data["tracks"][0]["bone"] = "wing"
    path.write_text(yaml.safe_dump(data))
    shutil.copy(path, anim_dir(proj) / "clips" / "renamed.yaml")
    code, out, _ = run(capsys, "animation", "validate", proj, CID)
    assert code == 1 and "ANM004" in out and "ANM002" in out
    code, out, _ = run(capsys, "project", "validate", proj)  # Milestone 2 command covers animations
    assert code == 1 and "ANM004" in out


def test_schema_exports_and_regressions(capsys, proj: str) -> None:
    for name in (
        "animation_clip",
        "animation_channel",
        "keyframe",
        "transform_keyframe",
        "bone_keyframe",
        "control_keyframe",
        "deformation_keyframe",
        "curve_definition",
        "animation_event",
        "loop_settings",
        "playback_settings",
        "animation_layer",
        "blend_settings",
        "motion_cycle",
        "animation_set",
        "deform_mesh",
        "spring_definition",
        "facial_rig",
        "rig",
    ):
        code, out, _ = run(capsys, "schema", "export", name)
        assert code == 0 and "properties" in json.loads(out)[name], name
    for args in (
        ("version",),
        ("modules",),
        ("project", "validate", proj),
        ("character", "validate", proj),
        ("face", "validate", proj, CID),
        ("character", "rig", "fk", proj, CID),
    ):
        assert run(capsys, *args)[0] == 0, args
