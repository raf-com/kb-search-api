#!/usr/bin/env python3
"""Portable port of scan_workflow_policy.ps1.

Walks .github/workflows/*.{yml,yaml} in each given repo and counts:
  - soft_fail_count   = matches of `|| true` or `continue-on-error: true`
  - stderr_mask_count = matches of `2>/dev/null`
  - unpinned_actions  = `uses:` lines whose ref isn't a 40-char SHA

Exits 0 if no thresholds violated, 2 otherwise.
Output JSON schema matches the PowerShell original so consumers don't break.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

SOFT_FAIL_RE = re.compile(r"\|\|\s*true|continue-on-error\s*:\s*true")
STDERR_MASK_RE = re.compile(r"2>/dev/null")
USES_RE = re.compile(r"^\s*uses:\s*([^\s]+)", re.MULTILINE)
SHA_PINNED_RE = re.compile(r"@[0-9a-fA-F]{40}(\s|$)")


def scan_repo(repo: Path) -> dict:
    wf_dir = repo / ".github" / "workflows"
    if not wf_dir.is_dir():
        return {
            "repo": str(repo),
            "workflow_files": 0,
            "soft_fail_count": 0,
            "stderr_mask_count": 0,
            "unpinned_actions": 0,
            "missing_workflow_dir": True,
        }

    files = [p for p in wf_dir.rglob("*") if p.is_file() and p.suffix in (".yml", ".yaml")]
    soft = stderr = unpinned = 0
    for f in files:
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        soft += len(SOFT_FAIL_RE.findall(text))
        stderr += len(STDERR_MASK_RE.findall(text))
        for line in USES_RE.findall(text):
            if not SHA_PINNED_RE.search(line + " "):
                unpinned += 1

    return {
        "repo": str(repo),
        "workflow_files": len(files),
        "soft_fail_count": soft,
        "stderr_mask_count": stderr,
        "unpinned_actions": unpinned,
        "missing_workflow_dir": False,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", action="append", required=True, dest="repos",
                    help="Repo path (repeatable).")
    ap.add_argument("--output", default="workflow_policy_scan_latest.json")
    ap.add_argument("--fail-on-soft-fail", action="store_true")
    ap.add_argument("--fail-on-stderr-mask", action="store_true")
    ap.add_argument("--fail-on-unpinned", action="store_true")
    ap.add_argument("--soft-fail-threshold", type=int, default=0)
    ap.add_argument("--stderr-mask-threshold", type=int, default=0)
    ap.add_argument("--unpinned-threshold", type=int, default=0)
    args = ap.parse_args()

    results = [scan_repo(Path(r)) for r in args.repos]

    violations: list[str] = []
    for r in results:
        if args.fail_on_soft_fail and int(r["soft_fail_count"]) > args.soft_fail_threshold:
            violations.append(
                f"{r['repo']}: soft_fail_count={r['soft_fail_count']} exceeds threshold={args.soft_fail_threshold}"
            )
        if args.fail_on_stderr_mask and int(r["stderr_mask_count"]) > args.stderr_mask_threshold:
            violations.append(
                f"{r['repo']}: stderr_mask_count={r['stderr_mask_count']} exceeds threshold={args.stderr_mask_threshold}"
            )
        if args.fail_on_unpinned and int(r["unpinned_actions"]) > args.unpinned_threshold:
            violations.append(
                f"{r['repo']}: unpinned_actions={r['unpinned_actions']} exceeds threshold={args.unpinned_threshold}"
            )

    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "repos": results,
        "policy": {
            "fail_on_soft_fail": bool(args.fail_on_soft_fail),
            "fail_on_stderr_mask": bool(args.fail_on_stderr_mask),
            "fail_on_unpinned": bool(args.fail_on_unpinned),
            "soft_fail_threshold": args.soft_fail_threshold,
            "stderr_mask_threshold": args.stderr_mask_threshold,
            "unpinned_threshold": args.unpinned_threshold,
        },
        "violations": violations,
        "overall_passed": len(violations) == 0,
    }

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps(out, indent=2))

    return 0 if out["overall_passed"] else 2


if __name__ == "__main__":
    sys.exit(main())
