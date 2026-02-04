"""Zotero content indexer."""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from ..integrations.zotero_client import ZoteroClient
from ..knowledge_graph import KnowledgeGraph

logger = logging.getLogger(__name__)


class ZoteroIndexer:
    """Indexer for Zotero library items, notes, and collections."""

    def __init__(self, kg: KnowledgeGraph | None = None):
        """Initialize the Zotero indexer.

        Args:
            kg: Knowledge graph instance. Creates new one if not provided.
        """
        self.kg = kg or KnowledgeGraph()

    def index_all(self, max_items: int = 5000) -> dict[str, Any]:
        """Index all Zotero content.

        Args:
            max_items: Maximum number of items to index.

        Returns:
            Statistics about the indexing operation.
        """
        logger.info("Starting full Zotero index")

        try:
            client = ZoteroClient()
        except ValueError as e:
            logger.error(f"Cannot initialize Zotero client: {e}")
            return {"error": str(e)}

        stats = {
            "items_indexed": 0,
            "notes_indexed": 0,
            "collections_indexed": 0,
            "authors_indexed": 0,
            "errors": 0,
        }

        try:
            # Index collections first (for hierarchy)
            collections = client.list_collections()
            for collection in collections:
                self._index_collection(collection, stats)
            logger.info(f"Indexed {stats['collections_indexed']} collections")

            # Index items
            items = client.list_items(limit=max_items)
            for item in items:
                self._index_item(client, item, stats)

            logger.info(f"Indexed {stats['items_indexed']} items")

        except Exception as e:
            logger.error(f"Error in Zotero indexing: {e}", exc_info=True)
            stats["errors"] += 1

        self.kg.set_last_sync(
            source="zotero",
            account="default",
            last_sync=datetime.now(timezone.utc),
            metadata={"type": "full", "stats": stats},
        )

        logger.info(f"Zotero indexing complete: {stats}")
        return stats

    def index_delta(self, days_back: int = 7) -> dict[str, Any]:
        """Index recently modified Zotero content.

        Args:
            days_back: Number of days to look back.

        Returns:
            Statistics about the indexing operation.
        """
        logger.info(f"Starting delta Zotero sync (last {days_back} days)")

        try:
            client = ZoteroClient()
        except ValueError as e:
            logger.error(f"Cannot initialize Zotero client: {e}")
            return {"error": str(e)}

        stats = {
            "items_updated": 0,
            "notes_updated": 0,
            "errors": 0,
        }

        try:
            # Get recently added/modified items
            recent_items = client.get_recent_items(days=days_back)

            for item in recent_items:
                self._index_item(client, item, stats, is_delta=True)

            logger.info(f"Delta indexed {stats['items_updated']} items")

        except Exception as e:
            logger.error(f"Error in Zotero delta sync: {e}", exc_info=True)
            stats["errors"] += 1

        self.kg.set_last_sync(
            source="zotero",
            account="default",
            last_sync=datetime.now(timezone.utc),
            metadata={"type": "delta", "stats": stats},
        )

        logger.info(f"Zotero delta sync complete: {stats}")
        return stats

    def _index_collection(self, collection: dict, stats: dict[str, int]) -> None:
        """Index a Zotero collection."""
        collection_key = collection["key"]
        content_id = f"zotero:collection:{collection_key}"

        # Build description
        body = f"Zotero collection containing {collection['item_count']} items."
        if collection.get("parent_key"):
            body += f"\nParent collection: {collection['parent_key']}"

        self.kg.upsert_content(
            content_id=content_id,
            content_type="collection",
            source="zotero",
            source_account="default",
            title=collection["name"],
            body=body,
            source_id=collection_key,
            url=None,
            timestamp=datetime.now(timezone.utc),
            metadata={
                "parent_key": collection.get("parent_key"),
                "item_count": collection["item_count"],
            },
        )

        stats["collections_indexed"] += 1

    def _index_item(
        self,
        client: ZoteroClient,
        item: dict,
        stats: dict[str, int],
        is_delta: bool = False,
    ) -> None:
        """Index a Zotero item (paper, book, etc.)."""
        item_key = item["key"]
        content_id = f"zotero:item:{item_key}"

        # Build rich body content
        body_parts = []

        # Abstract
        if item.get("abstract"):
            body_parts.append(f"Abstract:\n{item['abstract']}")

        # Authors
        if item.get("authors"):
            authors_str = ", ".join(item["authors"])
            body_parts.append(f"Authors: {authors_str}")

        # Publication info
        pub_info = []
        if item.get("journal"):
            pub_info.append(item["journal"])
        if item.get("volume"):
            pub_info.append(f"Vol. {item['volume']}")
        if item.get("issue"):
            pub_info.append(f"Issue {item['issue']}")
        if item.get("pages"):
            pub_info.append(f"pp. {item['pages']}")
        if item.get("year"):
            pub_info.append(f"({item['year']})")
        if pub_info:
            body_parts.append("Publication: " + ", ".join(pub_info))

        # DOI
        if item.get("doi"):
            body_parts.append(f"DOI: {item['doi']}")

        # Tags
        if item.get("tags"):
            body_parts.append(f"Tags: {', '.join(item['tags'])}")

        # Extra field (often contains additional metadata)
        if item.get("extra"):
            body_parts.append(f"Notes: {item['extra']}")

        body = "\n\n".join(body_parts)

        # Build title with type prefix
        item_type = item.get("item_type", "item")
        type_label = self._format_item_type(item_type)
        title = f"[{type_label}] {item['title']}"

        # Parse timestamp
        timestamp = self._parse_timestamp(item.get("date_added"))

        # Build URL (prefer DOI, then URL field)
        url = None
        if item.get("doi"):
            url = f"https://doi.org/{item['doi']}"
        elif item.get("url"):
            url = item["url"]

        self.kg.upsert_content(
            content_id=content_id,
            content_type="paper",
            source="zotero",
            source_account="default",
            title=title,
            body=body,
            source_id=item_key,
            url=url,
            timestamp=timestamp,
            metadata={
                "item_type": item_type,
                "authors": item.get("authors", []),
                "year": item.get("year"),
                "journal": item.get("journal"),
                "doi": item.get("doi"),
                "tags": item.get("tags", []),
                "collections": item.get("collections", []),
                "date_modified": item.get("date_modified"),
            },
        )

        # Update stats
        if is_delta:
            stats["items_updated"] += 1
        else:
            stats["items_indexed"] += 1

        # Index authors as entities
        self._extract_authors(item, content_id, stats)

        # Index notes for this item
        try:
            notes = client.get_item_notes(item_key)
            for note in notes:
                self._index_note(note, item, stats, is_delta)
        except Exception as e:
            logger.debug(f"Could not fetch notes for item {item_key}: {e}")

    def _index_note(
        self,
        note: dict,
        parent_item: dict,
        stats: dict[str, int],
        is_delta: bool = False,
    ) -> None:
        """Index a note attached to an item."""
        note_key = note["key"]
        content_id = f"zotero:note:{note_key}"

        # Strip HTML from note content for indexing
        note_text = self._strip_html(note.get("note", ""))

        title = f"Note on: {parent_item['title']}"

        self.kg.upsert_content(
            content_id=content_id,
            content_type="note",
            source="zotero",
            source_account="default",
            title=title,
            body=note_text,
            source_id=note_key,
            url=None,
            timestamp=self._parse_timestamp(note.get("date_added")),
            metadata={
                "parent_key": note["parent_key"],
                "parent_title": parent_item["title"],
            },
        )

        # Link note to parent item
        self.kg.add_relationship(
            from_id=content_id,
            from_type="note",
            to_id=f"zotero:item:{note['parent_key']}",
            to_type="paper",
            relation="note_on",
        )

        if is_delta:
            stats["notes_updated"] += 1
        else:
            stats["notes_indexed"] += 1

    def _extract_authors(
        self,
        item: dict,
        content_id: str,
        stats: dict[str, int],
    ) -> None:
        """Extract and index authors as person entities."""
        creators = item.get("creators", [])

        for creator in creators:
            name = creator.get("name", "")
            if not name:
                first = creator.get("first_name", "")
                last = creator.get("last_name", "")
                name = f"{first} {last}".strip()

            if not name or name == "Unknown":
                continue

            # Create stable person ID from name
            person_id = f"person:zotero:{self._normalize_name(name)}"

            is_new = self.kg.upsert_entity(
                entity_id=person_id,
                entity_type="person",
                name=name,
                source="zotero",
                source_account="default",
                metadata={
                    "first_name": creator.get("first_name"),
                    "last_name": creator.get("last_name"),
                    "role": creator.get("type", "author"),
                },
            )

            if is_new:
                stats["authors_indexed"] += 1

            # Link author to paper
            relation = creator.get("type", "author")
            self.kg.add_relationship(
                from_id=content_id,
                from_type="paper",
                to_id=person_id,
                to_type="person",
                relation=relation,
            )

    def _format_item_type(self, item_type: str) -> str:
        """Format item type for display."""
        type_map = {
            "journalArticle": "Article",
            "book": "Book",
            "bookSection": "Book Chapter",
            "conferencePaper": "Conference",
            "thesis": "Thesis",
            "report": "Report",
            "webpage": "Web",
            "preprint": "Preprint",
            "manuscript": "Manuscript",
            "patent": "Patent",
        }
        return type_map.get(item_type, item_type.title())

    def _normalize_name(self, name: str) -> str:
        """Normalize a name for use as an ID."""
        # Lowercase, replace spaces with underscores
        normalized = name.lower().strip()
        normalized = normalized.replace(" ", "_")
        # Remove special characters
        normalized = "".join(c for c in normalized if c.isalnum() or c == "_")
        return normalized

    def _strip_html(self, html: str) -> str:
        """Strip HTML tags from a string."""
        import re
        # Remove HTML tags
        text = re.sub(r"<[^>]+>", "", html)
        # Decode common entities
        text = text.replace("&nbsp;", " ")
        text = text.replace("&amp;", "&")
        text = text.replace("&lt;", "<")
        text = text.replace("&gt;", ">")
        text = text.replace("&quot;", '"')
        # Collapse whitespace
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    def _parse_timestamp(self, timestamp_str: str | None) -> datetime | None:
        """Parse an ISO timestamp string."""
        if not timestamp_str:
            return None
        try:
            return datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            return None
