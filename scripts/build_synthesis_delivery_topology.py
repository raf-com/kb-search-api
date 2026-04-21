#!/usr/bin/env python3
"""
Build the Step 59-62 synthesis, alignment, deployment, and observability
baseline and merge it into context_manifest_v1.json.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


PROJECT_ROOT = Path(__file__).resolve().parents[1]
INFRA_ROOT = Path(r"C:\infra")
MANIFEST_PATH = PROJECT_ROOT / "metadata" / "context_manifest_v1.json"
INTERACTION_SPEC_PATH = PROJECT_ROOT / "interaction" / "specs" / "interaction_design.yaml"
FEEDBACK_PATH = (
    PROJECT_ROOT / "feedback" / "annotated" / "step_014_feedback_annotations_2026-04-21.json"
)
MAIN_APP_PATH = PROJECT_ROOT / "main.py"
REFINEMENT_REPORT_PATH = (
    PROJECT_ROOT / "design" / "iterations" / "step_039_design_refinement_report_2026-04-21.json"
)
PROMPT_VERSION_DIFF_PATH = PROJECT_ROOT / "prompts" / "versions" / "version_diff.yaml"
REFINEMENT_LOG_PATH = (
    PROJECT_ROOT / "ux" / "refinement_logs" / "step_039_refinement_log_2026-04-21.json"
)

STEP_FILE_CANDIDATES = {
    "STEP_059": [
        PROJECT_ROOT / "metadata" / "context_manifest_v1.json",
        PROJECT_ROOT / "requirements" / "prd_retrieval_generation_contract_v1.json",
        PROJECT_ROOT / "specs" / "functional" / "step_017_pattern_library_2026-04-21.json",
    ],
    "STEP_060": [
        PROJECT_ROOT / "metadata" / "context_manifest_v1.json",
        PROJECT_ROOT / "feedback" / "annotated" / "step_014_feedback_annotations_2026-04-21.json",
        PROJECT_ROOT / "evals" / "golden_set" / "step_014_concept_validation_golden_set_2026-04-21.jsonl",
    ],
    "STEP_061": [
        PROJECT_ROOT / "docker-compose.standalone.yml",
        PROJECT_ROOT / "docker-compose.rag-domains.yml",
        INFRA_ROOT / "docker-compose.yml",
        INFRA_ROOT / "docker-compose.loki.yml",
    ],
    "STEP_062": [
        PROJECT_ROOT / "observability" / "package-observability.yml",
        INFRA_ROOT / "config" / "prometheus.yml",
        INFRA_ROOT / "config" / "loki-config.yml",
        INFRA_ROOT / "config" / "promtail-config.yml",
    ],
}

HASH_SOURCE_FILES = [
    PROJECT_ROOT / "docker-compose.standalone.yml",
    PROJECT_ROOT / "docker-compose.rag-domains.yml",
    PROJECT_ROOT / "observability" / "package-observability.yml",
    INFRA_ROOT / "docker-compose.yml",
    INFRA_ROOT / "docker-compose.loki.yml",
    INFRA_ROOT / "observability" / "package-observability.yml",
]

EXTENSIONS = {".py", ".json", ".yaml", ".yml", ".md", ".txt"}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def recursive_listing(directory: Path) -> list[str]:
    if not directory.exists():
        return []
    results: list[str] = []
    for path in directory.rglob("*"):
        if not path.is_file():
            continue
        try:
            results.append(str(path.relative_to(PROJECT_ROOT)))
        except ValueError:
            results.append(str(path))
    return results


def locate_step_marker(step_name: str) -> dict[str, Any] | None:
    pattern = re.compile(step_name, re.IGNORECASE)
    for candidate in STEP_FILE_CANDIDATES.get(step_name, []):
        if not candidate.exists():
            continue
        for line_number, line in enumerate(
            candidate.read_text(encoding="utf-8", errors="ignore").splitlines(),
            start=1,
        ):
            if pattern.search(line):
                try:
                    relative_path = str(candidate.relative_to(PROJECT_ROOT))
                except ValueError:
                    relative_path = str(candidate)
                return {
                    "path": relative_path,
                    "line_number": line_number,
                    "line": line.strip(),
                }
    return None


def find_named_files(names: set[str]) -> list[str]:
    results: list[str] = []
    for path in PROJECT_ROOT.rglob("*"):
        if not path.is_file():
            continue
        if path.name in names:
            results.append(str(path.relative_to(PROJECT_ROOT)))
    return sorted(results)


def search_text_hits(
    roots: list[Path],
    patterns: dict[str, re.Pattern[str]],
) -> dict[str, list[str]]:
    hits = {name: [] for name in patterns}
    for root in roots:
        if not root.exists():
            continue
        if root.is_file():
            candidates = [root]
        else:
            candidates = [
                path
                for path in root.rglob("*")
                if path.is_file()
                and path.suffix.lower() in EXTENSIONS
                and "__pycache__" not in path.parts
                and ".git" not in path.parts
            ]
        for path in candidates:
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for name, pattern in patterns.items():
                if pattern.search(text):
                    try:
                        rel = str(path.relative_to(PROJECT_ROOT))
                    except ValueError:
                        rel = str(path)
                    hits[name].append(rel)
    return {name: sorted(set(paths)) for name, paths in hits.items()}


def parse_jsonish(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_compose_services(path: Path) -> list[str]:
    if not path.exists():
        return []
    services: list[str] = []
    in_services = False
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        if not in_services:
            if line.strip() == "services:":
                in_services = True
            continue
        if line and not line.startswith(" "):
            break
        match = re.match(r"^  ([A-Za-z0-9_-]+):\s*$", line)
        if match:
            services.append(match.group(1))
    return services


def extract_routes(path: Path) -> list[str]:
    if not path.exists():
        return []
    pattern = re.compile(r"@app\.(?:get|post|put|delete)\(\s*[\"']([^\"']+)[\"']")
    return sorted(set(pattern.findall(path.read_text(encoding="utf-8", errors="ignore"))))


def probe_http(url: str) -> dict[str, Any]:
    request = Request(url, headers={"User-Agent": "codex-manifest-builder/1.0"})
    try:
        with urlopen(request, timeout=20) as response:
            body = response.read().decode("utf-8", errors="ignore")
            payload: Any
            try:
                payload = json.loads(body)
            except json.JSONDecodeError:
                payload = body[:400]
            return {
                "reachable": True,
                "status_code": response.status,
                "payload": payload,
            }
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="ignore")
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            payload = body[:400]
        return {
            "reachable": False,
            "status_code": exc.code,
            "payload": payload,
        }
    except URLError as exc:
        return {"reachable": False, "error": str(exc.reason)}
    except OSError as exc:
        return {"reachable": False, "error": str(exc)}


def compute_infrastructure_hash() -> dict[str, Any]:
    combined = hashlib.sha256()
    files: list[dict[str, str]] = []
    for path in HASH_SOURCE_FILES:
        if not path.exists():
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        combined.update(str(path).encode("utf-8"))
        combined.update(digest.encode("utf-8"))
        files.append({"path": str(path), "sha256": digest})
    return {"combined_sha256": combined.hexdigest(), "files": files}


def extract_inline_value(path: Path, key: str) -> str | None:
    if not path.exists():
        return None
    pattern = re.compile(rf"{re.escape(key)}\s*:\s*(.+)")
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        match = pattern.search(line)
        if match:
            return match.group(1).strip()
    return None


def load_text(path: Path) -> str | None:
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8", errors="ignore")


def build_generation_topology(manifest: dict[str, Any]) -> dict[str, Any]:
    persona_definitions = manifest.get("persona_definitions", {})
    requirement_set = manifest.get("requirement_set", {})
    system_vitals = manifest.get("system_vitals_threshold", {})
    interaction_spec = parse_jsonish(INTERACTION_SPEC_PATH)
    version_diff = (
        parse_jsonish(PROMPT_VERSION_DIFF_PATH)
        if PROMPT_VERSION_DIFF_PATH.exists()
        else {}
    )
    refinement_report = (
        load_json(REFINEMENT_REPORT_PATH)
        if REFINEMENT_REPORT_PATH.exists()
        else {}
    )
    interaction_library = interaction_spec.get("interaction_pattern_library", {})
    routes = extract_routes(MAIN_APP_PATH)
    prompt_hits = search_text_hits(
        [
            PROJECT_ROOT / "scripts",
            PROJECT_ROOT / "services",
            PROJECT_ROOT / "context_gates",
            PROJECT_ROOT / "interaction",
            PROJECT_ROOT / "ux",
            PROJECT_ROOT / "requirements",
            PROJECT_ROOT / "specs",
        ],
        {
            "portkey": re.compile(r"\bportkey\b", re.IGNORECASE),
            "pezzo": re.compile(r"\bpezzo\b", re.IGNORECASE),
            "langsmith_prompt_hub": re.compile(
                r"\blangsmith\b|\bprompt hub\b", re.IGNORECASE
            ),
            "system_instructions": re.compile(r"system_instructions", re.IGNORECASE),
            "few_shot_examples": re.compile(r"few[-_ ]shot", re.IGNORECASE),
            "cove": re.compile(
                r"chain[- ]of[- ]verification|\bcove\b", re.IGNORECASE
            ),
        },
    )
    search_api_health = probe_http("http://127.0.0.1:8010/api/v1/health")
    pattern_registry_probe = probe_http("http://127.0.0.1:8027/health")
    embedding_component = (
        search_api_health.get("payload", {})
        .get("components", {})
        .get("embedding_provider", {})
        if isinstance(search_api_health.get("payload"), dict)
        else {}
    )
    generation_routes = [
        route
        for route in routes
        if any(token in route for token in ("answer", "synth", "response", "generate"))
    ]

    prompt_directories = {
        name: (PROJECT_ROOT / name).exists()
        for name in ("prompts", "templates", "llm_logic", "guardrails")
    }

    return {
        "step": "STEP_059",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "step_manifest_hit": locate_step_marker("STEP_059"),
        "directories": {
            "prompt_dirs_present": prompt_directories,
            "actual_generation_logic_dirs": {
                "context_gates": recursive_listing(PROJECT_ROOT / "context_gates"),
                "interaction": recursive_listing(PROJECT_ROOT / "interaction"),
                "requirements": recursive_listing(PROJECT_ROOT / "requirements"),
                "specs_functional": recursive_listing(PROJECT_ROOT / "specs" / "functional"),
                "ux_personas": recursive_listing(PROJECT_ROOT / "ux" / "personas"),
            },
            "named_files": find_named_files(
                {
                    "synthesis_config.yaml",
                    "system_instructions.md",
                    "context_manifest_v1.json",
                }
            ),
        },
        "prompt_management_system": {
            "status": refinement_report.get("prompt_management_system", {}).get(
                "type",
                "missing",
            ),
            "detectors": prompt_hits,
            "registry_root": refinement_report.get("prompt_management_system", {}).get(
                "registry_root"
            ),
            "version_diff_path": refinement_report.get("prompt_management_system", {}).get(
                "version_diff_path"
            ),
            "details": "Local file-backed prompt versioning exists via prompts/versions, but no Portkey, Pezzo, or LangSmith Prompt Hub implementation was found in the scanned kb-search-api sources.",
        },
        "core_grounding_logic": {
            "persona_source": "ux/personas/persona_catalog.json",
            "persona_prompt_prefixes_available": bool(
                persona_definitions.get("persona_uuid_map")
            ),
            "prompt_version_files": recursive_listing(PROJECT_ROOT / "prompts" / "versions"),
            "requirement_guard": "context_gates/step_016.py",
            "citation_contract": "requirements/step_016_requirement_registry.json",
            "interaction_registry": "interaction/specs/interaction_design.yaml",
            "functional_pattern_library": "specs/functional/step_017_pattern_library_2026-04-21.json",
            "validation_service_on_disk": str(
                PROJECT_ROOT / "services" / "validation_service" / "app.py"
            ),
        },
        "generation_runtime": {
            "main_api_routes": routes,
            "answer_generation_routes": generation_routes,
            "status": "missing"
            if not generation_routes
            else "present",
            "details": (
                "No answer-generation or synthesis route was found in main.py."
                if not generation_routes
                else "At least one generation-like route was detected in main.py."
            ),
        },
        "context_anchors": {
            "strict_grounding": {
                "required_citations": requirement_set.get("variable_values", {}).get(
                    "required_citations"
                ),
                "knowledge_gap_behavior": "fail_closed",
                "source_trust_floor": system_vitals.get("variable_values", {}).get(
                    "hallucination_tolerance"
                ),
            },
            "citation_and_attribution": {
                "citation_style": interaction_library.get("citation_style"),
                "citation_format": interaction_library.get("citation_format"),
                "required_citations": requirement_set.get("variable_values", {}).get(
                    "required_citations"
                ),
            },
            "persona_and_brand_voice": {
                "default_user_id": persona_definitions.get("default_user_id"),
                "persona_count": len(persona_definitions.get("personas", [])),
                "prompt_prefix_count": len(persona_definitions.get("persona_uuid_map", {})),
            },
            "chain_of_verification": {
                "status": "missing",
                "details": "Validation and benchmarking exist, but no multi-pass CoVe synthesis loop was found in the live generation path.",
                "supporting_components": [
                    "services/validation_service/app.py",
                    "services/benchmarking_service/app.py",
                    "specs/functional/step_017_pattern_library_2026-04-21.json",
                ],
            },
        },
        "endpoint_verification": {
            "prompt_registry_api": {
                "status": "missing",
                "details": "No Prompt_Registry_API implementation or configuration was found on disk.",
            },
            "pattern_registry_runtime": pattern_registry_probe,
            "llm_inference_service": {
                "status": "embedding_only"
                if embedding_component
                else "missing",
                "details": embedding_component,
                "note": "The verified live surface is an embedding provider behind /api/v1/health, not a dedicated answer-synthesis inference service.",
            },
        },
        "variable_context_keys": {
            "system_prompt_version": "state.system_prompt_version",
            "citation_style": "state.citation_style",
            "hallucination_guard_level": "state.hallucination_guard_level",
        },
        "variable_values": {
            "system_prompt_version": version_diff.get("release_candidate_version"),
            "citation_style": interaction_library.get("citation_style"),
            "hallucination_guard_level": system_vitals.get("variable_values", {}).get(
                "hallucination_tolerance"
            ),
        },
        "synthesis_limits": {
            "explicit_max_token_limit": None,
            "max_response_words": requirement_set.get("variable_values", {}).get(
                "max_response_words"
            ),
            "prompt_word_budget": refinement_report.get("optimization_anchors", {})
            .get("prompt_delta", {})
            .get("max_response_words"),
            "token_budget_per_user": load_json(PROJECT_ROOT / "ops" / "billing" / "cost_config.json")
            .get("query_budget", {})
            .get("token_budget_per_user", {}),
            "few_shot_examples": [],
            "few_shot_details": "No few-shot citation examples were found in the scanned prompt and interaction assets.",
        },
        "gap_notes": [
            "The repo encodes grounding, citation, and persona policy, but the main API still exposes retrieval-first routes instead of a synthesized answer endpoint.",
            "No prompt registry, system_instructions.md, or CoVe implementation was found in kb-search-api.",
        ],
    }


def build_alignment_baseline() -> dict[str, Any]:
    feedback = load_json(FEEDBACK_PATH) if FEEDBACK_PATH.exists() else {}
    feedback_annotations = feedback.get("annotations", [])
    refinement_report = (
        load_json(REFINEMENT_REPORT_PATH)
        if REFINEMENT_REPORT_PATH.exists()
        else {}
    )
    refinement_log = (
        load_json(REFINEMENT_LOG_PATH) if REFINEMENT_LOG_PATH.exists() else {}
    )
    version_diff = (
        parse_jsonish(PROMPT_VERSION_DIFF_PATH)
        if PROMPT_VERSION_DIFF_PATH.exists()
        else {}
    )
    alignment_hits = search_text_hits(
        [
            PROJECT_ROOT / "evals",
            PROJECT_ROOT / "feedback",
            PROJECT_ROOT / "services",
            PROJECT_ROOT / "metadata",
            PROJECT_ROOT / "prompts",
            PROJECT_ROOT / "design",
            PROJECT_ROOT / "ux",
        ],
        {
            "argilla": re.compile(r"\bargilla\b", re.IGNORECASE),
            "wandb": re.compile(r"\bweights & biases\b|\bwandb\b", re.IGNORECASE),
            "reward_bench": re.compile(r"\breward bench\b", re.IGNORECASE),
            "dpo": re.compile(r"\bdpo\b|direct preference optimization", re.IGNORECASE),
            "preference_model": re.compile(r"\breward_model\b|\bpreference model\b", re.IGNORECASE),
            "red_team": re.compile(r"red[_ -]?team", re.IGNORECASE),
        },
    )
    refinement_dir = PROJECT_ROOT / "services" / "refinement_service"
    refinement_files = recursive_listing(refinement_dir)
    sentiment_histogram: dict[str, int] = {}
    for annotation in feedback_annotations:
        sentiment = annotation.get("sentiment", "unknown")
        sentiment_histogram[sentiment] = sentiment_histogram.get(sentiment, 0) + 1

    return {
        "step": "STEP_060",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "step_manifest_hit": locate_step_marker("STEP_060"),
        "directories": {
            "evals": recursive_listing(PROJECT_ROOT / "evals"),
            "feedback": recursive_listing(PROJECT_ROOT / "feedback"),
            "red_teaming_logs_present": (PROJECT_ROOT / "red_teaming" / "logs").exists(),
            "refinement_service_files": refinement_files,
        },
        "alignment_tooling": {
            "status": refinement_report.get("prompt_management_system", {}).get(
                "type",
                "local_file_backed_only",
            ),
            "detectors": alignment_hits,
            "details": "Refinement is tracked through local prompt versions, a design-refinement report, and file-backed feedback annotations. No Argilla, Weights & Biases Reward Bench, or DPO training pipeline was found.",
        },
        "feedback_store": {
            "path": str(FEEDBACK_PATH.relative_to(PROJECT_ROOT)) if FEEDBACK_PATH.exists() else None,
            "annotation_count": len(feedback_annotations),
            "sentiment_histogram": sentiment_histogram,
            "sample_weights": feedback_annotations[0].get("weights") if feedback_annotations else None,
        },
        "prompt_versions": {
            "prototype_version": version_diff.get("prototype_version"),
            "release_candidate_version": version_diff.get("release_candidate_version"),
            "current_target_version": refinement_report.get("optimization_anchors", {})
            .get("prompt_delta", {})
            .get("target_version"),
            "ab_flags": refinement_report.get("ab_flags", []),
        },
        "preference_data_api": {
            "status": "missing",
            "details": "No Preference_Data_API endpoint or thumbs-up/down ingestion service was found in the repo or running stack.",
        },
        "dpo_pipeline": {
            "status": "missing",
            "details": "No DPO training job, reward model scorer, or refinement_results.json artifact was found.",
        },
        "red_team_surface": {
            "status": "missing",
            "details": "The repo contains a few red-team planning references, but no dedicated red_teaming/logs artifact set or executable red-team pipeline.",
        },
        "runtime_alignment_nodes": {
            "validation_service_on_disk": str(
                (PROJECT_ROOT / "services" / "validation_service" / "app.py").relative_to(PROJECT_ROOT)
            ),
            "refinement_service_on_disk": str(
                (refinement_dir / "app.py").relative_to(PROJECT_ROOT)
            )
            if (refinement_dir / "app.py").exists()
            else None,
            "refinement_service_placeholder": refinement_dir.exists() and not refinement_files,
            "refinement_log_entries": len(refinement_log.get("entries", [])),
        },
        "variable_context_keys": {
            "dpo_win_rate": "state.dpo_win_rate",
            "red_team_pass_rate": "state.red_team_pass_rate",
            "refinement_iteration_count": "state.refinement_iteration_count",
        },
        "variable_values": {
            "dpo_win_rate": None,
            "red_team_pass_rate": None,
            "refinement_iteration_count": len(refinement_log.get("entries", [])),
        },
        "gap_notes": [
            "Human feedback annotations, prompt versions, and a refinement service exist, but there is no automated preference-ranker or DPO loop attached to live responses.",
            "The refinement service and prompt registry are implemented on disk, but they are not part of the currently verified standalone compose deployment.",
        ],
    }


def build_production_infrastructure_hash() -> dict[str, Any]:
    app_configured_services = parse_compose_services(PROJECT_ROOT / "docker-compose.standalone.yml")
    domain_services = parse_compose_services(PROJECT_ROOT / "docker-compose.rag-domains.yml")
    search_api_health = probe_http("http://127.0.0.1:8010/api/v1/health")
    benchmarking_health = probe_http("http://127.0.0.1:8023/health")
    phoenix_health = probe_http("http://127.0.0.1:6006")
    degraded_components: list[str] = []
    if isinstance(search_api_health.get("payload"), dict):
        components = search_api_health["payload"].get("components", {})
        degraded_components = [
            name
            for name, details in components.items()
            if isinstance(details, dict) and details.get("status") != "ok"
        ]

    return {
        "step": "STEP_061",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "step_manifest_hit": locate_step_marker("STEP_061"),
        "deployment_target": "local_docker_compose",
        "deployment_strategy": {
            "type": "compose_restart",
            "details": "kb-search-api deployment is defined through Docker Compose. No Kubernetes manifests, service mesh file, or canary rollout controller was found in this repo.",
        },
        "configured_surfaces": {
            "standalone_compose_services": app_configured_services,
            "rag_domains_compose_services": domain_services,
            "github_workflows": recursive_listing(PROJECT_ROOT / ".github"),
            "k8s_present": (PROJECT_ROOT / "k8s").exists(),
            "terraform_present": (PROJECT_ROOT / "terraform").exists(),
        },
        "runtime_probes": {
            "search_api_health": search_api_health,
            "benchmarking_service_health": benchmarking_health,
            "phoenix_ui": phoenix_health,
        },
        "deployment_risks": {
            "search_api_status": (
                search_api_health.get("payload", {}).get("status")
                if isinstance(search_api_health.get("payload"), dict)
                else None
            ),
            "degraded_components": degraded_components,
            "details": "The live search-api health probe is degraded because some sidecar hostnames referenced by the app are not healthy in the current runtime response.",
        },
        "infrastructure_hash": compute_infrastructure_hash(),
        "variable_context_keys": {
            "deployment_target": "state.deployment_target",
            "is_canary_active": "state.is_canary_active",
            "rollback_status": "state.rollback_status",
        },
        "variable_values": {
            "deployment_target": "local_docker_compose",
            "is_canary_active": False,
            "rollback_status": "not_configured",
        },
        "gap_notes": [
            "No blue-green, canary, or automated rollback controller was found in kb-search-api.",
            "The running stack includes more live services than the standalone compose file defines, so deployment drift should be assumed until reconciled.",
        ],
    }


def build_observability_topology(manifest: dict[str, Any]) -> dict[str, Any]:
    system_vitals = manifest.get("system_vitals_threshold", {})
    cost_config = load_json(PROJECT_ROOT / "ops" / "billing" / "cost_config.json")
    prometheus_health = probe_http("http://127.0.0.1:9090/-/healthy")
    grafana_health = probe_http("http://127.0.0.1:3000/api/health")
    phoenix_health = probe_http("http://127.0.0.1:6006")
    search_api_health = probe_http("http://127.0.0.1:8010/api/v1/health")

    return {
        "step": "STEP_062",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "step_manifest_hit": locate_step_marker("STEP_062"),
        "directories": {
            "kb_package_observability": recursive_listing(PROJECT_ROOT / "observability"),
            "infra_monitoring": recursive_listing(INFRA_ROOT / "monitoring"),
            "infra_config_grafana": recursive_listing(INFRA_ROOT / "config" / "grafana"),
            "infra_config_prometheus": recursive_listing(INFRA_ROOT / "config" / "prometheus"),
        },
        "providers": {
            "otel_export": {
                "status": "configured_in_app",
                "module": "telemetry.py",
                "default_traces_endpoint": "http://host.docker.internal:6006/v1/traces",
            },
            "phoenix_ui": phoenix_health,
            "prometheus": prometheus_health,
            "grafana": grafana_health,
            "loki_datasource": {
                "path": str(
                    (INFRA_ROOT / "config" / "grafana" / "datasources" / "loki.yaml")
                ),
                "url": "https://infra-loki:3100",
            },
        },
        "sampling_and_retention": {
            "prometheus_scrape_interval": extract_inline_value(
                INFRA_ROOT / "config" / "prometheus.yml",
                "scrape_interval",
            ),
            "prometheus_evaluation_interval": extract_inline_value(
                INFRA_ROOT / "config" / "prometheus.yml",
                "evaluation_interval",
            ),
            "prometheus_retention_time": "15d",
            "loki_retention_period": extract_inline_value(
                INFRA_ROOT / "config" / "loki-config.yml",
                "retention_period",
            ),
            "promtail_debug_log_sampling_rate": "0.1",
            "llm_trace_retention_period": None,
            "evaluation_sampling_rate": None,
        },
        "package_observability_status": {
            "path": "observability/package-observability.yml",
            "details": load_text(PROJECT_ROOT / "observability" / "package-observability.yml"),
        },
        "quality_signals": {
            "current_faithfulness_available": system_vitals.get("performance_monitor", {})
            .get("metrics", {})
            .get("answer_faithfulness"),
            "search_api_health_status": (
                search_api_health.get("payload", {}).get("status")
                if isinstance(search_api_health.get("payload"), dict)
                else None
            ),
            "token_budget_per_user": cost_config.get("query_budget", {}).get(
                "token_budget_per_user", {}
            ),
        },
        "variable_context_keys": {
            "current_faithfulness_avg": "state.current_faithfulness_avg",
            "token_spend_rate": "state.token_spend_rate",
            "alert_active": "state.alert_active",
        },
        "variable_values": {
            "current_faithfulness_avg": None,
            "token_spend_rate": None,
            "alert_active": None,
        },
        "gap_notes": [
            "OpenTelemetry export and Phoenix UI are present, but no explicit trace-retention policy was found in this repo.",
            "kb-search-api has a package observability manifest, but it still declares no Prometheus scrape targets or Grafana datasources of its own.",
            "The current live stack surfaces retrieval health and benchmarking, but answer-faithfulness remains unavailable.",
        ],
    }


def build_manifest_sections() -> dict[str, Any]:
    manifest = load_json(MANIFEST_PATH) if MANIFEST_PATH.exists() else {}

    generation_topology = build_generation_topology(manifest)
    alignment_baseline = build_alignment_baseline()
    production_infrastructure_hash = build_production_infrastructure_hash()
    observability_topology = build_observability_topology(manifest)

    manifest["generation_topology"] = generation_topology
    manifest["alignment_baseline"] = alignment_baseline
    manifest["production_infrastructure_hash"] = production_infrastructure_hash
    manifest["observability_topology"] = observability_topology

    variable_contexts = manifest.setdefault("variable_contexts", {})
    variable_contexts["generation_anchor_context"] = {
        "state_keys": generation_topology["variable_context_keys"],
        "current_values": generation_topology["variable_values"],
    }
    variable_contexts["alignment_anchor_context"] = {
        "state_keys": alignment_baseline["variable_context_keys"],
        "current_values": alignment_baseline["variable_values"],
    }
    variable_contexts["deployment_anchor_context"] = {
        "state_keys": production_infrastructure_hash["variable_context_keys"],
        "current_values": production_infrastructure_hash["variable_values"],
    }
    variable_contexts["observability_anchor_context"] = {
        "state_keys": observability_topology["variable_context_keys"],
        "current_values": observability_topology["variable_values"],
    }
    manifest["generated_at"] = datetime.now(timezone.utc).isoformat()
    return manifest


def main() -> int:
    manifest = build_manifest_sections()
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    summary = {
        "manifest_path": str(MANIFEST_PATH),
        "generation_topology_status": manifest["generation_topology"]["generation_runtime"][
            "status"
        ],
        "alignment_annotation_count": manifest["alignment_baseline"]["feedback_store"][
            "annotation_count"
        ],
        "deployment_target": manifest["production_infrastructure_hash"]["variable_values"][
            "deployment_target"
        ],
        "phoenix_reachable": manifest["observability_topology"]["providers"]["phoenix_ui"][
            "reachable"
        ],
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
