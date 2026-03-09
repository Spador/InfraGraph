"""
routes/graph.py — Read and management endpoints for the Neo4j resource graph.

GET  /graph                     — full graph
GET  /graph/resource/<id>       — depth-2 subgraph around one resource
GET  /graph/stats               — aggregate stats
POST /graph/reset               — delete all nodes and edges
"""

import urllib.parse

from flask import Blueprint, current_app, jsonify

from ..graph.neo4j_client import Neo4jClient
from ..graph import queries

graph_bp = Blueprint("graph", __name__)


def _get_client() -> Neo4jClient:
    return Neo4jClient.from_env()


# ---------------------------------------------------------------------------
# GET /graph
# ---------------------------------------------------------------------------

@graph_bp.route("", methods=["GET"])
def get_graph():
    try:
        with _get_client() as client:
            result = queries.get_full_graph(client)
        return jsonify(result), 200
    except Exception as exc:
        current_app.logger.exception("get_graph error")
        return jsonify({"error": str(exc)}), 500


# ---------------------------------------------------------------------------
# GET /graph/resource/<id>
# ---------------------------------------------------------------------------

@graph_bp.route("/resource/<path:resource_id>", methods=["GET"])
def get_subgraph(resource_id: str):
    # URL-decode (e.g. "Deployment%2Fdefault%2Fapp" → "Deployment/default/app")
    resource_id = urllib.parse.unquote(resource_id)
    try:
        with _get_client() as client:
            result = queries.get_subgraph(client, resource_id)

        if not result["nodes"]:
            return jsonify({"error": f"Resource not found: {resource_id}"}), 404

        return jsonify(result), 200

    except Exception as exc:
        current_app.logger.exception("get_subgraph error")
        return jsonify({"error": str(exc)}), 500


# ---------------------------------------------------------------------------
# GET /graph/stats
# ---------------------------------------------------------------------------

@graph_bp.route("/stats", methods=["GET"])
def get_stats():
    try:
        with _get_client() as client:
            result = queries.get_stats(client)
        return jsonify(result), 200
    except Exception as exc:
        current_app.logger.exception("get_stats error")
        return jsonify({"error": str(exc)}), 500


# ---------------------------------------------------------------------------
# POST /graph/reset
# ---------------------------------------------------------------------------

@graph_bp.route("/reset", methods=["POST"])
def reset_graph():
    try:
        with _get_client() as client:
            deleted = queries.reset_graph(client)
        return jsonify({"deleted": deleted}), 200
    except Exception as exc:
        current_app.logger.exception("reset_graph error")
        return jsonify({"error": str(exc)}), 500
