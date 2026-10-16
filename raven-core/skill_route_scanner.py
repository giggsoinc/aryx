#!/usr/bin/env python3
"""Raven skill scanner — trinity_scanner-compatible discovery without git_scanner.

Uses AST and source heuristics for FastAPI/Flask HTTP routes plus LLM/MCP/RAG/agent
signals. Invoked by /raven-asset-identification and commit hooks when
trinity_scanner is not installed.
"""

from __future__ import annotations

import ast
import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_SKIP_DIRS = {
    ".git",
    ".raven",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    "dist",
    "build",
    ".pytest_cache",
}

_HTTP_METHODS = {
    "get": "GET",
    "post": "POST",
    "put": "PUT",
    "patch": "PATCH",
    "delete": "DELETE",
    "head": "HEAD",
    "options": "OPTIONS",
}

_PY_API_SUFFIXES = {".py"}
_ROUTE_FILE_HINTS = (
    "main.py",
    "app.py",
    "server.py",
    "routes",
    "api",
    "router",
    "views",
    "endpoints",
)


def _endpoint_id(*parts: str) -> str:
    digest = hashlib.sha256("|".join(parts).encode()).hexdigest()
    return digest[:12]


def _rel_path(path: Path, repo_root: Path) -> str:
    try:
        return str(path.relative_to(repo_root))
    except ValueError:
        return str(path)


def _iter_python_files(repo_root: Path) -> list[Path]:
    files: list[Path] = []
    for path in repo_root.rglob("*.py"):
        if any(part in _SKIP_DIRS for part in path.parts):
            continue
        rel = path.relative_to(repo_root)
        lowered = str(rel).replace("\\", "/").lower()
        if any(hint in lowered for hint in _ROUTE_FILE_HINTS) or path.name in {"main.py", "app.py", "server.py"}:
            files.append(path)
    if not files and (repo_root / "app").is_dir():
        for path in (repo_root / "app").rglob("*.py"):
            if any(part in _SKIP_DIRS for part in path.parts):
                continue
            files.append(path)
    return sorted(set(files))


def _parse_models(tree: ast.AST) -> dict[str, ast.ClassDef]:
    models: dict[str, ast.ClassDef] = {}
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            bases = {getattr(base, "id", "") for base in node.bases}
            if "BaseModel" in bases or any("Model" in b for b in bases):
                models[node.name] = node
    return models


def _model_body_schema(model: ast.ClassDef) -> dict[str, Any]:
    properties: dict[str, Any] = {}
    for stmt in model.body:
        if not isinstance(stmt, ast.AnnAssign) or not isinstance(stmt.target, ast.Name):
            continue
        field_name = stmt.target.id
        type_name = "str"
        required = True
        if stmt.annotation is not None:
            type_name = ast.unparse(stmt.annotation)
            if "None" in type_name or "Optional" in type_name:
                required = False
        properties[field_name] = {"type": type_name, "required": required}
    return {
        "type": "object",
        "properties": properties,
        "title": model.name,
    }


def _decorator_route(dec: ast.expr) -> tuple[str, str] | None:
    if not isinstance(dec, ast.Call):
        return None
    func = dec.func
    if not isinstance(func, ast.Attribute):
        return None
    method = _HTTP_METHODS.get(func.attr.lower())
    if not method:
        return None
    if not dec.args:
        return None
    first = dec.args[0]
    if isinstance(first, ast.Constant) and isinstance(first.value, str):
        return method, first.value
    return None


def _handler_body_schema(func: ast.FunctionDef | ast.AsyncFunctionDef, models: dict[str, ast.ClassDef]) -> dict[str, Any] | None:
    for arg in func.args.args:
        if arg.arg in {"self", "cls", "request", "response"}:
            continue
        if arg.annotation is None:
            continue
        if isinstance(arg.annotation, ast.Name) and arg.annotation.id in models:
            return _model_body_schema(models[arg.annotation.id])
        if isinstance(arg.annotation, ast.Attribute) and arg.annotation.attr in models:
            return _model_body_schema(models[arg.annotation.attr])
    return None


