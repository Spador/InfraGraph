"""
routes/parse.py — File upload endpoints for Terraform and Kubernetes parsing.

POST /parse/terraform  — accepts .tf or .zip
POST /parse/kubernetes — accepts .yaml, .yml, or .zip

Flow per request:
  1. Validate file field and extension
  2. Save to tempfile (extract zip if needed)
  3. Parse via the appropriate parser wrapper (Layer 3 via parser wrapper)
  4. Load result into Neo4j via queries.load_graph()
  5. Return {node_count, edge_count}
  6. Cleanup temp files unconditionally in finally block
"""

import os
import shutil
import tempfile
import zipfile
from typing import Optional

from flask import Blueprint, current_app, jsonify, request

from ..graph.neo4j_client import Neo4jClient
from ..graph import queries
from ..parsers.terraform import TerraformParser
from ..parsers.kubernetes import KubernetesParser

parse_bp = Blueprint("parse", __name__)

_TF_EXTENSIONS = {".tf", ".zip"}
_K8S_EXTENSIONS = {".yaml", ".yml", ".zip"}


def _get_client() -> Neo4jClient:
    return Neo4jClient.from_env()


# ---------------------------------------------------------------------------
# POST /parse/terraform
# ---------------------------------------------------------------------------

@parse_bp.route("/terraform", methods=["POST"])
def parse_terraform():
    uploaded = request.files.get("file")
    if not uploaded or not uploaded.filename:
        return jsonify({"error": "No file provided"}), 400

    ext = os.path.splitext(uploaded.filename)[1].lower()
    if ext not in _TF_EXTENSIONS:
        return jsonify({
            "error": f"Unsupported file type '{ext}'. Accepted: .tf, .zip"
        }), 400

    tmp_file = None
    tmp_dir = None
    try:
        # Save upload to a named temp file
        tmp_file = tempfile.NamedTemporaryFile(suffix=ext, delete=False)
        uploaded.save(tmp_file.name)
        tmp_file.close()

        if ext == ".zip":
            tmp_dir = tempfile.mkdtemp()
            with zipfile.ZipFile(tmp_file.name) as zf:
                zf.extractall(tmp_dir)
            parse_path = tmp_dir
        else:
            parse_path = tmp_file.name

        parsed = TerraformParser(parse_path).parse()

        with _get_client() as client:
            result = queries.load_graph(client, parsed)

        return jsonify(result), 200

    except (ValueError, Exception) as exc:
        current_app.logger.exception("Terraform parse error")
        return jsonify({"error": str(exc)}), 500

    finally:
        _cleanup(tmp_file.name if tmp_file else None, tmp_dir)


# ---------------------------------------------------------------------------
# POST /parse/kubernetes
# ---------------------------------------------------------------------------

@parse_bp.route("/kubernetes", methods=["POST"])
def parse_kubernetes():
    uploaded = request.files.get("file")
    if not uploaded or not uploaded.filename:
        return jsonify({"error": "No file provided"}), 400

    ext = os.path.splitext(uploaded.filename)[1].lower()
    if ext not in _K8S_EXTENSIONS:
        return jsonify({
            "error": f"Unsupported file type '{ext}'. Accepted: .yaml, .yml, .zip"
        }), 400

    tmp_file = None
    tmp_dir = None
    try:
        tmp_file = tempfile.NamedTemporaryFile(suffix=ext, delete=False)
        uploaded.save(tmp_file.name)
        tmp_file.close()

        if ext == ".zip":
            tmp_dir = tempfile.mkdtemp()
            with zipfile.ZipFile(tmp_file.name) as zf:
                zf.extractall(tmp_dir)
            parse_path = tmp_dir
        else:
            parse_path = tmp_file.name

        parsed = KubernetesParser(parse_path).parse()

        with _get_client() as client:
            result = queries.load_graph(client, parsed)

        return jsonify(result), 200

    except (ValueError, Exception) as exc:
        current_app.logger.exception("Kubernetes parse error")
        return jsonify({"error": str(exc)}), 500

    finally:
        _cleanup(tmp_file.name if tmp_file else None, tmp_dir)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cleanup(tmp_file_path: Optional[str], tmp_dir: Optional[str]) -> None:
    """Remove temp files; log warning on failure but never raise."""
    if tmp_file_path:
        try:
            os.unlink(tmp_file_path)
        except Exception as exc:
            current_app.logger.warning("Failed to delete temp file %s: %s", tmp_file_path, exc)
    if tmp_dir:
        try:
            shutil.rmtree(tmp_dir, ignore_errors=True)
        except Exception as exc:
            current_app.logger.warning("Failed to delete temp dir %s: %s", tmp_dir, exc)
