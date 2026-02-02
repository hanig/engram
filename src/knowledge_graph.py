"""SQLite-based knowledge graph storage."""

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Generator

from .config import KNOWLEDGE_GRAPH_DB


class KnowledgeGraph:
    """SQLite-based storage for entities, content, and relationships."""

    def __init__(self, db_path: Path | str | None = None):
        """Initialize the knowledge graph.

        Args:
            db_path: Path to SQLite database. Defaults to config value.
        """
        self.db_path = Path(db_path) if db_path else KNOWLEDGE_GRAPH_DB
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @contextmanager
    def _connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Context manager for database connections."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_schema(self) -> None:
        """Initialize database schema."""
        with self._connection() as conn:
            conn.executescript("""
                -- Entities table (people, repos, channels, etc.)
                CREATE TABLE IF NOT EXISTS entities (
                    id TEXT PRIMARY KEY,
                    type TEXT NOT NULL,
                    name TEXT NOT NULL,
                    email TEXT,
                    source TEXT NOT NULL,
                    source_account TEXT,
                    metadata TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_entities_type ON entities(type);
                CREATE INDEX IF NOT EXISTS idx_entities_source ON entities(source);
                CREATE INDEX IF NOT EXISTS idx_entities_email ON entities(email);

                -- Content table (emails, documents, messages, etc.)
                CREATE TABLE IF NOT EXISTS content (
                    id TEXT PRIMARY KEY,
                    type TEXT NOT NULL,
                    title TEXT,
                    body TEXT,
                    source TEXT NOT NULL,
                    source_account TEXT,
                    source_id TEXT,
                    url TEXT,
                    timestamp TIMESTAMP,
                    metadata TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_content_type ON content(type);
                CREATE INDEX IF NOT EXISTS idx_content_source ON content(source);
                CREATE INDEX IF NOT EXISTS idx_content_timestamp ON content(timestamp);
                CREATE INDEX IF NOT EXISTS idx_content_source_id ON content(source_id);

                -- Relationships table
                CREATE TABLE IF NOT EXISTS relationships (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    from_id TEXT NOT NULL,
                    from_type TEXT NOT NULL,
                    to_id TEXT NOT NULL,
                    to_type TEXT NOT NULL,
                    relation TEXT NOT NULL,
                    metadata TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (from_id) REFERENCES entities(id) ON DELETE CASCADE,
                    FOREIGN KEY (to_id) REFERENCES entities(id) ON DELETE CASCADE
                );
                CREATE INDEX IF NOT EXISTS idx_rel_from ON relationships(from_id);
                CREATE INDEX IF NOT EXISTS idx_rel_to ON relationships(to_id);
                CREATE INDEX IF NOT EXISTS idx_rel_relation ON relationships(relation);
                CREATE UNIQUE INDEX IF NOT EXISTS idx_rel_unique
                    ON relationships(from_id, to_id, relation);

                -- Changelog for auditing
                CREATE TABLE IF NOT EXISTS changelog (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    table_name TEXT NOT NULL,
                    record_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    old_value TEXT,
                    new_value TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                CREATE INDEX IF NOT EXISTS idx_changelog_record ON changelog(table_name, record_id);
                CREATE INDEX IF NOT EXISTS idx_changelog_timestamp ON changelog(timestamp);

                -- Sync state tracking
                CREATE TABLE IF NOT EXISTS sync_state (
                    source TEXT NOT NULL,
                    account TEXT NOT NULL,
                    last_sync TIMESTAMP,
                    last_sync_token TEXT,
                    metadata TEXT,
                    PRIMARY KEY (source, account)
                );
            """)

    def upsert_entity(
        self,
        entity_id: str,
        entity_type: str,
        name: str,
        source: str,
        source_account: str | None = None,
        email: str | None = None,
        metadata: dict | None = None,
    ) -> bool:
        """Insert or update an entity.

        Returns:
            True if inserted, False if updated.
        """
        with self._connection() as conn:
            # Check if exists
            existing = conn.execute(
                "SELECT id FROM entities WHERE id = ?", (entity_id,)
            ).fetchone()

            metadata_json = json.dumps(metadata) if metadata else None

            if existing:
                conn.execute(
                    """
                    UPDATE entities
                    SET type = ?, name = ?, email = ?, source = ?, source_account = ?,
                        metadata = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (entity_type, name, email, source, source_account, metadata_json, entity_id),
                )
                self._log_change(conn, "entities", entity_id, "update")
                return False
            else:
                conn.execute(
                    """
                    INSERT INTO entities (id, type, name, email, source, source_account, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (entity_id, entity_type, name, email, source, source_account, metadata_json),
                )
                self._log_change(conn, "entities", entity_id, "insert")
                return True

    def upsert_content(
        self,
        content_id: str,
        content_type: str,
        source: str,
        source_account: str | None = None,
        title: str | None = None,
        body: str | None = None,
        source_id: str | None = None,
        url: str | None = None,
        timestamp: datetime | None = None,
        metadata: dict | None = None,
    ) -> bool:
        """Insert or update content.

        Returns:
            True if inserted, False if updated.
        """
        with self._connection() as conn:
            existing = conn.execute(
                "SELECT id FROM content WHERE id = ?", (content_id,)
            ).fetchone()

            metadata_json = json.dumps(metadata) if metadata else None
            ts = timestamp.isoformat() if timestamp else None

            if existing:
                conn.execute(
                    """
                    UPDATE content
                    SET type = ?, title = ?, body = ?, source = ?, source_account = ?,
                        source_id = ?, url = ?, timestamp = ?, metadata = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (
                        content_type, title, body, source, source_account,
                        source_id, url, ts, metadata_json, content_id
                    ),
                )
                self._log_change(conn, "content", content_id, "update")
                return False
            else:
                conn.execute(
                    """
                    INSERT INTO content
                    (id, type, title, body, source, source_account, source_id, url, timestamp, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        content_id, content_type, title, body, source, source_account,
                        source_id, url, ts, metadata_json
                    ),
                )
                self._log_change(conn, "content", content_id, "insert")
                return True

    def add_relationship(
        self,
        from_id: str,
        from_type: str,
        to_id: str,
        to_type: str,
        relation: str,
        metadata: dict | None = None,
    ) -> bool:
        """Add a relationship between entities.

        Returns:
            True if added, False if already exists.
        """
        with self._connection() as conn:
            try:
                metadata_json = json.dumps(metadata) if metadata else None
                conn.execute(
                    """
                    INSERT INTO relationships (from_id, from_type, to_id, to_type, relation, metadata)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (from_id, from_type, to_id, to_type, relation, metadata_json),
                )
                return True
            except sqlite3.IntegrityError:
                return False

    def get_entity(self, entity_id: str) -> dict | None:
        """Get an entity by ID."""
        with self._connection() as conn:
            row = conn.execute(
                "SELECT * FROM entities WHERE id = ?", (entity_id,)
            ).fetchone()
            return self._row_to_dict(row) if row else None

    def get_content(self, content_id: str) -> dict | None:
        """Get content by ID."""
        with self._connection() as conn:
            row = conn.execute(
                "SELECT * FROM content WHERE id = ?", (content_id,)
            ).fetchone()
            return self._row_to_dict(row) if row else None

    def search_entities(
        self,
        query: str | None = None,
        entity_type: str | None = None,
        source: str | None = None,
        limit: int = 100,
    ) -> list[dict]:
        """Search entities by name, type, or source."""
        with self._connection() as conn:
            conditions = []
            params = []

            if query:
                conditions.append("(name LIKE ? OR email LIKE ?)")
                params.extend([f"%{query}%", f"%{query}%"])
            if entity_type:
                conditions.append("type = ?")
                params.append(entity_type)
            if source:
                conditions.append("source = ?")
                params.append(source)

            where_clause = " AND ".join(conditions) if conditions else "1=1"
            sql = f"SELECT * FROM entities WHERE {where_clause} ORDER BY updated_at DESC LIMIT ?"
            params.append(limit)

            rows = conn.execute(sql, params).fetchall()
            return [self._row_to_dict(row) for row in rows]

    def search_content(
        self,
        query: str | None = None,
        content_type: str | None = None,
        source: str | None = None,
        source_account: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 100,
    ) -> list[dict]:
        """Search content with various filters."""
        with self._connection() as conn:
            conditions = []
            params = []

            if query:
                conditions.append("(title LIKE ? OR body LIKE ?)")
                params.extend([f"%{query}%", f"%{query}%"])
            if content_type:
                conditions.append("type = ?")
                params.append(content_type)
            if source:
                conditions.append("source = ?")
                params.append(source)
            if source_account:
                conditions.append("source_account = ?")
                params.append(source_account)
            if since:
                conditions.append("timestamp >= ?")
                params.append(since.isoformat())
            if until:
                conditions.append("timestamp <= ?")
                params.append(until.isoformat())

            where_clause = " AND ".join(conditions) if conditions else "1=1"
            sql = f"""
                SELECT * FROM content
                WHERE {where_clause}
                ORDER BY timestamp DESC
                LIMIT ?
            """
            params.append(limit)

            rows = conn.execute(sql, params).fetchall()
            return [self._row_to_dict(row) for row in rows]

    def get_relationships(
        self,
        entity_id: str,
        relation: str | None = None,
        direction: str = "both",
    ) -> list[dict]:
        """Get relationships for an entity.

        Args:
            entity_id: The entity ID.
            relation: Filter by relation type.
            direction: "outgoing", "incoming", or "both".
        """
        with self._connection() as conn:
            results = []

            if direction in ("outgoing", "both"):
                conditions = ["from_id = ?"]
                params = [entity_id]
                if relation:
                    conditions.append("relation = ?")
                    params.append(relation)

                rows = conn.execute(
                    f"SELECT * FROM relationships WHERE {' AND '.join(conditions)}",
                    params,
                ).fetchall()
                results.extend([self._row_to_dict(row) for row in rows])

            if direction in ("incoming", "both"):
                conditions = ["to_id = ?"]
                params = [entity_id]
                if relation:
                    conditions.append("relation = ?")
                    params.append(relation)

                rows = conn.execute(
                    f"SELECT * FROM relationships WHERE {' AND '.join(conditions)}",
                    params,
                ).fetchall()
                results.extend([self._row_to_dict(row) for row in rows])

            return results

    def get_last_sync(self, source: str, account: str) -> dict | None:
        """Get the last sync state for a source/account combination."""
        with self._connection() as conn:
            row = conn.execute(
                "SELECT * FROM sync_state WHERE source = ? AND account = ?",
                (source, account),
            ).fetchone()
            return self._row_to_dict(row) if row else None

    def set_last_sync(
        self,
        source: str,
        account: str,
        last_sync: datetime,
        sync_token: str | None = None,
        metadata: dict | None = None,
    ) -> None:
        """Update the sync state for a source/account combination."""
        with self._connection() as conn:
            metadata_json = json.dumps(metadata) if metadata else None
            conn.execute(
                """
                INSERT INTO sync_state (source, account, last_sync, last_sync_token, metadata)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(source, account) DO UPDATE SET
                    last_sync = excluded.last_sync,
                    last_sync_token = excluded.last_sync_token,
                    metadata = excluded.metadata
                """,
                (source, account, last_sync.isoformat(), sync_token, metadata_json),
            )

    def get_stats(self) -> dict[str, Any]:
        """Get statistics about the knowledge graph."""
        with self._connection() as conn:
            stats = {}

            # Entity counts by type
            rows = conn.execute(
                "SELECT type, COUNT(*) as count FROM entities GROUP BY type"
            ).fetchall()
            stats["entities_by_type"] = {row["type"]: row["count"] for row in rows}

            # Content counts by type
            rows = conn.execute(
                "SELECT type, COUNT(*) as count FROM content GROUP BY type"
            ).fetchall()
            stats["content_by_type"] = {row["type"]: row["count"] for row in rows}

            # Content counts by source
            rows = conn.execute(
                "SELECT source, COUNT(*) as count FROM content GROUP BY source"
            ).fetchall()
            stats["content_by_source"] = {row["source"]: row["count"] for row in rows}

            # Total counts
            stats["total_entities"] = conn.execute(
                "SELECT COUNT(*) FROM entities"
            ).fetchone()[0]
            stats["total_content"] = conn.execute(
                "SELECT COUNT(*) FROM content"
            ).fetchone()[0]
            stats["total_relationships"] = conn.execute(
                "SELECT COUNT(*) FROM relationships"
            ).fetchone()[0]

            # Last sync times
            rows = conn.execute("SELECT * FROM sync_state").fetchall()
            stats["sync_state"] = [self._row_to_dict(row) for row in rows]

            return stats

    def _log_change(
        self,
        conn: sqlite3.Connection,
        table_name: str,
        record_id: str,
        action: str,
        old_value: str | None = None,
        new_value: str | None = None,
    ) -> None:
        """Log a change to the changelog table."""
        conn.execute(
            """
            INSERT INTO changelog (table_name, record_id, action, old_value, new_value)
            VALUES (?, ?, ?, ?, ?)
            """,
            (table_name, record_id, action, old_value, new_value),
        )

    def _row_to_dict(self, row: sqlite3.Row) -> dict:
        """Convert a database row to a dictionary."""
        d = dict(row)
        # Parse JSON metadata if present
        if "metadata" in d and d["metadata"]:
            try:
                d["metadata"] = json.loads(d["metadata"])
            except json.JSONDecodeError:
                pass
        return d

    def delete_content(self, content_id: str) -> bool:
        """Delete content by ID.

        Returns:
            True if deleted, False if not found.
        """
        with self._connection() as conn:
            cursor = conn.execute("DELETE FROM content WHERE id = ?", (content_id,))
            if cursor.rowcount > 0:
                self._log_change(conn, "content", content_id, "delete")
                return True
            return False

    def delete_entity(self, entity_id: str) -> bool:
        """Delete an entity by ID.

        Returns:
            True if deleted, False if not found.
        """
        with self._connection() as conn:
            cursor = conn.execute("DELETE FROM entities WHERE id = ?", (entity_id,))
            if cursor.rowcount > 0:
                self._log_change(conn, "entities", entity_id, "delete")
                return True
            return False

    def get_content_ids_by_source(
        self, source: str, source_account: str | None = None
    ) -> set[str]:
        """Get all content IDs for a given source.

        Useful for detecting deleted items during sync.
        """
        with self._connection() as conn:
            if source_account:
                rows = conn.execute(
                    "SELECT id FROM content WHERE source = ? AND source_account = ?",
                    (source, source_account),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT id FROM content WHERE source = ?", (source,)
                ).fetchall()
            return {row["id"] for row in rows}
