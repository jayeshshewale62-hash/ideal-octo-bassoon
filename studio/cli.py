"""``studio`` command-line interface (argparse, standard library only).

Exit codes: 0 success, 1 validation failure or studio error, 2 usage error.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from studio import MILESTONE, __version__
from studio.core.assets import AssetManager
from studio.core.config import Settings, configure_logging, load_settings
from studio.core.environment import run_checks
from studio.core.exceptions import StudioError
from studio.core.project import Project, validate_project
from studio.core.schemas import (
    SCHEMAS,
    AssetCategory,
    AssetLicense,
    AssetSource,
    ProjectKind,
    ProviderKind,
    SourceKind,
)
from studio.core.validation import ValidationReport
from studio.modules import MODULES
from studio.providers import list_providers, provider_status, resolve_selection

Handler = Callable[[argparse.Namespace, Settings], int]


# --- output helpers --------------------------------------------------------------------------


def _print_json(data: Any) -> None:
    print(json.dumps(data, indent=2, ensure_ascii=False, default=str))


def _print_report(report: ValidationReport, as_json: bool) -> int:
    if as_json:
        _print_json(report.to_dict())
    else:
        for issue in report.issues:
            print(issue)
        verdict = "VALID" if report.ok else "INVALID"
        print(
            f"{verdict}: {report.subject} ({report.checks} checks, "
            f"{len(report.errors)} errors, {len(report.warnings)} warnings)"
        )
    return 0 if report.ok else 1


def _table(rows: list[list[str]], headers: list[str]) -> str:
    widths = [max(len(str(x)) for x in col) for col in zip(headers, *rows, strict=False)]
    line = "  ".join(h.ljust(w) for h, w in zip(headers, widths, strict=True))
    sep = "  ".join("-" * w for w in widths)
    body = ["  ".join(str(c).ljust(w) for c, w in zip(r, widths, strict=True)) for r in rows]
    return "\n".join([line, sep, *body])


# --- commands ---------------------------------------------------------------------------------


def cmd_version(args: argparse.Namespace, settings: Settings) -> int:
    data = {
        "studio": settings.studio.studio.name,
        "version": __version__,
        "milestone": MILESTONE,
        "python": sys.version.split()[0],
        "config_dir": str(settings.config_dir) if settings.config_dir else "(built-in defaults)",
    }
    if args.json:
        _print_json(data)
    else:
        print(f"{data['studio']} {__version__} (milestone {MILESTONE}, Python {data['python']})")
        print(f"config: {data['config_dir']}")
    return 0


def cmd_doctor(args: argparse.Namespace, settings: Settings) -> int:
    checks = run_checks()
    if args.json:
        _print_json([c.__dict__ | {"state": c.state} for c in checks])
    else:
        print(_table([[c.name, c.state, c.detail] for c in checks], ["check", "state", "detail"]))
    return 0 if all(c.ok or not c.required for c in checks) else 1


def cmd_modules(args: argparse.Namespace, settings: Settings) -> int:
    if args.json:
        _print_json([m.__dict__ for m in MODULES])
        return 0
    rows = [[str(m.number), m.name, m.package, f"M{m.milestone}", m.status.value] for m in MODULES]
    print(_table(rows, ["#", "module", "package", "milestone", "status"]))
    return 0


def cmd_config_validate(args: argparse.Namespace, settings: Settings) -> int:
    source = settings.config_dir or "(built-in defaults)"
    print(f"configuration OK: {source}")
    print(
        f"  render profiles: {', '.join(sorted(settings.render_profiles.profiles))} "
        f"(default {settings.render_profiles.default})"
    )
    print(
        f"  network for providers: {'allowed' if settings.providers.allow_network else 'disabled'}"
    )
    return 0


def cmd_config_show(args: argparse.Namespace, settings: Settings) -> int:
    _print_json(
        {
            "config_dir": str(settings.config_dir) if settings.config_dir else None,
            "studio": settings.studio.model_dump(mode="json"),
            "render_profiles": settings.render_profiles.model_dump(mode="json"),
            "providers": settings.providers.model_dump(mode="json"),
        }
    )
    return 0


def cmd_new(args: argparse.Namespace, settings: Settings) -> int:
    project = Project.create(
        args.name,
        settings,
        projects_dir=Path(args.projects_dir) if args.projects_dir else None,
        title=args.title,
        kind=ProjectKind(args.kind) if args.kind else None,
        description=args.description or "",
        render_profile=args.profile,
    )
    print(f"created project {project.metadata.slug} ({project.id})")
    print(f"  location: {project.root}")
    report = validate_project(project.root, settings)
    return _print_report(report, as_json=False)


def cmd_project_validate(args: argparse.Namespace, settings: Settings) -> int:
    return _print_report(validate_project(Path(args.path), settings), args.json)


def cmd_project_info(args: argparse.Namespace, settings: Settings) -> int:
    project = Project.load(Path(args.path))
    registry = project.registry()
    meta = project.metadata
    profile = settings.profile(project.settings.render_profile)
    info = {
        "id": meta.id,
        "slug": meta.slug,
        "title": meta.title,
        "kind": meta.kind.value,
        "description": meta.description,
        "created_at": meta.created_at.isoformat(),
        "updated_at": meta.updated_at.isoformat(),
        "studio_version": meta.studio_version,
        "render_profile": project.settings.render_profile,
        "output": f"{profile.width}x{profile.height} @ {profile.fps:g} fps",
        "preview_profile": project.settings.preview_profile,
        "assets": len(registry),
        "root": str(project.root),
    }
    if args.json:
        _print_json(info)
    else:
        for key, value in info.items():
            print(f"{key:>16}: {value}")
    return 0


def cmd_asset_list(args: argparse.Namespace, settings: Settings) -> int:
    project = Project.load(Path(args.path))
    records = [
        r for r in project.registry() if not args.category or r.category.value == args.category
    ]
    if args.json:
        _print_json([r.model_dump(mode="json") for r in records])
        return 0
    if not records:
        print(f"no assets registered in {project.metadata.slug}")
        return 0
    rows = [
        [
            r.id,
            r.name,
            r.category.value,
            r.format,
            f"v{r.current_version}",
            r.current.path,
            r.current.content_hash[7:19],
            r.license.spdx,
        ]
        for r in records
    ]
    print(_table(rows, ["id", "name", "category", "format", "ver", "path", "hash", "license"]))
    print(f"{len(records)} asset(s)")
    return 0


def cmd_asset_validate(args: argparse.Namespace, settings: Settings) -> int:
    from studio.core.assets import validate_assets

    project = Project.load(Path(args.path))
    report = ValidationReport(subject=f"assets of {project.root}")
    validate_assets(project.root, project.id, report)
    return _print_report(report, args.json)


def cmd_asset_register(args: argparse.Namespace, settings: Settings) -> int:
    project = Project.load(Path(args.path))
    manager = AssetManager(project)
    result = manager.register(
        Path(args.file),
        name=args.name,
        category=AssetCategory(args.category),
        source_info=AssetSource(
            kind=SourceKind(args.source_kind), author=args.author or "", url=args.url or ""
        ),
        license=AssetLicense(spdx=args.license),
        dependencies=args.depends or [],
        tags=args.tag or [],
        note=args.note or "",
        allow_duplicate=args.allow_duplicate,
    )
    record = result.record
    action = "copied to" if result.copied else "registered in place at"
    print(f"registered {record.id} '{record.name}' v1, {action} {record.current.path}")
    print(f"  hash: {record.current.content_hash}")
    return 0


def cmd_asset_add_version(args: argparse.Namespace, settings: Settings) -> int:
    project = Project.load(Path(args.path))
    result = AssetManager(project).add_version(args.asset_id, Path(args.file), note=args.note or "")
    record = result.record
    print(f"{record.id} is now v{record.current_version}: {record.current.path}")
    return 0


def cmd_providers_list(args: argparse.Namespace, settings: Settings) -> int:
    overrides = {}
    if args.project:
        overrides = Project.load(Path(args.project)).settings.providers
    allow = settings.providers.allow_network
    active: dict[str, dict[str, str]] = {}
    for kind in ProviderKind:
        selection = resolve_selection(kind, settings.providers, overrides)
        state, detail = provider_status(kind, selection, allow_network=allow)
        active[kind.value] = {"selected": selection.provider, "state": state, "detail": detail}
    catalogue = [p.to_dict() for p in list_providers()]
    if args.json:
        _print_json({"allow_network": allow, "selected": active, "catalogue": catalogue})
        return 0
    print(f"network access for providers: {'allowed' if allow else 'disabled'}\n")
    print("Selected:")
    print(
        _table(
            [[k, v["selected"], v["state"], v["detail"]] for k, v in active.items()],
            ["kind", "provider", "state", "detail"],
        )
    )
    print("\nCatalogue:")
    rows = [
        [
            p["kind"],
            p["name"],
            p["status"] + (f" (M{p['planned_milestone']})" if p["planned_milestone"] else ""),
            "local" if p["local"] else "cloud",
            ",".join(p["credentials_env"]) or "-",
            p["description"],
        ]
        for p in catalogue
    ]
    print(_table(rows, ["kind", "name", "status", "where", "credentials (env)", "description"]))
    return 0


def cmd_schema_export(args: argparse.Namespace, settings: Settings) -> int:
    names = [args.name] if args.name else sorted(SCHEMAS)
    unknown = [n for n in names if n not in SCHEMAS]
    if unknown:
        raise StudioError(f"unknown schema {unknown[0]!r} (known: {', '.join(sorted(SCHEMAS))})")
    _print_json({n: SCHEMAS[n].model_json_schema() for n in names})
    return 0


# --- parser ----------------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="studio",
        description=(
            "Motion Animation Studio: rig-first 2D animation production (milestone 2 foundation)."
        ),
    )
    parser.add_argument(
        "--config-dir", help="configuration directory (default: auto-detect ./config)"
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")

    def add(sp: Any, name: str, handler: Handler, help_text: str) -> argparse.ArgumentParser:
        p: argparse.ArgumentParser = sp.add_parser(name, help=help_text, description=help_text)
        p.set_defaults(handler=handler)
        return p

    def json_flag(p: argparse.ArgumentParser) -> None:
        p.add_argument("--json", action="store_true", help="machine-readable output")

    json_flag(add(sub, "version", cmd_version, "show version and configuration source"))
    json_flag(
        add(sub, "doctor", cmd_doctor, "check this machine's tools (no installs, no downloads)")
    )
    json_flag(add(sub, "modules", cmd_modules, "list the sixteen studio modules and their status"))

    p_new = add(sub, "new", cmd_new, "create a new project")
    p_new.add_argument("name", help="project name (the folder name is its slug)")
    p_new.add_argument("--title", help="display title (default: the name)")
    p_new.add_argument("--kind", choices=[k.value for k in ProjectKind])
    p_new.add_argument("--description")
    p_new.add_argument("--profile", help="render profile id (default from config/studio.yaml)")
    p_new.add_argument(
        "--projects-dir", help="parent folder (default: projects/ in the repository)"
    )

    p_cfg = add(sub, "config", lambda a, s: _missing(p_cfg), "configuration commands")
    cfg = p_cfg.add_subparsers(dest="config_command", metavar="ACTION")
    add(cfg, "validate", cmd_config_validate, "validate the configuration files")
    add(cfg, "show", cmd_config_show, "print the effective configuration as JSON")

    p_proj = add(sub, "project", lambda a, s: _missing(p_proj), "project commands")
    proj = p_proj.add_subparsers(dest="project_command", metavar="ACTION")
    for name, handler, text in (
        ("validate", cmd_project_validate, "validate a project folder"),
        ("info", cmd_project_info, "show project metadata"),
    ):
        p = add(proj, name, handler, text)
        p.add_argument("path", help="project folder, e.g. projects/demo")
        json_flag(p)

    p_asset = add(sub, "asset", lambda a, s: _missing(p_asset), "asset commands")
    asset = p_asset.add_subparsers(dest="asset_command", metavar="ACTION")
    p = add(asset, "list", cmd_asset_list, "list registered assets")
    p.add_argument("path")
    p.add_argument("--category", choices=[c.value for c in AssetCategory])
    json_flag(p)
    p = add(asset, "validate", cmd_asset_validate, "check files, hashes and references")
    p.add_argument("path")
    json_flag(p)
    p = add(
        asset,
        "register",
        cmd_asset_register,
        "register a file (copied in; the original is untouched)",
    )
    p.add_argument("path", help="project folder")
    p.add_argument("file", help="file to register")
    p.add_argument("--name", required=True)
    p.add_argument("--category", required=True, choices=[c.value for c in AssetCategory])
    p.add_argument("--license", default="unknown", help="SPDX id, 'proprietary' or 'unknown'")
    p.add_argument(
        "--source-kind",
        default=SourceKind.ORIGINAL.value,
        choices=[s.value for s in SourceKind if s is not SourceKind.AI_GENERATED],
    )
    p.add_argument("--author")
    p.add_argument("--url")
    p.add_argument("--note")
    p.add_argument("--depends", action="append", metavar="ASSET_ID")
    p.add_argument("--tag", action="append")
    p.add_argument(
        "--allow-duplicate", action="store_true", help="register identical content again"
    )
    p = add(asset, "add-version", cmd_asset_add_version, "register a new version of an asset")
    p.add_argument("path")
    p.add_argument("asset_id")
    p.add_argument("file")
    p.add_argument("--note")

    p_prov = add(sub, "providers", lambda a, s: _missing(p_prov), "AI provider commands")
    prov = p_prov.add_subparsers(dest="providers_command", metavar="ACTION")
    p = add(prov, "list", cmd_providers_list, "show selected providers and the catalogue")
    p.add_argument("--project", help="apply a project's provider overrides")
    json_flag(p)

    p_schema = add(sub, "schema", lambda a, s: _missing(p_schema), "data schema commands")
    schema = p_schema.add_subparsers(dest="schema_command", metavar="ACTION")
    p = add(schema, "export", cmd_schema_export, "print JSON Schema for the data documents")
    p.add_argument("name", nargs="?", help=f"one of: {', '.join(sorted(SCHEMAS))}")
    return parser


def _missing(parser: argparse.ArgumentParser) -> int:
    parser.print_help(sys.stderr)
    return 2


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "handler", None):
        parser.print_help()
        return 0
    try:
        settings = load_settings(Path(args.config_dir) if args.config_dir else None)
        configure_logging(settings, verbose=args.verbose)
        result: int = args.handler(args, settings)
        return result
    except StudioError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
