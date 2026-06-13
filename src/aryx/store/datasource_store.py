"""CRUD for datasource registry + secret audit log (Slice 2).

Secrets are Fernet-encrypted in datasource_secrets and stored as opaque
ciphertext here; this module never logs or returns plaintext. Every
decrypt-for-use path writes an aryx_secret_audit row so we have a full
trail of who used which secret when.
"""
from __future__ import annotations

import logging
from typing import Any

import psycopg
from psycopg.types.json import Json

from aryx import datasource_secrets
from aryx.queries import load
from aryx.store.pool import get_pool

logger = logging.getLogger(__name__)


class DatasourceStore:
    """Registry of named datasources per workspace, with encrypted secrets."""

    def __init__(self, dsn: str) -> None:
        self._pool = get_pool(dsn)

    def add(self, workspace_id: int, name: str, kind: str,
            config: dict[str, Any], secret: str) -> dict[str, Any]:
        """Encrypt the secret then persist the datasource row."""
        cipher = datasource_secrets.encrypt(secret)
        mask = datasource_secrets.mask(secret)
        with self._pool.connection() as conn, conn.cursor() as cur:
            cur.execute(load("insert_datasource"), {
                "workspace_id": int(workspace_id), "name": name,
                "kind": kind, "config_json": Json(config or {}),
                "secret_cipher": cipher, "secret_mask": mask})
            row = cur.fetchone()
        logger.info("datasource added id=%s ws=%s kind=%s",
                    row[0], workspace_id, kind)
        return self._row(row, omit_cipher=True)

    def list(self, workspace_id: int) -> list[dict[str, Any]]:
        """List all datasources in a workspace (never returns ciphertext)."""
        with self._pool.connection() as conn, conn.cursor() as cur:
            cur.execute(load("select_datasources"),
                        {"workspace_id": int(workspace_id)})
            return [self._row(r, omit_cipher=True) for r in cur.fetchall()]

    def get(self, datasource_id: int) -> dict[str, Any] | None:
        """Return a single datasource row (callers may decrypt via secret_of)."""
        with self._pool.connection() as conn, conn.cursor() as cur:
            cur.execute(load("select_datasource_by_id"),
                        {"id": int(datasource_id)})
            row = cur.fetchone()
        if not row:
            return None
        return self._row(row, omit_cipher=True)

    def delete(self, datasource_id: int) -> None:
        """Hard-delete a datasource and its audit trail (FK cascades)."""
        with self._pool.connection() as conn, conn.cursor() as cur:
            cur.execute(load("delete_datasource_row"),
                        {"id": int(datasource_id)})
        logger.info("datasource deleted id=%s", datasource_id)

    def secret_of(self, datasource_id: int, actor: str) -> str:
        """Decrypt and return the secret; logs an audit row before returning."""
        with self._pool.connection() as conn, conn.cursor() as cur:
            cur.execute(load("select_datasource_by_id"),
                        {"id": int(datasource_id)})
            row = cur.fetchone()
            if not row:
                raise ValueError(f"datasource {datasource_id} not found")
            cur.execute(load("insert_secret_audit"), {
                "datasource_id": int(datasource_id),
                "action": "decrypt", "actor": actor})
        return datasource_secrets.decrypt(row[5] or "")

    @staticmethod
    def _row(row: tuple, omit_cipher: bool) -> dict[str, Any]:
        """Project a row tuple to a dict; cipher is never returned over API.

        Two row shapes:
          - 7 cols (insert / list): id, ws, name, kind, config, mask, ts
          - 8 cols (get by id):     id, ws, name, kind, config, cipher, mask, ts
        """
        has_cipher = len(row) >= 8
        mask_idx = 6 if has_cipher else 5
        data = {"id": row[0], "workspace_id": row[1], "name": row[2],
                "kind": row[3], "config": row[4] or {},
                "secret_mask": row[mask_idx], "created_at": row[-1]}
        if not omit_cipher and has_cipher:
            data["secret_cipher"] = row[5]
        return data


def open_url(kind: str, config: dict, secret: str) -> str:
    """Build a SQLAlchemy URL from datasource config + decrypted secret."""
    drivers = {
        "postgresql": "postgresql+psycopg", "postgres": "postgresql+psycopg",
        "mysql": "mysql+pymysql", "mariadb": "mysql+pymysql",
        "oracle": "oracle+oracledb", "sqlite": "sqlite",
    }
    if kind == "sqlite":
        return f"sqlite:///{config.get('database', '')}"
    driver = drivers.get(kind)
    if not driver:
        raise ValueError(f"unsupported datasource kind: {kind}")
    user = config.get("user", "")
    auth = f"{user}:{secret}@" if user else ""
    port = f":{config['port']}" if config.get("port") else ""
    return (f"{driver}://{auth}{config.get('host', '')}{port}"
            f"/{config.get('database', '')}")
