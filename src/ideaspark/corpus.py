"""Paper corpus management — indexing, embedding, and retrieval of Hani's publications."""

import json
import logging
from pathlib import Path

import numpy as np
from openai import OpenAI

from src.config import OPENAI_API_KEY, EMBEDDING_MODEL, PROJECT_ROOT

logger = logging.getLogger(__name__)

DATA_DIR = PROJECT_ROOT / "data" / "ideaspark"
CORPUS_PATH = DATA_DIR / "papers_corpus.json"


# ── Method + biology tags for categorisation ──────────────────────────

METHOD_TAGS = [
    "foundation model", "deep learning", "single-cell", "CRISPR screen",
    "liquid biopsy", "RNA structure", "splicing", "perturbation modeling",
    "generative model", "NLP/LLM", "computer vision", "graph neural network",
    "sequence model", "codon optimization", "flow cytometry", "mass spec",
    "spatial transcriptomics", "drug screening", "phylogenetics",
]

BIOLOGY_TAGS = [
    "RNA regulation", "cancer detection", "drug response", "metastasis",
    "tRNA biology", "codon usage", "breast cancer", "prostate cancer",
    "tumor evolution", "RNA therapeutics", "cell-free RNA", "oncRNA",
    "RBP networks", "splicing dysregulation", "RNA structure switches",
    "single-cell atlas", "perturbation biology", "translation regulation",
]


class PaperCorpus:
    """Manages Hani's publication corpus with embeddings for semantic retrieval."""

    def __init__(self):
        self.papers: list[dict] = []
        self.embeddings: np.ndarray | None = None
        self._oai = None
        if OPENAI_API_KEY:
            try:
                self._oai = OpenAI(api_key=OPENAI_API_KEY)
            except Exception as e:
                logger.warning(f"Could not init OpenAI client: {e}")
        self._load()

    # ── persistence ───────────────────────────────────────────────────

    def _load(self):
        if CORPUS_PATH.exists():
            with open(CORPUS_PATH) as f:
                self.papers = json.load(f)
            emb_path = DATA_DIR / "paper_embeddings.npy"
            if emb_path.exists():
                self.embeddings = np.load(emb_path)
            logger.info(f"Loaded corpus: {len(self.papers)} papers")

    def save(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(CORPUS_PATH, "w") as f:
            json.dump(self.papers, f, indent=2)
        if self.embeddings is not None:
            np.save(DATA_DIR / "paper_embeddings.npy", self.embeddings)
        logger.info(f"Saved corpus: {len(self.papers)} papers")

    # ── corpus building ───────────────────────────────────────────────

    def add_paper(self, paper: dict):
        """Add a paper dict with keys: title, abstract, authors, year, journal, doi, citations."""
        self.papers.append(paper)

    def build_from_list(self, papers: list[dict]):
        """Bulk-load a list of paper dicts."""
        self.papers = papers
        logger.info(f"Loaded {len(papers)} papers into corpus")

    # ── embedding ─────────────────────────────────────────────────────

    def _text_for_paper(self, p: dict) -> str:
        title = p.get("title", "")
        abstract = p.get("abstract", "")
        return f"{title}\n{abstract}".strip()

    def embed_all(self):
        """Compute embeddings for all papers using OpenAI text-embedding-3-large."""
        if not self._oai:
            raise RuntimeError("OPENAI_API_KEY not set — cannot embed")

        texts = [self._text_for_paper(p) for p in self.papers]
        # batch in chunks of 50
        all_embs = []
        for i in range(0, len(texts), 50):
            batch = texts[i : i + 50]
            resp = self._oai.embeddings.create(model=EMBEDDING_MODEL, input=batch)
            all_embs.extend([d.embedding for d in resp.data])
        self.embeddings = np.array(all_embs, dtype=np.float32)
        logger.info(f"Embedded {len(self.papers)} papers → shape {self.embeddings.shape}")

    def embed_query(self, query: str) -> np.ndarray:
        """Embed a single query string."""
        if not self._oai:
            raise RuntimeError("OPENAI_API_KEY not set")
        resp = self._oai.embeddings.create(model=EMBEDDING_MODEL, input=[query])
        return np.array(resp.data[0].embedding, dtype=np.float32)

    # ── retrieval ─────────────────────────────────────────────────────

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        """Semantic search over corpus. Returns top-k papers with scores."""
        if self.embeddings is None or len(self.embeddings) == 0:
            logger.warning("No embeddings — returning random sample")
            import random
            return random.sample(self.papers, min(top_k, len(self.papers)))

        q_emb = self.embed_query(query)
        # cosine similarity
        norms = np.linalg.norm(self.embeddings, axis=1) * np.linalg.norm(q_emb)
        sims = (self.embeddings @ q_emb) / np.where(norms > 0, norms, 1.0)

        idxs = np.argsort(sims)[::-1][:top_k]
        results = []
        for idx in idxs:
            paper = self.papers[idx].copy()
            paper["relevance_score"] = float(sims[idx])
            results.append(paper)
        return results

    def search_by_tags(self, method_tags: list[str] = None, biology_tags: list[str] = None, top_k: int = 5) -> list[dict]:
        """Filter papers by method and/or biology tags."""
        results = []
        for p in self.papers:
            p_methods = set(p.get("method_tags", []))
            p_biology = set(p.get("biology_tags", []))
            score = 0
            if method_tags:
                score += len(p_methods & set(method_tags))
            if biology_tags:
                score += len(p_biology & set(biology_tags))
            if score > 0:
                paper = p.copy()
                paper["tag_match_score"] = score
                results.append(paper)
        results.sort(key=lambda x: x["tag_match_score"], reverse=True)
        return results[:top_k]

    # ── stats ─────────────────────────────────────────────────────────

    @property
    def size(self) -> int:
        return len(self.papers)

    def summary(self) -> str:
        if not self.papers:
            return "Empty corpus"
        years = [p.get("year", 0) for p in self.papers]
        return (
            f"{len(self.papers)} papers, "
            f"{min(years)}–{max(years)}, "
            f"embeddings={'yes' if self.embeddings is not None else 'no'}"
        )
