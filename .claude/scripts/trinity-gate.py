#!/usr/bin/env python3
"""
trinity-gate.py — Trinity evaluation utility for Raven Enterprise

Modes:
    --detect        Scan git diff --cached for new API endpoint definitions
    --scan-all      Scan entire working tree for all API endpoints
    --start-app     Start the project app as a background subprocess
    --run-prompts   Send prompts sequentially to a live endpoint and collect responses
    --stop-app      Stop a previously started app subprocess

All output is JSON on stdout. Diagnostic logs suppressed.
Stdlib only — no third-party dependencies.
"""

import argparse
import copy
import json
import os
import re
import signal
import subprocess
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PID_FILE = Path(".raven") / ".trinity-app.pid"

# Regex patterns to detect route definitions per framework.
# Group 1: HTTP method (or path for Django). Group 2: path (where applicable).
ROUTE_PATTERNS = {
    "fastapi": [
        r'@(?:app|router|api)\.(get|post|put|patch|delete|options|head)\s*\(\s*["\']([^"\']+)',
    ],
    "flask": [
        r'@(?:app|bp|blueprint)\.(route)\s*\(\s*["\']([^"\']+)',
        r'@(?:app|bp|blueprint)\.(get|post|put|patch|delete)\s*\(\s*["\']([^"\']+)',
    ],
    "django": [
        r'(?:re_)?path\s*\(\s*r?["\']([^"\']+)',
    ],
    "aiohttp": [
        r'(?:app|router)\.router\.add_(?:route|get|post|put|patch|delete)\s*\(\s*["\']([^"\']+)',
    ],
}

RUNNER_ORDER = ["main.py", "app.py", "server.py", "run.py", "manage.py", "wsgi.py"]
HEALTH_PATHS = ["/health", "/api/health", "/docs", "/"]
POLL_INTERVAL = 2    # seconds between readiness checks
STARTUP_TIMEOUT = 30 # seconds before giving up on app start

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def log(msg: str):
    pass


def emit(data: dict):
    sys.stdout.write(json.dumps(data, indent=2) + "\n")
    sys.stdout.flush()


def _parse_routes(lines: list, filename: str, additions_only: bool) -> list:
    routes = []
    for i, line in enumerate(lines, 1):
        if additions_only:
            if not line.startswith("+") or line.startswith("+++"):
                continue
            content = line[1:]
        else:
            content = line

        for framework, patterns in ROUTE_PATTERNS.items():
            for pattern in patterns:
                match = re.search(pattern, content)
                if match:
                    groups = match.groups()
                    if framework == "django":
                        method = "ANY"
                        path = groups[0]
                    else:
                        method = groups[0].upper()
                        path = groups[1] if len(groups) > 1 else "/"
                    routes.append({
                        "method": method,
                        "path": path,
                        "file": filename,
                        "line": i,
                        "framework": framework,
                    })
                    break
    return routes


def _dedup(routes: list) -> list:
    seen = set()
    out = []
    for r in routes:
        key = (r["method"], r["path"], r["file"])
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out


# ---------------------------------------------------------------------------
# Mode: --detect
# ---------------------------------------------------------------------------

def cmd_detect():
    try:
        result = subprocess.run(
            ["git", "diff", "--cached"],
            capture_output=True, text=True, timeout=15,
        )
    except FileNotFoundError:
        emit({"found": False, "count": 0, "endpoints": [], "error": "git not found in PATH"})
        return
    except subprocess.TimeoutExpired:
        emit({"found": False, "count": 0, "endpoints": [], "error": "git diff timed out"})
        return

    current_file = None
    all_routes = []

    for line in result.stdout.splitlines():
        if line.startswith("diff --git"):
            parts = line.split(" b/")
            current_file = parts[-1].strip() if parts else "unknown"
        elif current_file and current_file.endswith(".py"):
            all_routes.extend(_parse_routes([line], current_file, additions_only=True))

    unique = _dedup(all_routes)
    emit({"found": len(unique) > 0, "count": len(unique), "endpoints": unique})


# ---------------------------------------------------------------------------
# Mode: --scan-all
# ---------------------------------------------------------------------------

