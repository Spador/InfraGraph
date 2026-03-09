"""
test_kubernetes_parser.py — Milestone 3 acceptance tests for the Kubernetes parser.

All tests operate on backend/tests/fixtures/sample-k8s.yaml.
No live services required — pure Python YAML parsing only.
"""

import os
import re
import shutil
import pytest

# parse_kubernetes_files is importable thanks to conftest.py adding execution/ to sys.path
from parse_kubernetes import parse_kubernetes_files

# ---------------------------------------------------------------------------
# Fixture: path to sample-k8s.yaml
# ---------------------------------------------------------------------------

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")
SAMPLE_K8S = os.path.join(FIXTURES_DIR, "sample-k8s.yaml")


@pytest.fixture(scope="module")
def parsed():
    """Parse sample-k8s.yaml once and share result across all tests."""
    return parse_kubernetes_files(SAMPLE_K8S)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_resource_count(parsed):
    """sample-k8s.yaml has 7 documents; parser must find all."""
    ids = {r["id"] for r in parsed["resources"]}
    assert "ConfigMap/default/app-config" in ids
    assert "Secret/default/app-secrets" in ids
    assert "Deployment/default/app" in ids
    assert "Service/default/app" in ids
    assert "Ingress/default/main" in ids
    assert "Deployment/workers/worker" in ids
    assert "ServiceMonitor/default/app-monitor" in ids
    assert len(parsed["resources"]) == 7


def test_service_to_deployment_edge(parsed):
    """Service/default/app selector matches Deployment/default/app labels → edge must exist."""
    edge_pairs = {(e["source"], e["target"]) for e in parsed["edges"]}
    assert ("Service/default/app", "Deployment/default/app") in edge_pairs


def test_deployment_to_configmap_edge(parsed):
    """Deployment references ConfigMap via envFrom → edge must exist."""
    edge_pairs = {(e["source"], e["target"]) for e in parsed["edges"]}
    assert ("Deployment/default/app", "ConfigMap/default/app-config") in edge_pairs


def test_deployment_to_secret_edge(parsed):
    """Deployment references Secret via envFrom → edge must exist."""
    edge_pairs = {(e["source"], e["target"]) for e in parsed["edges"]}
    assert ("Deployment/default/app", "Secret/default/app-secrets") in edge_pairs


def test_ingress_to_service_edge(parsed):
    """Ingress backend points to Service/default/app → edge must exist."""
    edge_pairs = {(e["source"], e["target"]) for e in parsed["edges"]}
    assert ("Ingress/default/main", "Service/default/app") in edge_pairs


def test_no_duplicate_edges(parsed):
    """ConfigMap is referenced via both envFrom AND volume — must produce only 1 edge."""
    configmap_edges = [
        e for e in parsed["edges"]
        if e["source"] == "Deployment/default/app"
        and e["target"] == "ConfigMap/default/app-config"
    ]
    assert len(configmap_edges) == 1, (
        f"Expected 1 edge to ConfigMap (deduped), found {len(configmap_edges)}"
    )


def test_no_cross_namespace_edges(parsed):
    """Deployment/workers/worker is isolated — no edges should cross namespace boundaries."""
    worker_edges = [
        e for e in parsed["edges"]
        if "workers/worker" in e["source"] or "workers/worker" in e["target"]
    ]
    assert worker_edges == [], f"Unexpected cross-namespace edges: {worker_edges}"


def test_unknown_kind_parsed(parsed):
    """ServiceMonitor (unknown kind) must be parsed as a Resource node."""
    ids = {r["id"] for r in parsed["resources"]}
    assert "ServiceMonitor/default/app-monitor" in ids


def test_unknown_kind_no_edges(parsed):
    """ServiceMonitor must produce no edges (unknown kind → no inference rules apply)."""
    monitor_edges = [
        e for e in parsed["edges"]
        if "ServiceMonitor" in e["source"] or "ServiceMonitor" in e["target"]
    ]
    assert monitor_edges == []


def test_resource_id_format(parsed):
    """All resource IDs must match the pattern Kind/namespace/name."""
    pattern = re.compile(r'^[A-Za-z][A-Za-z0-9]+/[a-z][a-z0-9-]*/[a-z][a-z0-9-]*$')
    for r in parsed["resources"]:
        assert pattern.match(r["id"]), f"Bad resource ID format: {r['id']}"


def test_missing_namespace_defaults_to_default():
    """A document without metadata.namespace must default to namespace 'default'."""
    import yaml
    import tempfile

    manifest = yaml.dump({
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "metadata": {"name": "no-namespace-cm"},
        "data": {"key": "value"},
    })
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(manifest)
        tmp_path = f.name

    try:
        result = parse_kubernetes_files(tmp_path)
        ids = {r["id"] for r in result["resources"]}
        assert "ConfigMap/default/no-namespace-cm" in ids
    finally:
        os.unlink(tmp_path)


def test_file_not_found_raises():
    """parse_kubernetes_files must raise FileNotFoundError for a non-existent path."""
    with pytest.raises(FileNotFoundError):
        parse_kubernetes_files("/nonexistent/path/to/file.yaml")


def test_multi_doc_yaml(parsed):
    """All 7 documents separated by --- in the file must be parsed."""
    assert len(parsed["resources"]) == 7


def test_directory_input(tmp_path):
    """Passing a directory with one YAML file must produce the same result as the file."""
    dest = tmp_path / "sample-k8s.yaml"
    shutil.copy(SAMPLE_K8S, dest)

    result_file = parse_kubernetes_files(str(dest))
    result_dir = parse_kubernetes_files(str(tmp_path))

    assert {r["id"] for r in result_file["resources"]} == {r["id"] for r in result_dir["resources"]}
    assert {(e["source"], e["target"]) for e in result_file["edges"]} == \
           {(e["source"], e["target"]) for e in result_dir["edges"]}