def _read_source_segment(path: Path, node: ast.AST) -> str:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    start = max(getattr(node, "lineno", 1) - 1, 0)
    end = getattr(node, "end_lineno", start + 1) or (start + 1)
    return "\n".join(lines[start:end])


def _extract_llm_assets(source: str, *, file_path: str, line: int, function: str) -> list[dict[str, Any]]:
    assets: list[dict[str, Any]] = []
    if not re.search(r"(chat\.completions\.create|ChatOpenAI|Anthropic|messages\s*=\s*\[)", source):
        return assets

    model_match = re.search(r"model\s*=\s*['\"]([^'\"]+)['\"]", source)
    temp_match = re.search(r"temperature\s*=\s*([0-9.]+)", source)
    provider = "openai"
    if "anthropic" in source.lower():
        provider = "anthropic"

    system_prompt = None
    const_match = re.search(r"([A-Z][A-Z0-9_]*SYSTEM[_A-Z]*PROMPT)\s*=", source)
    if const_match:
        system_prompt = {
            "content": f"variable:{const_match.group(1)}",
            "is_dynamic": False,
            "construction_pattern": f"variable:{const_match.group(1)}",
            "user_fields_injected": [],
        }
    elif re.search(r"role\s*:\s*['\"]system['\"]", source) or '"system"' in source:
        content_match = re.search(r"['\"]content['\"]\s*:\s*['\"]([^'\"]{8,})['\"]", source)
        if content_match:
            system_prompt = {
                "content": content_match.group(1),
                "is_dynamic": False,
                "construction_pattern": "inline",
                "user_fields_injected": [],
            }

    asset: dict[str, Any] = {
        "provider": provider,
        "model": {
            "name": "model",
            "value": model_match.group(1) if model_match else "unknown",
            "source": "hardcoded" if model_match else "inferred",
            "raw": model_match.group(0) if model_match else "",
        },
        "temperature": {
            "name": "temperature",
            "value": float(temp_match.group(1)) if temp_match else None,
            "source": "hardcoded" if temp_match else "inferred",
            "raw": temp_match.group(0) if temp_match else "",
        },
        "extra_params": [],
        "call_site": {"file": file_path, "line": line, "function": function},
    }
    if system_prompt:
        asset["system_prompt"] = system_prompt
    assets.append(asset)
    return assets


def _extract_mcp_assets(source: str, *, file_path: str, line: int, function: str) -> list[dict[str, Any]]:
    invocations: list[dict[str, Any]] = []
    for match in re.finditer(r"call_tool\(\s*['\"]([^'\"]+)['\"]", source):
        invocations.append({
            "tool_name": match.group(1),
            "arguments": {},
            "raw_arguments": match.group(0),
            "source": "dynamic",
        })
    if invocations:
        return [{
            "tools": [],
            "framework": "mcp-sdk",
            "tool_invocations": invocations,
            "call_site": {"file": file_path, "line": line, "function": function},
            "call_pattern": "call_tool",
        }]
    if "ClientSession" in source:
        return [{
            "tools": [],
            "framework": "mcp-sdk",
            "tool_invocations": [],
            "call_site": {"file": file_path, "line": line, "function": function},
            "call_pattern": "ClientSession",
        }]
    return []


def _extract_rag_assets(source: str, *, file_path: str, line: int, function: str) -> list[dict[str, Any]]:
    if not re.search(r"(Chroma|FAISS|as_retriever|\.invoke\()", source, re.I):
        return []
    return [{
        "framework": "langchain",
        "vector_store": {"type": "chroma", "source": "inferred"},
        "retriever": {"source": "inferred"},
        "call_site": {"file": file_path, "line": line, "function": function},
        "call_pattern": "as_retriever",
    }]


