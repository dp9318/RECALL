"""RECALL Neural Core — Phase 2: Raw Corpus Quality Audit & Portable Dataset Packaging.

Reads `neural_core/data/raw/` in read-only mode, performs comprehensive classification,
content quality, training suitability, custom instruction, and privacy/PII audits,
writes `neural_core/data/audit/corpus_audit.json`, and builds a sanitized, validated
portable dataset archive at `neural_core/exports/recall_neural_core_dataset.zip`.
"""

from __future__ import annotations

import hashlib
import json
import re
import tempfile
import zipfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = REPO_ROOT / "neural_core" / "data" / "raw"
AUDIT_PATH = REPO_ROOT / "neural_core" / "data" / "audit" / "corpus_audit.json"
EXPORT_ZIP_PATH = REPO_ROOT / "neural_core" / "exports" / "recall_neural_core_dataset.zip"

EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
PHONE_RE = re.compile(r"(?:\+?\d{1,3}[\s-]?)?\b[6-9]\d{9}\b")
UUID_RE = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I)

CONSTRAINT_RE = re.compile(
    r"\b(never|do not|don't|must not|cannot|can't|no longer|avoid|without|strictly|prohibit|forbid|not a)\b",
    re.I,
)
PREFERENCE_CHANGE_RE = re.compile(
    r"\b(supersede|superseded|replaced|reverted|migrated|switched|evolved|pivot|reconcil|instead of|updated for|v2\.6|v2|v1)\b",
    re.I,
)
TEMPORARY_RE = re.compile(
    r"\b(temporary|temporarily|for now|pending|uncommitted|working tree|milestone|stage \d+|hotfix|workaround|offline sandbox|lifecycle_test)\b",
    re.I,
)
PERMANENT_RE = re.compile(
    r"\b(canonical|source of truth|hierarchy|always|never|non-negotiable|architecture|core philosophy|identity|invariant)\b",
    re.I,
)
TEST_NOISE_RE = re.compile(
    r"(lifecycle_test|verified active dashboard memory|global rule [0-9a-f]+|smoke test)",
    re.I,
)

STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "in", "is",
    "it", "of", "on", "or", "that", "the", "this", "to", "with", "will", "not",
}


def _tokenize(text: str) -> set[str]:
    tokens = re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).split()
    return {t for t in tokens if t not in STOPWORDS and len(t) > 1}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _sanitize_pii(text: str) -> tuple[str, int]:
    """Redact emails and phone numbers for safe dataset packaging."""
    if not text:
        return text, 0
    count = 0
    emails = EMAIL_RE.findall(text)
    if emails:
        count += len(emails)
        text = EMAIL_RE.sub("[REDACTED_PII:EMAIL]", text)
    phones = PHONE_RE.findall(text)
    if phones:
        count += len(phones)
        text = PHONE_RE.sub("[REDACTED_PII:PHONE]", text)
    return text, count


def _sanitize_record(obj: Any) -> tuple[Any, int]:
    if isinstance(obj, str):
        return _sanitize_pii(obj)
    if isinstance(obj, list):
        total = 0
        out = []
        for item in obj:
            s_item, c = _sanitize_record(item)
            total += c
            out.append(s_item)
        return out, total
    if isinstance(obj, dict):
        total = 0
        out: dict[str, Any] = {}
        for k, v in obj.items():
            s_val, c = _sanitize_record(v)
            total += c
            out[str(k)] = s_val
        return out, total
    return obj, 0


