#!/usr/bin/env python3
"""
parse_terraform.py — Layer 3 Execution Script

Purpose : Parse Terraform (.tf) files and extract Resource nodes + DEPENDS_ON edges.
Inputs  : --input <file or directory of .tf files>
          --output <optional JSON output file>
          --verbose flag
Outputs : JSON { "resources": [...], "edges": [...] }
          Each resource: { id, name, type, file, line_number, source }
          Each edge:     { source, target }

Deps    : python-hcl2 (pip install python-hcl2)
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Regex patterns for dependency inference
# ---------------------------------------------------------------------------

# Matches resource references embedded in string values:
#   aws_vpc.main.id  →  group(1)=aws_vpc  group(2)=main
#   ${aws_subnet.private.id}  →  same
RESOURCE_REF = re.compile(
    r'\b((?:aws|google|azurerm|kubernetes|helm|random|null|tls|local|archive|vault)_[a-z0-9_]+)'
    r'\.([a-zA-Z0-9_-]+)\b'
)

# Matches data source references: data.aws_ami.ubuntu.id
#   group(1)=aws_ami  group(2)=ubuntu
DATA_REF = re.compile(
    r'\bdata\.([a-z_]+)\.([a-zA-Z0-9_-]+)\b'
)

# Matches resource declaration for line-number pre-scan
RESOURCE_DECL = re.compile(
    r'resource\s+"([^"]+)"\s+"([^"]+)"'
)
DATA_DECL = re.compile(
    r'data\s+"([^"]+)"\s+"([^"]+)"'
)
VARIABLE_DECL = re.compile(
    r'variable\s+"([^"]+)"'
)
OUTPUT_DECL = re.compile(
    r'output\s+"([^"]+)"'
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_line_map(raw: str) -> dict[tuple[str, str], int]:
    """
    Pre-scan raw file content to map (type, name) → line_number
    for resource and data blocks. Variables and outputs use name → line.
    Returns a flat dict keyed by (block_type_prefix, name).
    """
    line_map: dict[tuple[str, str], int] = {}
    for lineno, line in enumerate(raw.splitlines(), start=1):
        m = RESOURCE_DECL.search(line)
        if m:
            line_map[("resource", m.group(1), m.group(2))] = lineno
            continue
        m = DATA_DECL.search(line)
        if m:
            line_map[("data", m.group(1), m.group(2))] = lineno
            continue
        m = VARIABLE_DECL.search(line)
        if m:
            line_map[("variable", m.group(1))] = lineno
            continue
        m = OUTPUT_DECL.search(line)
        if m:
            line_map[("output", m.group(1))] = lineno
    return line_map


def _walk_strings(obj: Any):
    """Recursively yield all string leaf values from a nested dict/list."""
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _walk_strings(v)
    elif isinstance(obj, list):
        for item in obj:
            yield from _walk_strings(item)


def _infer_edges(resource_id: str, body: Any, known_ids: set[str]) -> list[tuple[str, str]]:
    """
    Walk all string values in a resource body and extract implicit dependency
    references. Also handles explicit depends_on lists.
    Returns list of (source_id, target_id) tuples (not yet deduped).
    """
    edges: list[tuple[str, str]] = []

    for val in _walk_strings(body):
        # Track spans covered by data source refs so RESOURCE_REF doesn't double-match them
        data_spans: list[tuple[int, int]] = []

        # Data source references  e.g. data.aws_ami.ubuntu.id
        for m in DATA_REF.finditer(val):
            target_id = f"data.{m.group(1)}.{m.group(2)}"
            if target_id != resource_id:
                edges.append((resource_id, target_id))
            data_spans.append((m.start(), m.end()))

        # Resource interpolation references  e.g. aws_vpc.main.id
        # Skip matches that fall inside a data source span (avoids double-counting)
        for m in RESOURCE_REF.finditer(val):
            if any(ds <= m.start() < de for ds, de in data_spans):
                continue
            target_id = f"{m.group(1)}.{m.group(2)}"
            if target_id != resource_id:
                edges.append((resource_id, target_id))

    return edges


# ---------------------------------------------------------------------------
# Core parsing function (importable as a module)
# ---------------------------------------------------------------------------

def parse_terraform_files(input_path: str, verbose: bool = False) -> dict:
    """
    Parse one .tf file or all .tf files in a directory.

    Returns:
        {
            "resources": [ {id, name, type, file, line_number, source}, ... ],
            "edges":     [ {source, target}, ... ]
        }
    """
    path = Path(input_path)
    if not path.exists():
        raise FileNotFoundError(f"Input path does not exist: {input_path}")

    # Collect .tf files
    if path.is_dir():
        tf_files = sorted(path.glob("*.tf"))
    else:
        tf_files = [path]

    if not tf_files:
        if verbose:
            print(f"[warn] No .tf files found in {input_path}", file=sys.stderr)
        return {"resources": [], "edges": []}

    all_resources: list[dict] = []
    all_edges: set[tuple[str, str]] = set()

    for tf_file in tf_files:
        try:
            resources, edges = _parse_single_file(str(tf_file), verbose=verbose)
            all_resources.extend(resources)
            all_edges.update(edges)
        except Exception as exc:
            print(f"[error] Failed to parse {tf_file}: {exc}", file=sys.stderr)
            # Continue with remaining files

    # Remove duplicate resources (same id)
    seen_ids: set[str] = set()
    deduped_resources: list[dict] = []
    for r in all_resources:
        if r["id"] not in seen_ids:
            seen_ids.add(r["id"])
            deduped_resources.append(r)

    if verbose:
        print(f"[info] Parsed {len(tf_files)} file(s): "
              f"{len(deduped_resources)} resources, {len(all_edges)} edges", file=sys.stderr)

    return {
        "resources": deduped_resources,
        "edges": [{"source": s, "target": t} for s, t in sorted(all_edges)],
    }


def _parse_single_file(
    file_path: str, verbose: bool = False
) -> tuple[list[dict], set[tuple[str, str]]]:
    """Parse a single .tf file. Returns (resources, edge_set)."""
    try:
        import hcl2
    except ImportError:
        raise ImportError(
            "python-hcl2 is required. Install with: pip install python-hcl2"
        )

    with open(file_path, encoding="utf-8") as fh:
        raw = fh.read()

    # Detect HCL1 (Terraform <0.12) which hcl2 cannot parse
    if re.search(r'^\s*variable\s+"[^"]+"\s*\{[^}]*default\s*=\s*"', raw, re.MULTILINE):
        pass  # Might be HCL2 with quoted defaults — proceed
    # Build line number lookup before parsing
    line_map = _build_line_map(raw)

    rel_path = os.path.basename(file_path)

    try:
        with open(file_path, encoding="utf-8") as fh:
            parsed = hcl2.load(fh)
    except Exception as exc:
        raise ValueError(f"HCL2 parse error in {file_path}: {exc}")

    resources: list[dict] = []
    edge_set: set[tuple[str, str]] = set()

    # --- Resource blocks ---
    for block in parsed.get("resource", []):
        for res_type, names in block.items():
            for res_name, body in names.items():
                res_id = f"{res_type}.{res_name}"
                lineno = line_map.get(("resource", res_type, res_name), 0)
                resources.append({
                    "id": res_id,
                    "name": res_name,
                    "type": res_type,
                    "file": rel_path,
                    "line_number": lineno,
                    "source": "terraform",
                })
                for src, tgt in _infer_edges(res_id, body, set()):
                    if src != tgt:
                        edge_set.add((src, tgt))

    # --- Data sources ---
    for block in parsed.get("data", []):
        for data_type, names in block.items():
            for data_name, body in names.items():
                res_id = f"data.{data_type}.{data_name}"
                lineno = line_map.get(("data", data_type, data_name), 0)
                resources.append({
                    "id": res_id,
                    "name": data_name,
                    "type": f"data.{data_type}",
                    "file": rel_path,
                    "line_number": lineno,
                    "source": "terraform",
                })
                for src, tgt in _infer_edges(res_id, body, set()):
                    if src != tgt:
                        edge_set.add((src, tgt))

    # --- Variables ---
    for block in parsed.get("variable", []):
        for var_name, body in block.items():
            res_id = f"variable.{var_name}"
            lineno = line_map.get(("variable", var_name), 0)
            resources.append({
                "id": res_id,
                "name": var_name,
                "type": "variable",
                "file": rel_path,
                "line_number": lineno,
                "source": "terraform",
            })

    # --- Outputs ---
    for block in parsed.get("output", []):
        for out_name, body in block.items():
            res_id = f"output.{out_name}"
            lineno = line_map.get(("output", out_name), 0)
            resources.append({
                "id": res_id,
                "name": out_name,
                "type": "output",
                "file": rel_path,
                "line_number": lineno,
                "source": "terraform",
            })
            # Outputs can reference resources too
            for src, tgt in _infer_edges(res_id, body, set()):
                if src != tgt:
                    edge_set.add((src, tgt))

    if verbose:
        print(
            f"[info] {rel_path}: {len(resources)} resources, {len(edge_set)} edges",
            file=sys.stderr,
        )

    return resources, edge_set


# ---------------------------------------------------------------------------
# Optional pre-parse validation (requires terraform CLI)
# ---------------------------------------------------------------------------

def _try_validate_hcl(file_path: str) -> None:
    """
    Attempt to validate HCL formatting using the terraform CLI.
    Silently skips if terraform is not installed.
    """
    import subprocess
    try:
        result = subprocess.run(
            ["terraform", "fmt", "-check", file_path],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            print(f"[warn] {file_path} may have formatting issues", file=sys.stderr)
    except FileNotFoundError:
        pass  # terraform CLI not installed — skip validation
    except Exception as exc:
        print(f"[warn] terraform validation skipped: {exc}", file=sys.stderr)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Parse Terraform .tf files and extract resource dependency graph as JSON."
    )
    parser.add_argument(
        "--input", required=True,
        help="Path to a single .tf file or a directory containing .tf files"
    )
    parser.add_argument(
        "--output", default=None,
        help="Write JSON result to this file (default: stdout)"
    )
    parser.add_argument(
        "--verbose", action="store_true",
        help="Print debug information to stderr"
    )
    args = parser.parse_args()

    # Optional HCL validation (requires terraform CLI)
    input_path = Path(args.input)
    if input_path.is_file():
        _try_validate_hcl(args.input)

    try:
        result = parse_terraform_files(args.input, verbose=args.verbose)
    except FileNotFoundError as exc:
        print(f"[error] {exc}", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print(f"[error] {exc}", file=sys.stderr)
        sys.exit(1)

    output_json = json.dumps(result, indent=2)

    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        with open(args.output, "w") as fh:
            fh.write(output_json)
        if args.verbose:
            print(f"[info] Written to {args.output}", file=sys.stderr)
    else:
        print(output_json)


if __name__ == "__main__":
    main()
