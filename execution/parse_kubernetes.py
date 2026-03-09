#!/usr/bin/env python3
"""
parse_kubernetes.py — Layer 3 Execution Script

Purpose : Parse Kubernetes YAML files and extract Resource nodes + DEPENDS_ON edges.
Inputs  : --input <file or directory of .yaml/.yml files>
          --output <optional JSON output file>
          --verbose flag
Outputs : JSON { "resources": [...], "edges": [...] }
          Each resource: { id, name, type, file, line_number, source }
          Each edge:     { source, target }

Deps    : PyYAML (pip install pyyaml)

Inference rules:
  1. Service → Deployment   via spec.selector ⊆ pod template labels (same namespace)
  2. Deployment → ConfigMap via envFrom[].configMapRef.name OR volumes[].configMap.name
  3. Deployment → Secret    via envFrom[].secretRef.name OR volumes[].secret.secretName
  4. Ingress → Service      via spec.rules[].http.paths[].backend.service.name
"""

import argparse
import json
import os
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Optional devops_utils validation (graceful fallback if unavailable)
# ---------------------------------------------------------------------------

def _try_validate_manifest(file_path: str) -> None:
    """
    Attempt to validate the YAML manifest using KubernetesHelper from devops_utils.
    Silently skips if devops_utils is not importable.
    Suppresses stdout since devops_utils prints directly to stdout (not stderr).
    """
    import io
    import contextlib
    try:
        _skill_scripts = os.path.join(
            os.path.dirname(__file__), "..",
            ".claude", "skills", "devops-iac-engineer", "scripts"
        )
        if _skill_scripts not in sys.path:
            sys.path.insert(0, os.path.abspath(_skill_scripts))
        from devops_utils import KubernetesHelper
        with contextlib.redirect_stdout(io.StringIO()):
            KubernetesHelper.validate_manifest(file_path)
    except Exception:
        pass  # Validation is best-effort; never block parsing


# ---------------------------------------------------------------------------
# Resource extraction helpers
# ---------------------------------------------------------------------------

def _resource_id(kind: str, namespace: str, name: str) -> str:
    return f"{kind}/{namespace}/{name}"


def _parse_docs_from_file(file_path: str) -> list[dict]:
    """
    Load all YAML documents from a single file.
    Returns a list of (doc, file_path) tuples, skipping None/empty docs.
    """
    try:
        import yaml
    except ImportError:
        raise ImportError("PyYAML is required. Install with: pip install pyyaml")

    rel_path = os.path.basename(file_path)
    docs = []
    try:
        with open(file_path, encoding="utf-8") as fh:
            for doc in yaml.safe_load_all(fh):
                if doc is not None and isinstance(doc, dict):
                    docs.append((doc, rel_path))
    except Exception as exc:
        print(f"[error] Failed to parse {file_path}: {exc}", file=sys.stderr)
    return docs


def _extract_resources(docs: list[tuple[dict, str]]) -> list[dict]:
    """
    Convert raw YAML documents into Resource node dicts.
    Skips any doc missing 'kind' or 'metadata.name'.
    """
    resources = []
    for doc, rel_path in docs:
        kind = doc.get("kind")
        metadata = doc.get("metadata", {})
        name = metadata.get("name")
        if not kind or not name:
            continue
        namespace = metadata.get("namespace") or "default"
        res_id = _resource_id(kind, namespace, name)
        resources.append({
            "id": res_id,
            "name": name,
            "type": kind,
            "file": rel_path,
            "line_number": 0,   # PyYAML does not expose line numbers
            "source": "kubernetes",
            # Internal-only fields (stripped from final output)
            "_kind": kind,
            "_namespace": namespace,
            "_doc": doc,
        })
    return resources


# ---------------------------------------------------------------------------
# Edge inference
# ---------------------------------------------------------------------------

