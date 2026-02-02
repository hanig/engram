"""GitHub content indexer."""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from ..config import GITHUB_ORG, GITHUB_USERNAME
from ..integrations.github_client import GitHubClient
from ..knowledge_graph import KnowledgeGraph

logger = logging.getLogger(__name__)


class GitHubIndexer:
    """Indexer for GitHub repositories, issues, and PRs."""

    def __init__(self, kg: KnowledgeGraph | None = None):
        """Initialize the GitHub indexer.

        Args:
            kg: Knowledge graph instance. Creates new one if not provided.
        """
        self.kg = kg or KnowledgeGraph()

    def index_all(
        self,
        include_repos: bool = True,
        include_issues: bool = True,
        include_prs: bool = True,
        include_commits: bool = True,
        max_repos: int = 100,
    ) -> dict[str, Any]:
        """Index all GitHub content.

        Args:
            include_repos: Index repository metadata.
            include_issues: Index issues.
            include_prs: Index pull requests.
            include_commits: Index recent commits.
            max_repos: Maximum number of repos to index.

        Returns:
            Statistics about the indexing operation.
        """
        logger.info("Starting full GitHub index")

        client = GitHubClient()
        stats = {
            "repos_indexed": 0,
            "issues_indexed": 0,
            "prs_indexed": 0,
            "commits_indexed": 0,
            "people_extracted": 0,
            "errors": 0,
        }

        try:
            # Index repositories
            if include_repos:
                repos = client.list_repos(include_org=True, max_results=max_repos)
                for repo in repos:
                    self._index_repo(repo, stats)
                logger.info(f"Indexed {stats['repos_indexed']} repositories")

            # Index issues
            if include_issues:
                issues = client.get_my_issues(state="all", max_results=200)
                for issue in issues:
                    self._index_issue(issue, stats)
                logger.info(f"Indexed {stats['issues_indexed']} issues")

            # Index PRs
            if include_prs:
                prs = client.get_my_prs(state="all", max_results=200)
                for pr in prs:
                    self._index_pr(pr, stats)
                logger.info(f"Indexed {stats['prs_indexed']} pull requests")

            # Index recent commits
            if include_commits:
                since = datetime.now(timezone.utc) - timedelta(days=90)
                commits = client.get_recent_commits(max_results=100, since=since)
                for commit in commits:
                    self._index_commit(commit, stats)
                logger.info(f"Indexed {stats['commits_indexed']} commits")

        except Exception as e:
            logger.error(f"Error in GitHub indexing: {e}")
            stats["errors"] += 1

        self.kg.set_last_sync(
            source="github",
            account=GITHUB_USERNAME,
            last_sync=datetime.now(timezone.utc),
            metadata={"type": "full", "stats": stats},
        )

        logger.info(f"GitHub indexing complete: {stats}")
        return stats

    def index_delta(self, days_back: int = 7) -> dict[str, Any]:
        """Index recent GitHub activity.

        Args:
            days_back: Number of days to look back.

        Returns:
            Statistics about the indexing operation.
        """
        logger.info(f"Starting delta GitHub sync (last {days_back} days)")

        client = GitHubClient()
        stats = {
            "issues_updated": 0,
            "prs_updated": 0,
            "commits_indexed": 0,
            "errors": 0,
        }

        since = datetime.now(timezone.utc) - timedelta(days=days_back)

        try:
            # Update open issues
            issues = client.get_my_issues(state="open", max_results=100)
            for issue in issues:
                if issue.get("updated_at") and issue["updated_at"] > since:
                    self._index_issue(issue, stats)
                    stats["issues_updated"] += 1

            # Update open PRs
            prs = client.get_my_prs(state="open", max_results=100)
            for pr in prs:
                if pr.get("updated_at") and pr["updated_at"] > since:
                    self._index_pr(pr, stats)
                    stats["prs_updated"] += 1

            # Index new commits
            commits = client.get_recent_commits(max_results=50, since=since)
            for commit in commits:
                self._index_commit(commit, stats)
                stats["commits_indexed"] += 1

        except Exception as e:
            logger.error(f"Error in GitHub delta sync: {e}")
            stats["errors"] += 1

        self.kg.set_last_sync(
            source="github",
            account=GITHUB_USERNAME,
            last_sync=datetime.now(timezone.utc),
            metadata={"type": "delta", "stats": stats},
        )

        logger.info(f"GitHub delta sync complete: {stats}")
        return stats

    def _index_repo(self, repo: dict, stats: dict[str, int]) -> None:
        """Index a repository."""
        content_id = f"github:repo:{repo['full_name']}"

        self.kg.upsert_content(
            content_id=content_id,
            content_type="repository",
            source="github",
            source_account=GITHUB_USERNAME,
            title=repo["full_name"],
            body=repo.get("description") or "",
            source_id=str(repo["id"]),
            url=repo["url"],
            timestamp=repo.get("updated_at"),
            metadata={
                "language": repo.get("language"),
                "stars": repo.get("stars"),
                "forks": repo.get("forks"),
                "open_issues": repo.get("open_issues"),
                "private": repo.get("private"),
            },
        )

        stats["repos_indexed"] += 1

    def _index_issue(self, issue: dict, stats: dict[str, int]) -> None:
        """Index an issue and extract people."""
        repo = issue.get("repo") or "unknown"
        content_id = f"github:issue:{repo}:{issue['number']}"

        # Extract assignees as people
        for assignee in issue.get("assignees", []):
            self._extract_github_user(assignee, stats)
            self.kg.add_relationship(
                from_id=content_id,
                from_type="issue",
                to_id=f"person:github:{assignee}",
                to_type="person",
                relation="assignee",
            )

        # Extract creator
        if issue.get("user"):
            self._extract_github_user(issue["user"], stats)
            self.kg.add_relationship(
                from_id=content_id,
                from_type="issue",
                to_id=f"person:github:{issue['user']}",
                to_type="person",
                relation="author",
            )

        # Build body
        body_parts = [issue.get("body", "")]
        if issue.get("labels"):
            body_parts.append(f"Labels: {', '.join(issue['labels'])}")

        self.kg.upsert_content(
            content_id=content_id,
            content_type="issue",
            source="github",
            source_account=GITHUB_USERNAME,
            title=f"[{repo}] #{issue['number']}: {issue['title']}",
            body="\n".join(body_parts),
            source_id=str(issue["id"]),
            url=issue["url"],
            timestamp=issue.get("created_at"),
            metadata={
                "repo": repo,
                "number": issue["number"],
                "state": issue["state"],
                "labels": issue.get("labels", []),
                "comments": issue.get("comments", 0),
            },
        )

        stats["issues_indexed"] += 1

    def _index_pr(self, pr: dict, stats: dict[str, int]) -> None:
        """Index a pull request."""
        repo = pr.get("repo") or "unknown"
        content_id = f"github:pr:{repo}:{pr['number']}"

        # Extract creator
        if pr.get("user"):
            self._extract_github_user(pr["user"], stats)
            self.kg.add_relationship(
                from_id=content_id,
                from_type="pr",
                to_id=f"person:github:{pr['user']}",
                to_type="person",
                relation="author",
            )

        self.kg.upsert_content(
            content_id=content_id,
            content_type="pull_request",
            source="github",
            source_account=GITHUB_USERNAME,
            title=f"[{repo}] PR #{pr['number']}: {pr['title']}",
            body=pr.get("body", ""),
            source_id=str(pr["id"]),
            url=pr["url"],
            timestamp=pr.get("created_at"),
            metadata={
                "repo": repo,
                "number": pr["number"],
                "state": pr["state"],
            },
        )

        stats["prs_indexed"] += 1

    def _index_commit(self, commit: dict, stats: dict[str, int]) -> None:
        """Index a commit."""
        repo = commit.get("repo") or "unknown"
        content_id = f"github:commit:{repo}:{commit['sha']}"

        self.kg.upsert_content(
            content_id=content_id,
            content_type="commit",
            source="github",
            source_account=GITHUB_USERNAME,
            title=f"[{repo}] {commit['sha']}: {commit['message'][:100]}",
            body=commit["message"],
            source_id=commit["sha"],
            url=commit["url"],
            timestamp=commit.get("date"),
            metadata={
                "repo": repo,
                "sha": commit["sha"],
            },
        )

        stats["commits_indexed"] += 1

    def _extract_github_user(self, username: str, stats: dict[str, int]) -> None:
        """Extract and index a GitHub user as a person entity."""
        person_id = f"person:github:{username}"

        is_new = self.kg.upsert_entity(
            entity_id=person_id,
            entity_type="person",
            name=username,
            source="github",
            source_account=GITHUB_USERNAME,
            metadata={"github_username": username},
        )

        if is_new:
            stats["people_extracted"] += 1