def cmd_scan_all(project_root: str = "."):
    root = Path(project_root)
    skip_dirs = {".git", "__pycache__", ".venv", "venv", "env",
                 "node_modules", ".raven", "dist", "build"}
    all_routes = []

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in skip_dirs]
        for fname in filenames:
            if not fname.endswith(".py"):
                continue
            fpath = Path(dirpath) / fname
            try:
                lines = fpath.read_text(encoding="utf-8", errors="ignore").splitlines()
            except OSError:
                continue
            rel = str(fpath.relative_to(root)).replace("\\", "/")
            all_routes.extend(_parse_routes(lines, rel, additions_only=False))

    unique = _dedup(all_routes)
    emit({"found": len(unique) > 0, "count": len(unique), "endpoints": unique})


# ---------------------------------------------------------------------------
# Mode: --start-app
# ---------------------------------------------------------------------------

def _poll_ready(base_url: str, timeout: int) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        for path in HEALTH_PATHS:
            try:
                resp = urllib.request.urlopen(f"{base_url}{path}", timeout=3)
                if resp.status < 500:
                    return True
            except Exception:
                pass
        time.sleep(POLL_INTERVAL)
    return False


def _classify_error(stderr: str, port: int) -> dict:
    if "Address already in use" in stderr or "WinError 10048" in stderr:
        return {
            "reason": "port_in_use",
            "detail": f"Port {port} is already in use",
            "suggestion": f"Try --port {port + 1}",
        }
    if re.search(r"KeyError|os\.environ|getenv", stderr):
        vars_found = re.findall(r"KeyError: ['\"]([^'\"]+)['\"]", stderr)
        detail = f"Missing env vars: {', '.join(vars_found)}" if vars_found else "Missing required environment variables"
        return {
            "reason": "missing_env_vars",
            "detail": detail,
            "suggestion": "Set the required env vars or skip Trinity for this commit",
        }
    if re.search(r"Connection refused|could not connect to server", stderr, re.IGNORECASE):
        return {
            "reason": "db_unreachable",
            "detail": "Database connection refused",
            "suggestion": "Start the database or skip Trinity for this commit",
        }
    if re.search(r"ImportError|ModuleNotFoundError", stderr):
        mod = re.search(r"No module named ['\"]([^'\"]+)['\"]", stderr)
        detail = f"Missing module: {mod.group(1)}" if mod else "Missing dependency"
        return {
            "reason": "import_error",
            "detail": detail,
            "suggestion": "Run: pip install -r requirements.txt",
        }
    return {
        "reason": "unknown",
        "detail": stderr[:500] if stderr else "App exited with no output",
        "suggestion": "Check app logs and try starting it manually",
    }


def _resolve_python(venv: str = None) -> str:
    """Return the Python executable to use. Resolves a venv path to its interpreter."""
    if not venv:
        return sys.executable
    venv_path = Path(venv)
    # Accept either a venv root dir or a direct path to python[.exe]
    if venv_path.is_file():
        return str(venv_path)
    py_win = venv_path / "Scripts" / "python.exe"
    py_unix = venv_path / "bin" / "python"
    if py_win.exists():
        return str(py_win)
    if py_unix.exists():
        return str(py_unix)
    log(f"WARNING: venv path {venv!r} not recognised — falling back to system Python")
    return sys.executable


def _auto_install(python_exe: str, module: str) -> bool:
    """Try to pip-install a single missing module. Returns True if successful."""
    # Map import names to pip package names for common mismatches
    pip_name = {"fastapi": "fastapi", "uvicorn": "uvicorn", "pydantic": "pydantic",
                "flask": "flask", "aiohttp": "aiohttp", "starlette": "starlette"}.get(module)
    if pip_name is None:
        return False  # not in allowlist — install manually to avoid typo-squat risk
    try:
        result = subprocess.run(
            [python_exe, "-m", "pip", "install", pip_name],
            capture_output=True, timeout=60,
        )
        return result.returncode == 0
    except Exception:
        return False


