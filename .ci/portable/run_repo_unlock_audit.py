#!/usr/bin/env python3
"""Portable port of run_repo_unlock_audit.ps1.

For a single git repo:
  - Reads `git status --porcelain=v1` and counts dirty entries by status type.
  - Runs scan_workflow_policy.py and verify_workflow_scripts.py against the repo.
  - Emits JSON + Markdown summaries.

Exits 0 only if both sub-scans return exit 0 AND parsed JSON; exits 2 otherwise.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent


def run_json_step(argv: list[str]) -> dict:
    proc = subprocess.run(argv, capture_output=True, text=True)
    parsed = None
    try:
        parsed = json.loads(proc.stdout) if proc.stdout.strip() else None
    except json.JSONDecodeError:
        parsed = None
    return {
        "exit_code": proc.returncode,
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip(),
        "parsed": parsed,
    }


def git(repo: Path, *args: str) -> str:
    proc = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True)
    return proc.stdout.strip()


def is_git_repo(repo: Path) -> bool:
    proc = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "--is-inside-work-tree"],
        capture_output=True, text=True,
    )
    return proc.returncode == 0 and proc.stdout.strip() == "true"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--output-json", required=True)
    ap.add_argument("--output-md", required=True)
    args = ap.parse_args()

    repo = Path(args.repo)
    if not repo.exists():
        print(f"Repo path not found: {repo}", file=sys.stderr)
        return 99
    if not is_git_repo(repo):
        print(f"Path is not a git repository: {repo}", file=sys.stderr)
        return 99

    repo_name = repo.name
    safe_name = "".join(c if c.isalnum() or c in "._-" else "_" for c in repo_name)

    out_json = Path(args.output_json)
    out_md = Path(args.output_md)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_md.parent.mkdir(parents=True, exist_ok=True)

    sibling_dir = out_json.parent
    scan_policy_path = sibling_dir / f"workflow_policy_scan_unlock_{safe_name}.json"
    scan_parity_path = sibling_dir / f"workflow_script_parity_unlock_{safe_name}.json"

    status = git(repo, "status", "--porcelain=v1")
    status_lines = status.splitlines() if status else []

    counts = Counter()
    paths: list[str] = []
    tracked = untracked = 0

    for line in status_lines:
        if line.startswith("?? "):
            untracked += 1
            paths.append(line[3:])
            continue
        tracked += 1
        if len(line) < 2:
            continue
        x, y = line[0], line[1]
        for c in (x, y):
            if c == "A": counts["added"] += 1
            elif c == "M": counts["modified"] += 1
            elif c == "D": counts["deleted"] += 1
            elif c == "R": counts["renamed"] += 1
            elif c == "C": counts["copied"] += 1
            elif c == "T": counts["type_changed"] += 1
            elif c == "U": counts["unmerged"] += 1
        paths.append(line[3:] if len(line) > 3 else "")

    seg_counter: Counter = Counter()
    for p in paths:
        norm = p.replace("\\", "/")
        seg = norm.split("/")[0] if "/" in norm else "(root)"
        seg_counter[seg] += 1
    hotspots = [
        {"segment": seg, "count": cnt}
        for seg, cnt in seg_counter.most_common(20)
    ]

    policy_run = run_json_step([
        sys.executable, str(HERE / "scan_workflow_policy.py"),
        "--repo", str(repo),
        "--output", str(scan_policy_path),
    ])
    parity_run = run_json_step([
        sys.executable, str(HERE / "verify_workflow_scripts.py"),
        "--repo", str(repo),
        "--output", str(scan_parity_path),
    ])

    branch = git(repo, "rev-parse", "--abbrev-ref", "HEAD")
    head_sha = git(repo, "rev-parse", "--short", "HEAD")

    audit = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "repo": {
            "path": str(repo),
            "name": repo_name,
            "branch": branch,
            "head_sha": head_sha,
        },
        "dirty_state": {
            "total_entries": len(status_lines),
            "tracked_entries": tracked,
            "untracked_entries": untracked,
            "tracked_status_counts": {
                k: counts.get(k, 0) for k in
                ("added", "modified", "deleted", "renamed", "copied", "type_changed", "unmerged")
            },
            "top_level_hotspots": hotspots,
        },
        "policy_scan": {
            "artifact": str(scan_policy_path),
            "exit_code": policy_run["exit_code"],
            "overall_passed": bool(policy_run["parsed"].get("overall_passed")) if policy_run["parsed"] else False,
            "parsed": policy_run["parsed"],
        },
        "workflow_script_parity": {
            "artifact": str(scan_parity_path),
            "exit_code": parity_run["exit_code"],
            "overall_passed": bool(parity_run["parsed"].get("overall_passed")) if parity_run["parsed"] else False,
            "parsed": parity_run["parsed"],
        },
    }

    audit["black_box_resolved"] = (
        audit["policy_scan"]["exit_code"] == 0
        and audit["workflow_script_parity"]["exit_code"] == 0
        and audit["policy_scan"]["parsed"] is not None
        and audit["workflow_script_parity"]["parsed"] is not None
    )
    audit["unlock_status"] = (
        "unlocked_with_dirty_state" if audit["dirty_state"]["total_entries"] > 0 else "clean"
    )
    audit["recommended_next_actions"] = [
        "Preserve working state and avoid destructive cleanup while black-box status is resolved.",
        "If cleanup is needed, perform it on a dedicated WIP branch, then rerun this audit.",
        "Treat policy/parity artifacts as current evidence for repo-level governance checks.",
    ]

    out_json.write_text(json.dumps(audit, indent=2), encoding="utf-8")

    md_lines = [
        "# Repo Unlock Audit",
        "",
        f"- Generated (UTC): {audit['generated_at_utc']}",
        f"- Repo: {audit['repo']['path']}",
        f"- Branch: {audit['repo']['branch']}",
        f"- Head: {audit['repo']['head_sha']}",
        f"- Unlock Status: {audit['unlock_status']}",
        f"- Black-box Resolved: {audit['black_box_resolved']}",
        "",
        "## Dirty State",
        f"- Total entries: {audit['dirty_state']['total_entries']}",
        f"- Tracked entries: {audit['dirty_state']['tracked_entries']}",
        f"- Untracked entries: {audit['dirty_state']['untracked_entries']}",
        "",
        "| Segment | Count |",
        "|---|---:|",
    ]
    for h in audit["dirty_state"]["top_level_hotspots"]:
        md_lines.append(f"| {h['segment']} | {h['count']} |")
    md_lines += [
        "",
        "## Policy Evidence",
        f"- Workflow policy scan artifact: {audit['policy_scan']['artifact']}",
        f"- Workflow policy overall passed: {audit['policy_scan']['overall_passed']}",
        f"- Workflow script parity artifact: {audit['workflow_script_parity']['artifact']}",
        f"- Workflow script parity overall passed: {audit['workflow_script_parity']['overall_passed']}",
        "",
        "## Next Actions",
    ]
    for n in audit["recommended_next_actions"]:
        md_lines.append(f"- {n}")
    out_md.write_text("\n".join(md_lines) + "\n", encoding="utf-8")

    print(json.dumps(audit, indent=2))
    return 0 if audit["black_box_resolved"] else 2


if __name__ == "__main__":
    sys.exit(main())
