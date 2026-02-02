"""Google Drive API client."""

import io
import logging
from datetime import datetime
from typing import Any

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload

from .google_auth import get_credentials

logger = logging.getLogger(__name__)


# MIME types we can extract text from
EXPORTABLE_MIME_TYPES = {
    "application/vnd.google-apps.document": "text/plain",
    "application/vnd.google-apps.spreadsheet": "text/csv",
    "application/vnd.google-apps.presentation": "text/plain",
}

# Standard document types we can read
READABLE_MIME_TYPES = {
    "text/plain",
    "text/html",
    "text/csv",
    "text/markdown",
    "application/json",
    "application/xml",
}


class DriveClient:
    """Client for interacting with Google Drive API."""

    def __init__(self, account: str):
        """Initialize Drive client for a specific account.

        Args:
            account: Account identifier (e.g., "arc", "personal").
        """
        self.account = account
        self._service = None

    @property
    def service(self):
        """Lazily initialize the Drive service."""
        if self._service is None:
            creds = get_credentials(self.account)
            if not creds:
                raise RuntimeError(f"No valid credentials for account '{self.account}'")
            self._service = build("drive", "v3", credentials=creds)
        return self._service

    def get_about(self) -> dict:
        """Get user info and storage quota."""
        return (
            self.service.about()
            .get(fields="user,storageQuota")
            .execute()
        )

    def list_files(
        self,
        query: str | None = None,
        page_size: int = 100,
        page_token: str | None = None,
        order_by: str = "modifiedTime desc",
        fields: str = "nextPageToken, files(id, name, mimeType, modifiedTime, size, parents, webViewLink, owners)",
    ) -> dict[str, Any]:
        """List files matching criteria.

        Args:
            query: Drive search query (see Drive API docs for syntax).
            page_size: Number of files per page.
            page_token: Token for pagination.
            order_by: Sort order.
            fields: Fields to return.

        Returns:
            Dictionary with 'files' list and optional 'nextPageToken'.
        """
        try:
            params = {
                "pageSize": min(page_size, 1000),
                "orderBy": order_by,
                "fields": fields,
            }
            if query:
                params["q"] = query
            if page_token:
                params["pageToken"] = page_token

            return self.service.files().list(**params).execute()
        except HttpError as e:
            logger.error(f"Error listing files: {e}")
            raise

    def get_file(self, file_id: str, fields: str = "*") -> dict[str, Any] | None:
        """Get file metadata by ID.

        Args:
            file_id: The file ID.
            fields: Fields to return.

        Returns:
            File metadata or None if not found.
        """
        try:
            return self.service.files().get(fileId=file_id, fields=fields).execute()
        except HttpError as e:
            if e.resp.status == 404:
                return None
            logger.error(f"Error getting file {file_id}: {e}")
            raise

    def search_files(
        self,
        query: str,
        max_results: int = 100,
        file_types: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Search for files by content or name.

        Args:
            query: Search text (searches name and content).
            max_results: Maximum number of files to return.
            file_types: Filter by MIME types.

        Returns:
            List of file metadata dictionaries.
        """
        # Build Drive query
        q_parts = [f"fullText contains '{query}'"]

        if file_types:
            type_conditions = " or ".join(
                f"mimeType='{t}'" for t in file_types
            )
            q_parts.append(f"({type_conditions})")

        q_parts.append("trashed=false")
        drive_query = " and ".join(q_parts)

        files = []
        page_token = None

        while len(files) < max_results:
            response = self.list_files(
                query=drive_query,
                page_size=min(max_results - len(files), 100),
                page_token=page_token,
            )

            files.extend(response.get("files", []))

            page_token = response.get("nextPageToken")
            if not page_token:
                break

        return files[:max_results]

    def get_file_content(self, file_id: str, max_size: int = 10_000_000) -> str | None:
        """Get text content of a file.

        Args:
            file_id: The file ID.
            max_size: Maximum file size in bytes to download.

        Returns:
            Text content or None if not extractable.
        """
        try:
            # Get file metadata first
            file_meta = self.get_file(file_id)
            if not file_meta:
                return None

            mime_type = file_meta.get("mimeType", "")
            size = int(file_meta.get("size", 0))

            # Skip large files
            if size > max_size:
                logger.warning(f"File {file_id} too large ({size} bytes)")
                return None

            # Handle Google Docs types (export)
            if mime_type in EXPORTABLE_MIME_TYPES:
                return self._export_google_doc(file_id, EXPORTABLE_MIME_TYPES[mime_type])

            # Handle regular text files (download)
            if mime_type in READABLE_MIME_TYPES:
                return self._download_file(file_id)

            # Skip binary files
            logger.debug(f"Skipping non-text file {file_id} ({mime_type})")
            return None

        except HttpError as e:
            logger.error(f"Error getting file content {file_id}: {e}")
            return None

    def _export_google_doc(self, file_id: str, export_mime_type: str) -> str | None:
        """Export a Google Docs/Sheets/Slides file to text."""
        try:
            request = self.service.files().export_media(
                fileId=file_id, mimeType=export_mime_type
            )
            content = io.BytesIO()
            downloader = MediaIoBaseDownload(content, request)

            done = False
            while not done:
                _, done = downloader.next_chunk()

            return content.getvalue().decode("utf-8", errors="ignore")
        except HttpError as e:
            logger.error(f"Error exporting file {file_id}: {e}")
            return None

    def _download_file(self, file_id: str) -> str | None:
        """Download a regular file and return content as text."""
        try:
            request = self.service.files().get_media(fileId=file_id)
            content = io.BytesIO()
            downloader = MediaIoBaseDownload(content, request)

            done = False
            while not done:
                _, done = downloader.next_chunk()

            return content.getvalue().decode("utf-8", errors="ignore")
        except HttpError as e:
            logger.error(f"Error downloading file {file_id}: {e}")
            return None

    def list_recent_changes(
        self,
        page_token: str | None = None,
        page_size: int = 100,
    ) -> dict[str, Any]:
        """List recent changes for incremental sync.

        Args:
            page_token: Start page token (use getStartPageToken for initial).
            page_size: Number of changes per page.

        Returns:
            Dictionary with 'changes', 'newStartPageToken', and optional 'nextPageToken'.
        """
        if not page_token:
            # Get initial page token
            response = self.service.changes().getStartPageToken().execute()
            page_token = response.get("startPageToken")

        try:
            return (
                self.service.changes()
                .list(
                    pageToken=page_token,
                    pageSize=page_size,
                    fields="nextPageToken, newStartPageToken, changes(fileId, removed, file(id, name, mimeType, modifiedTime))",
                )
                .execute()
            )
        except HttpError as e:
            logger.error(f"Error listing changes: {e}")
            raise

    def get_start_page_token(self) -> str:
        """Get the starting page token for changes API."""
        response = self.service.changes().getStartPageToken().execute()
        return response.get("startPageToken")

    @staticmethod
    def parse_file(file: dict) -> dict[str, Any]:
        """Parse a Drive file into a structured format.

        Args:
            file: Raw file metadata from Drive API.

        Returns:
            Parsed file metadata.
        """
        result = {
            "id": file["id"],
            "name": file.get("name", "Untitled"),
            "mime_type": file.get("mimeType", ""),
            "size": int(file.get("size", 0)),
            "web_link": file.get("webViewLink", ""),
            "parents": file.get("parents", []),
        }

        # Parse modified time
        if "modifiedTime" in file:
            result["modified_time"] = datetime.fromisoformat(
                file["modifiedTime"].replace("Z", "+00:00")
            )

        # Parse owners
        if "owners" in file:
            result["owners"] = [
                {"email": o.get("emailAddress"), "name": o.get("displayName")}
                for o in file["owners"]
            ]

        return result
