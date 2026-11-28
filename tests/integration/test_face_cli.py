"""End-to-end tests of every ``studio face`` command (in-process CLI)."""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
import yaml

from studio.cli import main
from tests.conftest import CONFIG_DIR

CID = "chr_mira-vale"
ALIGNMENT = {
    "schema_version": 1,
    "source": {"provider": "manual", "model": "hand-timed test"},
    "language": "en",
    "duration": 1.0,
    "transcript": "hello",
    "words": [{"word": "hello", "start": 0.1, "end": 0.6}],
    "phonemes": [
        {"phoneme": "HH", "start": 0.1, "end": 0.18},
        {"phoneme": "AH0", "start": 0.18, "end": 0.3},
        {"phoneme": "L", "start": 0.3, "end": 0.38},
        {"phoneme": "OW1", "start": 0.38, "end": 0.6},
    ],
}


def run(capsys, *args: str) -> tuple[int, str, str]:
    code = main(["--config-dir", str(CONFIG_DIR), *args])
    out, err = capsys.readouterr()
    return code, out, err


@pytest.fixture
def proj(capsys, tmp_path: Path) -> str:
    run(capsys, "new", "film", "--projects-dir", str(tmp_path))
    path = str(tmp_path / "film")
    run(capsys, "character", "create", path, "Mira Vale")
    code, out, _ = run(capsys, "face", "create", path, CID)
    assert code == 0, out
    return path


@pytest.fixture
def alignment(tmp_path: Path) -> Path:
    path = tmp_path / "hello.alignment.json"
    path.write_text(json.dumps(ALIGNMENT))
    return path


@pytest.fixture
def lipsync(capsys, alignment: Path, tmp_path: Path) -> Path:
    out = tmp_path / "hello.lipsync.yaml"
    assert run(capsys, "face", "phonemes", "map", str(alignment), "--out", str(out))[0] == 0
    return out


def test_create_info_validate(capsys, proj: str) -> None:
    code, out, _ = run(capsys, "face", "info", proj, CID)
    assert code == 0 and "face_mira_vale v1" in out and "eye_l" in out and "blink[0..1]=0" in out
    info = json.loads(run(capsys, "face", "info", proj, CID, "--json")[1])
    assert len(info["components"]) == 9
    code, out, _ = run(capsys, "face", "validate", proj, CID)
    assert code == 0 and "VALID" in out and "FAC012" in out
    code, _, err = run(capsys, "face", "create", proj, CID)
    assert code == 1 and "already has" in err
    run(capsys, "character", "create", proj, "Bo")
    code, _, err = run(capsys, "face", "info", proj, "chr_bo")
    assert code == 1 and "no facial rig" in err


def test_face_errors_reported_by_validate(capsys, proj: str) -> None:
    path = Path(proj) / "characters" / CID / "face.yaml"
    data = yaml.safe_load(path.read_text())
    data["components"][0]["attachment"] = {"part": "tail"}
    path.write_text(yaml.safe_dump(data))
    code, out, _ = run(capsys, "face", "validate", proj, CID)
    assert code == 1 and "FAC006" in out
    code, out, _ = run(capsys, "project", "validate", proj)
    assert code == 1 and "FAC006" in out


def test_set_asset(capsys, proj: str, samples) -> None:
    _, out, _ = run(
        capsys,
        "asset",
        "register",
        proj,
        str(samples["svg"]),
        "--name",
        "eye",
        "--category",
        "character",
    )
    aid = out.split()[1]
    code, out, _ = run(capsys, "face", "set-asset", proj, CID, "eye_l", aid)
    assert code == 0 and "v2" in out
    code, out, _ = run(capsys, "face", "set-asset", proj, CID, "mouth", aid, "--shape", "ai")
    assert code == 0 and "shape ai" in out
    code, _, err = run(capsys, "face", "set-asset", proj, CID, "mouth", aid, "--shape", "zz")
    assert code == 1 and "no shape" in err


