"""
neo4j_client.py — Neo4j connection manager for InfraGraph.

Follows the pattern from .claude/agents/neo4j-docker-client-generator.md:
  - Context manager for safe resource cleanup
  - execute_read  → returns list[dict] (column name → value)
  - execute_write → executes a write query, discards result
  - execute_write_batch → UNWIND-based batch write in a single round trip

Security: all queries must use named parameters ($param). Never interpolate values.
"""

from __future__ import annotations

import os
import sys
import time
from typing import Any

from neo4j import GraphDatabase
from neo4j.exceptions import ServiceUnavailable


class Neo4jClient:
    """
    Thread-safe Neo4j connection manager.

    Usage (context manager — preferred):
        with Neo4jClient.from_env() as client:
            records = client.execute_read("MATCH (n:Resource) RETURN n.id AS id")

    Usage (manual):
        client = Neo4jClient(uri, username, password)
        try:
            ...
        finally:
            client.close()
    """

    def __init__(
        self,
        uri: str,
        username: str,
        password: str,
        database: str = "neo4j",
    ) -> None:
        self._driver = GraphDatabase.driver(uri, auth=(username, password))
        self._database = database

    # ------------------------------------------------------------------
    # Class factory
    # ------------------------------------------------------------------

    @classmethod
    def from_env(cls) -> "Neo4jClient":
        """
        Create a client from environment variables.
        Reads: NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD, NEO4J_DATABASE.
        """
        return cls(
            uri=os.environ["NEO4J_URI"],
            username=os.environ["NEO4J_USERNAME"],
            password=os.environ["NEO4J_PASSWORD"],
            database=os.environ.get("NEO4J_DATABASE", "neo4j"),
        )

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self) -> "Neo4jClient":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()

    def close(self) -> None:
        self._driver.close()

    # ------------------------------------------------------------------
    # Query execution
    # ------------------------------------------------------------------

    def execute_read(self, query: str, **params: Any) -> list[dict]:
        """
        Run a read (MATCH / RETURN) query and return all records as dicts.
        Each dict maps return column name → value (may include Node objects).
        """
        with self._driver.session(database=self._database) as session:
            result = session.run(query, **params)
            return [dict(record) for record in result]

    def execute_write(self, query: str, **params: Any) -> None:
        """
        Run a write query (CREATE / MERGE / DELETE). Result is discarded.
        """
        with self._driver.session(database=self._database) as session:
            session.run(query, **params).consume()

    def execute_write_batch(self, query: str, items: list[dict]) -> None:
        """
        Execute a parameterized query once per item using a single explicit
        transaction for efficiency. Intended for bulk MERGE operations.

        The query receives each item's fields as named parameters ($key).
        """
        if not items:
            return
        with self._driver.session(database=self._database) as session:
            with session.begin_transaction() as tx:
                for item in items:
                    tx.run(query, **item)
                tx.commit()

    # ------------------------------------------------------------------
    # Readiness check
    # ------------------------------------------------------------------

    def wait_until_ready(
        self,
        max_retries: int = 30,
        retry_interval: float = 2.0,
    ) -> None:
        """
        Block until Neo4j is reachable, retrying up to max_retries times.
        Raises RuntimeError if it never becomes available.
        """
        for attempt in range(max_retries):
            try:
                self.execute_read("RETURN 1 AS ok")
                return
            except ServiceUnavailable:
                if attempt == max_retries - 1:
                    raise RuntimeError(
                        f"Neo4j did not become available after "
                        f"{max_retries * retry_interval:.0f} seconds"
                    )
                print(
                    f"[neo4j] Waiting for Neo4j... attempt {attempt + 1}/{max_retries}",
                    file=sys.stderr,
                )
                time.sleep(retry_interval)
