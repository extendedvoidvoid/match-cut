#!/usr/bin/env python3
"""mc module — list / run / mix / apply modular pipeline features.

Mix creates a new module (recipe) from parent module ids.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
MOD_ROOT = Path(__file__).resolve().parent
REGISTRY_PATH = MOD_ROOT / "registry.json"
RECIPES_DIR = MOD_ROOT / "recipes"


def load_registry() -> dict[str, Any]:
    if not REGISTRY_PATH.is_file():
        return {"version": 1, "modules": {}}
    return json.loads(REGISTRY_PATH.read_text())


def save_registry(reg: dict[str, Any]) -> None:
    REGISTRY_PATH.write_text(json.dumps(reg, indent=2, ensure_ascii=False) + "\n")


def get_module(reg: dict[str, Any], mid: str) -> dict[str, Any] | None:
    mods = reg.get("modules") or {}
    if mid in mods:
        return mods[mid]
    # allow short names: kiss_mouth_geo → classify.kiss_mouth_geo
    for k, v in mods.items():
        if k == mid or k.endswith("." + mid) or k.split(".")[-1] == mid:
            return v
    return None


def cmd_list(args: argparse.Namespace) -> int:
    reg = load_registry()
    mods = reg.get("modules") or {}
    rows = []
    for mid, m in sorted(mods.items()):
        if args.type and m.get("type") != args.type:
            continue
        if args.status and m.get("status") != args.status:
            continue
        rows.append(
            {
                "id": mid,
                "type": m.get("type"),
                "status": m.get("status"),
                "title": m.get("title", ""),
            }
        )
    if args.json:
        print(json.dumps(rows, indent=2))
        return 0
    print(f"{'ID':<36} {'TYPE':<10} {'STATUS':<12} TITLE")
    print("-" * 90)
    for r in rows:
        print(f"{r['id']:<36} {r['type'] or '':<10} {r['status'] or '':<12} {r['title']}")
    print(f"\n{len(rows)} modules  registry={REGISTRY_PATH}")
    return 0


def build_cmd(module: dict[str, Any], extra: list[str], param_overrides: dict[str, str]) -> list[str] | None:
    runner = module.get("runner") or {}
    kind = runner.get("kind")
    if kind == "stub":
        return None
    if kind != "python":
        raise SystemExit(f"unsupported runner kind: {kind}")

    script = ROOT / runner["script"]
    if not script.is_file():
        raise SystemExit(f"script missing: {script}")

    # Prefer film-grab venv for scripts that need httpx/selectolax stack
    py = sys.executable
    venv_py = ROOT / ".venv-film-grab" / "bin" / "python"
    if "fetch-film-grab" in str(script) and venv_py.is_file():
        py = str(venv_py)
    cmd = [py, str(script)]
    cmd.extend(runner.get("fixed_args") or [])

    params = dict(module.get("params") or {})
    params.update(param_overrides)

    # boolean flags from args_from_params when truthy
    for key, flag in (runner.get("args_from_params") or {}).items():
        val = params.get(key)
        if val is True or val == "true" or val == "1":
            cmd.append(flag)
        elif val is False or val is None or val == "false":
            continue

    # key → --cli-flag value
    for key, flag in (runner.get("args_map") or {}).items():
        if key in params and params[key] is not None:
            cmd.extend([flag, str(params[key])])

    cmd.extend(extra)
    return cmd


def parse_set_params(items: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for item in items:
        if "=" not in item:
            raise SystemExit(f"--set needs key=value, got {item}")
        k, v = item.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def cmd_run(args: argparse.Namespace) -> int:
    reg = load_registry()
    module = get_module(reg, args.module_id)
    if not module:
        print(f"error: unknown module {args.module_id}", file=sys.stderr)
        return 1

    overrides = parse_set_params(args.set or [])
    # coerce known booleans
    for k, v in list(overrides.items()):
        if v.lower() in ("true", "1", "yes"):
            overrides[k] = True  # type: ignore[assignment]
        elif v.lower() in ("false", "0", "no"):
            overrides[k] = False  # type: ignore[assignment]
        else:
            try:
                if "." in v:
                    overrides[k] = float(v)  # type: ignore[assignment]
                else:
                    overrides[k] = int(v)  # type: ignore[assignment]
            except ValueError:
                pass

    runner = module.get("runner") or {}
    if runner.get("kind") == "stub":
        print(
            json.dumps(
                {
                    "module": module["id"],
                    "status": "stub",
                    "message": runner.get("message", "not implemented"),
                    "params": {**(module.get("params") or {}), **overrides},
                },
                indent=2,
            )
        )
        return 0

    cmd = build_cmd(module, args.extra or [], overrides)  # type: ignore[arg-type]
    assert cmd is not None
    print(f"module run {module['id']}: {' '.join(cmd)}", file=sys.stderr)
    return subprocess.call(cmd, cwd=str(ROOT))


def cmd_show(args: argparse.Namespace) -> int:
    reg = load_registry()
    module = get_module(reg, args.module_id)
    if not module:
        print(f"error: unknown module {args.module_id}", file=sys.stderr)
        return 1
    print(json.dumps(module, indent=2))
    return 0


def cmd_mix(args: argparse.Namespace) -> int:
    """Compose parent modules into a new mix module + recipe file."""
    reg = load_registry()
    parents: list[str] = []
    graph: list[dict[str, Any]] = []
    for pid in args.parents:
        m = get_module(reg, pid)
        if not m:
            print(f"error: unknown parent module {pid}", file=sys.stderr)
            return 1
        mid = m["id"]
        parents.append(mid)
        graph.append({"module": mid, "params": dict(m.get("params") or {})})

    new_id = args.as_id
    if not new_id.startswith("mix."):
        new_id = f"mix.{new_id}"

    recipe = {
        "id": new_id,
        "type": "mix",
        "version": "1.0.0",
        "title": args.title or f"Mix of {', '.join(parents)}",
        "status": "experiment",
        "parents": parents,
        "graph": graph,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "outputs": ["exports/reels/", "exports/manifests/", "assets/film-grab/pools/"],
    }

    RECIPES_DIR.mkdir(parents=True, exist_ok=True)
    recipe_path = RECIPES_DIR / f"{new_id.replace('.', '_')}.json"
    recipe_path.write_text(json.dumps(recipe, indent=2, ensure_ascii=False) + "\n")

    reg.setdefault("modules", {})[new_id] = {
        "id": new_id,
        "version": recipe["version"],
        "type": "mix",
        "title": recipe["title"],
        "status": "experiment",
        "parents": parents,
        "recipe": str(recipe_path.relative_to(ROOT)),
        "runner": {
            "kind": "recipe",
            "recipe": str(recipe_path.relative_to(ROOT)),
        },
    }
    save_registry(reg)

    print(
        json.dumps(
            {
                "created_module": new_id,
                "parents": parents,
                "recipe": str(recipe_path),
                "apply": f"mc module apply {new_id}",
            },
            indent=2,
        )
    )
    return 0


def cmd_apply(args: argparse.Namespace) -> int:
    """Run each step in a mix recipe graph (stubs report only)."""
    reg = load_registry()
    module = get_module(reg, args.recipe_id)
    if not module:
        print(f"error: unknown recipe/module {args.recipe_id}", file=sys.stderr)
        return 1

    if module.get("type") != "mix" and not (module.get("runner") or {}).get("kind") == "recipe":
        # single module apply = run
        ns = argparse.Namespace(module_id=module["id"], set=args.set or [], extra=args.extra or [])
        return cmd_run(ns)

    recipe_rel = (module.get("runner") or {}).get("recipe") or module.get("recipe")
    if not recipe_rel:
        print("error: mix module missing recipe path", file=sys.stderr)
        return 1
    recipe_path = ROOT / recipe_rel
    if not recipe_path.is_file():
        print(f"error: recipe missing {recipe_path}", file=sys.stderr)
        return 1
    recipe = json.loads(recipe_path.read_text())
    graph = recipe.get("graph") or []

    print(
        json.dumps(
            {
                "apply": recipe.get("id"),
                "on": args.on,
                "steps": len(graph),
                "dry_run": args.dry_run,
            },
            indent=2,
        ),
        file=sys.stderr,
    )

    results = []
    for i, step in enumerate(graph, 1):
        mid = step["module"]
        m = get_module(reg, mid)
        if not m:
            print(f"error: graph step unknown {mid}", file=sys.stderr)
            return 1
        # merge step params as --set
        sets = [f"{k}={v}" for k, v in (step.get("params") or {}).items()]
        if args.set:
            sets.extend(args.set)
        if args.dry_run:
            results.append({"step": i, "module": mid, "status": "dry_run", "params": step.get("params")})
            print(f"  [{i}/{len(graph)}] {mid} (dry-run)", file=sys.stderr)
            continue
        if (m.get("runner") or {}).get("kind") == "stub":
            results.append({"step": i, "module": mid, "status": "stub", "params": step.get("params")})
            print(f"  [{i}/{len(graph)}] {mid} (stub — not implemented)", file=sys.stderr)
            continue
        ns = argparse.Namespace(module_id=mid, set=sets, extra=args.extra or [])
        print(f"  [{i}/{len(graph)}] run {mid}", file=sys.stderr)
        rc = cmd_run(ns)
        results.append({"step": i, "module": mid, "exit": rc})
        if rc != 0:
            print(json.dumps({"failed_at": mid, "results": results}, indent=2))
            return rc

    print(json.dumps({"apply_ok": recipe.get("id"), "results": results}, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Match-cut module registry CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_list = sub.add_parser("list", help="List modules")
    p_list.add_argument("--type", default=None)
    p_list.add_argument("--status", default=None)
    p_list.add_argument("--json", action="store_true")
    p_list.set_defaults(func=cmd_list)

    p_show = sub.add_parser("show", help="Show one module JSON")
    p_show.add_argument("module_id")
    p_show.set_defaults(func=cmd_show)

    p_run = sub.add_parser("run", help="Run a module")
    p_run.add_argument("module_id")
    p_run.add_argument("--set", action="append", default=[], help="param=value")
    p_run.add_argument("extra", nargs="*", help="extra args passed to script")
    p_run.set_defaults(func=cmd_run)

    p_mix = sub.add_parser("mix", help="Compose parents into new mix module")
    p_mix.add_argument("parents", nargs="+", help="Parent module ids")
    p_mix.add_argument("--as", dest="as_id", required=True, help="New module id (mix.* added if missing)")
    p_mix.add_argument("--title", default=None)
    p_mix.set_defaults(func=cmd_mix)

    p_apply = sub.add_parser("apply", help="Apply mix recipe (or single module)")
    p_apply.add_argument("recipe_id")
    p_apply.add_argument("--on", default="stills", help="stills|video|batch name (metadata for now)")
    p_apply.add_argument("--dry-run", action="store_true")
    p_apply.add_argument("--set", action="append", default=[])
    p_apply.add_argument("extra", nargs="*")
    p_apply.set_defaults(func=cmd_apply)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
