"""Feedback loop and preference learning for IdeaSpark."""

import json
import logging
from datetime import datetime
from pathlib import Path

import numpy as np

from src.config import PROJECT_ROOT

logger = logging.getLogger(__name__)

DATA_DIR = PROJECT_ROOT / "data" / "ideaspark"
IDEA_LOG_PATH = DATA_DIR / "idea_log.json"
PREFS_PATH = DATA_DIR / "preferences.json"
EMBEDDINGS_PATH = DATA_DIR / "idea_embeddings.npy"


class IdeaMemory:
    """Tracks pitched ideas, feedback, and learned preferences."""

    def __init__(self):
        self.idea_log: list[dict] = []
        self.preferences: dict = {
            "theme_weights": {},       # theme → cumulative score
            "method_affinities": {},   # method keyword → score
            "biology_affinities": {},  # biology keyword → score
            "strategy_weights": {"A": 0.0, "B": 0.0},
            "total_ideas": 0,
            "total_fire": 0,
            "total_thumbsdown": 0,
        }
        self._embeddings: np.ndarray | None = None  # (N, dim) array, lazy-loaded
        self._load()

    # ── persistence ───────────────────────────────────────────────────

    def _load(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        if IDEA_LOG_PATH.exists():
            with open(IDEA_LOG_PATH) as f:
                self.idea_log = json.load(f)
            # Migrate: strip any leftover embeddings from JSON
            for entry in self.idea_log:
                entry.pop("embedding", None)
        if PREFS_PATH.exists():
            with open(PREFS_PATH) as f:
                self.preferences = json.load(f)
        if EMBEDDINGS_PATH.exists():
            self._embeddings = np.load(EMBEDDINGS_PATH)

    def save(self):
        with open(IDEA_LOG_PATH, "w") as f:
            json.dump(self.idea_log, f, indent=2)
        with open(PREFS_PATH, "w") as f:
            json.dump(self.preferences, f, indent=2)
        if self._embeddings is not None:
            np.save(EMBEDDINGS_PATH, self._embeddings)

    def _append_embedding(self, embedding: list[float] | np.ndarray):
        """Append one embedding vector to the .npy store."""
        vec = np.array(embedding, dtype=np.float32).reshape(1, -1)
        if self._embeddings is None:
            self._embeddings = vec
        else:
            self._embeddings = np.vstack([self._embeddings, vec])

    # ── idea logging ──────────────────────────────────────────────────

    def log_idea(
        self,
        idea_number: int,
        theme: str,
        strategy: str,
        title: str,
        brief: str,
        scores: dict,
        source_papers: list[str],
        new_papers: list[str],
        is_stretch: bool = False,
        slack_ts: str | None = None,
        embedding: list[float] | None = None,
    ):
        """Log a pitched idea."""
        entry = {
            "id": idea_number,
            "date": datetime.now().isoformat(),
            "theme": theme,
            "strategy": strategy,
            "title": title,
            "brief": brief,
            "scores": scores,
            "source_papers": source_papers,
            "new_papers": new_papers,
            "is_stretch": is_stretch,
            "slack_ts": slack_ts,
            "reaction": None,  # filled in by feedback collection
        }
        self.idea_log.append(entry)
        if embedding is not None:
            self._append_embedding(embedding)
        self.preferences["total_ideas"] = len(self.idea_log)
        self.save()
        return entry

    # ── feedback processing ───────────────────────────────────────────

    def record_feedback(self, idea_id: int, reaction: str):
        """Record a feedback reaction for a given idea.

        reaction: "fire" (🔥), "thinking" (🤔), "thumbsdown" (👎), or None

        👎 triggers full deletion — idea is purged from log and embeddings.
        """
        for idx, entry in enumerate(self.idea_log):
            if entry["id"] == idea_id:
                if reaction == "thumbsdown":
                    self._update_preferences(entry, reaction)
                    self._delete_idea(idx)
                    logger.info(f"Idea #{idea_id} thumbed down — deleted from log and embeddings")
                    return True
                entry["reaction"] = reaction
                self._update_preferences(entry, reaction)
                self.save()
                return True
        return False

    def _delete_idea(self, idx: int):
        """Remove idea at index from log and its embedding row, then save."""
        self.idea_log.pop(idx)
        if self._embeddings is not None and idx < len(self._embeddings):
            self._embeddings = np.delete(self._embeddings, idx, axis=0)
            if len(self._embeddings) == 0:
                self._embeddings = None
        self.preferences["total_ideas"] = len(self.idea_log)
        self.save()

    def _update_preferences(self, entry: dict, reaction: str):
        """Update preference weights based on feedback."""
        if reaction == "fire":
            delta = 1.0
            self.preferences["total_fire"] += 1
        elif reaction == "thumbsdown":
            delta = -1.0
            self.preferences["total_thumbsdown"] += 1
        else:  # thinking or None
            delta = 0.0
            return

        # theme weight
        theme = entry.get("theme", "")
        tw = self.preferences["theme_weights"]
        tw[theme] = tw.get(theme, 0.0) + delta

        # strategy weight
        strategy = entry.get("strategy", "")
        if strategy in self.preferences["strategy_weights"]:
            self.preferences["strategy_weights"][strategy] += delta

    # ── deduplication ─────────────────────────────────────────────────

    def is_duplicate(self, embedding: list[float] | np.ndarray, threshold: float = 0.88) -> bool:
        """Check if a proposed idea is too similar to a past one."""
        if self._embeddings is None or len(self._embeddings) == 0:
            return False

        q = np.array(embedding, dtype=np.float32)
        # Vectorised cosine similarity against all past embeddings
        norms = np.linalg.norm(self._embeddings, axis=1) * np.linalg.norm(q) + 1e-9
        sims = self._embeddings @ q / norms
        max_idx = int(np.argmax(sims))
        max_sim = float(sims[max_idx])
        if max_sim > threshold:
            # Find the idea number for logging (index may not align perfectly
            # if some ideas lacked embeddings, but best effort)
            idea_id = self.idea_log[max_idx]["id"] if max_idx < len(self.idea_log) else "?"
            logger.info(f"Duplicate detected: similarity {max_sim:.3f} with idea #{idea_id}")
            return True
        return False

    # ── preference queries ────────────────────────────────────────────

    def get_preferred_themes(self, top_k: int = 3) -> list[str]:
        """Return themes ranked by cumulative feedback score."""
        tw = self.preferences.get("theme_weights", {})
        if not tw:
            return []
        sorted_themes = sorted(tw.items(), key=lambda x: x[1], reverse=True)
        return [t for t, _ in sorted_themes[:top_k]]

    def get_preferred_strategy(self) -> str:
        """Return the strategy with higher cumulative score, or alternate."""
        sw = self.preferences.get("strategy_weights", {})
        if sw.get("A", 0) > sw.get("B", 0):
            return "A"
        elif sw.get("B", 0) > sw.get("A", 0):
            return "B"
        # alternate based on total ideas
        return "A" if self.preferences.get("total_ideas", 0) % 2 == 0 else "B"

    def get_idea_count(self) -> int:
        return len(self.idea_log)

    def should_be_stretch(self) -> bool:
        """~1 in 7 ideas should be a stretch."""
        count = len(self.idea_log)
        return count > 0 and count % 7 == 0

    def generate_meta_summary(self) -> str | None:
        """After 30+ ideas, summarize preference patterns."""
        if len(self.idea_log) < 30:
            return None

        fire_ideas = [e for e in self.idea_log if e.get("reaction") == "fire"]
        down_ideas = [e for e in self.idea_log if e.get("reaction") == "thumbsdown"]

        fire_themes = {}
        for e in fire_ideas:
            t = e.get("theme", "unknown")
            fire_themes[t] = fire_themes.get(t, 0) + 1

        lines = [
            f"## IdeaSpark Meta-Summary (after {len(self.idea_log)} ideas)",
            f"- 🔥 {len(fire_ideas)} | 👎 {len(down_ideas)} | Total {len(self.idea_log)}",
            f"- Hit rate: {len(fire_ideas)/len(self.idea_log)*100:.0f}%",
            "",
            "### Top themes (by 🔥 count):",
        ]
        for theme, count in sorted(fire_themes.items(), key=lambda x: x[1], reverse=True)[:5]:
            lines.append(f"  - {theme}: {count} 🔥")

        return "\n".join(lines)