def _infer_edges(resources: list[dict]) -> set[tuple[str, str]]:
    """
    Apply all 4 inference rules to the full resource registry.
    Returns a set of (source_id, target_id) tuples (deduped, no self-edges).
    """
    edges: set[tuple[str, str]] = set()

    # Index resources for fast lookup
    by_kind_ns: dict[tuple[str, str], list[dict]] = {}
    for r in resources:
        key = (r["_kind"], r["_namespace"])
        by_kind_ns.setdefault(key, []).append(r)

    for r in resources:
        kind = r["_kind"]
        ns = r["_namespace"]
        doc = r["_doc"]
        src_id = r["id"]
        spec = doc.get("spec", {}) or {}

        # ── Rule 1: Service → Deployment ────────────────────────────────────
        if kind == "Service":
            selector = spec.get("selector") or {}
            if selector:
                for dep in by_kind_ns.get(("Deployment", ns), []):
                    pod_labels = (
                        dep["_doc"]
                        .get("spec", {})
                        .get("template", {})
                        .get("metadata", {})
                        .get("labels", {})
                        or {}
                    )
                    # selector must be a non-empty subset of pod_labels
                    if selector and all(pod_labels.get(k) == v for k, v in selector.items()):
                        _add_edge(edges, src_id, dep["id"])

        # ── Rules 2 & 3: Deployment → ConfigMap / Secret ────────────────────
        elif kind == "Deployment":
            pod_spec = spec.get("template", {}).get("spec", {}) or {}
            containers = pod_spec.get("containers", []) or []
            init_containers = pod_spec.get("initContainers", []) or []
            volumes = pod_spec.get("volumes", []) or []

            for container in containers + init_containers:
                for env_from in (container.get("envFrom") or []):
                    # ConfigMap reference via envFrom
                    cm_ref = (env_from.get("configMapRef") or {}).get("name")
                    if cm_ref:
                        _add_edge(edges, src_id, _resource_id("ConfigMap", ns, cm_ref))
                    # Secret reference via envFrom
                    sec_ref = (env_from.get("secretRef") or {}).get("name")
                    if sec_ref:
                        _add_edge(edges, src_id, _resource_id("Secret", ns, sec_ref))

                # Individual env vars sourcing from ConfigMap/Secret
                for env in (container.get("env") or []):
                    value_from = env.get("valueFrom") or {}
                    cm_key_ref = (value_from.get("configMapKeyRef") or {}).get("name")
                    if cm_key_ref:
                        _add_edge(edges, src_id, _resource_id("ConfigMap", ns, cm_key_ref))
                    sec_key_ref = (value_from.get("secretKeyRef") or {}).get("name")
                    if sec_key_ref:
                        _add_edge(edges, src_id, _resource_id("Secret", ns, sec_key_ref))

            for volume in volumes:
                # ConfigMap volume
                cm_vol = (volume.get("configMap") or {}).get("name")
                if cm_vol:
                    _add_edge(edges, src_id, _resource_id("ConfigMap", ns, cm_vol))
                # Secret volume
                sec_vol = (volume.get("secret") or {}).get("secretName")
                if sec_vol:
                    _add_edge(edges, src_id, _resource_id("Secret", ns, sec_vol))

        # ── Rule 4: Ingress → Service ────────────────────────────────────────
        elif kind == "Ingress":
            for rule in (spec.get("rules") or []):
                http = rule.get("http") or {}
                for path in (http.get("paths") or []):
                    backend = path.get("backend") or {}
                    # networking.k8s.io/v1 format: backend.service.name
                    svc_name = (backend.get("service") or {}).get("name")
                    if not svc_name:
                        # extensions/v1beta1 format: backend.serviceName
                        svc_name = backend.get("serviceName")
                    if svc_name:
                        _add_edge(edges, src_id, _resource_id("Service", ns, svc_name))

    return edges


def _add_edge(edges: set[tuple[str, str]], source: str, target: str) -> None:
    """Add edge only if it's not a self-reference."""
    if source != target:
        edges.add((source, target))


# ---------------------------------------------------------------------------
# Core parsing function (importable as a module)
# ---------------------------------------------------------------------------

def parse_kubernetes_files(input_path: str, verbose: bool = False) -> dict:
    """
    Parse one YAML file or all .yaml/.yml files in a directory.

    Builds the full resource registry across ALL files BEFORE inferring edges
    so cross-file Service → Deployment relationships are resolved correctly.

    Returns:
        {
            "resources": [ {id, name, type, file, line_number, source}, ... ],
            "edges":     [ {source, target}, ... ]
        }
    """
    path = Path(input_path)
    if not path.exists():
        raise FileNotFoundError(f"Input path does not exist: {input_path}")

    # Collect YAML files
    if path.is_dir():
        yaml_files = sorted(
            list(path.glob("*.yaml")) + list(path.glob("*.yml"))
        )
    else:
        yaml_files = [path]

    if not yaml_files:
        if verbose:
            print(f"[warn] No YAML files found in {input_path}", file=sys.stderr)
        return {"resources": [], "edges": []}

    # Phase 1: load all documents from all files
    all_docs: list[tuple[dict, str]] = []
    for yaml_file in yaml_files:
        if yaml_file.is_file():
            _try_validate_manifest(str(yaml_file))
            all_docs.extend(_parse_docs_from_file(str(yaml_file)))

    # Phase 2: extract resource nodes (full registry)
    all_resources = _extract_resources(all_docs)

    if verbose:
        print(
            f"[info] Parsed {len(yaml_files)} file(s): {len(all_resources)} resources",
            file=sys.stderr,
        )

    # Phase 3: infer edges across full registry
    edge_set = _infer_edges(all_resources)

    if verbose:
        print(f"[info] Inferred {len(edge_set)} edges", file=sys.stderr)

    # Strip internal fields before returning
    clean_resources = [
        {k: v for k, v in r.items() if not k.startswith("_")}
        for r in all_resources
    ]

    return {
        "resources": clean_resources,
        "edges": [{"source": s, "target": t} for s, t in sorted(edge_set)],
    }


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Parse Kubernetes YAML files and extract resource dependency graph as JSON."
    )
    parser.add_argument(
        "--input", required=True,
        help="Path to a single .yaml/.yml file or a directory containing YAML files"
    )
    parser.add_argument(
        "--output", default=None,
        help="Write JSON result to this file (default: stdout)"
    )
    parser.add_argument(
        "--verbose", action="store_true",
        help="Print debug information to stderr"
    )
    args = parser.parse_args()

    try:
        result = parse_kubernetes_files(args.input, verbose=args.verbose)
    except FileNotFoundError as exc:
        print(f"[error] {exc}", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print(f"[error] {exc}", file=sys.stderr)
        sys.exit(1)

    output_json = json.dumps(result, indent=2)

    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, "w") as fh:
            fh.write(output_json)
        if args.verbose:
            print(f"[info] Written to {args.output}", file=sys.stderr)
    else:
        print(output_json)


if __name__ == "__main__":
    main()
