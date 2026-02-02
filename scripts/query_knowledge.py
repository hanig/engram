#!/usr/bin/env python3
"""CLI for querying the knowledge graph."""

import argparse
import json
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.knowledge_graph import KnowledgeGraph
from src.query.engine import QueryEngine


def search(query: str, top_k: int = 10, content_type: str | None = None) -> None:
    """Search the knowledge graph.

    Args:
        query: Search query.
        top_k: Number of results.
        content_type: Filter by content type.
    """
    engine = QueryEngine()

    content_types = [content_type] if content_type else None

    results = engine.search(
        query=query,
        content_types=content_types,
        top_k=top_k,
    )

    print(f"\nSearch results for: {query}")
    print("=" * 60)

    if not results:
        print("No results found.")
        return

    for i, result in enumerate(results, 1):
        score = result.get("score", 0)
        title = result.get("metadata", {}).get("title", result.get("id", "Untitled"))
        source_type = result.get("type", result.get("metadata", {}).get("source_type", ""))
        text = result.get("text", "")[:200]

        print(f"\n{i}. [{score:.2f}] {title}")
        print(f"   Type: {source_type}")
        if text:
            print(f"   {text}...")


def find_person(query: str) -> None:
    """Find a person in the knowledge graph.

    Args:
        query: Name or email to search for.
    """
    engine = QueryEngine()
    results = engine.find_person(query)

    print(f"\nPeople matching: {query}")
    print("=" * 60)

    if not results:
        print("No people found.")
        return

    for person in results:
        name = person.get("name", "Unknown")
        email = person.get("email", "")
        source = person.get("source", "")

        print(f"\n• {name}")
        if email:
            print(f"  Email: {email}")
        print(f"  Source: {source}")


def show_stats() -> None:
    """Show knowledge graph statistics."""
    kg = KnowledgeGraph()
    stats = kg.get_stats()

    print("\nKnowledge Graph Statistics")
    print("=" * 60)

    print("\nEntities by type:")
    for entity_type, count in stats.get("entities_by_type", {}).items():
        print(f"  {entity_type}: {count}")

    print("\nContent by type:")
    for content_type, count in stats.get("content_by_type", {}).items():
        print(f"  {content_type}: {count}")

    print("\nContent by source:")
    for source, count in stats.get("content_by_source", {}).items():
        print(f"  {source}: {count}")

    print(f"\nTotals:")
    print(f"  Entities: {stats.get('total_entities', 0)}")
    print(f"  Content: {stats.get('total_content', 0)}")
    print(f"  Relationships: {stats.get('total_relationships', 0)}")

    print("\nSync status:")
    for sync in stats.get("sync_state", []):
        source = sync.get("source", "unknown")
        account = sync.get("account", "")
        last_sync = sync.get("last_sync", "never")
        print(f"  {source}/{account}: {last_sync}")


def get_content(content_id: str) -> None:
    """Get content by ID.

    Args:
        content_id: Content ID.
    """
    kg = KnowledgeGraph()
    content = kg.get_content(content_id)

    if content:
        print(json.dumps(content, indent=2, default=str))
    else:
        print(f"Content not found: {content_id}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Query the knowledge graph")

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # Search command
    search_parser = subparsers.add_parser("search", help="Search the knowledge graph")
    search_parser.add_argument("query", type=str, help="Search query")
    search_parser.add_argument(
        "-n", "--top-k", type=int, default=10, help="Number of results"
    )
    search_parser.add_argument(
        "-t", "--type", type=str, help="Content type filter"
    )

    # Person command
    person_parser = subparsers.add_parser("person", help="Find a person")
    person_parser.add_argument("query", type=str, help="Name or email")

    # Stats command
    subparsers.add_parser("stats", help="Show statistics")

    # Get command
    get_parser = subparsers.add_parser("get", help="Get content by ID")
    get_parser.add_argument("id", type=str, help="Content ID")

    args = parser.parse_args()

    if args.command == "search":
        search(args.query, args.top_k, args.type)
    elif args.command == "person":
        find_person(args.query)
    elif args.command == "stats":
        show_stats()
    elif args.command == "get":
        get_content(args.id)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
