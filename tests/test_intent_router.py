"""Tests for intent classification."""

import pytest

from src.bot.intent_router import Intent, IntentRouter


class TestIntentRouter:
    """Tests for IntentRouter class."""

    @pytest.fixture
    def router(self):
        """Create router without API key (uses keyword fallback)."""
        return IntentRouter(api_key=None)

    def test_classify_calendar(self, router):
        """Test calendar intent classification."""
        intent = router.classify("What's on my calendar today?")

        assert intent.intent in ("calendar_check", "calendar_availability")

    def test_classify_calendar_availability(self, router):
        """Test availability intent classification."""
        intent = router.classify("When am I free tomorrow?")

        assert intent.intent == "calendar_availability"
        assert intent.entities.get("date") == "tomorrow"

    def test_classify_email(self, router):
        """Test email intent classification."""
        intent = router.classify("Search my emails for quarterly report")

        assert intent.intent == "email_search"

    def test_classify_email_draft(self, router):
        """Test email draft intent classification."""
        intent = router.classify("Draft an email to john about the meeting")

        assert intent.intent == "email_draft"

    def test_classify_github_prs(self, router):
        """Test GitHub PR list intent."""
        intent = router.classify("Show me my open PRs")

        assert intent.intent == "github_list_prs"

    def test_classify_github_issue(self, router):
        """Test GitHub create issue intent."""
        intent = router.classify("Create an issue in the repo")

        assert intent.intent == "github_create_issue"

    def test_classify_briefing(self, router):
        """Test briefing intent classification."""
        intent = router.classify("What did I miss yesterday?")

        assert intent.intent == "briefing"

    def test_classify_help(self, router):
        """Test help intent classification."""
        intent = router.classify("help")

        assert intent.intent == "help"

    def test_classify_search_default(self, router):
        """Test that ambiguous queries default to search."""
        intent = router.classify("find information about machine learning")

        assert intent.intent == "search"

    def test_extract_date_today(self, router):
        """Test date extraction for today."""
        intent = router.classify("What's happening today?")

        assert intent.entities.get("date") == "today"

    def test_extract_date_tomorrow(self, router):
        """Test date extraction for tomorrow."""
        intent = router.classify("What's on tomorrow?")

        assert intent.entities.get("date") == "tomorrow"

    def test_intent_confidence(self, router):
        """Test that intents have confidence scores."""
        intent = router.classify("calendar today")

        assert 0 <= intent.confidence <= 1
