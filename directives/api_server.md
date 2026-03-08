# Directive: API Server (Flask)

## Objective

Expose a Flask REST API that accepts file uploads, delegates parsing to the execution scripts, loads results into Neo4j, and serves graph query results to the frontend. The API is the Layer 2 surface that orchestrates Layer 3 execution scripts.

---

## Inputs

| Endpoint | Input Type | Description |
|---|---|---|
| `POST /parse/terraform` | `multipart/form-data`, field `file` | `.tf` file or `.zip` of `.tf` files |
| `POST /parse/kubernetes` | `multipart/form-data`, field `file` | `.yaml`/`.yml` file or `.zip` of YAML files |
| `GET /graph` | — | No parameters |
| `GET /graph/resource/{id}` | URL path param | URL-encoded resource ID |
| `GET /graph/stats` | — | No parameters |
| `POST /graph/reset` | — | No body |

---

## Tools / Scripts

| Module | Role |
|---|---|
| `backend/app/parsers/terraform.py` | Thin wrapper calling `execution/parse_terraform.py` |
| `backend/app/parsers/kubernetes.py` | Thin wrapper calling `execution/parse_kubernetes.py` |
| `backend/app/graph/neo4j_client.py` | Connection manager (used as context manager in routes) |
| `backend/app/graph/queries.py` | All Cypher query functions |
| `backend/app/models/resource.py` | Pydantic models for request/response validation |

---

## Outputs

All successful responses: `Content-Type: application/json`

| Endpoint | Success Response |
|---|---|
| `POST /parse/terraform` | `200 {"node_count": N, "edge_count": M}` |
| `POST /parse/kubernetes` | `200 {"node_count": N, "edge_count": M}` |
| `GET /graph` | `200 {"nodes": [...], "edges": [...]}` |
| `GET /graph/resource/{id}` | `200 {"nodes": [...], "edges": [...]}` |
| `GET /graph/stats` | `200 {"node_count": N, "edge_count": M, "most_connected": {...}, "isolated_count": N, "circular_dependencies": N}` |
| `POST /graph/reset` | `200 {"deleted": N}` |
| `GET /health` | `200 {"status": "ok"}` |

---

## Application Structure

### App Factory (`backend/app/main.py`)

```python
from flask import Flask
from flask_cors import CORS
from .routes.parse import parse_bp
from .routes.graph import graph_bp

def create_app():
    app = Flask(__name__)
    CORS(app, origins=["http://localhost:3000", "http://localhost:5173"])

    app.register_blueprint(parse_bp, url_prefix="/parse")
    app.register_blueprint(graph_bp, url_prefix="/graph")

    @app.route("/health")
    def health():
        return {"status": "ok"}

    @app.errorhandler(400)
    def bad_request(e):
        return {"error": str(e)}, 400

    @app.errorhandler(404)
    def not_found(e):
        return {"error": "Not found"}, 404

    @app.errorhandler(500)
    def server_error(e):
        return {"error": "Internal server error"}, 500

    return app
```

### Parse Routes (`backend/app/routes/parse.py`)

**POST /parse/terraform**:
1. Check `request.files.get('file')` — return 400 if missing
2. Check file extension: `.tf` or `.zip` — return 400 if unsupported
3. Save to `tempfile.NamedTemporaryFile(suffix=ext, delete=False)`
4. If `.zip`: extract to `tempfile.mkdtemp()`; point parser at extracted directory
5. Call `TerraformParser(path).parse()` → `{resources, edges}`
6. Call `neo4j_load.load_graph(result)` → `{node_count, edge_count}`
7. Cleanup temp files in `finally` block
8. Return `jsonify({node_count, edge_count})`

**POST /parse/kubernetes**: same pattern with `KubernetesParser`.

### Graph Routes (`backend/app/routes/graph.py`)

Use Neo4j client as context manager in each route:
```python
from ..graph.neo4j_client import Neo4jClient
from ..graph import queries
import os

def get_client():
    return Neo4jClient(
        uri=os.environ["NEO4J_URI"],
        username=os.environ["NEO4J_USERNAME"],
        password=os.environ["NEO4J_PASSWORD"],
        database=os.environ.get("NEO4J_DATABASE", "neo4j"),
    )
```

**GET /graph**: `get_full_graph(client)` → `jsonify`

**GET /graph/resource/<path:resource_id>**: URL-decode; call `get_subgraph(client, resource_id)`; return 404 if empty

**GET /graph/stats**: `get_stats(client)` → `jsonify`

**POST /graph/reset**: `reset_graph(client)` → `jsonify({"deleted": count})`

### Parser Wrappers (`backend/app/parsers/`)

Each parser wrapper calls the corresponding execution script as a subprocess or imports it as a module. Prefer module import for performance:

```python
# terraform.py
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../../../execution'))
from parse_terraform import parse_terraform_files

class TerraformParser:
    def __init__(self, path: str):
        self.path = path

    def parse(self) -> dict:
        return parse_terraform_files(self.path)
```

---

## Error Handling

All route handlers wrapped in `try/except`:

```python
try:
    result = ...
    return jsonify(result), 200
except ValueError as e:
    return jsonify({"error": str(e)}), 400
except FileNotFoundError as e:
    return jsonify({"error": str(e)}), 404
except Exception as e:
    app.logger.exception("Unexpected error")
    return jsonify({"error": "Internal server error"}), 500
```

---

## CORS

Allow both dev server origins:
- `http://localhost:3000` (Docker/production frontend)
- `http://localhost:5173` (Vite dev server)

---

## Dockerfile

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV FLASK_APP=app.main:create_app
ENV FLASK_RUN_HOST=0.0.0.0
ENV FLASK_RUN_PORT=5000
CMD ["python", "-m", "flask", "run"]
```

---

## Environment Variables Required

```
NEO4J_URI=bolt://neo4j:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=password
NEO4J_DATABASE=neo4j
FLASK_ENV=development
```

---

## Edge Cases

| Scenario | Handling |
|---|---|
| No `file` field in multipart | Return 400 `{"error": "No file provided"}` |
| Unsupported file extension | Return 400 `{"error": "Unsupported file type. Accepted: .tf, .yaml, .yml, .zip"}` |
| `.zip` with no `.tf` files | Parser returns empty result; return `{node_count: 0, edge_count: 0}` |
| Parse error (malformed HCL/YAML) | Catch exception; return 500 with message |
| Neo4j unavailable | Connection error bubbles up; return 500 with descriptive message |
| `GET /graph/resource/{id}` — resource not found | Return 404 |
| Temp file cleanup failure | Log warning; do not return error to client |
| Large file upload | No size limit in MVP; werkzeug defaults apply |

---

## Update Log

- Initial version: 6 endpoints, file upload, .zip support, error handling, CORS
- Fix: `str | None` union syntax requires Python 3.10+; use `Optional[str]` from `typing` for Python 3.9 compatibility
- Parser wrappers use dual-candidate path resolution (3 levels up locally, 2 levels up in Docker) to locate execution/ directory
- `GET /graph/resource/<path:resource_id>` uses Flask `<path:...>` converter to allow slashes in Kubernetes IDs (e.g. `Deployment/default/app`)
- `_cleanup()` uses `ignore_errors=True` on rmtree — never raises, always runs in finally block
