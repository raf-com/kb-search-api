#!/usr/bin/env python3
"""Portable port of run_authentic_completion_gate.ps1 (CI-safe subset).

The original PowerShell version invoked an `agentic500-guardrails` step that
probes the local Windows host's Docker stack. That sub-step is intentionally
dropped here because GitHub Actions on `ubuntu-latest` cannot reach this host's
Docker daemon. The remaining four steps are pure file/git scans and run
identically anywhere Python 3 + git are available:

  1. workflow-policy-scan
  2. workflow-script-parity
  3. failure-injection-workflow-scanners
  4. repo-unlock-audit (one per --audit-repo)

Exits 0 if every step exits 0; exits 2 otherwise.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent


def run_step(name: str, argv: list[str]) -> dict:
    proc = subprocess.run(argv, capture_output=True, text=True)
    return {
        "name": name,
        "ok": proc.returncode == 0,
        "exit_code": proc.returncode,
        "stdout_tail": proc.stdout[-2000:].strip(),
        "stderr_tail": proc.stderr[-2000:].strip(),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scan-repo", action="append", default=[], dest="scan_repos",
                    help="Repo path to feed to policy + parity scans (repeatable).")
    ap.add_argument("--audit-repo", action="append", default=[], dest="audit_repos",
                    help="Repo path to run the unlock audit on (repeatable).")
    ap.add_argument("--artifacts-dir", default="gate-artifacts",
                    help="Directory for per-step JSON outputs.")
    ap.add_argument("--output", default="authentic_completion_gate_latest.json")
    args = ap.parse_args()

    if not args.scan_repos:
        # Default to the workspace root when invoked from a checkout.
        args.scan_repos = ["."]

    artifacts = Path(args.artifacts_dir)
    artifacts.mkdir(parents=True, exist_ok=True)

    steps = []

    policy_out = artifacts / "workflow_policy_scan.json"
    policy_argv = [
        sys.executable, str(HERE / "scan_workflow_policy.py"),
        "--fail-on-stderr-mask", "--stderr-mask-threshold", "0",
        "--output", str(policy_out),
    ]
    for r in args.scan_repos:
        policy_argv += ["--repo", r]
    steps.append(run_step("workflow-policy-scan", policy_argv))

    parity_out = artifacts / "workflow_script_parity.json"
    parity_argv = [
        sys.executable, str(HERE / "verify_workflow_scripts.py"),
        "--fail-on-missing",
        "--output", str(parity_out),
    ]
    for r in args.scan_repos:
        parity_argv += ["--repo", r]
    steps.append(run_step("workflow-script-parity", parity_argv))

    inj_out = artifacts / "failure_injection_workflow_scanners.json"
    steps.append(run_step("failure-injection-workflow-scanners", [
        sys.executable, str(HERE / "run_failure_injection_checks.py"),
        "--output", str(inj_out),
    ]))

    for r in args.audit_repos:
        repo_path = Path(r)
        safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in repo_path.name)
        audit_json = artifacts / f"repo_unlock_audit_{safe}.json"
        audit_md = artifacts / f"repo_unlock_audit_{safe}.md"
        steps.append(run_step(f"repo-unlock-audit-{safe}", [
            sys.executable, str(HERE / "run_repo_unlock_audit.py"),
            "--repo", str(repo_path),
            "--output-json", str(audit_json),
            "--output-md", str(audit_md),
        ]))

    failed = [s for s in steps if not s["ok"]]
    summary = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "total_steps": len(steps),
        "passed_steps": len(steps) - len(failed),
        "failed_steps": len(failed),
        "overall_passed": len(failed) == 0,
        "scan_repos": args.scan_repos,
        "audit_repos": args.audit_repos,
        "steps": steps,
        "dropped_steps": [
            {
                "name": "guardrails-dev-run",
                "reason": "local-docker-probe-not-portable-to-github-actions-ubuntu-runner",
            }
        ],
    }

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))

    return 0 if summary["overall_passed"] else 2


if __name__ == "__main__":
    sys.exit(main())
