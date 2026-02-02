"""Tests for knowledge graph storage."""

import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.knowledge_graph import KnowledgeGraph


@pytest.fixture
def kg():
    """Create a temporary knowledge graph for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        yield KnowledgeGraph(db_path)


class TestKnowledgeGraph:
    """Tests for KnowledgeGraph class."""

    def test_upsert_entity_insert(self, kg):
        """Test inserting a new entity."""
        is_new = kg.upsert_entity(
            entity_id="person:test@example.com",
            entity_type="person",
            name="Test User",
            email="test@example.com",
            source="gmail",
            source_account="personal",
        )

        assert is_new is True

    def test_upsert_entity_update(self, kg):
        """Test updating an existing entity."""
        kg.upsert_entity(
            entity_id="person:test@example.com",
            entity_type="person",
            name="Test User",
            email="test@example.com",
            source="gmail",
        )

        is_new = kg.upsert_entity(
            entity_id="person:test@example.com",
            entity_type="person",
            name="Updated Name",
            email="test@example.com",
            source="gmail",
        )

        assert is_new is False

    def test_get_entity(self, kg):
        """Test retrieving an entity."""
        kg.upsert_entity(
            entity_id="person:test@example.com",
            entity_type="person",
            name="Test User",
            email="test@example.com",
            source="gmail",
        )

        entity = kg.get_entity("person:test@example.com")

        assert entity is not None
        assert entity["name"] == "Test User"
        assert entity["email"] == "test@example.com"

    def test_get_entity_not_found(self, kg):
        """Test retrieving non-existent entity."""
        entity = kg.get_entity("nonexistent")
        assert entity is None

    def test_upsert_content(self, kg):
        """Test inserting content."""
        is_new = kg.upsert_content(
            content_id="gmail:personal:123",
            content_type="email",
            source="gmail",
            source_account="personal",
            title="Test Email",
            body="This is a test email body.",
            timestamp=datetime.now(timezone.utc),
        )

        assert is_new is True

    def test_search_content(self, kg):
        """Test searching content."""
        kg.upsert_content(
            content_id="gmail:personal:123",
            content_type="email",
            source="gmail",
            title="Important Meeting",
            body="Discussion about quarterly report",
        )

        results = kg.search_content(query="quarterly")

        assert len(results) == 1
        assert "quarterly" in results[0]["body"].lower()

    def test_search_content_by_type(self, kg):
        """Test searching content filtered by type."""
        kg.upsert_content(
            content_id="email1",
            content_type="email",
            source="gmail",
            title="Email",
        )
        kg.upsert_content(
            content_id="file1",
            content_type="file",
            source="drive",
            title="File",
        )

        results = kg.search_content(content_type="email")

        assert len(results) == 1
        assert results[0]["type"] == "email"

    def test_add_relationship(self, kg):
        """Test adding a relationship."""
        kg.upsert_entity("person:a", "person", "Person A", "gmail")
        kg.upsert_entity("person:b", "person", "Person B", "gmail")

        added = kg.add_relationship(
            from_id="person:a",
            from_type="person",
            to_id="person:b",
            to_type="person",
            relation="knows",
        )

        assert added is True

    def test_add_relationship_duplicate(self, kg):
        """Test that duplicate relationships are ignored."""
        kg.upsert_entity("person:a", "person", "Person A", "gmail")
        kg.upsert_entity("person:b", "person", "Person B", "gmail")

        kg.add_relationship("person:a", "person", "person:b", "person", "knows")
        added = kg.add_relationship("person:a", "person", "person:b", "person", "knows")

        assert added is False

    def test_get_relationships(self, kg):
        """Test getting relationships."""
        kg.upsert_entity("person:a", "person", "Person A", "gmail")
        kg.upsert_entity("person:b", "person", "Person B", "gmail")
        kg.add_relationship("person:a", "person", "person:b", "person", "knows")

        rels = kg.get_relationships("person:a", direction="outgoing")

        assert len(rels) == 1
        assert rels[0]["relation"] == "knows"

    def test_sync_state(self, kg):
        """Test sync state management."""
        now = datetime.now(timezone.utc)

        kg.set_last_sync(
            source="gmail",
            account="personal",
            last_sync=now,
            sync_token="abc123",
        )

        state = kg.get_last_sync("gmail", "personal")

        assert state is not None
        assert state["last_sync_token"] == "abc123"

    def test_get_stats(self, kg):
        """Test getting statistics."""
        kg.upsert_entity("e1", "person", "Test", "gmail")
        kg.upsert_content("c1", "email", "gmail", title="Test")

        stats = kg.get_stats()

        assert stats["total_entities"] == 1
        assert stats["total_content"] == 1

    def test_delete_content(self, kg):
        """Test deleting content."""
        kg.upsert_content("c1", "email", "gmail", title="Test")

        deleted = kg.delete_content("c1")
        assert deleted is True

        content = kg.get_content("c1")
        assert content is None

    def test_delete_content_not_found(self, kg):
        """Test deleting non-existent content."""
        deleted = kg.delete_content("nonexistent")
        assert deleted is False
