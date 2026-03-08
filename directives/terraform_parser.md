# Directive: Terraform Parser

## Objective

Parse one or more Terraform (`.tf`) files and extract all resource blocks, data sources, variables, and outputs as `Resource` nodes, plus all dependency edges (`DEPENDS_ON`). Output a structured JSON object ready for loading into Neo4j.

---

## Inputs

| Input | Type | Description |
|---|---|---|
| `--input` | path | Path to a single `.tf` file OR a directory containing `.tf` files |
| `--output` | path (optional) | Write JSON result to this file instead of stdout |
| `--verbose` | flag (optional) | Print debug info: number of files scanned, resources found, edges inferred |

---

## Tools / Scripts

**Primary script**: `execution/parse_terraform.py`

**Validation helper** (call before parsing):
```python
from .claude.skills.devops-iac-engineer.scripts.devops_utils import TerraformHelper
TerraformHelper.validate_hcl(file_path)
```

**Library**: `python-hcl2` (`pip install python-hcl2`)

---

## Outputs

JSON object on stdout (or to `--output` file):

```json
{
  "resources": [
    {
      "id": "aws_s3_bucket.uploads",
      "name": "uploads",
      "type": "aws_s3_bucket",
      "file": "main.tf",
      "line_number": 12,
      "source": "terraform"
    }
  ],
  "edges": [
    {
      "source": "aws_iam_role.app_role",
      "target": "aws_s3_bucket.uploads"
    }
  ]
}
```

Exit code `0` on success, `1` on parse error.

---

## Parsing Logic

### Step 1 — Line Number Pre-Scan
Before calling `hcl2.load()`, scan the raw file content with:
```python
import re
pattern = re.compile(r'resource\s+"([^"]+)"\s+"([^"]+)"')
```
Build a lookup dict: `{(type, name): line_number}`. Use this to populate `line_number` in each resource node. If not found, set `line_number = 0`.

### Step 2 — HCL2 Parse
```python
import hcl2
with open(file_path) as f:
    parsed = hcl2.load(f)
```
`parsed` is a dict with optional keys: `resource`, `data`, `variable`, `output`, `locals`, `module`.

### Step 3 — Extract Resources

**Resource blocks** (`parsed.get('resource', [])`):
- Each item in the list is a dict: `{resource_type: {resource_name: body}}`
- Resource ID: `f"{resource_type}.{resource_name}"`
- Type: `resource_type` (e.g., `aws_s3_bucket`)

**Data sources** (`parsed.get('data', [])`):
- Each item: `{data_type: {data_name: body}}`
- Resource ID: `f"data.{data_type}.{data_name}"`
- Type: `f"data.{data_type}"`

**Variables** (`parsed.get('variable', [])`):
- Each item: `{var_name: body}`
- Resource ID: `f"variable.{var_name}"`
- Type: `"variable"`

**Outputs** (`parsed.get('output', [])`):
- Each item: `{output_name: body}`
- Resource ID: `f"output.{output_name}"`
- Type: `"output"`

### Step 4 — Infer Dependencies

For each resource/data block body, walk all values recursively:

```python
def _walk_values(obj):
    """Yield all string leaf values from a nested dict/list."""
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _walk_values(v)
    elif isinstance(obj, list):
        for item in obj:
            yield from _walk_values(item)
```

**Implicit interpolation references** — match against all string values:
```python
RESOURCE_REF = re.compile(
    r'\b((?:aws|google|azurerm|kubernetes|helm|random|null|tls|local|archive|vault)_[a-z0-9_]+)'
    r'\.([a-zA-Z0-9_-]+)\b'
)
```
NOTE: Use `[a-z0-9_]+` (with digit) — not `[a-z_]+`. Resource types like `aws_s3_bucket`
contain digits in the suffix. Without the digit, `s3_bucket` won't match.
For each match: target ID = `f"{match.group(1)}.{match.group(2)}"`.

**Data source references** — process BEFORE RESOURCE_REF to avoid double-matching:
```python
DATA_REF = re.compile(r'\bdata\.([a-z_]+)\.([a-zA-Z0-9_-]+)\b')
```
Track the spans matched by DATA_REF, then skip any RESOURCE_REF match whose start
position falls within a data span. This prevents `data.aws_ami.ubuntu.id` from producing
both `data.aws_ami.ubuntu` (correct) and a spurious `aws_ami.ubuntu` edge.
Target ID = `f"data.{match.group(1)}.{match.group(2)}"`.

**Explicit `depends_on`**: python-hcl2 parses `depends_on = [aws_s3_bucket.uploads]`
as `["${aws_s3_bucket.uploads}"]` — a list of strings. The RESOURCE_REF regex walk
over all string values will catch these automatically — no special handling needed.

### Step 5 — Deduplicate Edges

```python
edge_set = set()  # set of (source_id, target_id) tuples
# Skip if source == target (self-reference)
# Skip if target resource not in the known resource set (optional: still include for cross-file refs)
```

---

## Multi-File Handling

If `--input` is a directory, parse every `.tf` file found (non-recursive by default). Merge all `resources` and `edges` lists. Deduplicate edges across files.

---

## Edge Cases

| Scenario | Handling |
|---|---|
| Malformed / unparsable HCL | Wrap `hcl2.load()` in `try/except`; log error with filename; skip file; continue with remaining files |
| File with only variables/outputs | Still parse and include as Resource nodes; no edges expected from them unless they reference other resources |
| Self-referential edge (`source == target`) | Skip |
| Duplicate edges across files | Deduplicate using `set` of `(source, target)` tuples |
| Reference to unknown resource | Include edge anyway (cross-file or external module reference) |
| Empty `depends_on` list | Skip gracefully |
| Nested module calls | Parse `module` blocks as Resource nodes with type `module`; do not recurse into module source files |
| HCL1 syntax (Terraform <0.12) | Not supported; raise `ValueError("HCL1 not supported — use Terraform 0.12+ syntax")` |

---

## Update Log

- Initial version: explicit + implicit + data source dependency inference, multi-file, deduplication
- Fix: RESOURCE_REF pattern changed from `[a-z_]+` to `[a-z0-9_]+` — resource types like `aws_s3_bucket` contain digits
- Fix: DATA_REF processed first with span tracking to prevent double-matching data source references
- Confirmed: `depends_on = [...]` is stored by python-hcl2 as `["${ref}"]` strings — caught by regex walk automatically