def test_expressions_list_create_set(capsys, proj: str) -> None:
    code, out, _ = run(capsys, "face", "expressions", "list", proj, CID)
    assert code == 0 and "12 expression(s)" in out and "errors=0" in out
    code, out, _ = run(
        capsys,
        "face",
        "expressions",
        "create",
        proj,
        CID,
        "smug",
        "--name",
        "Smug",
        "--from",
        "happy",
        "--set",
        "mouth.corner_r=-0.2",
        "--shape",
        "mouth=e",
    )
    assert code == 0 and "created expression smug v1" in out
    code, out, _ = run(
        capsys, "face", "expressions", "set", proj, CID, "smug", "--set", "eye_l.blink=0.4"
    )
    assert code == 0 and "v2" in out
    rows = json.loads(run(capsys, "face", "expressions", "list", proj, CID, "--json")[1])
    assert {r["id"] for r in rows if r["kind"] == "custom"} == {"smug"}
    for bad in (
        ["--set", "mouth.open"],
        ["--set", "mouth.open=x"],
        ["--set", "tail.wag=1"],
        ["--shape", "mouth"],
    ):
        code, _, err = run(
            capsys, "face", "expressions", "create", proj, CID, "bad", "--name", "B", *bad
        )
        assert code == 1 and err.startswith("error:"), bad


def test_expression_preview_and_blend(capsys, proj: str, tmp_path: Path) -> None:
    code, out, _ = run(capsys, "face", "expressions", "preview", proj, CID, "happy", "sad")
    assert code == 0 and "2 panel(s)" in out
    svg = Path(proj) / "renders" / "previews" / f"{CID}-face-happy-sad.svg"
    root = ET.fromstring(svg.read_text())
    assert "not continuous animation" in root.find("{http://www.w3.org/2000/svg}title").text
    data = json.loads(
        run(capsys, "face", "expressions", "preview", proj, CID, "surprised", "--json")[1]
    )
    assert data["expression surprised"]["geometry"]["mouth"]["params"]["gap"] > 0
    code, out, _ = run(
        capsys,
        "face",
        "expressions",
        "blend",
        proj,
        CID,
        "neutral",
        "happy",
        "--weight",
        "0.5",
        "--out",
        str(tmp_path / "b.svg"),
    )
    assert code == 0 and "mouth.corner_l" in out and "0.4000" in out
    assert (tmp_path / "b.svg").is_file()
    state = json.loads(
        run(
            capsys,
            "face",
            "expressions",
            "blend",
            proj,
            CID,
            "neutral",
            "happy",
            "--weight",
            "2",
            "--json",
        )[1]
    )
    assert any(i["code"] == "BLD002" for i in state["issues"])
    code, _, err = run(
        capsys, "face", "expressions", "blend", proj, CID, "neutral", "nope", "--weight", "0.5"
    )
    assert code == 1 and "unknown expression" in err
    code, _, err = run(
        capsys, "face", "expressions", "blend", proj, CID, "neutral", "happy", "--weight", "nan"
    )
    assert code == 1 and "finite" in err


def test_visemes_and_maps(capsys) -> None:
    code, out, _ = run(capsys, "face", "visemes", "list")
    assert code == 0 and "mbp" in out and "tongue" in out
    assert json.loads(run(capsys, "face", "visemes", "list", "--json")[1])["rest"] == "rest"
    code, out, _ = run(capsys, "face", "phonemes", "maps")
    assert code == 0 and "en_arpabet" in out and "ipa_basic" in out


def test_phonemes_map(capsys, alignment: Path, tmp_path: Path) -> None:
    code, out, _ = run(capsys, "face", "phonemes", "map", str(alignment))
    assert code == 0 and "4 phonemes -> 5 viseme events" in out
    track = json.loads(
        run(
            capsys,
            "face",
            "phonemes",
            "map",
            str(alignment),
            "--json",
            "--coarticulation",
            "0.3",
            "--character",
            CID,
        )[1]
    )
    assert track["settings"]["coarticulation"] == 0.3 and track["character_id"] == CID
    bad = tmp_path / "bad.json"
    data = json.loads(json.dumps(ALIGNMENT))
    data["phonemes"][1]["start"] = 0.15  # overlaps the previous phoneme (0.1-0.18)
    bad.write_text(json.dumps(data))
    code, _, err = run(capsys, "face", "phonemes", "map", str(bad))
    assert code == 1 and "LIP002" in err
    words_only = tmp_path / "words.json"
    data = {**ALIGNMENT, "phonemes": []}
    words_only.write_text(json.dumps(data))
    code, _, err = run(capsys, "face", "phonemes", "map", str(words_only))
    assert code == 1 and "LIP008" in err
    data = json.loads(json.dumps(ALIGNMENT))
    data["phonemes"][0]["phoneme"] = "QQ"
    unk = tmp_path / "unk.json"
    unk.write_text(json.dumps(data))
    code, out, _ = run(capsys, "face", "phonemes", "map", str(unk))
    assert code == 0 and "LIP005" in out


