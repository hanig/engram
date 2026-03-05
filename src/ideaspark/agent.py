"""IdeaSpark agent — daily AI × cancer research idea generation."""

import json
import logging
from datetime import datetime

import anthropic

from src.config import ANTHROPIC_API_KEY, AGENT_MODEL, get_user_timezone
from src.ideaspark.corpus import PaperCorpus
from src.ideaspark.literature import LiteratureMonitor
from src.ideaspark.memory import IdeaMemory

logger = logging.getLogger(__name__)

# ── Rotating thematic schedule ────────────────────────────────────────

THEMES = [
    {
        "name": "Foundation models + cancer genomics",
        "query": "foundation model DNA RNA cancer genomics tumor mutation codon language model",
        "description": (
            "Genomic and biological foundation models applied to cancer — including but NOT "
            "limited to Hani's own (Evo 2, Mach-1, CodonFM). Actively consider external FMs: "
            "Enformer, Borzoi, Nucleotide Transformer 3, Caduceus, scFoundation, "
            "ESM/ESM2, AlphaFold/AlphaFold3, Boltz-2, RiNALMo. Cross any of these "
            "with cancer biology questions: tumor genomes, codon usage, variant effect "
            "prediction, regulatory grammar, gene expression programs."
        ),
    },
    {
        "name": "AI + liquid biopsy / early detection",
        "query": "liquid biopsy cell-free RNA cfRNA cancer detection early diagnosis multi-analyte foundation model",
        "description": (
            "cfRNA/cfDNA models, oncRNA signatures, multi-analyte integration, early cancer "
            "detection. Consider how any foundation model (Evo 2, Enformer, Borzoi, scFoundation, etc.) "
            "could improve liquid biopsy feature extraction, denoising, or multi-modal integration."
        ),
    },
    {
        "name": "AI + tumor evolution & heterogeneity",
        "query": "tumor evolution clonal dynamics heterogeneity resistance phylogenetic cancer foundation model",
        "description": (
            "Phylogenetic models, clonal dynamics prediction, therapy resistance modeling. "
            "How can FMs (genomic or single-cell) improve evolutionary trajectory prediction, "
            "resistance mechanism discovery, or clonal fitness estimation?"
        ),
    },
    {
        "name": "AI + RNA biology in cancer",
        "query": "RNA structure splicing RBP RNA-binding protein post-transcriptional regulation cancer language model",
        "description": (
            "Structural switches in oncogenes, splicing dysregulation, RBP networks in cancer. "
            "Consider RNA FMs (Mach-1, CodonFM, RiNALMo, SHAPE-FM) alongside protein "
            "language models (ESM/ESM2, Boltz-2) for RNA–protein interaction prediction."
        ),
    },
    {
        "name": "AI + drug response & perturbation",
        "query": "drug response perturbation prediction virtual screening combination therapy cancer foundation model",
        "description": (
            "Virtual screening, perturbation prediction, drug combinations, CRISPR screens. "
            "Consider how cell-level FMs (STATE, Tahoe-x1, scFoundation) or chemical FMs "
            "(MolBERT, ChemBERTa, MolGPT) enable better perturbation modeling or drug response prediction."
        ),
    },
    {
        "name": "AI + single-cell & spatial omics",
        "query": "single-cell spatial transcriptomics cell state deconvolution niche modeling cancer foundation model",
        "description": (
            "Cell state inference, deconvolution, spatial niche modeling in tumors. "
            "Explore how single-cell FMs (STATE, Tahoe-x1, scFoundation) and "
            "spatial methods can be combined for tumor microenvironment understanding."
        ),
    },
    {
        "name": "AI + RNA therapeutics",
        "query": "RNA therapeutics mRNA design delivery optimization generative AI RNA drugs foundation model",
        "description": (
            "Generative design of RNA drugs, target discovery, delivery optimization. "
            "Consider RNA language models (Mach-1, CodonFM, RiNALMo, SHAPE-FM), protein structure "
            "models (AlphaFold/AlphaFold3, Boltz-2), and generative chemistry models for "
            "end-to-end RNA therapeutic design."
        ),
    },
]


