"""Benchmark script to query ChromaDB semantic search directly.

Mimics the exact query structure, filters, and similarity calculation used in RECALL's
SQLiteSemanticIndexRepository.search_similar(), with precision timestamps and elapsed timings
at each stage to diagnose latency bottlenecks.

Usage:
    python scripts/benchmark_chroma.py [--sqlite-path PATH] [--chroma-path PATH] [--project-id UUID]
"""

from __future__ import annotations

import argparse
import datetime
import os
import sqlite3
import sys
import time
from pathlib import Path


def log_timestamp(label: str) -> None:
    now_str = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
    print(f"[{now_str}] {label}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark ChromaDB semantic retrieval performance")
    default_sqlite = os.getenv("RECALL_DB_PATH", str(Path.home() / ".recall" / "recall.sqlite3"))
    parser.add_argument(
        "--sqlite-path",
        default=default_sqlite,
        help="Path to RECALL SQLite database file",
    )
    parser.add_argument(
        "--chroma-path",
        default=os.getenv("RECALL_CHROMA_PATH"),
        help="Path to ChromaDB directory (defaults to <sqlite-path>.chromadb)",
    )
    parser.add_argument(
        "--project-id",
        default=os.getenv("RECALL_PROJECT_ID"),
        help="Target project UUID filter (optional; queries all active memories if omitted)",
    )
    parser.add_argument(
        "--model-name",
        default=os.getenv("RECALL_EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"),
        help="SentenceTransformer model name",
    )
    args = parser.parse_args()

    sqlite_path = Path(args.sqlite_path)
    chroma_path = Path(args.chroma_path) if args.chroma_path else sqlite_path.with_suffix(sqlite_path.suffix + ".chromadb")
    collection_name = "memories"
    project_id = args.project_id

    if not sqlite_path.exists():
        print(f"Error: SQLite database not found at {sqlite_path}", file=sys.stderr)
        print("Set --sqlite-path or RECALL_DB_PATH to an existing database.", file=sys.stderr)
        sys.exit(1)

    if not chroma_path.exists():
        print(f"Error: ChromaDB index not found at {chroma_path}", file=sys.stderr)
        print("Set --chroma-path or RECALL_CHROMA_PATH to an existing index directory.", file=sys.stderr)
        sys.exit(1)

    t_import_start = time.perf_counter()
    import chromadb
    from sentence_transformers import SentenceTransformer
    t_import_end = time.perf_counter()
    print(f"\n[TIMING] Library imports (chromadb, sentence_transformers): {t_import_end - t_import_start:.3f}s\n")

    log_timestamp(f"Connecting to ChromaDB client at: {chroma_path}")
    t0 = time.perf_counter()
    client = chromadb.PersistentClient(path=str(chroma_path))
    t_client = time.perf_counter()
    print(f"    -> Client connection took: {t_client - t0:.3f}s")

    log_timestamp(f"Opening collection '{collection_name}'...")
    try:
        collection = client.get_collection(name=collection_name)
    except Exception as exc:
        print(f"Error: Collection '{collection_name}' could not be opened: {exc}", file=sys.stderr)
        sys.exit(1)

    count = collection.count()
    t_coll = time.perf_counter()
    print(f"    -> Collection opened (Total indexed vectors: {count}) in: {t_coll - t_client:.3f}s")

    log_timestamp(f"Loading local embedding model: {args.model_name}...")
    t_model_start = time.perf_counter()
    model = SentenceTransformer(args.model_name, device="cpu")
    t_model_end = time.perf_counter()
    print(f"    -> Model weights loading took: {t_model_end - t_model_start:.3f}s")

    log_timestamp(f"Connecting to SQLite database: {sqlite_path}")
    sqlite_conn = sqlite3.connect(sqlite_path)
    sqlite_conn.row_factory = sqlite3.Row

    test_queries = [
        "retrieve what is stored in memory",
        "project architecture and technology stack",
        "recall persistent memory engine architecture",
    ]

    query_timings = []

    for idx, query in enumerate(test_queries, start=1):
        print("\n" + "=" * 80)
        log_timestamp(f"[{idx}/{len(test_queries)}] QUERY: '{query}'")
        print("=" * 80)
        t_query_start = time.perf_counter()

        # 1. Generate query embedding
        log_timestamp("Step 1: Encoding query with model...")
        t_enc_start = time.perf_counter()
        query_embedding = model.encode([query]).tolist()
        t_enc_end = time.perf_counter()
        print(f"    -> Query embedding generated in: {t_enc_end - t_enc_start:.3f}s")

        # 2. Build Chroma filter
        where_filter: dict = {"status": "active"}
        if project_id:
            where_filter = {
                "$and": [
                    {"status": "active"},
                    {
                        "$or": [
                            {"project_id": str(project_id)},
                            {
                                "$and": [
                                    {"scope": "global"},
                                    {"project_id": "__global__"},
                                ]
                            },
                        ]
                    },
                ]
            }

        # 3. Query ChromaDB vector collection
        log_timestamp("Step 2: Querying ChromaDB vector index...")
        t_chroma_start = time.perf_counter()
        results = collection.query(
            query_embeddings=query_embedding,
            n_results=3,
            where=where_filter,
            include=["distances", "metadatas"],
        )
        t_chroma_end = time.perf_counter()
        print(f"    -> ChromaDB search completed in: {t_chroma_end - t_chroma_start:.3f}s")

        ids = results.get("ids", [[]])[0]
        distances = results.get("distances", [[]])[0]

        if not ids:
            print("No matching memories found in ChromaDB.")
            continue

        # 4. Hydrate from SQLite
        log_timestamp(f"Step 3: Hydrating {len(ids)} matches from SQLite canonical storage...")
        t_hydrate_start = time.perf_counter()
        matches = []
        for rank, (mem_id, distance) in enumerate(zip(ids, distances), start=1):
            similarity_score = 1.0 - float(distance)
            row = sqlite_conn.execute(
                "SELECT content, memory_type, scope, created_at FROM memories WHERE memory_id = ?",
                (mem_id,),
            ).fetchone()
            matches.append((rank, mem_id, similarity_score, distance, row))
        t_hydrate_end = time.perf_counter()
        print(f"    -> SQLite hydration completed in: {t_hydrate_end - t_hydrate_start:.3f}s")

        print(f"\nTop {len(matches)} Semantic Matches:")
        for rank, mem_id, similarity_score, distance, row in matches:
            print(f"\n  [{rank}] Memory ID: {mem_id}")
            print(f"      Similarity Score: {similarity_score:.4f} (Cosine Distance: {distance:.4f})")
            if row:
                print(f"      Type: {row['memory_type']} | Scope: {row['scope']} | Date: {row['created_at']}")
                content_preview = row["content"].replace("\n", " ")
                if len(content_preview) > 180:
                    content_preview = content_preview[:180] + "..."
                print(f"      Canonical Content: {content_preview}")
            else:
                print("      (Record not found in SQLite)")

        t_query_end = time.perf_counter()
        total_q_time = t_query_end - t_query_start
        query_timings.append((query, total_q_time, t_enc_end - t_enc_start, t_chroma_end - t_chroma_start, t_hydrate_end - t_hydrate_start))
        print(f"\n    [Total latency for this query: {total_q_time:.3f}s]")

    sqlite_conn.close()

    if query_timings:
        print("\n" + "#" * 80)
        print("QUERY TIMINGS SUMMARY")
        print("#" * 80)
        print(f"{'#':<3} {'Query':<50} {'Encode':<10} {'Chroma':<10} {'SQLite':<10} {'Total':<10}")
        print("-" * 95)
        for i, (q, total_t, enc_t, chr_t, hyd_t) in enumerate(query_timings, start=1):
            q_display = (q[:47] + "...") if len(q) > 50 else q
            print(f"{i:<3} {q_display:<50} {enc_t * 1000:>6.1f}ms  {chr_t * 1000:>6.1f}ms  {hyd_t * 1000:>6.1f}ms  {total_t * 1000:>7.1f}ms")
        print("-" * 95)
        avg_total = sum(t[1] for t in query_timings) / len(query_timings)
        print(f"Average latency per search query: {avg_total * 1000:.1f}ms ({avg_total:.3f}s)")
    log_timestamp("All operations finished.\n")


if __name__ == "__main__":
    main()
