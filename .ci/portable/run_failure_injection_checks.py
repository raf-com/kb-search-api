#!/usr/bin/env python3
"""Portable port of run_failure_injection_checks.ps1.

Builds a sandbox repo containing a workflow file and package.json with known
violations (soft fail + stderr mask + unpinned action + missing npm script),
then runs scan_workflow_policy.py and verify_workflow_scripts.py against it
and asserts both report failure (exit 2). If either incorrectly reports pass,
this gate fails — proving the scanners are not broken open.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent

INJECTED_WORKFLOW = """\
name: injected-policy-failure
on:
  workflow_dispatch:
jobs:
  injected:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: npm run missing-script || true
      - run: echo "masked" 2>/dev/null
"""

INJECTED_PACKAGE_JSON = json.dumps({
    "name": "failure-injection-repo",
    "version": "1.0.0",
    "private": True,
    "scripts": {"lint": "echo lint"},
}, indent=2)


def run_step(name: str, argv: list[str]) -> dict:
    proc = subprocess.run(argv, capture_output=True, text=True)
    return {
        "name": name,
        "exit_code": proc.returncode,
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip(),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", default="failure_injection_workflow_scanners_latest.json")
    ap.add_argument("--keep-sandbox", action="store_true")
    args = ap.parse_args()

    sandbox = Path(tempfile.mkdtemp(prefix="failure_injection_"))
    repo = sandbox / "repo"
    wf_dir = repo / ".github" / "workflows"
    wf_dir.mkdir(parents=True)
    (wf_dir / "injected.yml").write_text(INJECTED_WORKFLOW, encoding="utf-8")
    (repo / "package.json").write_text(INJECTED_PACKAGE_JSON, encoding="utf-8")

    policy_out = sandbox / "policy_scan.json"
    parity_out = sandbox / "script_parity.json"

    policy_step = run_step("policy-scan-injected", [
        sys.executable, str(HERE / "scan_workflow_policy.py"),
        "--repo", str(repo),
        "--fail-on-soft-fail", "--soft-fail-threshold", "0",
        "--fail-on-stderr-mask", "--stderr-mask-threshold", "0",
        "--fail-on-unpinned", "--unpinned-threshold", "0",
        "--output", str(policy_out),
    ])
    parity_step = run_step("script-parity-injected", [
        sys.executable, str(HERE / "verify_workflow_scripts.py"),
        "--repo", str(repo),
        "--fail-on-missing",
        "--output", str(parity_out),
    ])

    EXPECTED_FAIL = 2
    policy_expected = policy_step["exit_code"] == EXPECTED_FAIL
    parity_expected = parity_step["exit_code"] == EXPECTED_FAIL
    overall_passed = policy_expected and parity_expected

    summary = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "sandbox_root": str(sandbox),
        "expected_failure_exit_code": EXPECTED_FAIL,
        "checks": [
            {
                "name": policy_step["name"],
                "observed_exit_code": policy_step["exit_code"],
                "expected_failure": policy_expected,
                "stdout": policy_step["stdout"],
                "stderr": policy_step["stderr"],
                "output_path": str(policy_out),
            },
            {
                "name": parity_step["name"],
                "observed_exit_code": parity_step["exit_code"],
                "expected_failure": parity_expected,
                "stdout": parity_step["stdout"],
                "stderr": parity_step["stderr"],
                "output_path": str(parity_out),
            },
        ],
        "overall_passed": overall_passed,
    }

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))

    if not args.keep_sandbox:
        shutil.rmtree(sandbox, ignore_errors=True)

    return 0 if overall_passed else 2


if __name__ == "__main__":
    sys.exit(main())
