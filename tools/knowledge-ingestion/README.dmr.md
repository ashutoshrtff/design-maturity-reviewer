# Knowledge Ingestion Tooling for DMR

## Provenance
- **Source Repository**: `enterprise/knowledge-ingestion` (placeholder - standalone baseline implementation)
- **Source Commit**: `a1b2c3d4e5f6` (placeholder)
- **Copy Date**: `2026-10-21`
- **Entrypoint**: `tools/knowledge-ingestion/ingest.py`

## Embedding Client Interface
The embedding client interface is defined in `tools/knowledge-ingestion/embeddings.py`:
- Class: `EmbeddingClient`
- Primary Methods:
  - `embed_text(text: str) -> List[float]`
  - `embed_batch(texts: List[str]) -> List[List[float]]`
  - `dimension: int` (default 384 for standard compact models, 1536 for OpenAI `text-embedding-3-small`)
- Offline / Deterministic Mode:
  - If no external API keys are configured (`OPENAI_API_KEY`, etc.), `EmbeddingClient(offline=True)` produces deterministic normalized semantic pseudo-embeddings derived from text n-grams and vocabulary hashes. This guarantees full offline testability and reproducible test vectors without live network calls.

## Index File Format
The generated index directory contains:
1. `manifest.json`:
   ```json
   {
     "page_id": "123456",
     "page_title": "Instant Payment Settlement Engine",
     "page_version": 12,
     "ingested_at": "2026-10-21T00:00:00Z",
     "embedding_model": "deterministic-hash-v1",
     "dimension": 384,
     "chunk_count": 6,
     "schema_version": "1.0",
     "child_page_ids": ["123457", "123458"],
     "source_content_hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
   }
   ```
2. `chunks.json`:
   List of chunk records with `chunk_id`, `page_id`, `page_title`, `heading_path`, `text`, `source_version`, and `token_estimate`.
3. `index.faiss` / `vectors.npy`:
   Dense vector storage indexed with Faiss (IndexFlatIP) or binary numpy cosine index for environments without compiled faiss C++ binaries.

## Known Assumptions & Upstream Drift Considerations
- **Concurrency**: Ingestion must be treated as a single-owner operation or run as a scheduled CI job. Concurrent ticket reviews must never write to or re-ingest the index.
- **Git LFS**: In production repositories with large design corpora, `*.faiss` files may be tracked via Git LFS.
- **Child Page Depth**: Default traversal limits child page recursion to 3 levels to prevent index bloat and excessive token consumption.
