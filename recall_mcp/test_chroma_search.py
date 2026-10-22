"""Isolated test script to query ChromaDB semantic search directly.

Mimics the exact query structure, filters, and similarity calculation used in RECALL's
`SQLiteSemanticIndexRepository.search_similar()`, with precision timestamps and elapsed timings
at each stage to diagnose bottlenecks.

Usage:
    C:\\Users\\dipan\\AppData\\Local\\Programs\\Python\\Python312\\python.exe recall_mcp/test_chroma_search.py
"""

from __future__ import annotations

import datetime
import sqlite3
import time
from pathlib import Path
from uuid import UUID

t_import_start = time.perf_counter()
import chromadb
from sentence_transformers import SentenceTransformer
t_import_end = time.perf_counter()


# 1. Config / Canonical Paths (matches database/repositories/unit_of_work.py)
SQLITE_PATH = Path.home() / ".recall" / "recall.sqlite3"
CHROMA_PATH = SQLITE_PATH.with_suffix(SQLITE_PATH.suffix + ".chromadb")
COLLECTION_NAME = "memories"
MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

# Target Project ID:
# e.g., "195081f5-657b-47fc-a578-57ce84464f75" (Portfolio), or None to query across all active memories
PROJECT_ID = "195081f5-657b-47fc-a578-57ce84464f75"


def log_timestamp(label: str) -> None:
    now_str = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
    print(f"[{now_str}] {label}")


def main():
    print(f"\n[TIMING] Heavy library imports (chromadb, torch, sentence_transformers): {t_import_end - t_import_start:.3f}s\n")

    log_timestamp(f"Connecting to ChromaDB client at: {CHROMA_PATH}")
    t0 = time.perf_counter()
    client = chromadb.PersistentClient(path=str(CHROMA_PATH))
    t_client = time.perf_counter()
    print(f"    -> Client connection took: {t_client - t0:.3f}s")

    log_timestamp(f"Opening collection '{COLLECTION_NAME}'...")
    collection = client.get_collection(name=COLLECTION_NAME)
    count = collection.count()
    t_coll = time.perf_counter()
    print(f"    -> Collection opened (Total indexed vectors: {count}) in: {t_coll - t_client:.3f}s")

    log_timestamp(f"Loading local embedding model: {MODEL_NAME}...")
    t_model_start = time.perf_counter()
    model = SentenceTransformer(MODEL_NAME, device="cpu")
    t_model_end = time.perf_counter()
    print(f"    -> Model weights loading took: {t_model_end - t_model_start:.3f}s")

    log_timestamp(f"Connecting to SQLite database: {SQLITE_PATH}")
    sqlite_conn = sqlite3.connect(SQLITE_PATH)
    sqlite_conn.row_factory = sqlite3.Row

    # Define 5 diverse test queries to evaluate once model and db are warmed up
    test_queries = [
        "retrieve what is stored in memory",
        "what projects did dipankar work on",
        "portfolio build and technology stack",
        "recall persistent memory engine architecture",
        "educational qualifications and university details",
    ]

    query_timings = []

    for idx, query in enumerate(test_queries, start=1):
        print("\n" + "=" * 80)
        log_timestamp(f"[{idx}/{len(test_queries)}] QUERY: '{query}'")
        print("=" * 80)
        t_query_start = time.perf_counter()

        # 1. Generate query embedding (sentence-transformers)
        log_timestamp("Step 1: Encoding query with model...")
        t_enc_start = time.perf_counter()
        query_embedding = model.encode([query]).tolist()
        t_enc_end = time.perf_counter()
        print(f"    -> Query embedding generated in: {t_enc_end - t_enc_start:.3f}s")

        # 2. Build Chroma filter (mimics SQLiteSemanticIndexRepository.search_similar)
        where_filter = {"status": "active"}
        if PROJECT_ID:
            where_filter = {
                "$and": [
                    {"status": "active"},
                    {
                        "$or": [
                            {"project_id": str(PROJECT_ID)},
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

        # 4. Hydrate from SQLite canonical memory table
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

    print("\n" + "#" * 80)
    print("QUERY TIMINGS SUMMARY (Post-Import & Warm Cache)")
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