def cmd_start_app(project_root: str = ".", port: int = 8000, venv: str = None):
    python_exe = _resolve_python(venv)
    log(f"Using Python: {python_exe}")

    root = Path(project_root)
    runner = None
    cmd = None
    start_method = None

    for candidate in RUNNER_ORDER:
        if (root / candidate).exists():
            runner = candidate
            if candidate == "manage.py":
                # cwd is already root, so just use the filename
                cmd = [python_exe, candidate, "runserver", f"0.0.0.0:{port}", "--noreload"]
                start_method = "django"
            else:
                cmd = [python_exe, candidate]
                start_method = "python"
            break

    if runner is None:
        if (root / "Dockerfile").exists():
            runner = "Dockerfile"
            start_method = "docker"
        elif (root / "docker-compose.yml").exists() or (root / "docker-compose.yaml").exists():
            runner = "docker-compose.yml"
            start_method = "docker-compose"

    if runner is None:
        emit({
            "started": False,
            "reason": "no_runner",
            "detail": "No entry point found (main.py, app.py, server.py, run.py, manage.py, Dockerfile, docker-compose.yml)",
            "suggestion": "Add a main.py or app.py entry point",
        })
        return

    log(f"Starting via {runner} on port {port}")
    base_url = f"http://localhost:{port}"

    if start_method in ("docker", "docker-compose"):
        _start_docker(root, runner, start_method, port, base_url)
        return

    env = os.environ.copy()
    env["PORT"] = str(port)

    auto_installs = 0

    for attempt in range(3):  # up to 2 auto-install retries
        try:
            proc = subprocess.Popen(
                cmd, cwd=str(root), env=env,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
        except FileNotFoundError as e:
            emit({"started": False, "reason": "runner_not_found",
                  "detail": str(e), "suggestion": "Ensure Python is in PATH"})
            return

        PID_FILE.parent.mkdir(parents=True, exist_ok=True)
        PID_FILE.write_text(str(proc.pid))

        if _poll_ready(base_url, STARTUP_TIMEOUT):
            emit({
                "started": True,
                "pid": proc.pid,
                "port": port,
                "base_url": base_url,
                "runner": runner,
                "start_method": start_method,
                **({"auto_installed": auto_installs} if auto_installs else {}),
            })
            return

        # App didn't come up — read stderr and classify
        try:
            proc.terminate()
            _, stderr_bytes = proc.communicate(timeout=5)
            stderr_text = stderr_bytes.decode(errors="ignore")
        except Exception:
            stderr_text = ""

        classification = _classify_error(stderr_text, port)

        # Soft recovery: auto-install 1–2 missing modules then retry once
        if classification["reason"] == "import_error" and auto_installs < 2:
            mod = re.search(r"No module named ['\"]([^'.\"]+)", stderr_text)
            if mod:
                module_name = mod.group(1)
                if _auto_install(python_exe, module_name):
                    auto_installs += 1
                    log(f"Installed {module_name}, retrying app start...")
                    continue  # retry the Popen loop

        emit({"started": False, **classification})
        return


def _start_docker(root: Path, runner: str, start_method: str, port: int, base_url: str):
    if start_method == "docker":
        build = subprocess.run(
            ["docker", "build", "-t", "trinity-test-app", "."],
            cwd=str(root), capture_output=True,
        )
        if build.returncode != 0:
            emit({
                "started": False,
                "reason": "docker_build_failed",
                "detail": build.stderr.decode(errors="ignore")[:500],
                "suggestion": "Fix the Dockerfile and retry",
            })
            return
        proc = subprocess.Popen(
            ["docker", "run", "--rm", "-p", f"{port}:{port}", "trinity-test-app"],
            cwd=str(root), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
    else:
        # Try modern `docker compose` first, fall back to legacy `docker-compose`
        cmd = ["docker", "compose", "up"]
        try:
            proc = subprocess.Popen(
                cmd, cwd=str(root), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
        except FileNotFoundError:
            proc = subprocess.Popen(
                ["docker-compose", "up"],
                cwd=str(root), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )

    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(str(proc.pid))

    if _poll_ready(base_url, STARTUP_TIMEOUT):
        emit({"started": True, "pid": proc.pid, "port": port,
              "base_url": base_url, "runner": runner, "start_method": start_method})
    else:
        proc.terminate()
        emit({
            "started": False,
            "reason": "docker_not_ready",
            "detail": f"App did not respond on {base_url} within {STARTUP_TIMEOUT}s",
            "suggestion": "Check Docker logs",
        })


# ---------------------------------------------------------------------------
# Mode: --run-prompts
# ---------------------------------------------------------------------------

def _path_set(obj: dict, path: str, value) -> dict:
    """Inject `value` into `obj` at the given path, e.g. 'messages[0][content]'."""
    segments = [s for s in re.split(r'[\[\]]', path) if s != '']
    parsed = []
    for s in segments:
        try:
            parsed.append(int(s))
        except ValueError:
            parsed.append(s)

    obj = copy.deepcopy(obj)
    target = obj
    for seg in parsed[:-1]:
        target = target[seg]
    target[parsed[-1]] = value
    return obj


def _path_get(obj, path: str):
    """Extract value from `obj` at the given path, e.g. 'choices[0][message][content]'."""
    segments = [s for s in re.split(r'[\[\]]', path) if s != '']
    target = obj
    for seg in segments:
        try:
            target = target[int(seg)]
        except (ValueError, TypeError):
            target = target[seg]
    return target


RESULTS_FILE = Path(".raven") / ".trinity-results.json"


def cmd_run_prompts(url: str, method: str, prompts_json: str = None,
                    prompts_file: str = None,
                    request_sample: str = None, request_path: str = None,
                    response_path: str = None,
                    body_key: str = "message", headers_json: str = "{}",
                    output_file: str = None):
    results_path = Path(output_file) if output_file else RESULTS_FILE

    if prompts_file:
        try:
            prompts = json.loads(Path(prompts_file).read_text(encoding="utf-8"))
        except Exception as e:
            emit({"error": f"Cannot read --prompts-file {prompts_file}: {e}"})
            return
    else:
        try:
            prompts = json.loads(prompts_json)
        except json.JSONDecodeError as e:
            emit({"error": f"Invalid --prompts-json: {e}"})
            return

    try:
        extra_headers = json.loads(headers_json)
    except json.JSONDecodeError:
        extra_headers = {}

    # Build base request body template
    if request_sample:
        try:
            base_body = json.loads(request_sample)
        except json.JSONDecodeError:
            base_body = {}
    else:
        base_body = {}

    # Resolve injection path: prefer --request-path, fall back to --body-key
    inject_path = request_path or body_key

    results = []
    total = len(prompts)

    for idx, item in enumerate(prompts, 1):
        # Accept both flat strings and legacy {prompt, text} objects
        if isinstance(item, str):
            prompt_text = item
        else:
            prompt_text = item.get("prompt") or item.get("text", "")

        # Inject prompt into the correct field of the request body
        if base_body:
            try:
                body_obj = _path_set(base_body, inject_path, prompt_text)
            except (KeyError, IndexError, TypeError):
                body_obj = dict(base_body)
                body_obj[inject_path] = prompt_text
        else:
            body_obj = {inject_path: prompt_text}

        body_bytes = json.dumps(body_obj).encode("utf-8")
        req = urllib.request.Request(url, data=body_bytes if method.upper() != "GET" else None)
        req.add_header("Content-Type", "application/json")
        req.method = method.upper()
        for k, v in extra_headers.items():
            req.add_header(k, v)

        t0 = time.time()
        try:
            resp = urllib.request.urlopen(req, timeout=15)
            raw_body = resp.read().decode("utf-8", errors="ignore")
            status_code = resp.status
        except urllib.error.HTTPError as e:
            raw_body = e.read().decode("utf-8", errors="ignore")
            status_code = e.code
        except Exception as e:
            raw_body = f"ERROR: {e}"
            status_code = 0

        response_ms = int((time.time() - t0) * 1000)

        # Extract response text using response_path
        response_text = raw_body
        if response_path and status_code not in (0,):
            try:
                resp_obj = json.loads(raw_body)
                response_text = str(_path_get(resp_obj, response_path))
            except Exception:
                response_text = raw_body

        log(f"[{idx}/{total}] {status_code} {response_ms}ms — {prompt_text[:55]}...")

        result_item = {
            "prompt": prompt_text,
            "response": response_text,
            "status_code": status_code,
            "response_ms": response_ms,
        }
        # Carry prompt metadata (categories, attackStrategy) through to results
        if isinstance(item, dict):
            for field in ("categories", "attackStrategy"):
                if field in item:
                    result_item[field] = item[field]
        results.append(result_item)

    # Write results to file — avoids stdout parsing issues for large payloads
    results_path.parent.mkdir(parents=True, exist_ok=True)
    results_path.write_text(json.dumps({"results": results}, indent=2), encoding="utf-8")

    ok_count = sum(1 for r in results if 200 <= r["status_code"] < 300)
    emit({"status": "ok", "total": total, "ok": ok_count, "results_file": str(results_path)})


# ---------------------------------------------------------------------------
# Mode: --stop-app
# ---------------------------------------------------------------------------

def _is_alive(pid: int) -> bool:
    if sys.platform == "win32":
        r = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                           capture_output=True, text=True)
        return str(pid) in r.stdout
    else:
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False


def _kill_pid(pid: int):
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True)
    else:
        try:
            os.kill(pid, signal.SIGKILL)
        except Exception:
            pass


def cmd_stop_app(pid: int = None):
    if pid is None:
        if PID_FILE.exists():
            try:
                pid = int(PID_FILE.read_text().strip())
            except (ValueError, OSError):
                emit({"stopped": False, "error": "PID file unreadable"})
                return
        else:
            emit({"stopped": False, "error": "No --pid given and no PID file at .raven/.trinity-app.pid"})
            return

    log(f"Stopping PID {pid}")

    if not _is_alive(pid):
        if PID_FILE.exists():
            PID_FILE.unlink()
        emit({"stopped": True, "pid": pid, "note": "process was already gone"})
        return

    # Graceful terminate first
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/PID", str(pid)], capture_output=True)
    else:
        try:
            os.kill(pid, signal.SIGTERM)
        except PermissionError as e:
            emit({"stopped": False, "pid": pid, "error": str(e)})
            return

    # Wait up to 5s then force-kill
    for _ in range(10):
        time.sleep(0.5)
        if not _is_alive(pid):
            break
    else:
        _kill_pid(pid)

    if PID_FILE.exists():
        PID_FILE.unlink()

    emit({"stopped": True, "pid": pid})


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Trinity gate utility — endpoint detection, app management, prompt runner"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--detect",       action="store_true", help="Scan staged diff for new endpoints")
    group.add_argument("--scan-all",     action="store_true", help="Scan working tree for all endpoints")
    group.add_argument("--start-app",    action="store_true", help="Start the project app")
    group.add_argument("--run-prompts",  action="store_true", help="Send prompts to live endpoint")
    group.add_argument("--stop-app",     action="store_true", help="Stop a running app")

    parser.add_argument("--project-root", default=".",    help="Project root (default: .)")
    parser.add_argument("--port",   type=int, default=8000, help="Port for --start-app (default: 8000)")
    parser.add_argument("--venv",   default=None, help="Path to venv dir or Python exe for --start-app (e.g. .venv)")
    parser.add_argument("--pid",    type=int, default=None, help="PID for --stop-app")
    parser.add_argument("--url",                             help="Endpoint URL for --run-prompts")
    parser.add_argument("--method",          default="POST", help="HTTP method for --run-prompts (default: POST)")
    parser.add_argument("--prompts-json",  default=None,      help="Inline JSON array of prompts for --run-prompts")
    parser.add_argument("--prompts-file",  default=None,      help="Path to JSON file of prompts — preferred over --prompts-json (avoids CLI length limits)")
    parser.add_argument("--request-sample",  default=None,   help="JSON string — sample request body used as template")
    parser.add_argument("--request-path",    default=None,   help="Path in request body to inject prompt (e.g. message, messages[0][content])")
    parser.add_argument("--response-path",   default=None,   help="Path in response JSON to extract model text (e.g. response, choices[0][message][content])")
    parser.add_argument("--body-key",        default="message", help="Fallback request body key when --request-path is not set (default: message)")
    parser.add_argument("--headers",         default="{}",   help="JSON headers dict for --run-prompts")
    parser.add_argument("--output-file",     default=None,   help="Path to write results JSON (default: .raven/.trinity-results.json)")

    args = parser.parse_args()

    if args.detect:
        cmd_detect()
    elif args.scan_all:
        cmd_scan_all(args.project_root)
    elif args.start_app:
        cmd_start_app(args.project_root, args.port, args.venv)
    elif args.run_prompts:
        if not args.url or (not args.prompts_json and not args.prompts_file):
            parser.error("--run-prompts requires --url and either --prompts-file or --prompts-json")
        cmd_run_prompts(
            args.url, args.method,
            prompts_json=args.prompts_json,
            prompts_file=args.prompts_file,
            request_sample=args.request_sample,
            request_path=args.request_path,
            response_path=args.response_path,
            body_key=args.body_key,
            headers_json=args.headers,
            output_file=args.output_file,
        )
    elif args.stop_app:
        cmd_stop_app(args.pid)


if __name__ == "__main__":
    main()
