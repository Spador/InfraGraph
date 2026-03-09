"""
resource.py — Pydantic models for InfraGraph resources, edges, and API responses.

These models are the single source of truth for the shape of all data flowing
through the Flask API. The neo4j client and query functions return dicts;
routes validate/serialize them through these models.
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel


class Resource(BaseModel):
    """A single infrastructure resource node (Terraform or Kubernetes)."""
    id: str             # e.g. "aws_s3_bucket.uploads" or "Deployment/default/app"
    name: str           # Resource name as declared in source file
    type: str           # Resource type string e.g. "aws_s3_bucket", "Deployment"
    file: str           # Relative path to source file
    line_number: int    # Line of declaration (0 if unavailable)
    source: str         # "terraform" or "kubernetes"


class Edge(BaseModel):
    """A directed dependency edge between two Resource nodes."""
    source: str         # ID of the dependent resource
    target: str         # ID of the dependency


class GraphData(BaseModel):
    """Full or partial graph returned by GET /graph and GET /graph/resource/{id}."""
    nodes: List[Resource]
    edges: List[Edge]


class MostConnected(BaseModel):
    """Most connected resource (by total degree) for stats endpoint."""
    id: str
    name: str
    type: str
    degree: int


class GraphStats(BaseModel):
    """Aggregate statistics returned by GET /graph/stats."""
    node_count: int
    edge_count: int
    most_connected: Optional[MostConnected]
    isolated_count: int
    circular_dependencies: int


class ParseResult(BaseModel):
    """Response from POST /parse/terraform and POST /parse/kubernetes."""
    node_count: int
    edge_count: int


class ResetResult(BaseModel):
    """Response from POST /graph/reset."""
    deleted: int
