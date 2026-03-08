"""
test_terraform_parser.py — Milestone 2 acceptance tests for the Terraform parser.

All tests operate on backend/tests/fixtures/sample.tf.
No live services required — pure Python parsing only.
"""

import os
import re
import pytest

# parse_terraform_files is importable thanks to conftest.py adding execution/ to sys.path
from parse_terraform import parse_terraform_files

# ---------------------------------------------------------------------------
# Fixture: path to sample.tf
# ---------------------------------------------------------------------------

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")
SAMPLE_TF = os.path.join(FIXTURES_DIR, "sample.tf")


@pytest.fixture(scope="module")
def parsed():
    """Parse sample.tf once and share result across all tests."""
    return parse_terraform_files(SAMPLE_TF)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_resource_count(parsed):
    """sample.tf declares 8 resource/data/variable/output blocks; parser must find all."""
    # data: 1 (aws_ami.ubuntu)
    # resource: 6 (vpc, subnet, sg, instance, s3, iam_role, iam_policy) → 7
    # variable: 2 (region, instance_type)
    # output: 2 (instance_ip, bucket_name)
    # total = 12
    ids = {r["id"] for r in parsed["resources"]}
    assert "data.aws_ami.ubuntu" in ids
    assert "aws_vpc.main" in ids
    assert "aws_subnet.private" in ids
    assert "aws_security_group.app" in ids
    assert "aws_instance.app" in ids
    assert "aws_s3_bucket.uploads" in ids
    assert "aws_iam_role.app_role" in ids
    assert "aws_iam_policy.s3_access" in ids
    assert "variable.region" in ids
    assert "variable.instance_type" in ids
    assert "output.instance_ip" in ids
    assert "output.bucket_name" in ids
    assert len(parsed["resources"]) == 12


def test_explicit_depends_on_edge(parsed):
    """aws_iam_role.app_role depends_on [aws_s3_bucket.uploads] must produce an edge."""
    edge_pairs = {(e["source"], e["target"]) for e in parsed["edges"]}
    assert ("aws_iam_role.app_role", "aws_s3_bucket.uploads") in edge_pairs


def test_implicit_vpc_edge(parsed):
    """aws_subnet.private references aws_vpc.main.id → implicit edge must exist."""
    edge_pairs = {(e["source"], e["target"]) for e in parsed["edges"]}
    assert ("aws_subnet.private", "aws_vpc.main") in edge_pairs


def test_implicit_sg_to_vpc_edge(parsed):
    """aws_security_group.app references aws_vpc.main.id → implicit edge must exist."""
    edge_pairs = {(e["source"], e["target"]) for e in parsed["edges"]}
    assert ("aws_security_group.app", "aws_vpc.main") in edge_pairs


def test_implicit_instance_edges(parsed):
    """aws_instance.app references subnet, sg, and data source → three edges must exist."""
    edge_pairs = {(e["source"], e["target"]) for e in parsed["edges"]}
    assert ("aws_instance.app", "aws_subnet.private") in edge_pairs
    assert ("aws_instance.app", "aws_security_group.app") in edge_pairs
    assert ("aws_instance.app", "data.aws_ami.ubuntu") in edge_pairs


def test_data_source_parsed(parsed):
    """Data source 'data.aws_ami.ubuntu' must appear in resources with correct fields."""
    data_resources = [r for r in parsed["resources"] if r["id"] == "data.aws_ami.ubuntu"]
    assert len(data_resources) == 1
    r = data_resources[0]
    assert r["name"] == "ubuntu"
    assert r["type"] == "data.aws_ami"
    assert r["source"] == "terraform"


def test_variable_parsed(parsed):
    """Variables must appear as Resource nodes with type='variable'."""
    var_resources = [r for r in parsed["resources"] if r["type"] == "variable"]
    var_ids = {r["id"] for r in var_resources}
    assert "variable.region" in var_ids
    assert "variable.instance_type" in var_ids


def test_output_parsed(parsed):
    """Outputs must appear as Resource nodes with type='output'."""
    output_resources = [r for r in parsed["resources"] if r["type"] == "output"]
    output_ids = {r["id"] for r in output_resources}
    assert "output.instance_ip" in output_ids
    assert "output.bucket_name" in output_ids


def test_no_self_references(parsed):
    """No edge should have source == target."""
    for edge in parsed["edges"]:
        assert edge["source"] != edge["target"], (
            f"Self-reference detected: {edge['source']}"
        )


def test_no_duplicate_edges(parsed):
    """Edge list must contain no duplicate (source, target) pairs."""
    edge_pairs = [(e["source"], e["target"]) for e in parsed["edges"]]
    assert len(edge_pairs) == len(set(edge_pairs)), "Duplicate edges detected"


def test_resource_id_format(parsed):
    """Resource IDs for resource blocks must match the pattern 'type.name'."""
    resource_blocks = [
        r for r in parsed["resources"]
        if r["type"] not in ("variable", "output") and not r["type"].startswith("data.")
    ]
    pattern = re.compile(r'^[a-z][a-z0-9_]+\.[a-zA-Z0-9_-]+$')
    for r in resource_blocks:
        assert pattern.match(r["id"]), f"Bad resource ID format: {r['id']}"


def test_file_not_found_raises():
    """parse_terraform_files must raise FileNotFoundError for a non-existent path."""
    with pytest.raises(FileNotFoundError):
        parse_terraform_files("/nonexistent/path/to/file.tf")


def test_directory_input(tmp_path):
    """Passing a directory with one .tf file must produce the same result as passing the file."""
    import shutil
    dest = tmp_path / "sample.tf"
    shutil.copy(SAMPLE_TF, dest)

    result_file = parse_terraform_files(str(dest))
    result_dir = parse_terraform_files(str(tmp_path))

    # Same resource IDs
    assert {r["id"] for r in result_file["resources"]} == {r["id"] for r in result_dir["resources"]}
    # Same edge pairs
    assert {(e["source"], e["target"]) for e in result_file["edges"]} == \
           {(e["source"], e["target"]) for e in result_dir["edges"]}
