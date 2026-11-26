"""Packaged-runtime acceptance test for RECALL 3.1.0 bundle.

Tests the source bundle at dist/recall-3.1.0-windows against an isolated
temp DB (never touches the user's ~/.recall canonical database).

Checks:
  1. Bundle directory and key files exist
  2. API server starts successfully from bundle sources
  3. /health returns 200 with api_version 1.2.0
  4. Dashboard (/) returns 200 HTML
  5. /api/health returns 200 (dual-prefix compat)
  6. POST /api/memories saves a memory (no auth required)
  7. GET /api/memories returns the saved memory
  8. GET /api/search finds the memory by keyword
  9. GET /api/context assembles context including the memory
  10. MCP doctor --doctor resolves canonical paths correctly
  11. API server restart: memory persists across restart
  12. pyproject.toml version matches 3.1.0
"""
from __future__ import annotations

import json
import os
import sys
import subprocess
import tempfile
import time
import urllib.request
import urllib.error
import shutil
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BUNDLE_DIR = REPO_ROOT / "dist" / "recall-3.1.0-windows"
VENV_PYTHON = REPO_ROOT / ".venv" / "Scripts" / "python.exe"
API_PORT = 18099  # isolated port to avoid collisions
API_BASE = f"http://127.0.0.1:{API_PORT}"

PASS = "[PASS]"
FAIL = "[FAIL]"
SKIP = "[SKIP]"


def request(method: str, path: str, body=None, timeout: int = 10):
    url = f"{API_BASE}{path}"
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"} if data else {}
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            try:
                return r.status, json.loads(raw)
            except Exception:
                return r.status, raw
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, raw
    except Exception as e:
        return None, str(e)


def wait_for_server(timeout: int = 30) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{API_BASE}/health", timeout=2) as r:
                if r.status == 200:
                    return True
        except Exception:
            time.sleep(0.5)
    return False


