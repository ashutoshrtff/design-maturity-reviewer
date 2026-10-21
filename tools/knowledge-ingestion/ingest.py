"""
Confluence design knowledge ingestion tool for DMR.
Chunks design pages, embeds chunks with EmbeddingClient, and builds vector index.
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

# Ensure this module can import sibling modules
CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from embeddings import EmbeddingClient


def chunk_markdown(
    text: str,
    page_id: str,
    page_title: str,
    page_version: int,
    max_chars: int = 1200,
) -> List[Dict[str, Any]]:
    """
    Heading-aware chunking preserving hierarchy and breadcrumbs.
    Splits by headings (#, ##, ###, ####) and subdivides large sections.
    """
    lines = text.splitlines()
    sections: List[Tuple[str, List[str]]] = []
    current_path: List[str] = [page_title]
    current_lines: List[str] = []

    heading_re = re.compile(r"^(#{1,6})\s+(.*)$")

    for line in lines:
        m = heading_re.match(line)
        if m:
            if current_lines:
                sections.append((" / ".join(current_path), current_lines))
                current_lines = []
            level = len(m.group(1))
            title = m.group(2).strip()
            # Adjust hierarchy depth
            current_path = current_path[:1] + [title]
        else:
            current_lines.append(line)

    if current_lines:
        sections.append((" / ".join(current_path), current_lines))

    chunks: List[Dict[str, Any]] = []
    chunk_index = 0

    for heading_path, sec_lines in sections:
        body = "\n".join(sec_lines).strip()
        if not body:
            continue

        # If section is small enough, keep as single chunk
        if len(body) <= max_chars:
            chunk_index += 1
            chunks.append(
                {
                    "chunk_id": f"{page_id}-c{chunk_index:03d}",
                    "page_id": page_id,
                    "page_title": page_title,
                    "heading_path": heading_path,
                    "text": body,
                    "source_version": page_version,
                    "char_count": len(body),
                }
            )
        else:
            # Subdivide by paragraphs
            paragraphs = re.split(r"\n\s*\n", body)
            buf: List[str] = []
            buf_len = 0
            for p in paragraphs:
                p_str = p.strip()
                if not p_str:
                    continue
                if buf_len + len(p_str) > max_chars and buf:
                    chunk_index += 1
                    chunk_text = "\n\n".join(buf)
                    chunks.append(
                        {
                            "chunk_id": f"{page_id}-c{chunk_index:03d}",
                            "page_id": page_id,
                            "page_title": page_title,
                            "heading_path": heading_path,
                            "text": chunk_text,
                            "source_version": page_version,
                            "char_count": len(chunk_text),
                        }
                    )
                    buf = [p_str]
                    buf_len = len(p_str)
                else:
                    buf.append(p_str)
                    buf_len += len(p_str) + 2
            if buf:
                chunk_index += 1
                chunk_text = "\n\n".join(buf)
                chunks.append(
                    {
                        "chunk_id": f"{page_id}-c{chunk_index:03d}",
                        "page_id": page_id,
                        "page_title": page_title,
                        "heading_path": heading_path,
                        "text": chunk_text,
                        "source_version": page_version,
                        "char_count": len(chunk_text),
                    }
                )

    return chunks


def build_and_save_index(
    chunks: List[Dict[str, Any]],
    output_dir: Path,
    manifest: Dict[str, Any],
    embedder: EmbeddingClient,
) -> None:
    """Embed chunks and save index artifacts."""
    output_dir.mkdir(parents=True, exist_ok=True)

    texts = [f"{c['heading_path']}\n{c['text']}" for c in chunks]
    vectors = embedder.embed_batch(texts)
    vec_array = np.array(vectors, dtype=np.float32)

    # Save chunks.json
    chunks_path = output_dir / "chunks.json"
    with open(chunks_path, "w", encoding="utf-8") as f:
        json.dump(chunks, f, indent=2, ensure_ascii=False)

    # Save vectors.npy as dense fallback
    vec_path = output_dir / "vectors.npy"
    np.save(str(vec_path), vec_array)

    # Try saving native faiss index if faiss is available
    faiss_saved = False
    try:
        import faiss  # type: ignore

        d = vec_array.shape[1]
        index = faiss.IndexFlatIP(d)
        # Normalize for inner-product cosine similarity
        faiss.normalize_L2(vec_array)
        index.add(vec_array)
        faiss.write_index(index, str(output_dir / "index.faiss"))
        faiss_saved = True
    except ImportError:
        # Save a placeholder/compatible marker for faiss file
        with open(output_dir / "index.faiss", "wb") as f:
            f.write(b"DMR_NUMPY_VECTOR_STORE_V1\n")

    manifest["chunk_count"] = len(chunks)
    manifest["dimension"] = embedder.dimension
    manifest["embedding_model"] = embedder.model_name
    manifest["faiss_native"] = faiss_saved
    manifest["ingested_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()

    manifest_path = output_dir / "manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)


def run_ingest(
    page_id: str,
    output_dir: Path,
    confluence_file: Optional[Path] = None,
    page_title: str = "Design Document",
    page_version: int = 1,
    child_pages: Optional[List[Dict[str, Any]]] = None,
    offline: bool = True,
) -> Dict[str, Any]:
    """Ingest design doc content into knowledge index."""
    if confluence_file and confluence_file.exists():
        with open(confluence_file, "r", encoding="utf-8") as f:
            text = f.read()
    else:
        # Default placeholder/template if no source doc provided
        text = f"# {page_title}\n\nDesign document for page {page_id}."

    content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    chunks = chunk_markdown(text, page_id, page_title, page_version)

    child_ids = []
    if child_pages:
        for child in child_pages:
            c_id = child.get("page_id", "child")
            c_title = child.get("title", f"Child of {page_title}")
            c_ver = child.get("version", page_version)
            c_text = child.get("text", "")
            child_ids.append(c_id)
            c_chunks = chunk_markdown(c_text, c_id, c_title, c_ver)
            chunks.extend(c_chunks)

    embedder = EmbeddingClient(offline=offline)
    manifest = {
        "page_id": page_id,
        "page_title": page_title,
        "page_version": page_version,
        "schema_version": "1.0",
        "child_page_ids": child_ids,
        "source_content_hash": content_hash,
    }

    build_and_save_index(chunks, output_dir, manifest, embedder)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest Confluence design page into FAISS index.")
    parser.add_argument("--page-id", required=True, help="Confluence Page ID")
    parser.add_argument("--output", default="knowledge-index", help="Output directory path")
    parser.add_argument("--confluence-file", help="Path to markdown/text file of Confluence page")
    parser.add_argument("--title", default="Instant Payment Settlement Engine", help="Page title")
    parser.add_argument("--version", type=int, default=12, help="Page version")
    parser.add_argument("--offline", action="store_true", default=True, help="Use offline deterministic embeddings")
    args = parser.parse_args()

    out_path = Path(args.output)
    if out_path.name != args.page_id:
        out_path = out_path / args.page_id

    file_path = Path(args.confluence_file) if args.confluence_file else None

    manifest = run_ingest(
        page_id=args.page_id,
        output_dir=out_path,
        confluence_file=file_path,
        page_title=args.title,
        page_version=args.version,
        offline=args.offline,
    )
    print(json.dumps({"status": "SUCCESS", "manifest": manifest}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