def get_todays_theme(idea_count: int) -> dict:
    """Select theme based on rotating weekly schedule."""
    week_index = (idea_count // 7) % len(THEMES)
    return THEMES[week_index]


# ── Idea generation prompt ────────────────────────────────────────────

SYSTEM_PROMPT = """You are IdeaSpark, a research ideation agent for Hani Goodarzi's lab.

Hani is a Core Investigator at Arc Institute, Associate Professor at UCSF (becoming full Professor July 2026), and AI Research Lead at Arc Computational Tech Center. His lab works at the intersection of RNA biology, cancer genomics, AI/ML, single-cell omics, and virtual cell models.

Key active projects: Evo 2 (40B DNA foundation model), Mach-1/1.5 (RNA foundation models), CodonFM (codon-resolution FMs with NVIDIA), Orion (generative AI for oncRNA cancer detection), Exai-1 (multimodal cfRNA foundation model), scBaseCount (AI-curated single-cell repo), STATE (perturbation prediction), Tahoe-100M (largest single-cell drug perturbation atlas), GENEVA (molecular phenotyping), SwitchSeeker (RNA structural switches).

Companies: Exai Bio (liquid biopsy), Tahoe Therapeutics (single-cell drug perturbation), Therna Biosciences (programmable RNA therapeutics).

IMPORTANT — Foundation model scope: When generating ideas involving foundation models, do NOT limit yourself to Hani's own models. The field is broad. Actively consider external FMs and how Hani's expertise could intersect with them:
- DNA/genomic FMs: Evo 2, Enformer, Borzoi, Nucleotide Transformer 3, Caduceus
- Single-cell FMs: STATE, Tahoe-x1, scFoundation
- RNA FMs: Mach-1, CodonFM, RiNALMo, SHAPE-FM (unpublished, Goodarzi lab)
- Protein FMs: Boltz-2, ESM/ESM2 (Meta), AlphaFold/AlphaFold3
- Chemical/drug FMs: MolBERT, ChemBERTa, MolGPT
- Multi-modal: BiomedCLIP, PLIP
The best ideas often come from crossing Hani's unique datasets and biology with external models, or vice versa.

Your job is to generate ONE novel, well-grounded research idea per day at the intersection of AI and cancer biology. Each idea must:
1. Be grounded in Hani's published work (reference specific papers)
2. Connect to recent literature or emerging trends — including external FM releases
3. Be specific enough to act on (not vague hand-waving)
4. Be non-obvious — don't just suggest "apply X to Y"
5. Consider feasibility given the group's resources
6. Vary the external tools/models referenced — don't always default to the same FM

When suggesting collaborators, prioritize researchers at Arc Institute, Stanford, UCSF, and Berkeley."""


def build_generation_prompt(
    theme: dict,
    strategy: str,
    corpus_papers: list[dict],
    new_papers: list[dict],
    memory: IdeaMemory,
    is_stretch: bool = False,
) -> str:
    """Build the user prompt for idea generation."""

    # Format corpus papers
    corpus_section = "\n".join([
        f"- [{p.get('year', '')}] {p.get('title', '')} ({p.get('journal', '')})"
        for p in corpus_papers[:8]
    ])

    # Format new literature
    lit_section = "\n".join([
        f"- [{p.get('source', '')}] {p.get('title', '')} ({p.get('date', '')})"
        + (f"\n  Abstract: {p.get('abstract', '')[:200]}..." if p.get('abstract') else "")
        for p in new_papers[:10]
    ])

    # Preference context
    pref_context = ""
    preferred_themes = memory.get_preferred_themes()
    if preferred_themes:
        pref_context = f"\nHani has shown preference for ideas in: {', '.join(preferred_themes)}."

    # Strategy description
    if strategy == "A":
        strategy_desc = (
            "Strategy A — Cross Hani's published work against the new literature below. "
            "Find gaps his work could fill, extensions enabled by new methods, "
            "contradictions worth resolving, or datasets that unlock new analyses."
        )
    else:
        strategy_desc = (
            "Strategy B — Cross Hani's published work against emerging AI methods, "
            "clinical trial signals, or newly released datasets. Look for new architectures, "
            "training paradigms, biomarker approvals, or data releases that create opportunities."
        )

    stretch_note = ""
    if is_stretch:
        stretch_note = (
            "\n\n⚡ This is a STRETCH idea. Push boundaries — suggest moonshots that may "
            "require new collaborations, data types, or capabilities outside the current group. "
            "Still grounded in Hani's expertise, but ambitious."
        )

    idea_number = memory.get_idea_count() + 1

    prompt = f"""Generate IdeaSpark #{idea_number}.

**Today's Theme:** {theme['name']}
{theme['description']}

**{strategy_desc}**{stretch_note}{pref_context}

---

### Hani's Relevant Papers:
{corpus_section}

### Recent Literature (last 30 days):
{lit_section}

---

Produce a structured brief in EXACTLY this format (no markdown headers, use the exact labels):

🧬 IdeaSpark #{idea_number} — {datetime.now(get_user_timezone()).strftime('%A, %B %d, %Y')}
Theme: {theme['name']}
{"[STRETCH]" if is_stretch else ""}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━

*The Gap*
[2-3 sentences: what's missing, unsolved, or newly possible]

*Hypothesis*
[1-2 sentences: the core claim or bet]

*Proposed Approach*
[3-5 sentences: method sketch — what data, what model, what experiment]

*Why You*
[1-2 sentences: which specific papers/capabilities make Hani uniquely positioned]

*Key Risk*
[1 sentence: the thing most likely to make this fail]

*Relevant Papers*
- [Hani paper 1] — [why relevant]
- [Hani paper 2] — [why relevant]
- [New paper 1] — [what it enables]

*Potential Collaborators*
- [Name, Institution] — [why they're a good fit for this idea]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Scores: Novelty [X/5] · Feasibility [X/5] · Impact [X/5]
Strategy: {"A: your work × new lit" if strategy == "A" else "B: your work × trends"}

Also return a JSON block at the very end (after the brief) with:
```json
{{
  "title": "<short title for the idea>",
  "novelty": <1-5>,
  "feasibility": <1-5>,
  "impact": <1-5>,
  "source_papers": ["<title of Hani paper 1>", "<title of Hani paper 2>"],
  "new_papers": ["<title of new paper 1>"]
}}
```
"""
    return prompt


# ── Main generation pipeline ──────────────────────────────────────────

class IdeaSparkAgent:
    """Orchestrates daily idea generation."""

    def __init__(self):
        self.corpus = PaperCorpus()
        self.literature = LiteratureMonitor()
        self.memory = IdeaMemory()
        self.client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    def _get_literature(self) -> list[dict]:
        """Fetch or load cached recent literature."""
        if self.literature.has_today_cache():
            return self.literature.load_cache()
        papers = self.literature.fetch_all(limit_per_source=50)
        self.literature.cache_papers(papers)
        return papers

    def _filter_literature_by_theme(self, papers: list[dict], theme: dict) -> list[dict]:
        """Score and filter new papers by relevance to theme."""
        theme_keywords = set(theme["query"].lower().split())
        scored = []
        for p in papers:
            text = f"{p.get('title', '')} {p.get('abstract', '')}".lower()
            overlap = sum(1 for kw in theme_keywords if kw in text)
            if overlap >= 2:
                p["theme_relevance"] = overlap
                scored.append(p)
        scored.sort(key=lambda x: x.get("theme_relevance", 0), reverse=True)
        if scored:
            return scored[:10]
        return sorted(papers, key=lambda x: x.get("date", ""), reverse=True)[:10]

    def generate_idea(self, max_retries: int = 3) -> dict | None:
        """Run the full pipeline: theme → papers → literature → LLM → brief.

        Retry strategy on duplicate/low-quality:
          Attempt 1: original theme + preferred strategy
          Attempt 2: same theme, flipped strategy, shuffled corpus
          Attempt 3: rotate to next theme entirely

        Returns dict with keys: brief, title, scores, metadata, or None on failure.
        """
        import random

        idea_count = self.memory.get_idea_count()
        base_theme = get_todays_theme(idea_count)
        base_strategy = self.memory.get_preferred_strategy()
        is_stretch = self.memory.should_be_stretch()
        if is_stretch:
            logger.info("STRETCH idea day")

        new_papers = self._get_literature()

        rejected_titles: list[str] = []
        for attempt in range(1, max_retries + 1):
            # Vary inputs on retry
            if attempt == 1:
                theme = base_theme
                strategy = base_strategy
            elif attempt == 2:
                # Same theme, flip strategy, different corpus sample
                theme = base_theme
                strategy = "B" if base_strategy == "A" else "A"
                logger.info(f"Attempt {attempt}: flipping to strategy {strategy}")
            else:
                # Rotate to next theme as escape hatch
                theme_idx = (THEMES.index(base_theme) + 1) % len(THEMES)
                theme = THEMES[theme_idx]
                strategy = "B" if base_strategy == "A" else "A"
                logger.info(f"Attempt {attempt}: rotating to theme '{theme['name']}'")

            logger.info(f"Theme: {theme['name']}, Strategy: {strategy}")

            # Get corpus papers (shuffle on retry so different papers surface)
            corpus_papers = self.corpus.search(theme["query"], top_k=8)
            if attempt > 1:
                random.shuffle(corpus_papers)
            logger.info(f"Corpus papers: {len(corpus_papers)}")

            # Filter literature for current theme
            relevant_new = self._filter_literature_by_theme(new_papers, theme)
            logger.info(f"New literature: {len(new_papers)}, theme-relevant: {len(relevant_new)}")

            # Build prompt
            prompt = build_generation_prompt(
                theme=theme,
                strategy=strategy,
                corpus_papers=corpus_papers,
                new_papers=relevant_new,
                memory=self.memory,
                is_stretch=is_stretch,
            )

            if rejected_titles:
                prompt += (
                    f"\n\nIMPORTANT: Do NOT propose ideas similar to these (already generated): "
                    f"{', '.join(rejected_titles)}. Find a genuinely different angle, "
                    f"different biological question, different methodology."
                )

            # Call Claude
            try:
                response = self.client.messages.create(
                    model=AGENT_MODEL,
                    max_tokens=2000,
                    system=SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": prompt}],
                )
                full_text = response.content[0].text
            except Exception as e:
                logger.error(f"Claude API call failed: {e}")
                return None

            # Parse response
            brief, metadata = self._parse_response(full_text)
            if not metadata:
                metadata = {
                    "title": f"IdeaSpark #{idea_count + 1}",
                    "novelty": 3, "feasibility": 3, "impact": 3,
                    "source_papers": [], "new_papers": [],
                }

            scores = {
                "novelty": metadata.get("novelty", 3),
                "feasibility": metadata.get("feasibility", 3),
                "impact": metadata.get("impact", 3),
            }

            # Quality gate
            if all(v < 2 for v in scores.values()):
                logger.info(f"Attempt {attempt}: below quality threshold — retrying")
                rejected_titles.append(metadata.get("title", "unknown"))
                continue

            # Deduplication check
            emb = None
            try:
                temp_corpus = PaperCorpus()
                emb = temp_corpus.embed_query(brief[:500])
                if self.memory.is_duplicate(emb.tolist()):
                    logger.info(f"Attempt {attempt}: duplicate detected — retrying")
                    rejected_titles.append(metadata.get("title", "unknown"))
                    continue
            except Exception:
                pass

            # Passed — break out of retry loop
            break
        else:
            logger.warning(f"Failed to generate unique idea after {max_retries} attempts")
            return None

        # Log the idea
        idea_number = idea_count + 1
        self.memory.log_idea(
            idea_number=idea_number,
            theme=theme["name"],
            strategy=strategy,
            title=metadata.get("title", ""),
            brief=brief,
            scores=scores,
            source_papers=metadata.get("source_papers", []),
            new_papers=metadata.get("new_papers", []),
            is_stretch=is_stretch,
            embedding=emb.tolist() if emb is not None else None,
        )

        return {
            "brief": brief,
            "title": metadata.get("title", ""),
            "scores": scores,
            "theme": theme["name"],
            "strategy": strategy,
            "is_stretch": is_stretch,
            "idea_number": idea_number,
            "metadata": metadata,
        }

    def _parse_response(self, text: str) -> tuple[str, dict | None]:
        """Separate the structured brief from the JSON metadata block."""
        # Find JSON block
        metadata = None
        brief = text

        json_start = text.rfind("```json")
        if json_start == -1:
            json_start = text.rfind("```\n{")

        if json_start != -1:
            brief = text[:json_start].strip()
            json_block = text[json_start:]
            # Extract JSON
            json_block = json_block.replace("```json", "").replace("```", "").strip()
            try:
                metadata = json.loads(json_block)
            except json.JSONDecodeError:
                logger.warning("Failed to parse JSON metadata from response")

        return brief, metadata
