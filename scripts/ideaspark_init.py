#!/usr/bin/env python3
"""IdeaSpark initialization — build paper corpus from Google Scholar or manual input."""

import argparse
import json
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import PROJECT_ROOT
from src.ideaspark.corpus import PaperCorpus, METHOD_TAGS, BIOLOGY_TAGS

logger = logging.getLogger(__name__)

DATA_DIR = PROJECT_ROOT / "data" / "ideaspark"

# ── Hani Goodarzi's publication corpus (extracted from CV) ────────────
# This is the seed corpus. Can be augmented by Scholar scraping.

SEED_PAPERS = [
    {
        "title": "Systematic discovery of cap-independent translation sequences in human and viral genomes",
        "authors": "Weingarten-Gabbay S, Elber S, ..., Goodarzi H, Segal E",
        "year": 2016,
        "journal": "Science",
        "abstract": "Systematic identification of IRES elements using massively parallel reporter assays.",
        "method_tags": ["deep learning", "sequence model"],
        "biology_tags": ["RNA regulation", "translation regulation"],
    },
    {
        "title": "Metastasis-suppressor transcript destabilization through TARBP2 binding of mRNA hairpins",
        "authors": "Goodarzi H, et al.",
        "year": 2014,
        "journal": "Nature",
        "abstract": "TARBP2 binds structured RNA elements in metastasis-suppressor transcripts to promote their degradation.",
        "method_tags": ["RNA structure"],
        "biology_tags": ["RNA regulation", "metastasis", "RNA structure switches"],
    },
    {
        "title": "Endogenous tRNA-Derived Fragments Suppress Breast Cancer Progression via YBX1 Displacement",
        "authors": "Goodarzi H, et al.",
        "year": 2015,
        "journal": "Cell",
        "abstract": "tRNA-derived fragments suppress breast cancer metastasis by displacing YBX1 from oncogenic transcripts.",
        "method_tags": ["CRISPR screen"],
        "biology_tags": ["tRNA biology", "breast cancer", "metastasis", "RNA regulation"],
    },
    {
        "title": "Modulated Expression of Specific tRNAs Drives Gene Expression and Cancer Progression",
        "authors": "Goodarzi H, et al.",
        "year": 2016,
        "journal": "Cell",
        "abstract": "Cancer cells modulate specific tRNA levels to drive codon-biased translation of pro-metastatic transcripts.",
        "method_tags": ["codon optimization"],
        "biology_tags": ["tRNA biology", "codon usage", "breast cancer", "metastasis", "translation regulation"],
    },
    {
        "title": "HNRNPA2B1 Is a Mediator of m6A-Dependent Nuclear RNA Processing Events",
        "authors": "Alarcón CR, Goodarzi H, et al.",
        "year": 2015,
        "journal": "Cell",
        "abstract": "HNRNPA2B1 reads m6A marks to mediate alternative splicing and microRNA processing.",
        "method_tags": ["RNA structure"],
        "biology_tags": ["RNA regulation", "splicing dysregulation", "RBP networks"],
    },
    {
        "title": "Revealing post-transcriptional regulatory elements through network-level conservation",
        "authors": "Goodarzi H, Najafabadi HS, Oikonomou P, et al.",
        "year": 2012,
        "journal": "PLOS Computational Biology",
        "abstract": "Computational framework for discovering post-transcriptional regulatory elements via network conservation.",
        "method_tags": ["graph neural network", "sequence model"],
        "biology_tags": ["RNA regulation", "RBP networks"],
    },
    {
        "title": "Orphan non-coding RNA GIANA promotes breast cancer metastasis through a novel RNA structural interaction",
        "authors": "Fish L, ..., Goodarzi H",
        "year": 2018,
        "journal": "Nature Medicine",
        "abstract": "Discovery of a novel orphan ncRNA that drives metastasis through RNA structural interactions.",
        "method_tags": ["RNA structure"],
        "biology_tags": ["RNA regulation", "metastasis", "breast cancer", "RNA structure switches", "oncRNA"],
    },
    {
        "title": "A quantitative proteomics tool to identify DNA-protein interactions in primary cells or blood",
        "authors": "Goodarzi H, et al.",
        "year": 2016,
        "journal": "Journal of Proteome Research",
        "abstract": "Quantitative proteomics method for identifying DNA-protein interactions from primary cells.",
        "method_tags": ["mass spec"],
        "biology_tags": ["RNA regulation"],
    },
    {
        "title": "TARBP2 as an RNA-binding protein mediating post-transcriptional gene regulation in cancer",
        "authors": "Fish L, ..., Goodarzi H",
        "year": 2019,
        "journal": "Molecular Cell",
        "abstract": "TARBP2 regulates cancer-relevant transcripts via structured RNA elements in 3'UTRs.",
        "method_tags": ["RNA structure", "CRISPR screen"],
        "biology_tags": ["RNA regulation", "breast cancer", "RBP networks", "RNA structure switches"],
    },
    {
        "title": "Compressed sensing of the human genome for RNA-based cancer detection",
        "authors": "Fish L, ..., Goodarzi H",
        "year": 2021,
        "journal": "Science (submitted/published)",
        "abstract": "Using RNA structural switches as compressed sensors of the cancer genome for liquid biopsy.",
        "method_tags": ["foundation model", "deep learning", "liquid biopsy"],
        "biology_tags": ["cancer detection", "RNA structure switches", "cell-free RNA", "oncRNA"],
    },
    {
        "title": "RBMS1 suppresses colon cancer metastasis through targeted stabilization of its mRNA regulon",
        "authors": "Zhang B, ..., Goodarzi H",
        "year": 2020,
        "journal": "Cancer Discovery",
        "abstract": "RBMS1 stabilizes a metastasis-suppressive mRNA regulon in colon cancer.",
        "method_tags": ["CRISPR screen"],
        "biology_tags": ["RNA regulation", "metastasis", "RBP networks"],
    },
    {
        "title": "Sense-antisense lncRNA pair encoded by human cancer genome",
        "authors": "Nojima T, ..., Goodarzi H",
        "year": 2021,
        "journal": "Nature Cancer",
        "abstract": "Characterization of sense-antisense lncRNA pairs in human cancers.",
        "method_tags": ["RNA structure"],
        "biology_tags": ["RNA regulation", "oncRNA"],
    },
    {
        "title": "Codon-dependent translational rewiring in cancer",
        "authors": "Lorent J, ..., Goodarzi H",
        "year": 2022,
        "journal": "Nature Cancer",
        "abstract": "Cancer cells exploit codon-dependent translation to drive malignant phenotypes.",
        "method_tags": ["codon optimization", "deep learning"],
        "biology_tags": ["codon usage", "translation regulation"],
    },
    {
        "title": "Codon usage and mRNA stability in cancer",
        "authors": "Wu Q, ..., Goodarzi H",
        "year": 2022,
        "journal": "Nature Cell Biology",
        "abstract": "Codon optimality controls mRNA stability in a cancer-specific manner.",
        "method_tags": ["codon optimization", "sequence model"],
        "biology_tags": ["codon usage", "RNA regulation", "translation regulation"],
    },
    {
        "title": "Evo: DNA foundation model spanning all domains of life",
        "authors": "Nguyen E, ..., Goodarzi H, et al.",
        "year": 2024,
        "journal": "Science",
        "abstract": "Evo is a 7B-parameter DNA foundation model trained on 300B tokens spanning all domains of life, enabling prediction and generation at molecular to genome scale.",
        "method_tags": ["foundation model", "deep learning", "generative model", "sequence model"],
        "biology_tags": ["RNA regulation", "codon usage"],
    },
    {
        "title": "Evo 2: genome modeling at 131k context",
        "authors": "ArcInstitute team, Goodarzi H, et al.",
        "year": 2025,
        "journal": "Preprint/Science",
        "abstract": "Evo 2 is a 40B-parameter DNA foundation model with 131k context, enabling long-range genomic understanding.",
        "method_tags": ["foundation model", "deep learning", "generative model", "sequence model"],
        "biology_tags": ["RNA regulation", "codon usage"],
    },
    {
        "title": "Exai-1: multimodal cell-free RNA foundation model for liquid biopsy",
        "authors": "Goodarzi H, et al.",
        "year": 2024,
        "journal": "Nature Medicine",
        "abstract": "Multimodal cfRNA foundation model for cancer detection from liquid biopsy.",
        "method_tags": ["foundation model", "deep learning", "liquid biopsy"],
        "biology_tags": ["cancer detection", "cell-free RNA", "oncRNA"],
    },
    {
        "title": "GENEVA: scalable molecular phenotyping of tumor models",
        "authors": "Goodarzi H, et al.",
        "year": 2024,
        "journal": "Published",
        "abstract": "Scalable molecular phenotyping platform for characterizing tumor model fidelity.",
        "method_tags": ["flow cytometry", "drug screening"],
        "biology_tags": ["drug response", "perturbation biology"],
    },
    {
        "title": "SwitchSeeker: RNA structural switch discovery",
        "authors": "Goodarzi H, et al.",
        "year": 2024,
        "journal": "Published",
        "abstract": "Computational framework for discovering RNA structural switches genome-wide.",
        "method_tags": ["RNA structure", "deep learning", "sequence model"],
        "biology_tags": ["RNA regulation", "RNA structure switches"],
    },
    {
        "title": "Artificial intelligence in drug discovery and development",
        "authors": "Goodarzi H, et al.",
        "year": 2020,
        "journal": "Frontiers in Artificial Intelligence",
        "abstract": "Review of AI methods for drug discovery and development.",
        "method_tags": ["deep learning", "NLP/LLM"],
        "biology_tags": ["drug response"],
    },
    {
        "title": "Androgen signaling regulates SARS-CoV-2 entry in human airway cells",
        "authors": "..., Goodarzi H",
        "year": 2020,
        "journal": "Cell Stem Cell",
        "abstract": "Androgen receptor signaling modulates ACE2 and TMPRSS2 expression affecting COVID-19 susceptibility.",
        "method_tags": ["single-cell"],
        "biology_tags": ["RNA regulation"],
    },
    # ── Additional publications from CV ──────────────────────────────────
    {
        "title": "Systematic discovery of structural elements governing stability of mammalian messenger RNAs",
        "authors": "Goodarzi H, Najafabadi HS, Oikonomou P, et al.",
        "year": 2012,
        "journal": "Nature",
        "abstract": "Systematic discovery of cis-regulatory structural elements in 3'UTRs that control mRNA stability in mammalian cells.",
        "method_tags": ["sequence model", "RNA structure"],
        "biology_tags": ["RNA regulation", "RNA structure switches"],
    },
    {
        "title": "Asparagine bioavailability governs metastasis in a model of breast cancer",
        "authors": "Knott SRV, ..., Goodarzi H, Poulogiannis G, Hannon GJ",
        "year": 2018,
        "journal": "Nature",
        "abstract": "Asparagine availability promotes breast cancer metastasis; dietary restriction or asparaginase reduce metastatic potential.",
        "method_tags": ["CRISPR screen"],
        "biology_tags": ["metastasis", "breast cancer", "drug response"],
    },
    {
        "title": "Tumoural activation of TLR3-SLIT2 axis in endothelium drives metastasis",
        "authors": "Tavora B, ..., Goodarzi H, Tavazoie SF",
        "year": 2020,
        "journal": "Nature",
        "abstract": "Tumor-derived signals activate endothelial TLR3-SLIT2 axis to promote metastatic dissemination.",
        "method_tags": [],
        "biology_tags": ["metastasis", "tumor microenvironment"],
    },
    {
        "title": "N6-methyladenosine marks primary miRNAs for processing",
        "authors": "Alarcon C, Lee H, Goodarzi H, Tavazoie SF",
        "year": 2015,
        "journal": "Nature",
        "abstract": "m6A modification of primary miRNAs facilitates their recognition and processing by DGCR8.",
        "method_tags": ["RNA structure"],
        "biology_tags": ["RNA regulation", "RBP networks"],
    },
    {
        "title": "A pro-metastatic splicing program regulated by SNRPA1 interactions with structured RNA elements",
        "authors": "Fish L, Khoroshkin M, Navickas A, ..., Goodarzi H",
        "year": 2021,
        "journal": "Science",
        "abstract": "SNRPA1 drives a pro-metastatic alternative splicing program through recognition of RNA structural elements.",
        "method_tags": ["RNA structure", "CRISPR screen"],
        "biology_tags": ["splicing dysregulation", "metastasis", "RNA structure switches", "RBP networks"],
    },
    {
        "title": "ERα is an RNA-binding protein sustaining tumor cell survival and drug resistance",
        "authors": "Xu Y, ..., Goodarzi H, Ruggero D",
        "year": 2021,
        "journal": "Cell",
        "abstract": "ERα functions as an RNA-binding protein to stabilize transcripts that sustain tumor cell survival and drug resistance.",
        "method_tags": [],
        "biology_tags": ["RNA regulation", "drug response", "RBP networks", "breast cancer"],
    },
    {
        "title": "Genomic Hallmarks and Structural Variation in Metastatic Prostate Cancer",
        "authors": "Quigley DA, ..., Goodarzi H, Gilbert LA, ..., Feng FY",
        "year": 2018,
        "journal": "Cell",
        "abstract": "Comprehensive genomic characterization of metastatic castration-resistant prostate cancer, revealing structural variants and non-coding alterations.",
        "method_tags": ["deep learning"],
        "biology_tags": ["prostate cancer", "tumor evolution"],
    },
    {
        "title": "Functional Genomics In Vivo Reveal Metabolic Dependencies of Pancreatic Cancer Cells",
        "authors": "Zhu XG, ..., Goodarzi H, Birsoy K",
        "year": 2020,
        "journal": "Cell Metabolism",
        "abstract": "In vivo functional genomics screen reveals metabolic dependencies specific to pancreatic cancer.",
        "method_tags": ["CRISPR screen"],
        "biology_tags": ["drug response", "perturbation biology"],
    },
    {
        "title": "An mRNA processing pathway suppresses metastasis by governing translational control from the nucleus",
        "authors": "Navickas A, Asgharian H, ..., Goodarzi H",
        "year": 2021,
        "journal": "Nature Cell Biology",
        "abstract": "Nuclear mRNA processing pathway controls translation of metastasis-related transcripts.",
        "method_tags": ["CRISPR screen"],
        "biology_tags": ["RNA regulation", "metastasis", "translation regulation", "splicing dysregulation"],
    },
    {
        "title": "The LC3-conjugation machinery specifies the loading of RNA-binding proteins into extracellular vesicles",
        "authors": "Leidal AM, ..., Goodarzi H, ..., Debnath J",
        "year": 2020,
        "journal": "Nature Cell Biology",
        "abstract": "LC3-conjugation machinery directs specific RNA-binding proteins and their RNA targets into extracellular vesicles.",
        "method_tags": [],
        "biology_tags": ["RNA regulation", "RBP networks", "cell-free RNA"],
    },
    {
        "title": "Mechanosensitive pannexin-1 channels mediate microvascular metastatic cell survival",
        "authors": "Furlow PW, ..., Goodarzi H, ..., Tavazoie SF",
        "year": 2015,
        "journal": "Nature Cell Biology",
        "abstract": "Pannexin-1 channels enable metastatic cells to survive in the vasculature through mechanosensitive signaling.",
        "method_tags": [],
        "biology_tags": ["metastasis"],
    },
    {
        "title": "A stress-induced tyrosine-tRNA depletion response mediates codon-based translational repression and growth suppression",
        "authors": "Huh D, ..., Goodarzi H, Tavazoie SF",
        "year": 2020,
        "journal": "EMBO Journal",
        "abstract": "Stress-induced depletion of tyrosine-tRNA drives codon-dependent translational repression of growth-promoting genes.",
        "method_tags": ["codon optimization"],
        "biology_tags": ["tRNA biology", "codon usage", "translation regulation"],
    },
    {
        "title": "FTO controls reversible m6Am RNA methylation during snRNA biogenesis",
        "authors": "Mauer J, ..., Goodarzi H, Jaffrey S",
        "year": 2019,
        "journal": "Nature Chemical Biology",
        "abstract": "FTO demethylates m6Am on snRNAs, revealing a reversible epitranscriptomic modification.",
        "method_tags": [],
        "biology_tags": ["RNA regulation"],
    },
    {
        "title": "Inference of RNA decay rate from transcriptional profiling highlights the regulatory programs of Alzheimer's disease",
        "authors": "Alkallas R, Fish L, Goodarzi H, Najafabadi HS",
        "year": 2017,
        "journal": "Nature Communications",
        "abstract": "Computational inference of RNA decay rates from transcriptional profiling reveals disease-associated regulatory programs.",
        "method_tags": ["sequence model"],
        "biology_tags": ["RNA regulation"],
    },
    {
        "title": "Highly variable cancer subpopulations that exhibit enhanced transcriptome variability and metastatic fitness",
        "authors": "Nguyen A, Yoshida M, Goodarzi H, Tavazoie SF",
        "year": 2016,
        "journal": "Nature Communications",
        "abstract": "Cancer subpopulations with high transcriptome variability exhibit enhanced metastatic fitness.",
        "method_tags": ["single-cell"],
        "biology_tags": ["tumor evolution", "metastasis"],
    },
    {
        "title": "Muscleblind-like 1 suppresses breast cancer metastatic colonization and stabilizes metastasis suppressor transcripts",
        "authors": "Fish L, Pencheva N, Goodarzi H, et al.",
        "year": 2016,
        "journal": "Genes & Development",
        "abstract": "MBNL1 suppresses metastatic colonization by stabilizing transcripts of metastasis suppressor genes.",
        "method_tags": [],
        "biology_tags": ["RNA regulation", "metastasis", "breast cancer", "RBP networks"],
    },
    {
        "title": "TMEM2 Is a SOX4-Regulated Gene That Mediates Metastatic Migration and Invasion in Breast Cancer",
        "authors": "Lee H, Goodarzi H, Tavazoie SF, Alarcon CR",
        "year": 2016,
        "journal": "Cancer Research",
        "abstract": "TMEM2 promotes breast cancer metastasis downstream of SOX4 transcriptional regulation.",
        "method_tags": [],
        "biology_tags": ["metastasis", "breast cancer"],
    },
    {
        "title": "PAPERCLIP Identifies MicroRNA Targets and a Role of CstF64/64tau in Promoting Non-canonical poly(A) Site Usage",
        "authors": "Hwang HW, ..., Goodarzi H, ..., Darnell RB",
        "year": 2016,
        "journal": "Cell Reports",
        "abstract": "PAPERCLIP method for mapping protein-RNA interactions reveals miRNA target sites and polyadenylation regulation.",
        "method_tags": [],
        "biology_tags": ["RNA regulation", "RBP networks"],
    },
    {
        "title": "Systematic Identification of Regulatory Elements in Conserved 3'UTRs of Human Transcripts",
        "authors": "Oikonomou P, Goodarzi H, Tavazoie S",
        "year": 2014,
        "journal": "Cell Reports",
        "abstract": "Systematic computational and experimental identification of conserved regulatory elements in human 3'UTRs.",
        "method_tags": ["sequence model"],
        "biology_tags": ["RNA regulation"],
    },
    {
        "title": "A massively parallel 3'UTR reporter assay reveals relationships between nucleotide content, sequence conservation, and mRNA destabilization",
        "authors": "Litterman J, ..., Goodarzi H, Erle DJ, Ansel KM",
        "year": 2019,
        "journal": "Genome Research",
        "abstract": "Massively parallel reporter assay systematically maps 3'UTR elements that control mRNA stability.",
        "method_tags": ["deep learning"],
        "biology_tags": ["RNA regulation"],
    },
    {
        "title": "A global cancer data integrator reveals principles of synthetic lethality, sex disparity and immunotherapy",
        "authors": "Yogodzinski C, Arab A, Pritchard JR, Goodarzi H, Gilbert LA",
        "year": 2021,
        "journal": "Genome Medicine",
        "abstract": "Integrated cancer data platform reveals synthetic lethal interactions, sex-based disparities, and immunotherapy response patterns.",
        "method_tags": ["deep learning"],
        "biology_tags": ["drug response", "perturbation biology"],
    },
    {
        "title": "The molecular consequences of androgen activity in the human breast",
        "authors": "Raths F, Karimzadeh M, ..., Goodarzi H, ..., Knott SRV",
        "year": 2022,
        "journal": "Cell Genomics",
        "abstract": "Characterization of androgen receptor signaling consequences in human breast tissue.",
        "method_tags": ["single-cell"],
        "biology_tags": ["breast cancer", "RNA regulation"],
    },
    {
        "title": "Revealing Global Regulatory Perturbations across Human Cancers",
        "authors": "Goodarzi H, Elemento O, Tavazoie S",
        "year": 2009,
        "journal": "Molecular Cell",
        "abstract": "Computational framework revealing global regulatory perturbations in post-transcriptional programs across cancer types.",
        "method_tags": ["sequence model", "graph neural network"],
        "biology_tags": ["RNA regulation", "RBP networks"],
    },
    {
        "title": "Global discovery of adaptive mutations",
        "authors": "Goodarzi H, Hottes AK, Tavazoie S",
        "year": 2009,
        "journal": "Nature Methods",
        "abstract": "Computational method for systematically discovering adaptive mutations from evolution experiments.",
        "method_tags": ["deep learning"],
        "biology_tags": [],
    },
    {
        "title": "MicroRNA-203 predicts human survival after resection of colorectal liver metastasis",
        "authors": "Kingham PT, ..., Goodarzi H, Tavazoie SF",
        "year": 2016,
        "journal": "Oncotarget",
        "abstract": "miR-203 expression predicts survival outcomes following colorectal cancer liver metastasis resection.",
        "method_tags": [],
        "biology_tags": ["metastasis", "cancer detection"],
    },
    {
        "title": "Massively multiplex single-molecule oligonucleosome footprinting",
        "authors": "Abdulhay NJ, ..., Goodarzi H, Narlikar GJ, Ramani V",
        "year": 2020,
        "journal": "eLife",
        "abstract": "Single-molecule method for massively parallel chromatin accessibility profiling at nucleosome resolution.",
        "method_tags": ["single-cell"],
        "biology_tags": [],
    },
]