def test_lipsync_validate_evaluate_preview(capsys, proj: str, lipsync: Path) -> None:
    code, out, _ = run(capsys, "face", "lipsync", "validate", str(lipsync))
    assert code == 0 and "VALID" in out
    code, out, _ = run(
        capsys, "face", "lipsync", "evaluate", str(lipsync), "--time", "0.3", "--time", "0.65"
    )
    assert code == 0 and "segment=l" in out and "segment=rest" in out
    states = json.loads(
        run(capsys, "face", "lipsync", "evaluate", str(lipsync), "--sample", "0.1", "--json")[1]
    )
    assert len(states) == 11 and states[0]["viseme"] == "rest"
    code, out, _ = run(
        capsys,
        "face",
        "lipsync",
        "preview",
        proj,
        CID,
        str(lipsync),
        "--sample",
        "0.2",
        "--expression",
        "happy",
    )
    assert code == 0 and "6 sampled state(s)" in out
    code, _, err = run(capsys, "face", "lipsync", "evaluate", str(lipsync))
    assert code == 1 and "--time" in err
    code, _, err = run(capsys, "face", "lipsync", "evaluate", str(lipsync), "--time", "-1")
    assert code == 1 and "time must be" in err
    data = yaml.safe_load(lipsync.read_text())
    data["events"][1]["viseme"] = "zz"
    lipsync.write_text(yaml.safe_dump(data))
    code, out, _ = run(capsys, "face", "lipsync", "validate", str(lipsync))
    assert code == 1 and "LIP006" in out


def test_alignment_inspect_and_run(
    capsys, proj: str, alignment: Path, tmp_path: Path, samples
) -> None:
    code, out, _ = run(capsys, "face", "alignment", "inspect", str(alignment))
    assert code == 0 and "lip_sync_ready: True" in out
    code, _, err = run(capsys, "face", "alignment", "run", str(samples["wav"]), "--text", "hello")
    assert code == 1 and "disabled" in err  # default provider: none
    settings = Path(proj) / "settings.yaml"
    settings.write_text(
        settings.read_text().replace("providers: {}", "providers:\n  asr:\n    provider: mock")
    )
    out_file = tmp_path / "mock.alignment.json"
    code, out, _ = run(
        capsys,
        "face",
        "alignment",
        "run",
        str(samples["wav"]),
        "--text",
        "hello there",
        "--project",
        proj,
        "--out",
        str(out_file),
    )
    assert code == 0 and "2 words, 0 phonemes" in out and "cannot drive lip-sync" in out
    code, out, _ = run(capsys, "face", "alignment", "inspect", str(out_file))
    assert code == 0 and "lip_sync_ready: False" in out


def test_schema_exports_and_existing_commands(capsys, proj: str) -> None:
    for name in (
        "facial_rig",
        "facial_control",
        "facial_component",
        "facial_expression",
        "expression_blend",
        "viseme",
        "viseme_set",
        "phoneme_map",
        "phoneme_event",
        "viseme_event",
        "lipsync_track",
        "alignment_result",
        "character_definition",
    ):
        code, out, _ = run(capsys, "schema", "export", name)
        assert code == 0 and "properties" in json.loads(out)[name], name
    for args in (
        ("character", "validate", proj),
        ("character", "rig", "fk", proj, CID),
        ("project", "validate", proj),
        ("modules",),
        ("version",),
    ):
        assert run(capsys, *args)[0] == 0, args