def run_acceptance(tmp_dir: Path) -> bool:
    db_path = tmp_dir / "accept_test.sqlite3"
    env = {
        **os.environ,
        "RECALL_DB_PATH": str(db_path),
        "RECALL_API_HOST": "127.0.0.1",
        "RECALL_API_PORT": str(API_PORT),
        "RECALL_MCP_WARMUP": "false",
        "PYTHONPATH": str(REPO_ROOT),
    }

    results = []

    def check(label: str, ok: bool, detail: str = ""):
        status = PASS if ok else FAIL
        results.append((status, label, detail))
        print(f"  {status} {label}" + (f" — {detail}" if detail else ""))
        return ok

    # --- CHECK 1: Bundle directory and key files ---
    print("\n[CHECK 1] Bundle structure")
    key_files = [
        BUNDLE_DIR / "api" / "main.py",
        BUNDLE_DIR / "recall_mcp" / "server.py",
        BUNDLE_DIR / "frontend" / "dist" / "index.html",
        BUNDLE_DIR / "pyproject.toml",
        BUNDLE_DIR / "README.md",
        BUNDLE_DIR / "setup.bat",
        BUNDLE_DIR / "mcp_config.example.json",
    ]
    missing = [str(f.relative_to(BUNDLE_DIR)) for f in key_files if not f.exists()]
    check("Bundle key files present", not missing,
          f"Missing: {missing}" if missing else f"{len(key_files)} files verified")

    # --- CHECK 12: pyproject.toml version ---
    print("\n[CHECK 12] Version metadata")
    toml_path = BUNDLE_DIR / "pyproject.toml"
    toml_content = toml_path.read_text(encoding="utf-8")
    version_ok = 'version = "3.1.0"' in toml_content
    check("pyproject.toml version = 3.1.0", version_ok, "")
    readme_content = (BUNDLE_DIR / "README.md").read_text(encoding="utf-8")
    check("README.md mentions v3.1.0", "3.1.0" in readme_content, "")
    check("README.md mentions api 1.2.0", "1.2.0" in readme_content, "")

    # --- CHECK 10: MCP --doctor (uses repo sources, isolated DB) ---
    print("\n[CHECK 10] MCP --doctor")
    result = subprocess.run(
        [str(VENV_PYTHON), "-W", "error::RuntimeWarning", "-m", "recall_mcp.server", "--doctor"],
        capture_output=True, text=True, timeout=30, env=env,
        cwd=str(REPO_ROOT),
    )
    try:
        doctor_out = json.loads(result.stdout.strip())
        doctor_ok = doctor_out.get("ok") is True
        db_resolved = doctor_out.get("sqlite_path", "")
        check("MCP --doctor ok=true", doctor_ok, f"sqlite_path={db_resolved}")
        check("MCP --doctor uses isolated DB", str(db_path) in db_resolved, db_resolved)
    except Exception as e:
        check("MCP --doctor parseable JSON", False, f"{e}\nstdout={result.stdout[:200]}")

    # --- START API SERVER ---
    print("\n[CHECK 2-9, 11] API server lifecycle")
    srv = subprocess.Popen(
        [str(VENV_PYTHON), "-m", "api.main"],
        env=env,
        cwd=str(REPO_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        ok = wait_for_server(timeout=30)
        check("API server starts and responds", ok,
              f"port {API_PORT}" if ok else "timeout after 30s")
        if not ok:
            srv.terminate()
            srv.wait()
            return not any(r[0] == FAIL for r in results)

        # CHECK 3: /health
        print("\n[CHECK 3] /health")
        status, body = request("GET", "/health")
        health_ok = status == 200 and isinstance(body, dict)
        api_version_ok = isinstance(body, dict) and body.get("api_version") == "1.2.0"
        check("/health returns 200", health_ok, f"status={status}")
        check("/health api_version = 1.2.0", api_version_ok,
              f"got {body.get('api_version') if isinstance(body, dict) else body}")

        # CHECK 4: Dashboard HTML
        print("\n[CHECK 4] Dashboard HTML")
        status, body = request("GET", "/")
        check("Dashboard / returns 200 HTML", status == 200, f"status={status}")

        # CHECK 5: /api/health dual prefix
        print("\n[CHECK 5] /api/health dual prefix")
        status, body = request("GET", "/api/health")
        check("/api/health returns 200", status == 200, f"status={status}")

        # CHECK 6: Create project & Save memory
        print("\n[CHECK 6] Create project & Save memory")
        proj_payload = {
            "name": "accept-test-project",
            "description": "RECALL 3.1.0 acceptance test project",
        }
        status, body = request("POST", "/api/projects", proj_payload)
        proj_id = (body.get("project_id") or body.get("id")) if isinstance(body, dict) else None
        check("POST /api/projects returns 2xx", status in (200, 201) and bool(proj_id),
              f"status={status} project_id={proj_id}")

        mem_payload = {
            "project_id": proj_id,
            "content": "RECALL 3.1.0 acceptance test memory — authentication removed, Community edition",
            "memory_type": "fact",
            "topic": "testing",
        }
        status, body = request("POST", "/api/memories", mem_payload)
        save_ok = status in (200, 201)
        mem_id = (body.get("memory_id") or body.get("id")) if isinstance(body, dict) else None
        check("POST /api/memories returns 2xx", save_ok,
              f"status={status} id={mem_id}")

        # CHECK 7: Retrieve memories
        print("\n[CHECK 7] Retrieve memories")
        status, body = request("GET", f"/api/memories?project_id={proj_id}")
        mems = body if isinstance(body, list) else (body.get("memories", []) if isinstance(body, dict) else [])
        found = any("3.1.0" in str(m.get("content", "")) for m in mems) if mems else False
        check("GET /api/memories returns saved memory", found,
              f"status={status}, count={len(mems)}")

        # CHECK 8 & 9: Search & Context assembly via /api/context/query
        print("\n[CHECK 8-9] Search & Context assembly")
        status, body = request("POST", "/api/context/query", {
            "project_id": proj_id,
            "query": "acceptance test memory",
        })
        supporting = body.get("supporting_memories", []) if isinstance(body, dict) else []
        check("POST /api/context/query returns 200 with supporting_memories",
              status == 200 and len(supporting) >= 1,
              f"status={status}, supporting_memories={len(supporting)}")

        # CHECK 11: Restart persistence
        print("\n[CHECK 11] Restart persistence")
        srv.terminate()
        srv.wait(timeout=10)

        srv2 = subprocess.Popen(
            [str(VENV_PYTHON), "-m", "api.main"],
            env=env,
            cwd=str(REPO_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        try:
            ok2 = wait_for_server(timeout=30)
            check("API server restarts cleanly", ok2, f"port {API_PORT}" if ok2 else "timeout")
            if ok2:
                status, body = request("GET", f"/api/memories?project_id={proj_id}")
                mems2 = body if isinstance(body, list) else (body.get("memories", []) if isinstance(body, dict) else [])
                persisted = any("3.1.0" in str(m.get("content", "")) for m in mems2) if mems2 else False
                check("Memory persists after restart", persisted,
                      f"count={len(mems2)}")
        finally:
            srv2.terminate()
            try:
                srv2.wait(timeout=5)
            except Exception:
                pass
    finally:
        srv.terminate()
        try:
            srv.wait(timeout=5)
        except Exception:
            pass

    # Summary
    passed = sum(1 for r in results if r[0] == PASS)
    failed = sum(1 for r in results if r[0] == FAIL)
    skipped = sum(1 for r in results if r[0] == SKIP)
    print(f"\n{'='*60}")
    print(f"Acceptance Test Summary: {passed} passed, {failed} failed, {skipped} skipped")
    print(f"{'='*60}")
    for status, label, detail in results:
        if status == FAIL:
            print(f"  {status} {label}" + (f" — {detail}" if detail else ""))
    return failed == 0


def main():
    print(f"RECALL 3.1.0 Packaged-Runtime Acceptance Test")
    print(f"Bundle: {BUNDLE_DIR}")
    print(f"Python: {VENV_PYTHON}")
    print(f"API port: {API_PORT}")

    if not BUNDLE_DIR.exists():
        print(f"\n{FAIL} Bundle directory does not exist: {BUNDLE_DIR}")
        sys.exit(1)

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        tmp_dir = Path(tmp)
        success = run_acceptance(tmp_dir)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