def build_corpus_from_seed():
    """Initialize corpus from the hardcoded seed papers."""
    corpus = PaperCorpus()
    corpus.build_from_list(SEED_PAPERS)
    print(f"Built corpus with {corpus.size} papers")

    # Embed all papers
    print("Generating embeddings (this may take a moment)...")
    try:
        corpus.embed_all()
        print(f"Embeddings generated: shape {corpus.embeddings.shape}")
    except Exception as e:
        print(f"Warning: Could not generate embeddings: {e}")
        print("Corpus saved without embeddings (semantic search will use random sampling)")

    corpus.save()
    print(f"Corpus saved to {DATA_DIR / 'papers_corpus.json'}")


def build_from_json(path: str):
    """Build corpus from a JSON file with paper dicts."""
    with open(path) as f:
        papers = json.load(f)
    corpus = PaperCorpus()
    corpus.build_from_list(papers)
    print(f"Loaded {corpus.size} papers from {path}")

    print("Generating embeddings...")
    try:
        corpus.embed_all()
    except Exception as e:
        print(f"Warning: {e}")

    corpus.save()
    print("Done.")


def auto_tag_papers():
    """Run auto-tagging on existing corpus papers that lack tags."""
    corpus = PaperCorpus()
    if not corpus.papers:
        print("No papers in corpus")
        return

    tagged = 0
    for p in corpus.papers:
        if p.get("method_tags") and p.get("biology_tags"):
            continue

        text = f"{p.get('title', '')} {p.get('abstract', '')}".lower()

        if not p.get("method_tags"):
            p["method_tags"] = [t for t in METHOD_TAGS if t.lower() in text]
        if not p.get("biology_tags"):
            p["biology_tags"] = [t for t in BIOLOGY_TAGS if t.lower() in text]
        tagged += 1

    corpus.save()
    print(f"Auto-tagged {tagged} papers")


def main():
    parser = argparse.ArgumentParser(description="Initialize IdeaSpark paper corpus")
    parser.add_argument("--seed", action="store_true", help="Build from hardcoded seed papers")
    parser.add_argument("--json", type=str, help="Build from a JSON file")
    parser.add_argument("--auto-tag", action="store_true", help="Auto-tag untagged papers")
    parser.add_argument("--status", action="store_true", help="Show corpus status")

    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    if args.status:
        corpus = PaperCorpus()
        print(f"Corpus: {corpus.summary()}")
        if corpus.papers:
            years = [p.get("year", 0) for p in corpus.papers]
            print(f"Years: {min(years)}–{max(years)}")
            journals = set(p.get("journal", "") for p in corpus.papers)
            print(f"Journals: {len(journals)}")
            with_tags = sum(1 for p in corpus.papers if p.get("method_tags"))
            print(f"Tagged: {with_tags}/{len(corpus.papers)}")
        return

    if args.seed:
        build_corpus_from_seed()
        return

    if args.json:
        build_from_json(args.json)
        return

    if args.auto_tag:
        auto_tag_papers()
        return

    # Default: build from seed
    print("No arguments provided. Building from seed corpus...")
    build_corpus_from_seed()


if __name__ == "__main__":
    main()
