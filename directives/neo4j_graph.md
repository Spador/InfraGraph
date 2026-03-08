# Directive: Neo4j Graph Storage

## Objective

Load parsed infrastructure resources and dependency edges into a Neo4j graph database, and provide a set of read query functions for the Flask API to call. All operations use the official `neo4j` Python driver with fully parameterized Cypher queries.

---

## Inputs

| Input | Source | Description |
|---|---|---|
| Parsed JSON | `execution/parse_terraform.py` or `execution/parse_kubernetes.py` | `{resources: [...], edges: [...]}` dict |
| `NEO4J_URI` | `.env` | Bolt URI, e.g. `bolt://localhost:7687` or `bolt://neo4j:7687` (in Docker) |
| `NEO4J_USERNAME` | `.env` | Auth username (default: `neo4j`) |
| `NEO4J_PASSWORD` | `.env` | Auth password |
| `NEO4J_DATABASE` | `.env` | Target database name (default: `neo4j`) |

---

## Tools / Scripts

| Script / Module | Role |
|---|---|
| `execution/neo4j_load.py` | CLI entry point — reads JSON, connects to Neo4j, calls load functions |
| `backend/app/graph/neo4j_client.py` | Connection manager class used by both execution scripts and Flask routes |
| `backend/app/graph/queries.py` | All parameterized Cypher query functions |
| `backend/app/models/resource.py` | Pydantic models: `Resource`, `Edge`, `GraphData`, `GraphStats` |

---

## Outputs

- Neo4j graph: `:Resource` nodes and `:DEPENDS_ON` edges loaded/upserted
- `neo4j_load.py` prints: `Loaded {n} resources, {m} edges` on success
- All read query functions return Python dicts or Pydantic model instances

---

## Connection Manager Pattern

Follow the pattern from `.claude/agents/neo4j-docker-client-generator.md`:

```python
class Neo4jClient:
    def __init__(self, uri: str, username: str, password: str, database: str = "neo4j"):
        self._driver = GraphDatabase.driver(uri, auth=(username, password))
        self._database = database

    def close(self):
        self._driver.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def execute_read(self, query: str, **params) -> list[dict]:
        with self._driver.session(database=self._database) as session:
            result = session.run(query, **params)
            return [dict(record) for record in result]

    def execute_write(self, query: str, **params):
        with self._driver.session(database=self._database) as session:
            return session.run(query, **params).consume()
```

---

## Cypher Operations

### Load (Write)

**Upsert a resource node** (`MERGE` = idempotent):
```cypher
MERGE (r:Resource {id: $id})
SET r.name = $name,
    r.type = $type,
    r.file = $file,
    r.line_number = $line_number,
    r.source = $source
```

**Upsert a DEPENDS_ON edge**:
```cypher
MATCH (a:Resource {id: $source}), (b:Resource {id: $target})
MERGE (a)-[:DEPENDS_ON]->(b)
```

### Read Queries (in `queries.py`)

**Full graph**:
```cypher
MATCH (n:Resource)
OPTIONAL MATCH (n)-[:DEPENDS_ON]->(m:Resource)
RETURN n, collect(m.id) AS targets
```

**Subgraph around a node (depth=2)**:
```cypher
MATCH (center:Resource {id: $id})
OPTIONAL MATCH path=(center)-[:DEPENDS_ON*0..2]-(neighbor:Resource)
WITH collect(DISTINCT center) + collect(DISTINCT neighbor) AS all_nodes
UNWIND all_nodes AS n
OPTIONAL MATCH (n)-[:DEPENDS_ON]->(m:Resource)
WHERE m IN all_nodes
RETURN DISTINCT n, collect(DISTINCT m.id) AS targets
```

**Node count**:
```cypher
MATCH (n:Resource) RETURN count(n) AS node_count
```

**Edge count**:
```cypher
MATCH ()-[r:DEPENDS_ON]->() RETURN count(r) AS edge_count
```

**Most connected node** (by total degree):
```cypher
MATCH (n:Resource)
WITH n, count{(n)-[:DEPENDS_ON]-()} AS degree
ORDER BY degree DESC
LIMIT 1
RETURN n.id AS id, n.name AS name, n.type AS type, degree
```

**Isolated nodes** (no relationships):
```cypher
MATCH (n:Resource)
WHERE NOT (n)-[:DEPENDS_ON]-() AND NOT ()-[:DEPENDS_ON]->(n)
RETURN count(n) AS isolated_count
```

**Circular dependency detection**:
```cypher
MATCH (n:Resource)-[:DEPENDS_ON*1..10]->(n)
RETURN count(DISTINCT n) AS circular_dependencies
```

**Reset**:
```cypher
MATCH (n:Resource)
WITH n, count(n) AS total
DETACH DELETE n
RETURN total
```

---

## Neo4j Startup Wait Logic

Before attempting to load data, verify Neo4j is reachable:

```python
import time
from neo4j.exceptions import ServiceUnavailable

MAX_RETRIES = 30
RETRY_INTERVAL = 2  # seconds

for attempt in range(MAX_RETRIES):
    try:
        client.execute_read("RETURN 1")
        break
    except ServiceUnavailable:
        if attempt == MAX_RETRIES - 1:
            raise RuntimeError("Neo4j did not become available after 60 seconds")
        time.sleep(RETRY_INTERVAL)
```

---

## Security Rules

- **Never** interpolate user-provided values into Cypher strings. Always use named parameters (`$param`).
- Use `MERGE` over `CREATE` to ensure idempotent loads.
- Validate all inputs with Pydantic models before passing to Cypher.

---

## Edge Cases

| Scenario | Handling |
|---|---|
| Neo4j not ready at startup | Retry loop (30 × 2s = 60s max); raise `RuntimeError` if never available |
| MERGE on existing node | `SET` overwrites properties — safe and idempotent |
| Edge where source or target node does not exist | The `MATCH` before `MERGE` returns no rows; edge is silently skipped; log warning |
| APOC not available | Basic cycle count query works without APOC; log warning if APOC call fails |
| Empty resource list | No-op; return `{node_count: 0, edge_count: 0}` |
| Connection closed unexpectedly | Rely on context manager `__exit__` to close driver; let caller handle reconnect |
| Large graphs (1000+ nodes) | `MERGE` batching: process resources in chunks of 100 inside a single transaction |

---

## Update Log

- Initial version: connection manager, load/upsert, full-graph, subgraph, stats, cycle detection, reset
- Added `execute_write_batch()` using explicit transactions for bulk MERGE (100 resources/edges per chunk)
- Added `Neo4jClient.from_env()` class factory for clean env-var construction
- Added `load_graph(client, parsed)` convenience wrapper in queries.py that calls load_resources + load_edges
- `neo4j_load.py` uses dual import path: `backend.app.graph` locally, `app.graph` inside Docker container
- `most_connected` query uses `OPTIONAL MATCH (n)-[:DEPENDS_ON]-(neighbor)` + count (compatible with all Neo4j 5.x)
- `get_subgraph` passes `depth` as a named parameter — Neo4j 5 supports variable-length paths with params
- reset_graph: two queries (count then delete) since execute_write discards result via .consume()
