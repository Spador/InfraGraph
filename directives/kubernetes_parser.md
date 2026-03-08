# Directive: Kubernetes Parser

## Objective

Parse one or more Kubernetes YAML files (including multi-document streams separated by `---`) and extract all Kubernetes resources as `Resource` nodes plus all inferred dependency edges (`DEPENDS_ON`). Output a structured JSON object ready for loading into Neo4j.

---

## Inputs

| Input | Type | Description |
|---|---|---|
| `--input` | path | Path to a single `.yaml`/`.yml` file OR a directory containing YAML files |
| `--output` | path (optional) | Write JSON result to this file instead of stdout |
| `--verbose` | flag (optional) | Print debug info: resources found, relationships inferred |

---

## Tools / Scripts

**Primary script**: `execution/parse_kubernetes.py`

**Validation helper** (call before parsing):
```python
from .claude.skills.devops-iac-engineer.scripts.devops_utils import KubernetesHelper
KubernetesHelper.validate_manifest(file_path)
```

**Library**: `PyYAML` (`pip install pyyaml`)

---

## Outputs

JSON object on stdout (or to `--output` file):

```json
{
  "resources": [
    {
      "id": "Deployment/default/app",
      "name": "app",
      "type": "Deployment",
      "file": "seed-k8s.yaml",
      "line_number": 0,
      "source": "kubernetes"
    }
  ],
  "edges": [
    {
      "source": "Service/default/app",
      "target": "Deployment/default/app"
    }
  ]
}
```

Exit code `0` on success, `1` on parse error.

---

## Parsing Logic

### Step 1 — Load All Documents

```python
import yaml

with open(file_path) as f:
    docs = [doc for doc in yaml.safe_load_all(f) if doc is not None]
```

Each `doc` is a dict representing a single Kubernetes manifest. The `---` separator produces separate documents in the stream.

### Step 2 — Extract Resource Nodes

For each document `doc`:
- `kind` = `doc.get('kind', 'Unknown')`
- `name` = `doc.get('metadata', {}).get('name', '')`
- `namespace` = `doc.get('metadata', {}).get('namespace', 'default')`
- Resource ID: `f"{kind}/{namespace}/{name}"`
- Type: `kind`
- `source`: `"kubernetes"`
- `line_number`: `0` (PyYAML does not expose line numbers without custom loader)

Skip documents where `name` is empty or `kind` is missing.

### Step 3 — Infer Dependency Edges

Process all 4 inference rules after all documents are loaded (so cross-document references can be resolved).

#### Rule 1: Service → Deployment (label selector)

```
service.spec.selector  ⊆  deployment.spec.template.metadata.labels
```

- Extract `service_selector = svc.get('spec', {}).get('selector', {})` — skip if empty or None
- For each Deployment in the same namespace:
  - `pod_labels = dep['spec']['template']['metadata']['labels']`
  - If all `(k, v)` in `service_selector` exist in `pod_labels` → add edge `Service/{ns}/{svc_name}` → `Deployment/{ns}/{dep_name}`

#### Rule 2 & 3: Deployment → ConfigMap / Secret (env refs)

For each Deployment, scan `spec.template.spec`:

**Containers `envFrom`**:
```python
for container in spec.get('containers', []):
    for env_from in container.get('envFrom', []):
        if 'configMapRef' in env_from:
            ref_name = env_from['configMapRef']['name']
            # edge: Deployment → ConfigMap/{ns}/{ref_name}
        if 'secretRef' in env_from:
            ref_name = env_from['secretRef']['name']
            # edge: Deployment → Secret/{ns}/{ref_name}
```

**Volumes**:
```python
for volume in spec.get('volumes', []):
    if 'configMap' in volume:
        ref_name = volume['configMap']['name']
        # edge: Deployment → ConfigMap/{ns}/{ref_name}
    if 'secret' in volume:
        ref_name = volume['secret']['secretName']
        # edge: Deployment → Secret/{ns}/{ref_name}
```

#### Rule 4: Ingress → Service (backend)

For each Ingress, scan `spec.rules`:
```python
for rule in ingress.get('spec', {}).get('rules', []):
    for path in rule.get('http', {}).get('paths', []):
        svc_name = path.get('backend', {}).get('service', {}).get('name')
        if svc_name:
            # edge: Ingress/{ns}/{ingress_name} → Service/{ns}/{svc_name}
```

### Step 4 — Deduplicate Edges

Use `set` of `(source_id, target_id)` tuples. Skip if `source == target`.

---

## Resource ID Format

```
{Kind}/{namespace}/{name}
```

Examples:
- `Deployment/default/app`
- `Service/production/api-gateway`
- `ConfigMap/staging/app-config`
- `Secret/default/db-credentials`
- `Ingress/default/main-ingress`

---

## Multi-File Handling

If `--input` is a directory, parse every `.yaml` and `.yml` file. Build a combined resource registry across all files before inferring edges (so cross-file Service → Deployment relationships are resolved).

---

## Edge Cases

| Scenario | Handling |
|---|---|
| Empty YAML document (`---` with no content) | Skip (`if doc is None: continue`) |
| Unknown `kind` (CRD, operator resource) | Parse as Resource node with `type = kind`; no edges inferred for unknown kinds |
| Missing `metadata.namespace` | Default to `"default"` |
| Service selector is `null` or `{}` | Skip Rule 1 for this Service |
| No matching Deployment for a Service selector | No edge created; not an error |
| `envFrom` references a ConfigMap/Secret not in the parsed files | Include edge anyway (may reference cluster-level resource) |
| Cross-namespace references | Do not create edges across namespaces |
| YAML parse error | Wrap in `try/except yaml.YAMLError`; log error with filename; skip file |
| Duplicate resources (same kind/ns/name in multiple files) | Last one wins; log warning |
| Multi-container Pods | Scan all containers in the pod spec |

---

## Update Log

- Initial version: 4 inference rules, multi-doc YAML, cross-file resource registry, namespace-scoped edges
- Fix: `KubernetesHelper.validate_manifest()` from devops_utils prints directly to stdout (not stderr) — must suppress stdout with `contextlib.redirect_stdout(io.StringIO())` to avoid corrupting JSON CLI output
- Confirmed: ConfigMap referenced via both envFrom AND volume correctly deduplicates to 1 edge via `set` of tuples
- Note: env[].valueFrom.configMapKeyRef / secretKeyRef also inferred (individual env var sources)
