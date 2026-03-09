#!/usr/bin/env python3
"""
neo4j_load.py — Layer 3 Execution Script

Purpose : Load parsed infrastructure JSON (from parse_terraform.py or
          parse_kubernetes.py) into Neo4j as Resource nodes and DEPENDS_ON edges.
Inputs  : --input <json_file>   (or stdin if omitted)
          --skip-wait           Skip Neo4j readiness wait (useful when Neo4j is known-ready)
Outputs : Prints "Loaded {n} resources, {m} edges" on success.

Env vars (loaded from .env if present):
    NEO4J_URI       bolt://localhost:7687
    NEO4J_USERNAME  neo4j
    NEO4J_PASSWORD  password
    NEO4J_DATABASE  neo4j
"""

import argparse
import json
import os
import sys


# ---------------------------------------------------------------------------
# Path setup: allow importing from backend/app/graph/
# ---------------------------------------------------------------------------

_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _PROJECT_ROOT)

# Load .env before importing the client (so os.environ is populated)
try:
    from dotenv import load_dotenv
    _env_file = os.path.join(_PROJECT_ROOT, ".env")
    if os.path.exists(_env_file):
        load_dotenv(_env_file)
except ImportError:
    pass  # python-dotenv not installed; rely on shell environment


def _get_client():
    """Import Neo4jClient at call-time (after env is loaded)."""
    try:
        # Local development: project root is <InfraGraph>/
        from backend.app.graph.neo4j_client import Neo4jClient
    except ModuleNotFoundError:
        # Docker: backend is mounted at /app/, execution at /app/execution/
        from app.graph.neo4j_client import Neo4jClient  # type: ignore[import]
    return Neo4jClient.from_env()


def _get_queries():
    """Import queries module at call-time."""
    try:
        from backend.app.graph import queries
    except ModuleNotFoundError:
        from app.graph import queries  # type: ignore[import]
    return queries


# ---------------------------------------------------------------------------
# Core load function (importable)
# ---------------------------------------------------------------------------

def load_from_dict(parsed: dict, skip_wait: bool = False, verbose: bool = False) -> dict:
    """
    Load a parsed result dict into Neo4j.

    Args:
        parsed: {"resources": [...], "edges": [...]}
        skip_wait: skip Neo4j readiness poll (use when caller already verified)
        verbose: print progress to stderr

    Returns:
        {"node_count": N, "edge_count": M}
    """
    queries = _get_queries()

    with _get_client() as client:
        if not skip_wait:
            client.wait_until_ready()

        resources = parsed.get("resources", [])
        edges = parsed.get("edges", [])

        if verbose:
            print(f"[neo4j_load] Loading {len(resources)} resources...", file=sys.stderr)
        node_count = queries.load_resources(client, resources)

        if verbose:
            print(f"[neo4j_load] Loading {len(edges)} edges...", file=sys.stderr)
        edge_count = queries.load_edges(client, edges)

    return {"node_count": node_count, "edge_count": edge_count}


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Load parsed Terraform/Kubernetes JSON into Neo4j."
    )
    parser.add_argument(
        "--input", default=None,
        help="Path to JSON file from parse_terraform.py or parse_kubernetes.py "
             "(default: read from stdin)"
    )
    parser.add_argument(
        "--skip-wait", action="store_true",
        help="Skip Neo4j readiness wait (assume it is already reachable)"
    )
    parser.add_argument(
        "--verbose", action="store_true",
        help="Print progress to stderr"
    )
    args = parser.parse_args()

    # Read input JSON
    try:
        if args.input:
            with open(args.input) as fh:
                parsed = json.load(fh)
        else:
            parsed = json.load(sys.stdin)
    except FileNotFoundError:
        print(f"[error] File not found: {args.input}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as exc:
        print(f"[error] Invalid JSON: {exc}", file=sys.stderr)
        sys.exit(1)

    # Validate expected shape
    if "resources" not in parsed or "edges" not in parsed:
        print(
            "[error] Input JSON must have 'resources' and 'edges' keys. "
            "Run parse_terraform.py or parse_kubernetes.py first.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Load into Neo4j
    try:
        result = load_from_dict(parsed, skip_wait=args.skip_wait, verbose=args.verbose)
    except KeyError as exc:
        print(
            f"[error] Missing environment variable: {exc}. "
            "Set NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD in .env or shell.",
            file=sys.stderr,
        )
        sys.exit(1)
    except RuntimeError as exc:
        print(f"[error] {exc}", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print(f"[error] {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"Loaded {result['node_count']} resources, {result['edge_count']} edges")


if __name__ == "__main__":
    main()
