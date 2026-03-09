#!/usr/bin/env python3
"""
seed_loader.py — Layer 3 Execution Script

Purpose : Auto-populate Neo4j with seed infrastructure data on first container start.
          Idempotent: skips loading if the graph already contains nodes.
Inputs  : --seed-dir <path>  Path to the seed/ directory containing main.tf, variables.tf,
                             and seed-k8s.yaml (default: ../seed relative to this script)
          --verbose           Print progress details
          --force             Load seed data even if graph is not empty (re-seed)
Env vars: SEED_ON_START=true required to run (allows disabling via env)
          NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD, NEO4J_DATABASE — from .env

Called by: backend/entrypoint.sh
"""

import argparse
import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.abspath(os.path.join(_SCRIPT_DIR, ".."))

# Ensure this execution/ directory is first on the path so we can import
# parse_terraform, parse_kubernetes, and neo4j_load from here.
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

# Also add project root so backend.app.graph imports work (local dev).
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# Load .env before any imports that need env vars
try:
    from dotenv import load_dotenv
    _env_path = os.path.join(_PROJECT_ROOT, ".env")
    if os.path.exists(_env_path):
        load_dotenv(_env_path)
except ImportError:
    pass

# ---------------------------------------------------------------------------
# Import Neo4jClient (dual-path: local vs Docker)
# ---------------------------------------------------------------------------


def _get_client():
    try:
        from backend.app.graph.neo4j_client import Neo4jClient
    except ModuleNotFoundError:
        from app.graph.neo4j_client import Neo4jClient  # type: ignore[import]
    return Neo4jClient.from_env()


# ---------------------------------------------------------------------------
# Core seeding logic
# ---------------------------------------------------------------------------

def seed(seed_dir: str, force: bool = False, verbose: bool = False) -> None:
    """
    Parse seed files and load them into Neo4j.
    Skips if the graph already has nodes (idempotent), unless force=True.
    """
    seed_path = Path(seed_dir)
    if not seed_path.exists():
        print(f"[seed_loader] Seed directory not found: {seed_dir}", file=sys.stderr)
        sys.exit(1)

    # Wait for Neo4j to be ready
    if verbose:
        print("[seed_loader] Waiting for Neo4j…", file=sys.stderr)
    with _get_client() as client:
        client.wait_until_ready()

        # Idempotency check
        if not force:
            result = client.execute_read("MATCH (n:Resource) RETURN count(n) AS c")
            existing = result[0]["c"] if result else 0
            if existing > 0:
                print(f"[seed_loader] Graph already has {existing} nodes — skipping seed.")
                return

    # Parse Terraform seed files
    from parse_terraform import parse_terraform_files  # noqa: E402

    tf_result: dict = {"resources": [], "edges": []}
    for tf_file in ["main.tf", "variables.tf"]:
        fp = seed_path / tf_file
        if fp.exists():
            if verbose:
                print(f"[seed_loader] Parsing {fp}…", file=sys.stderr)
            try:
                partial = parse_terraform_files(str(fp), verbose=verbose)
                tf_result["resources"].extend(partial["resources"])
                tf_result["edges"].extend(partial["edges"])
            except Exception as exc:
                print(f"[seed_loader] Warning: failed to parse {fp}: {exc}", file=sys.stderr)

    # Parse Kubernetes seed file
    from parse_kubernetes import parse_kubernetes_files  # noqa: E402

    k8s_result: dict = {"resources": [], "edges": []}
    k8s_file = seed_path / "seed-k8s.yaml"
    if k8s_file.exists():
        if verbose:
            print(f"[seed_loader] Parsing {k8s_file}…", file=sys.stderr)
        try:
            k8s_result = parse_kubernetes_files(str(k8s_file), verbose=verbose)
        except Exception as exc:
            print(f"[seed_loader] Warning: failed to parse {k8s_file}: {exc}", file=sys.stderr)

    # Merge Terraform + Kubernetes results; deduplicate edges
    all_resources = tf_result["resources"] + k8s_result["resources"]
    edge_set = {(e["source"], e["target"]) for e in tf_result["edges"] + k8s_result["edges"]}
    combined = {
        "resources": all_resources,
        "edges": [{"source": s, "target": t} for s, t in sorted(edge_set)],
    }

    if not combined["resources"]:
        print("[seed_loader] No resources found in seed directory.", file=sys.stderr)
        return

    # Load into Neo4j (Neo4j already verified ready above)
    from neo4j_load import load_from_dict  # noqa: E402

    result = load_from_dict(combined, skip_wait=True, verbose=verbose)
    print(f"Seed complete: {result['node_count']} resources, {result['edge_count']} edges loaded.")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Load seed infrastructure data into Neo4j."
    )
    parser.add_argument(
        "--seed-dir",
        default=os.path.join(_PROJECT_ROOT, "seed"),
        help="Path to directory containing main.tf, variables.tf, seed-k8s.yaml",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Load seed data even if graph already has nodes",
    )
    parser.add_argument(
        "--verbose", action="store_true",
        help="Print debug info to stderr",
    )
    args = parser.parse_args()

    # Respect SEED_ON_START env var — allows disabling via environment
    seed_on_start = os.environ.get("SEED_ON_START", "true").lower()
    if seed_on_start != "true":
        print("[seed_loader] SEED_ON_START is not 'true' — skipping seed.")
        return

    try:
        seed(args.seed_dir, force=args.force, verbose=args.verbose)
    except KeyError as exc:
        print(
            f"[seed_loader] Missing env var: {exc}. "
            "Set NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD in .env",
            file=sys.stderr,
        )
        sys.exit(1)
    except Exception as exc:
        print(f"[seed_loader] Error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
