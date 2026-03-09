"""
queries.py — All parameterized Cypher query functions for InfraGraph.

Every function accepts a Neo4jClient instance as its first argument.
No query uses string interpolation — only named parameters ($param).

Node model in Neo4j:
    (:Resource {id, name, type, file, line_number, source})
Edge model:
    (:Resource)-[:DEPENDS_ON]->(:Resource)
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .neo4j_client import Neo4jClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _node_to_dict(node: Any) -> dict:
    """Convert a neo4j Node object to a plain Python dict."""
    return dict(node.items())


# ---------------------------------------------------------------------------
# Write operations
# ---------------------------------------------------------------------------

UPSERT_RESOURCE = """
MERGE (r:Resource {id: $id})
SET r.name        = $name,
    r.type        = $type,
    r.file        = $file,
    r.line_number = $line_number,
    r.source      = $source
"""

UPSERT_EDGE = """
MATCH (a:Resource {id: $source}), (b:Resource {id: $target})
MERGE (a)-[:DEPENDS_ON]->(b)
"""


def load_resources(client: "Neo4jClient", resources: list[dict]) -> int:
    """
    Upsert all resource nodes. Returns the count of resources processed.
    Uses batch transactions (100 per chunk) for efficiency.
    """
    if not resources:
        return 0

    chunk_size = 100
    for i in range(0, len(resources), chunk_size):
        chunk = resources[i: i + chunk_size]
        client.execute_write_batch(UPSERT_RESOURCE, chunk)

    return len(resources)


def load_edges(client: "Neo4jClient", edges: list[dict]) -> int:
    """
    Upsert all DEPENDS_ON edges. Silently skips edges where either endpoint
    node does not yet exist in the graph (MATCH returns no rows).
    Returns the count of edges processed.
    """
    if not edges:
        return 0

    chunk_size = 100
    for i in range(0, len(edges), chunk_size):
        chunk = edges[i: i + chunk_size]
        client.execute_write_batch(UPSERT_EDGE, chunk)

    return len(edges)


def load_graph(client: "Neo4jClient", parsed: dict) -> dict:
    """
    Load a full parsed result dict (from parse_terraform or parse_kubernetes) into Neo4j.
    Returns {"node_count": N, "edge_count": M}.
    """
    node_count = load_resources(client, parsed.get("resources", []))
    edge_count = load_edges(client, parsed.get("edges", []))
    return {"node_count": node_count, "edge_count": edge_count}


# ---------------------------------------------------------------------------
# Read operations
# ---------------------------------------------------------------------------

def get_full_graph(client: "Neo4jClient") -> dict:
    """
    Return all Resource nodes and all DEPENDS_ON edges.
    Response shape: {"nodes": [...], "edges": [...]}
    """
    records = client.execute_read("""
        MATCH (n:Resource)
        OPTIONAL MATCH (n)-[:DEPENDS_ON]->(m:Resource)
        RETURN n, collect(m.id) AS targets
    """)

    seen: set[str] = set()
    nodes: list[dict] = []
    edges: list[dict] = []

    for record in records:
        node = _node_to_dict(record["n"])
        if node["id"] not in seen:
            nodes.append(node)
            seen.add(node["id"])
        for target_id in record["targets"]:
            if target_id:
                edges.append({"source": node["id"], "target": target_id})

    return {"nodes": nodes, "edges": edges}


def get_subgraph(client: "Neo4jClient", resource_id: str, depth: int = 2) -> dict:
    """
    Return the depth-N neighbourhood around a single Resource node.
    Includes all nodes within `depth` hops (in any direction) and all edges
    between those nodes.
    Response shape: {"nodes": [...], "edges": [...]}  (empty lists if not found)
    """
    records = client.execute_read(
        """
        MATCH (center:Resource {id: $id})
        OPTIONAL MATCH path=(center)-[:DEPENDS_ON*0..$depth]-(neighbor:Resource)
        WITH collect(DISTINCT center) + collect(DISTINCT neighbor) AS all_nodes
        UNWIND all_nodes AS n
        OPTIONAL MATCH (n)-[:DEPENDS_ON]->(m:Resource)
        WHERE m IN all_nodes
        RETURN DISTINCT n, collect(DISTINCT m.id) AS targets
        """,
        id=resource_id,
        depth=depth,
    )

    seen: set[str] = set()
    nodes: list[dict] = []
    edges: list[dict] = []

    for record in records:
        if record["n"] is None:
            continue
        node = _node_to_dict(record["n"])
        if node["id"] not in seen:
            nodes.append(node)
            seen.add(node["id"])
        for target_id in record["targets"]:
            if target_id:
                edges.append({"source": node["id"], "target": target_id})

    return {"nodes": nodes, "edges": edges}


def get_stats(client: "Neo4jClient") -> dict:
    """
    Return aggregate graph statistics.
    Response shape matches GraphStats Pydantic model.
    """
    # Node count
    node_records = client.execute_read(
        "MATCH (n:Resource) RETURN count(n) AS node_count"
    )
    node_count = node_records[0]["node_count"] if node_records else 0

    # Edge count
    edge_records = client.execute_read(
        "MATCH ()-[r:DEPENDS_ON]->() RETURN count(r) AS edge_count"
    )
    edge_count = edge_records[0]["edge_count"] if edge_records else 0

    # Most connected node (by total degree — both incoming and outgoing)
    most_connected = None
    try:
        mc_records = client.execute_read("""
            MATCH (n:Resource)
            OPTIONAL MATCH (n)-[:DEPENDS_ON]-(neighbor)
            WITH n, count(neighbor) AS degree
            ORDER BY degree DESC
            LIMIT 1
            RETURN n.id AS id, n.name AS name, n.type AS type, degree
        """)
        if mc_records and mc_records[0]["id"] is not None:
            most_connected = {
                "id": mc_records[0]["id"],
                "name": mc_records[0]["name"],
                "type": mc_records[0]["type"],
                "degree": mc_records[0]["degree"],
            }
    except Exception as exc:
        print(f"[warn] most_connected query failed: {exc}", file=sys.stderr)

    # Isolated nodes (no DEPENDS_ON relationships in any direction)
    isolated_records = client.execute_read("""
        MATCH (n:Resource)
        WHERE NOT (n)-[:DEPENDS_ON]->()
          AND NOT ()-[:DEPENDS_ON]->(n)
        RETURN count(n) AS isolated_count
    """)
    isolated_count = isolated_records[0]["isolated_count"] if isolated_records else 0

    # Circular dependency detection (nodes that appear in their own dependency chain)
    circular_dependencies = 0
    try:
        cycle_records = client.execute_read("""
            MATCH (n:Resource)-[:DEPENDS_ON*1..10]->(n)
            RETURN count(DISTINCT n) AS circular_dependencies
        """)
        if cycle_records:
            circular_dependencies = cycle_records[0]["circular_dependencies"]
    except Exception as exc:
        print(f"[warn] cycle detection query failed: {exc}", file=sys.stderr)

    return {
        "node_count": node_count,
        "edge_count": edge_count,
        "most_connected": most_connected,
        "isolated_count": isolated_count,
        "circular_dependencies": circular_dependencies,
    }


def reset_graph(client: "Neo4jClient") -> int:
    """
    Delete all Resource nodes (and their relationships). Returns the count deleted.
    """
    count_records = client.execute_read(
        "MATCH (n:Resource) RETURN count(n) AS total"
    )
    total = count_records[0]["total"] if count_records else 0
    client.execute_write("MATCH (n:Resource) DETACH DELETE n")
    return total
