# Retrieval & Knowledge Indexing

## Confluence Traversal
- Ingests primary design page and child pages up to 3 levels deep.
- Extracts Markdown sections delimited by headings (`#`, `##`, `###`), preserving full heading paths.

## Index Artifacts
Committed to `knowledge-index/<pageId>/`:
- `manifest.json`: Page version, timestamp, embedding model, dimension, chunk count, child page IDs, content hash.
- `chunks.json`: Text chunks with heading paths and IDs.
- `index.faiss`: Native Faiss IndexFlatIP (or numpy fallback vector store).
- `vectors.npy`: Dense vector array.

## Ingestion Ownership
- Run as a single CI job or by a designated index owner when designs change.
- Never auto-ingested on-the-fly during per-ticket runs to prevent concurrent binary write collisions.