def _extract_agent_assets(source: str, *, file_path: str, line: int, function: str) -> list[dict[str, Any]]:
    if "Agent(" not in source and ".kickoff(" not in source:
        return []
    role_match = re.search(r"role\s*=\s*['\"]([^'\"]+)['\"]", source)
    prompt_match = re.search(r"system_prompt\s*=\s*['\"]([^'\"]+)['\"]", source)
    call_pattern = "kickoff" if ".kickoff(" in source else "Agent"
    return [{
        "provider": "crewai",
        "framework": "crewai",
        "agent_type": "crewai",
        "role": role_match.group(1) if role_match else "agent",
        "system_prompt": {
            "content": prompt_match.group(1) if prompt_match else "",
            "is_dynamic": False,
        },
        "call_site": {"file": file_path, "line": line, "function": function},
        "call_pattern": call_pattern,
    }]


def _scan_python_file(path: Path, repo_root: Path, frameworks: set[str]) -> list[dict[str, Any]]:
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source, filename=str(path))
    except (OSError, SyntaxError):
        return []

    if "fastapi" in source.lower():
        frameworks.add("fastapi")
    if "flask" in source.lower():
        frameworks.add("flask")

    models = _parse_models(tree)
    route_targets: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Assign):
            if isinstance(node.value, ast.Call):
                func_name = getattr(node.value.func, "id", "") or getattr(node.value.func, "attr", "")
                if func_name in {"FastAPI", "APIRouter"}:
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            route_targets.add(target.id)

    endpoints: list[dict[str, Any]] = []
    rel_file = _rel_path(path, repo_root)

    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in node.decorator_list:
            route = _decorator_route(dec)
            if not route:
                continue
            if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute):
                if isinstance(dec.func.value, ast.Name) and dec.func.value.id not in route_targets:
                    if dec.func.value.id not in {"app", "router"} and dec.func.value.id not in route_targets:
                        continue
            method, route_path = route
            body_schema = _handler_body_schema(node, models)
            segment = _read_source_segment(path, node)
            line = getattr(node, "lineno", 1)
            entry = {
                "id": _endpoint_id(rel_file, method, route_path, node.name),
                "kind": "http",
                "handler_function": node.name,
                "handler_file": rel_file,
                "handler_line": line,
                "framework": "fastapi" if "fastapi" in frameworks else "flask",
                "method": method,
                "path": route_path,
            }
            request_schema: dict[str, Any] = {
                "method": method,
                "path": route_path,
                "path_params": [],
                "query_params": [],
                "content_type": "application/json",
            }
            if body_schema:
                request_schema["body_schema"] = body_schema
                request_schema["model_class"] = body_schema.get("title")

            endpoints.append({
                "entry_point": entry,
                "reachability": "direct",
                "auth": {"type": "none"},
                "request_schema": request_schema,
                "response_schema": {"status_codes": [200]},
                "validation_rules": [],
                "rate_limited": False,
                "llm_assets": _extract_llm_assets(segment, file_path=rel_file, line=line, function=node.name),
                "mcp_assets": _extract_mcp_assets(segment, file_path=rel_file, line=line, function=node.name),
                "agent_assets": _extract_agent_assets(segment, file_path=rel_file, line=line, function=node.name),
                "rag_assets": _extract_rag_assets(segment, file_path=rel_file, line=line, function=node.name),
                "injection_fields": [],
                "call_path": [node.name],
                "unresolved_calls": [],
                "confidence": 0.85,
            })
    return endpoints


def run_skill_scan(repo_root: Path | None = None, *, repo_name: str | None = None) -> dict[str, Any]:
    """Scan a repository and return a trinity_scanner-compatible discovery report."""
    root = Path(repo_root or ".").resolve()
    name = repo_name or root.name
    frameworks: set[str] = set()
    endpoints: list[dict[str, Any]] = []

    for path in _iter_python_files(root):
        endpoints.extend(_scan_python_file(path, root, frameworks))

    red_teamable = sum(1 for ep in endpoints if ep.get("reachability") == "direct")
    unreachable = len(endpoints) - red_teamable
    return {
        "meta": {
            "repo": name,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "framework": sorted(frameworks) or ["unknown"],
            "total_endpoints": len(endpoints),
            "red_teamable": red_teamable,
            "unreachable": unreachable,
            "scanner": "raven-skill-scanner",
        },
        "endpoints": endpoints,
    }
