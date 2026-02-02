"""Google Calendar content indexer."""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from ..config import GOOGLE_ACCOUNTS
from ..integrations.gcalendar import CalendarClient
from ..knowledge_graph import KnowledgeGraph

logger = logging.getLogger(__name__)


class CalendarIndexer:
    """Indexer for Google Calendar events across multiple accounts."""

    def __init__(self, kg: KnowledgeGraph | None = None):
        """Initialize the Calendar indexer.

        Args:
            kg: Knowledge graph instance. Creates new one if not provided.
        """
        self.kg = kg or KnowledgeGraph()

    def index_all(
        self,
        account: str,
        days_back: int = 365,
        days_forward: int = 90,
    ) -> dict[str, Any]:
        """Index all events for an account within a time range.

        Args:
            account: Google account identifier.
            days_back: Number of days to look back.
            days_forward: Number of days to look forward.

        Returns:
            Statistics about the indexing operation.
        """
        if account not in GOOGLE_ACCOUNTS:
            raise ValueError(f"Unknown account: {account}")

        logger.info(f"Starting full Calendar index for account '{account}'")

        client = CalendarClient(account)
        stats = {
            "events_processed": 0,
            "events_indexed": 0,
            "people_extracted": 0,
            "errors": 0,
        }

        # Calculate time range
        now = datetime.now(timezone.utc)
        time_min = now - timedelta(days=days_back)
        time_max = now + timedelta(days=days_forward)

        page_token = None

        while True:
            try:
                response = client.list_events(
                    time_min=time_min,
                    time_max=time_max,
                    page_token=page_token,
                    max_results=250,
                )

                for event in response.get("items", []):
                    try:
                        self._index_event(account, event, stats)
                        stats["events_processed"] += 1
                    except Exception as e:
                        logger.error(f"Error indexing event {event.get('id')}: {e}")
                        stats["errors"] += 1

                page_token = response.get("nextPageToken")
                if not page_token:
                    # Get sync token for incremental sync
                    sync_token = response.get("nextSyncToken")
                    if sync_token:
                        self.kg.set_last_sync(
                            source="calendar",
                            account=account,
                            last_sync=datetime.now(timezone.utc),
                            sync_token=sync_token,
                            metadata={"type": "full", "stats": stats},
                        )
                    break

                logger.info(f"Processed {stats['events_processed']} events...")

            except Exception as e:
                logger.error(f"Error listing events: {e}")
                stats["errors"] += 1
                break

        logger.info(f"Calendar indexing complete for '{account}': {stats}")
        return stats

    def index_delta(self, account: str) -> dict[str, Any]:
        """Index changed events since last sync.

        Args:
            account: Google account identifier.

        Returns:
            Statistics about the indexing operation.
        """
        if account not in GOOGLE_ACCOUNTS:
            raise ValueError(f"Unknown account: {account}")

        logger.info(f"Starting delta Calendar sync for account '{account}'")

        client = CalendarClient(account)
        stats = {
            "events_added": 0,
            "events_updated": 0,
            "events_deleted": 0,
            "errors": 0,
        }

        # Get last sync state
        sync_state = self.kg.get_last_sync("calendar", account)

        if not sync_state or not sync_state.get("last_sync_token"):
            logger.warning(f"No previous sync state for '{account}', doing full sync")
            return self.index_all(account)

        sync_token = sync_state["last_sync_token"]

        try:
            response = client.list_changes(sync_token=sync_token)

            for event in response.get("items", []):
                event_id = event.get("id")
                content_id = f"calendar:{account}:{event_id}"

                # Check if event was deleted or cancelled
                if event.get("status") == "cancelled":
                    if self.kg.delete_content(content_id):
                        stats["events_deleted"] += 1
                else:
                    try:
                        is_new = self._index_event(account, event, stats)
                        if is_new:
                            stats["events_added"] += 1
                        else:
                            stats["events_updated"] += 1
                    except Exception as e:
                        logger.error(f"Error indexing event {event_id}: {e}")
                        stats["errors"] += 1

            # Update sync state
            new_sync_token = response.get("nextSyncToken")
            if new_sync_token:
                self.kg.set_last_sync(
                    source="calendar",
                    account=account,
                    last_sync=datetime.now(timezone.utc),
                    sync_token=new_sync_token,
                    metadata={"type": "delta", "stats": stats},
                )

        except Exception as e:
            logger.error(f"Error in delta sync: {e}")
            stats["errors"] += 1
            # If sync token is invalid, do full sync
            if "sync token" in str(e).lower() or "410" in str(e):
                logger.info("Sync token expired, performing full sync")
                return self.index_all(account)

        logger.info(f"Calendar delta sync complete for '{account}': {stats}")
        return stats

    def _index_event(
        self,
        account: str,
        event: dict,
        stats: dict[str, int],
    ) -> bool:
        """Index a single event and extract entities.

        Returns:
            True if event was newly indexed, False if updated.
        """
        parsed = CalendarClient.parse_event(event)
        content_id = f"calendar:{account}:{parsed['id']}"

        # Extract and index attendees as people
        all_people = []

        # Organizer
        if parsed.get("organizer") and parsed["organizer"].get("email"):
            org = parsed["organizer"]
            all_people.append({
                "email": org["email"],
                "name": org.get("name"),
                "relation": "organizer",
            })

        # Attendees
        for attendee in parsed.get("attendees", []):
            if attendee.get("email"):
                all_people.append({
                    "email": attendee["email"],
                    "name": attendee.get("name"),
                    "relation": "attendee",
                })

        for person in all_people:
            person_id = f"person:{person['email']}"
            is_new = self.kg.upsert_entity(
                entity_id=person_id,
                entity_type="person",
                name=person["name"] or person["email"],
                email=person["email"],
                source="calendar",
                source_account=account,
            )
            if is_new:
                stats["people_extracted"] += 1

            # Add relationship
            self.kg.add_relationship(
                from_id=content_id,
                from_type="event",
                to_id=person_id,
                to_type="person",
                relation=person["relation"],
            )

        # Build event body for search
        body_parts = []
        if parsed["description"]:
            body_parts.append(parsed["description"])
        if parsed["location"]:
            body_parts.append(f"Location: {parsed['location']}")
        if parsed.get("conference_url"):
            body_parts.append(f"Conference: {parsed['conference_url']}")

        # Index the event
        is_new = self.kg.upsert_content(
            content_id=content_id,
            content_type="event",
            source="calendar",
            source_account=account,
            title=parsed["summary"],
            body="\n".join(body_parts) if body_parts else None,
            source_id=parsed["id"],
            url=parsed["html_link"],
            timestamp=parsed.get("start"),
            metadata={
                "end": parsed["end"].isoformat() if parsed.get("end") else None,
                "is_all_day": parsed["is_all_day"],
                "location": parsed["location"],
                "status": parsed["status"],
                "attendee_count": len(parsed.get("attendees", [])),
            },
        )

        if is_new:
            stats["events_indexed"] += 1

        return is_new
