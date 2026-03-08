# Directive: Docker Compose Local Stack

## Objective

Define a Docker Compose configuration that brings up the entire InfraGraph stack locally with a single command: `docker compose up --build`. The stack includes Neo4j, the Flask backend, and the nginx-served React frontend. On first start, seed data is auto-loaded so the graph is pre-populated for demonstration.

---

## Inputs

| Input | Source | Description |
|---|---|---|
| `.env` file | Project root | Neo4j credentials, Flask config, `SEED_ON_START` flag |
| `./backend/` | Local directory | Backend source code and Dockerfile |
| `./frontend/` | Local directory | Frontend source code and Dockerfile |
| `./seed/` | Local directory | Sample `.tf` and `.yaml` files for seeding |
| `./execution/` | Local directory | Python execution scripts (mounted into backend container) |

---

## Tools / Scripts

| File | Role |
|---|---|
| `docker-compose.yml` | Service definitions, volumes, networks |
| `.env.example` | Template for `.env` with all required variables |
| `execution/seed_loader.py` | CLI script run by backend on startup when `SEED_ON_START=true` |
| `backend/entrypoint.sh` | Shell script that runs seed_loader.py then starts Flask |

---

## Services

### neo4j

```yaml
neo4j:
  image: neo4j:5
  container_name: infragraph-neo4j
  ports:
    - "7474:7474"
    - "7687:7687"
  environment:
    NEO4J_AUTH: neo4j/${NEO4J_PASSWORD:-password}
    NEO4J_PLUGINS: '["apoc"]'
    NEO4J_dbms_memory_heap_max__size: 512m
  volumes:
    - neo4j_data:/data
  healthcheck:
    test: ["CMD", "wget", "-q", "--spider", "http://localhost:7474"]
    interval: 10s
    timeout: 5s
    retries: 10
    start_period: 30s
  networks:
    - infragraph_net
```

**Notes**:
- APOC plugin downloads automatically on first start via `NEO4J_PLUGINS` env var
- Port 7474: Neo4j Browser (http)
- Port 7687: Bolt protocol (used by Python driver)
- Volume `neo4j_data` persists the graph across restarts

### backend

```yaml
backend:
  build:
    context: ./backend
    dockerfile: Dockerfile
  container_name: infragraph-backend
  ports:
    - "5000:5000"
  environment:
    NEO4J_URI: bolt://neo4j:7687
    NEO4J_USERNAME: ${NEO4J_USERNAME:-neo4j}
    NEO4J_PASSWORD: ${NEO4J_PASSWORD:-password}
    NEO4J_DATABASE: ${NEO4J_DATABASE:-neo4j}
    FLASK_ENV: ${FLASK_ENV:-development}
    SEED_ON_START: ${SEED_ON_START:-true}
  volumes:
    - ./seed:/app/seed:ro
    - ./execution:/app/execution:ro
  depends_on:
    neo4j:
      condition: service_healthy
  healthcheck:
    test: ["CMD", "curl", "-f", "http://localhost:5000/health"]
    interval: 10s
    timeout: 5s
    retries: 5
    start_period: 15s
  networks:
    - infragraph_net
```

**Notes**:
- `seed/` and `execution/` are mounted read-only so seed_loader.py has access without being baked into the image
- `depends_on` with `condition: service_healthy` ensures Neo4j is ready before Flask starts

### frontend

```yaml
frontend:
  build:
    context: ./frontend
    dockerfile: Dockerfile
    args:
      VITE_API_URL: http://localhost:5000
  container_name: infragraph-frontend
  ports:
    - "3000:80"
  depends_on:
    - backend
  networks:
    - infragraph_net
```

**Notes**:
- nginx serves the static React build and proxies `/parse`, `/graph`, `/health` to the backend
- `VITE_API_URL` is a build-time arg baked into the JS bundle

---

## Volumes and Networks

```yaml
volumes:
  neo4j_data:
    driver: local

networks:
  infragraph_net:
    driver: bridge
```

---

## Seed Auto-Load (`execution/seed_loader.py`)

Called by backend's `entrypoint.sh` before starting Flask:

```bash
#!/bin/bash
set -e

if [ "$SEED_ON_START" = "true" ]; then
  echo "Running seed loader..."
  python /app/execution/seed_loader.py --seed-dir /app/seed
fi

exec python -m flask run
```

`seed_loader.py` logic:
1. Check `SEED_ON_START` env var; exit `0` silently if not set
2. Wait for Neo4j to be ready (retry loop: 30 attempts × 2s = 60s max)
3. Check if graph already has nodes (`MATCH (n) RETURN count(n)`); if `> 0`, skip seed (idempotent)
4. Parse `seed/main.tf` + `seed/variables.tf` using `parse_terraform_files()`
5. Parse `seed/seed-k8s.yaml` using `parse_kubernetes_files()`
6. Merge both result sets; call `neo4j_load.load_graph(combined)`
7. Print: `Seed complete: {node_count} resources, {edge_count} edges loaded`

---

## `.env.example`

```
# Neo4j
NEO4J_URI=bolt://localhost:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=password
NEO4J_DATABASE=neo4j

# Backend
FLASK_ENV=development
FLASK_SECRET_KEY=change-me-in-production

# Seed
SEED_ON_START=true
```

---

## Quick Start Commands

```bash
# First-time setup
cp .env.example .env
docker compose up --build

# Access
# App:         http://localhost:3000
# API:         http://localhost:5000
# Neo4j Browser: http://localhost:7474 (neo4j / password)

# Stop
docker compose down

# Destroy all data (including Neo4j volume)
docker compose down -v

# Rebuild after code changes
docker compose up --build
```

---

## Edge Cases

| Scenario | Handling |
|---|---|
| Neo4j takes >30s to start | Backend `depends_on` healthcheck retries 10× with 10s interval = 100s; backend start_period is 15s |
| APOC download fails (no internet) | Log warning in Neo4j container; cycle detection query falls back to basic Cypher |
| Seed already loaded (graph has nodes) | `seed_loader.py` detects existing nodes and skips re-seeding |
| `SEED_ON_START=false` | Seed loader exits immediately; graph starts empty |
| Port already in use | Docker Compose fails with a clear error; user must free the port |
| `.env` file missing | Docker Compose uses defaults from `${VAR:-default}` expressions in `docker-compose.yml` |
| Seed files not found | `seed_loader.py` raises `FileNotFoundError` with clear message; Flask still starts |
| Volume permissions | `neo4j_data` owned by Neo4j process inside container; no host permission issues |

---

## Update Log

- Initial version: 3 services, healthchecks, seed auto-load, named volume, bridge network
- `NEO4J_AUTH` format in docker-compose.yml: `"neo4j/${NEO4J_PASSWORD:-password}"` — must be quoted to prevent YAML parsing errors with the `/` character
- Backend env vars set explicitly with `${VAR:-default}` syntax (not env_file) so Docker-internal URIs (`bolt://neo4j:7687`) override any local `.env` values
- `VITE_API_URL: ""` (empty string) in frontend build args — ensures frontend uses relative URLs, which nginx then proxies to backend:5000
- seed_loader.py: idempotency check via `MATCH (n:Resource) RETURN count(n)` before loading; skips if > 0 nodes exist
- seed_loader.py: imports `load_from_dict` from `neo4j_load.py` (same directory) and calls with `skip_wait=True` (already waited in Neo4jClient.wait_until_ready())
- Seed produces 21 total resources (16 Terraform + 5 K8s) and 19 unique edges
