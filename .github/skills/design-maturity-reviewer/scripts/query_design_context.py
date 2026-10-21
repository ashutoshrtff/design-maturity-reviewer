"""
FAISS and dense vector query engine for DMR.
Queries indexed design context chunks filtered by Confluence page ID.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

CURRENT_DIR = Path(__file__).resolve().parent
REPO_ROOT = CURRENT_DIR.parents[3]
INGESTION_DIR = REPO_ROOT / "tools" / "knowledge-ingestion"
if str(INGESTION_DIR) not in sys.path:
    sys.path.insert(0, str(INGESTION_DIR))

from embeddings import EmbeddingClient, cosine_similarity, score_query_match


def load_index_chunks(index_dir: Path) -> Tuple[Dict[str, Any], List[Dict[str, Any]], np.ndarray]:
    """Load manifest, chunks.json, and vector store from knowledge-index directory."""
    manifest_path = index_dir / "manifest.json"
    chunks_path = index_dir / "chunks.json"

    if not manifest_path.exists() or not chunks_path.exists():
        raise FileNotFoundError(f"Knowledge index missing at {index_dir}. Run ingestion first.")

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    with open(chunks_path, "r", encoding="utf-8") as f:
        chunks = json.load(f)

    # Load vectors from vectors.npy or faiss index
    vectors: Optional[np.ndarray] = None
    vec_path = index_dir / "vectors.npy"
    if vec_path.exists():
        vectors = np.load(str(vec_path))
    else:
        # Fallback to faiss if available
        faiss_path = index_dir / "index.faiss"
        if faiss_path.exists():
            try:
                import faiss  # type: ignore

                idx = faiss.read_index(str(faiss_path))
                # Reconstruct vectors if supported
                vectors = np.array([idx.reconstruct(i) for i in range(idx.ntotal)], dtype=np.float32)
            except Exception:
                pass

    if vectors is None or len(vectors) != len(chunks):
        # Generate vectors on the fly if needed
        embedder = EmbeddingClient(offline=True)
        texts = [f"{c.get('heading_path','')}\n{c.get('text','')}" for c in chunks]
        vectors = np.array(embedder.embed_batch(texts), dtype=np.float32)

    return manifest, chunks, vectors


def query_design_context(
    query: str,
    page_id: str,
    index_base_dir: Optional[Path] = None,
    top_k: int = 8,
    max_chars_per_chunk: int = 1200,
    min_relevance: float = 0.35,
    offline: bool = True,
) -> Dict[str, Any]:
    base_dir = index_base_dir or (REPO_ROOT / "knowledge-index")
    page_index_dir = base_dir / page_id

    if not page_index_dir.exists():
        raise FileNotFoundError(
            f"Page {page_id} isn't ingested. Run ingestion first: "
            f"python tools/knowledge-ingestion/ingest.py --page-id {page_id} --output knowledge-index/{page_id}"
        )

    manifest, chunks, vectors = load_index_chunks(page_index_dir)
    embedder = EmbeddingClient(offline=offline)
    query_vec = np.array(embedder.embed_text(query), dtype=np.float32)

    # Normalize query vector
    q_norm = np.linalg.norm(query_vec)
    if q_norm > 0:
        query_vec = query_vec / q_norm

    # Compute cosine similarities
    scores: List[Tuple[float, Dict[str, Any]]] = []
    for idx, chunk in enumerate(chunks):
        # Filter to requested page_id or its indexed child pages
        c_page_id = str(chunk.get("page_id", ""))
        allowed_pages = {str(page_id)} | set(map(str, manifest.get("child_page_ids", [])))
        if c_page_id not in allowed_pages:
            continue

        c_vec = vectors[idx]
        sim = score_query_match(query_vec, c_vec, is_deterministic=embedder.offline)
        scores.append((sim, chunk))

    scores.sort(key=lambda x: x[0], reverse=True)
    top_items = scores[:top_k]

    mean_score = float(np.mean([s[0] for s in top_items])) if top_items else 0.0
    max_score = float(top_items[0][0]) if top_items else 0.0
    is_low_relevance = max_score < min_relevance

    result_chunks: List[Dict[str, Any]] = []
    for sim, ch in top_items:
        text = ch.get("text", "")
        if len(text) > max_chars_per_chunk:
            text = text[:max_chars_per_chunk] + "... [truncated]"
        result_chunks.append(
            {
                "chunk_id": ch.get("chunk_id", ""),
                "page_id": ch.get("page_id", page_id),
                "page_title": ch.get("page_title", manifest.get("page_title", "")),
                "heading_path": ch.get("heading_path", ""),
                "text": text,
                "score": round(sim, 4),
                "indexed_at": manifest.get("ingested_at", ""),
            }
        )

    return {
        "query": query,
        "page_id": page_id,
        "page_title": manifest.get("page_title", ""),
        "page_version": manifest.get("page_version", 1),
        "mean_relevance": round(mean_score, 4),
        "max_relevance": round(max_score, 4),
        "low_relevance_warning": is_low_relevance,
        "min_relevance_threshold": min_relevance,
        "total_chunks_matched": len(result_chunks),
        "chunks": result_chunks,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Query design context index.")
    parser.add_argument("--page-id", required=True, help="Confluence page ID")
    parser.add_argument("--query", required=True, help="Query text")
    parser.add_argument("--top-k", type=int, default=8, help="Max chunks to return")
    parser.add_argument("--min-relevance", type=float, default=0.35, help="Minimum relevance threshold")
    parser.add_argument("--index-dir", help="Index directory path")
    args = parser.parse_args()

    idx_dir = Path(args.index_dir) if args.index_dir else None
    res = query_design_context(
        query=args.query,
        page_id=args.page_id,
        index_base_dir=idx_dir,
        top_k=args.top_k,
        min_relevance=args.min_relevance,
    )
    print(json.dumps(res, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
