from __future__ import annotations

from datetime import UTC, datetime

import pytest

from studio.core.exceptions import SchemaValidationError
from studio.core.registry import AssetRegistry
from studio.core.schemas import (
    SCHEMAS,
    AssetRecord,
    AssetRegistryFile,
    AssetVersion,
    CharacterIdentity,
    EnvironmentMetadata,
    ProviderSelection,
)
from studio.core.validation import parse_model

NOW = datetime(2026, 11, 27, tzinfo=UTC)
PRJ = "prj_" + "a" * 32
HASH = "sha256:" + "0" * 64


def _version(n: int = 1, **kw) -> dict:
    return {
        "version": n,
        "path": f"assets/x.v{n}.svg",
        "content_hash": HASH,
        "size_bytes": 10,
        "created_at": NOW,
    } | kw


def _record(**kw) -> dict:
    return {
        "id": "ast_0123456789abcdef",
        "name": "x",
        "category": "prop",
        "format": "svg",
        "project_id": PRJ,
        "versions": [_version()],
        "created_at": NOW,
        "updated_at": NOW,
    } | kw


def test_asset_record_valid() -> None:
    record = AssetRecord.model_validate(_record())
    assert record.current_version == 1


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"id": "asset-1"}, "id"),
        ({"versions": []}, "versions"),
        ({"versions": [_version(2)]}, "numbered 1..n"),
        ({"versions": [_version(1, content_hash="md5:abc")]}, "sha256"),
        ({"versions": [_version(1, path="/abs/x.svg")]}, "relative"),
        ({"versions": [_version(1, path="../x.svg")]}, "'..'"),
        ({"source": {"kind": "ai_generated"}}, "ai_provenance"),
        ({"dependencies": ["ast_0123456789abcdef"]}, "itself"),
        ({"category": "hologram"}, "category"),
        ({"surprise": 1}, "unknown field"),
    ],
)
def test_asset_record_invalid(change: dict, message: str) -> None:
    with pytest.raises(SchemaValidationError, match=message):
        parse_model(AssetRecord, _record(**change), "record")


def test_registry_rejects_duplicate_ids_and_foreign_assets() -> None:
    with pytest.raises(SchemaValidationError, match="more than once"):
        parse_model(AssetRegistryFile, {"project_id": PRJ, "assets": [_record(), _record()]}, "r")
    with pytest.raises(SchemaValidationError, match="belongs to"):
        parse_model(
            AssetRegistryFile,
            {"project_id": PRJ, "assets": [_record(project_id="prj_" + "b" * 32)]},
            "r",
        )


def test_registry_save_is_sorted_and_atomic(tmp_path) -> None:
    path = tmp_path / "registry.json"
    reg = AssetRegistry.create(path, PRJ)
    for suffix in ("f", "1", "a"):
        reg.add(AssetRecord.model_validate(_record(id="ast_" + suffix * 16)))
    reg.save()
    text = path.read_text()
    assert text.index("ast_1111") < text.index("ast_aaaa") < text.index("ast_ffff")
    assert not list(tmp_path.glob(".*.tmp"))
    assert len(AssetRegistry.load(path)) == 3


def _character(**kw) -> dict:
    return {"id": "chr_mira", "name": "Mira", "proportions": {"height_heads": 4.5}} | kw


def test_character_identity() -> None:
    c = CharacterIdentity.model_validate(_character(palette={"skin": "#f2c9a0"}))
    assert c.palette["skin"] == "#F2C9A0"
    assert [v.value for v in c.required_views] == ["front", "three_quarter", "side", "back"]


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"original_design": False}, "original"),
        ({"required_views": ["side"]}, "front"),
        ({"required_views": ["front", "front"]}, "duplicates"),
        ({"status": "rigged"}, "rig_asset"),
        ({"palette": {"skin": "peach"}}, "#RRGGBB"),
        ({"proportions": {"height_heads": 40}}, "height_heads"),
        ({"id": "mira"}, "id"),
    ],
)
def test_character_identity_invalid(change: dict, message: str) -> None:
    with pytest.raises(SchemaValidationError, match=message):
        parse_model(CharacterIdentity, _character(**change), "character.yaml")


def test_environment_metadata() -> None:
    env = EnvironmentMetadata.model_validate(
        {
            "id": "env_forest",
            "name": "Forest",
            "layers": [{"name": "sky", "depth": 0.2}, {"name": "trees", "depth": 0.7}],
        }
    )
    assert len(env.layers) == 2
    with pytest.raises(SchemaValidationError, match="unique"):
        parse_model(
            EnvironmentMetadata,
            {
                "id": "env_x1",
                "name": "X",
                "layers": [{"name": "a", "depth": 1}, {"name": "a", "depth": 2}],
            },
            "env",
        )


def test_provider_selection_rules() -> None:
    assert ProviderSelection().provider == "none"
    with pytest.raises(SchemaValidationError, match="secret"):
        parse_model(ProviderSelection, {"provider": "mock", "options": {"ApiKey": "x"}}, "p")
    with pytest.raises(SchemaValidationError, match="credentials_env"):
        parse_model(ProviderSelection, {"credentials_env": ["lowercase"]}, "p")


def test_every_schema_has_version_and_exports_json_schema() -> None:
    for name, model in SCHEMAS.items():
        schema = model.model_json_schema()
        assert schema["type"] == "object", name
        if name != "asset_registry":
            assert "schema_version" in schema["properties"], name
    assert "schema_version" in AssetRegistryFile.model_json_schema()["properties"]


def test_error_messages_are_readable() -> None:
    with pytest.raises(SchemaValidationError) as err:
        parse_model(AssetVersion, {"version": 0}, "v")
    problems = err.value.problems
    assert "path: required field is missing" in problems
    assert any(p.startswith("version:") for p in problems)
    assert "v is not valid" in str(err.value)
