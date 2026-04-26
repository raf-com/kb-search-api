#!/usr/bin/env python3
"""Portable port of verify_workflow_scripts.ps1.

For each given repo:
  - Reads package.json's "scripts" keys.
  - Walks .github/workflows/*.{yml,yaml} for `npm run <name>` calls.
  - Reports any call to a script name not declared in package.json.

Exits 2 if --fail-on-missing and any missing calls were found, else 0.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

NPM_RUN_RE = re.compile(r"npm\s+run\s+([a-zA-Z0-9:_-]+)")


def _collect_scripts(pkg_path: Path) -> list[str]:
    try:
        data = json.loads(pkg_path.read_text(encoding="utf-8"))
        sc = data.get("scripts") or {}
        if isinstance(sc, dict):
            return list(sc.keys())
    except (OSError, json.JSONDecodeError):
        pass
    return []


def audit_repo(repo: Path) -> dict:
    # Collect scripts from root package.json AND any subdirectory package.json,
    # so workflows that `cd subdir && npm run X` don't generate false positives.
    pkg_path = repo / "package.json"
    scripts: list[str] = _collect_scripts(pkg_path) if pkg_path.is_file() else []
    for sub_pkg in repo.rglob("package.json"):
        if sub_pkg == pkg_path:
            continue
        # Skip node_modules to avoid collecting transitive dep scripts
        if "node_modules" in sub_pkg.parts:
            continue
        scripts.extend(_collect_scripts(sub_pkg))
    scripts = list(dict.fromkeys(scripts))  # deduplicate, preserve order

    missing: list[dict] = []
    wf_dir = repo / ".github" / "workflows"
    if wf_dir.is_dir():
        for f in wf_dir.rglob("*"):
            if not (f.is_file() and f.suffix in (".yml", ".yaml")):
                continue
            try:
                lines = f.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            for i, line in enumerate(lines, start=1):
                for m in NPM_RUN_RE.finditer(line):
                    name = m.group(1)
                    if name not in scripts:
                        missing.append({"file": str(f), "line": i, "script": name})

    return {
        "repo": str(repo),
        "package_json": pkg_path.is_file(),
        "script_count": len(scripts),
        "missing_script_calls": missing,
        "missing_count": len(missing),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", action="append", required=True, dest="repos",
                    help="Repo path (repeatable).")
    ap.add_argument("--output", default="workflow_script_parity_latest.json")
    ap.add_argument("--fail-on-missing", action="store_true")
    args = ap.parse_args()

    report = [audit_repo(Path(r)) for r in args.repos]
    violations = [
        f"{r['repo']}: missing_script_calls={r['missing_count']}"
        for r in report
        if int(r["missing_count"]) > 0
    ]

    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "fail_on_missing": bool(args.fail_on_missing),
        "repos": report,
        "violations": violations,
        "overall_passed": len(violations) == 0,
    }

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps(out, indent=2))

    if args.fail_on_missing and not out["overall_passed"]:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