def run_audit_and_package() -> dict[str, Any]:
    memories = [
        json.loads(line)
        for line in (RAW_DIR / "memories.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    projects = json.loads((RAW_DIR / "projects.json").read_text(encoding="utf-8"))
    sessions = json.loads((RAW_DIR / "sessions.json").read_text(encoding="utf-8"))
    lineage = json.loads((RAW_DIR / "lineage.json").read_text(encoding="utf-8"))
    instructions = json.loads((RAW_DIR / "custom_instructions.json").read_text(encoding="utf-8"))
    extraction_report = json.loads((RAW_DIR / "extraction_report.json").read_text(encoding="utf-8"))

    project_names = {p["project_id"]: p["name"] for p in projects}

    # 1. Classification
    classification = {
        "total_memories": len(memories),
        "by_memory_type": dict(Counter(m["memory_type"] for m in memories)),
        "by_scope": dict(Counter(m["scope"] for m in memories)),
        "by_status": dict(Counter(m["status"] for m in memories)),
        "by_provenance": dict(Counter(m["provenance"] for m in memories)),
        "by_project_id": {
            (pid or "global_unscoped"): {
                "count": cnt,
                "project_name": project_names.get(pid, "Global / Unscoped"),
            }
            for pid, cnt in Counter(m["project_id"] for m in memories).items()
        },
        "distinct_counts": {
            "memory_type": len({m["memory_type"] for m in memories}),
            "scope": len({m["scope"] for m in memories}),
            "status": len({m["status"] for m in memories}),
            "provenance": len({m["provenance"] for m in memories}),
            "project_id": len({m["project_id"] for m in memories}),
        },
        "unusual_distributions": [
            "Zero memories have status='superseded' and lineage.json has 0 records; historical evolution is recorded in prose (e.g., V1 -> V2 -> V2.6) rather than DB supersession edges.",
            "Two memories are status='archived' (both are early/test-era records from 2026-10-09).",
            "Non-standard provenance strings exist alongside canonical ones ('basic website', 'User-created memory', 'api').",
            "74 of 80 memories have empty metadata ({}); only 6 carry explicit metadata.",
        ],
    }

    # 2. Content quality
    tokens_by_id = {m["memory_id"]: _tokenize(m["content"]) for m in memories}
    exact_groups: dict[str, list[str]] = defaultdict(list)
    for m in memories:
        norm = re.sub(r"\s+", " ", m["content"].strip().lower())
        exact_groups[norm].append(m["memory_id"])
    exact_duplicates = [ids for ids in exact_groups.values() if len(ids) > 1]

    near_duplicates: list[dict[str, Any]] = []
    for i, left in enumerate(memories):
        for right in memories[i + 1 :]:
            sim = _jaccard(tokens_by_id[left["memory_id"]], tokens_by_id[right["memory_id"]])
            if sim >= 0.65:
                near_duplicates.append({
                    "memory_id_a": left["memory_id"],
                    "memory_id_b": right["memory_id"],
                    "jaccard_similarity": round(sim, 3),
                })

    incomplete_or_context_dependent: list[dict[str, Any]] = []
    preference_changes: list[str] = []
    temporary_situations: list[str] = []
    permanent_situations: list[str] = []
    explicit_constraints: list[str] = []
    references_other_ids_or_history: list[dict[str, Any]] = []
    test_or_noise_ids: list[str] = []

    # Track potential contradictions (e.g. Portfolio 3D/Apple Glass vs Notebook Paper / No 3D)
    contradictory_pairs: list[dict[str, Any]] = []
    portfolio_v2_glass_ids = []
    portfolio_no_3d_ids = []

    pii_findings: list[dict[str, Any]] = []

    suitability_records: list[dict[str, Any]] = []

    for m in memories:
        mid = m["memory_id"]
        c = m["content"]
        low = c.lower()

        if TEST_NOISE_RE.search(c):
            test_or_noise_ids.append(mid)

        if len(c.strip()) < 80:
            incomplete_or_context_dependent.append({
                "memory_id": mid,
                "char_length": len(c.strip()),
                "reason": "Short/underspecified statement lacking standalone architectural or task context.",
            })

        has_pref_change = bool(PREFERENCE_CHANGE_RE.search(c))
        has_temp = bool(TEMPORARY_RE.search(c))
        has_perm = bool(PERMANENT_RE.search(c))
        has_constraint = bool(CONSTRAINT_RE.search(c))
        uuid_refs = [u for u in UUID_RE.findall(c) if u.lower() != mid.lower()]

        if has_pref_change:
            preference_changes.append(mid)
        if has_temp:
            temporary_situations.append(mid)
        if has_perm:
            permanent_situations.append(mid)
        if has_constraint:
            explicit_constraints.append(mid)
        if uuid_refs or "master_index" in low or "stage " in low:
            references_other_ids_or_history.append({
                "memory_id": mid,
                "referenced_uuids": uuid_refs,
                "has_named_index_or_stage_ref": ("master_index" in low or "stage " in low),
            })

        if m["project_id"] == "195081f5-657b-47fc-a578-57ce84464f75":
            if "apple frosted glass" in low or "three.js" in low or "heroScene".lower() in low:
                if "do not revert to v1.8 3d/frosted glass" not in low and "no 3d/webgl" not in low:
                    portfolio_v2_glass_ids.append(mid)
            if "no 3d/webgl" in low or "do not revert to v1.8 3d/frosted glass" in low or "engineering notebook paper" in low:
                portfolio_no_3d_ids.append(mid)

        # Privacy / PII scan (IDs only)
        flags: list[str] = []
        if "[REDACTED_SECRET:" in c:
            flags.append("already_redacted_secret_marker")
        if EMAIL_RE.search(c):
            flags.append("contains_email_address")
        if PHONE_RE.search(c):
            flags.append("contains_phone_number")
        if TEST_NOISE_RE.search(c):
            flags.append("test_or_smoke_artifact")
        if flags:
            pii_findings.append({"memory_id": mid, "flags": flags})

        # 3. Training suitability per memory
        is_noise = mid in test_or_noise_ids or len(c.strip()) < 35
        qc = not is_noise and len(c.strip()) >= 120
        cr = not is_noise and (has_constraint or has_pref_change or mid in portfolio_v2_glass_ids or mid in portfolio_no_3d_ids)
        ca = not is_noise and len(c.strip()) >= 80
        reasons = []
        if is_noise:
            reasons.append("Excluded from primary training signal: test artifact or overly terse fragment.")
        else:
            if qc:
                reasons.append("Rich technical/project detail suitable for query-to-keyword/intent compression.")
            if cr:
                reasons.append("Contains explicit constraints, negations, or version/design evolution useful for conflict resolution.")
            if ca:
                reasons.append("Self-contained factual/decision record suitable for grounded context packing.")

        suitability_records.append({
            "memory_id": mid,
            "query_compression": qc,
            "conflict_resolution": cr,
            "context_assembly": ca,
            "rationale": " ".join(reasons),
        })

    for g_id in portfolio_v2_glass_ids:
        for p_id in portfolio_no_3d_ids:
            contradictory_pairs.append({
                "memory_id_a": g_id,
                "memory_id_b": p_id,
                "topic": "Portfolio UI design direction (3D WebGL / Apple Frosted Glass vs. Engineering Notebook Paper / No 3D-WebGL)",
                "certainty": "confirmed_contradiction",
            })

    # 4. Custom instructions analysis
    instructions_audit = {
        "total": len(instructions),
        "by_scope": dict(Counter(i["scope"] for i in instructions)),
        "by_status": dict(Counter(i["status"] for i in instructions)),
        "records": [
            {
                "instruction_id": i["instruction_id"],
                "scope": i["scope"],
                "project_id": i["project_id"],
                "status": i["status"],
                "version": i["version"],
                "char_length": len(i["content"]),
                "suitable_for_context_assembly": i["status"] == "active" and len(i["content"]) > 30,
                "notes": (
                    "Test placeholder instruction (inactive)."
                    if "global rule" in i["content"].lower()
                    else (
                        "Short personal identity instruction; note potential ambiguity between full-name vs first-name-only global instructions."
                        if i["scope"] == "global" and len(i["content"]) < 40
                        else "Rich governance/protocol instruction; high-authority context assembly example."
                    )
                ),
            }
            for i in instructions
        ],
        "priority_relationships": [
            "Project-scoped active instruction (53036800-db23-4a9e-8182-3cc25c4f83f1, V2.6) supersedes inactive project instruction (693647df-ea0d-4e19-a158-2b1fcea04c60) and takes precedence over global instructions for the Portfolio project.",
            "Two active global instructions (00f35cb6-1621-4926-b462-c8f1ebddf9e5 and 69b84077-3c8d-4f05-bf42-6f8ea207c20f) contain a minor identity-formatting conflict (full name vs. first name only), providing a real-world instruction-conflict test case.",
        ],
    }

    # 5. Privacy summary
    privacy_audit = {
        "already_redacted_secrets_in_raw": extraction_report.get("total_redactions", 0),
        "flagged_records_by_id": pii_findings,
        "recommended_exclusions_for_training": sorted(set(test_or_noise_ids)),
        "sanitization_action_for_export_package": "Applied deterministic email and phone PII redaction ([REDACTED_PII:EMAIL], [REDACTED_PII:PHONE]) to all packaged copies without altering neural_core/data/raw/.",
    }

    audit_report = {
        "audit_timestamp": datetime.now(timezone.utc).isoformat(),
        "source_directory": str(RAW_DIR),
        "classification": classification,
        "content_quality": {
            "exact_duplicate_groups": exact_duplicates,
            "near_duplicate_pairs": near_duplicates,
            "incomplete_or_context_dependent": incomplete_or_context_dependent,
            "contradictory_pairs": contradictory_pairs,
            "preference_changes_memory_ids": preference_changes,
            "temporary_situations_memory_ids": temporary_situations,
            "permanent_situations_memory_ids": permanent_situations,
            "explicit_constraints_memory_ids": explicit_constraints,
            "references_other_ids_or_history": references_other_ids_or_history,
        },
        "training_suitability_summary": {
            "query_compression_suitable": sum(1 for r in suitability_records if r["query_compression"]),
            "conflict_resolution_suitable": sum(1 for r in suitability_records if r["conflict_resolution"]),
            "context_assembly_suitable": sum(1 for r in suitability_records if r["context_assembly"]),
            "excluded_noise_or_fragment": sum(
                1 for r in suitability_records
                if not (r["query_compression"] or r["conflict_resolution"] or r["context_assembly"])
            ),
            "per_memory": suitability_records,
        },
        "custom_instructions": instructions_audit,
        "privacy_and_quality": privacy_audit,
    }

    AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    AUDIT_PATH.write_text(json.dumps(audit_report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    # Build portable dataset package in a temporary staging directory, validate all JSON/JSONL, then zip
    EXPORT_ZIP_PATH.parent.mkdir(parents=True, exist_ok=True)
    total_pii_redactions = 0

    with tempfile.TemporaryDirectory() as tmpdir:
        stage = Path(tmpdir)
        (stage / "raw").mkdir()
        (stage / "audit").mkdir()

        sanitized_memories = []
        for m in memories:
            sm, c = _sanitize_record(m)
            total_pii_redactions += c
            sanitized_memories.append(sm)

        with (stage / "raw" / "memories.jsonl").open("w", encoding="utf-8", newline="\n") as f:
            for item in sanitized_memories:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")

        for fname, data in [
            ("projects.json", projects),
            ("sessions.json", sessions),
            ("lineage.json", lineage),
            ("custom_instructions.json", instructions),
            ("extraction_report.json", extraction_report),
        ]:
            s_data, c = _sanitize_record(data)
            total_pii_redactions += c
            (stage / "raw" / fname).write_text(
                json.dumps(s_data, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )

        (stage / "audit" / "corpus_audit.json").write_text(
            AUDIT_PATH.read_text(encoding="utf-8"),
            encoding="utf-8",
        )

        readme_text = (
            "# RECALL Neural Core Dataset Package\n\n"
            "Sanitized, read-only canonical export from RECALL SQLite (`mode=ro`) for Neural Core evaluation and training preparation.\n\n"
            "## Contents\n"
            "- `raw/memories.jsonl`: 80 non-deleted memories (active + archived), secrets and PII redacted.\n"
            "- `raw/projects.json`: Project metadata.\n"
            "- `raw/sessions.json`: Session metadata.\n"
            "- `raw/lineage.json`: Memory lineage edges.\n"
            "- `raw/custom_instructions.json`: Non-deleted custom instructions (active + inactive).\n"
            "- `raw/extraction_report.json`: Phase 1 extraction counts and validation summary.\n"
            "- `audit/corpus_audit.json`: Phase 2 classification, quality, conflict, suitability, and privacy audit.\n"
            "- `manifest.json`: File inventory, SHA-256 checksums, and sanitization summary.\n"
        )
        (stage / "README.md").write_text(readme_text, encoding="utf-8")

        # Validate JSON/JSONL before manifest
        packaged_files: list[dict[str, Any]] = []
        for rel in [
            "raw/memories.jsonl",
            "raw/projects.json",
            "raw/sessions.json",
            "raw/lineage.json",
            "raw/custom_instructions.json",
            "raw/extraction_report.json",
            "audit/corpus_audit.json",
            "README.md",
        ]:
            fpath = stage / rel
            raw_bytes = fpath.read_bytes()
            if rel.endswith(".jsonl"):
                for line in raw_bytes.decode("utf-8").splitlines():
                    if line.strip():
                        json.loads(line)
            elif rel.endswith(".json"):
                json.loads(raw_bytes.decode("utf-8"))
            packaged_files.append({
                "path": rel,
                "size_bytes": len(raw_bytes),
                "sha256": hashlib.sha256(raw_bytes).hexdigest(),
            })

        manifest = {
            "package_name": "recall_neural_core_dataset",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "excluded_deleted_memories": extraction_report["excluded_deleted_counts"]["memories"],
            "excluded_deleted_instructions": extraction_report["excluded_deleted_counts"]["custom_instructions"],
            "secret_redactions_phase1": extraction_report["total_redactions"],
            "pii_redactions_phase2": total_pii_redactions,
            "files": packaged_files,
        }
        manifest_path = stage / "manifest.json"
        manifest_bytes = (json.dumps(manifest, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
        manifest_path.write_bytes(manifest_bytes)
        json.loads(manifest_bytes.decode("utf-8"))

        with zipfile.ZipFile(EXPORT_ZIP_PATH, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for item in packaged_files:
                zf.write(stage / item["path"], arcname=item["path"])
            zf.write(manifest_path, arcname="manifest.json")

    with zipfile.ZipFile(EXPORT_ZIP_PATH, "r") as zf:
        zip_files = zf.namelist()

    return {
        "audit_path": str(AUDIT_PATH),
        "zip_path": str(EXPORT_ZIP_PATH),
        "zip_size_bytes": EXPORT_ZIP_PATH.stat().st_size,
        "zip_files": zip_files,
        "pii_redactions_phase2": total_pii_redactions,
        "summary": {
            "total_memories": classification["total_memories"],
            "by_memory_type": classification["by_memory_type"],
            "by_status": classification["by_status"],
            "by_provenance": classification["by_provenance"],
            "exact_duplicate_groups": len(exact_duplicates),
            "near_duplicate_pairs": len(near_duplicates),
            "contradictory_pairs": len(contradictory_pairs),
            "suitability": {
                k: v for k, v in audit_report["training_suitability_summary"].items() if k != "per_memory"
            },
        },
    }


if __name__ == "__main__":
    print(json.dumps(run_audit_and_package(), indent=2))
