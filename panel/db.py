"""SQLite 数据层：建表、设置、节点、订阅用户、凭据、会话。

模型：
    subs     —— 订阅用户（一个人 / 一份订阅链接），持有 token、到期时间、流量额度
    clients  —— 该用户在某一个节点上的凭据（uuid），一个订阅可横跨多个节点
    nodes    —— 入站（Vision 或 XHTTP），含 REALITY 密钥

流量记在 clients 上，订阅总额度按 clients 汇总。
"""

from __future__ import annotations

import json
import os
import socket
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from .util import new_uuid, now, rand_hex, rand_token

DEFAULT_SETTINGS: dict[str, str] = {
    "panel_name": "Reality Panel",
    # 订阅/分享链接里使用的公网地址，留空则自动探测
    "public_host": "",
    # 新建节点时的默认 SNI（必须是有有效证书的自有域名）
    "default_sni": "",
    # REALITY 回落目标：本机 nginx
    "dest": "127.0.0.1:8003",
    "xver": "1",
    "fingerprint": "chrome",
    # Xray 相关
    "xray_bin": "xray",
    "xray_config": "/usr/local/etc/xray/config.json",
    "xray_api": "127.0.0.1:10085",
    "xray_service": "xray",
    "restart_cmd": "sudo -n systemctl restart xray",
    "status_cmd": "systemctl is-active xray",
    "xray_log": "/var/log/xray/error.log",
    # 自偷自 nginx
    "nginx_conf": "/etc/nginx/conf.d/reality-selfsteal.conf",
    "nginx_upstream": "https://www.lovelive-anime.jp",
    "nginx_listen": "127.0.0.1:8003",
    "panel_addr": "127.0.0.1:8080",
    "cert_dir": "/etc/letsencrypt/live",
    # 订阅
    "sub_base": "",
    "sub_interval_hours": "12",
    # 访问白名单（空 = 不限制）
    "access_allowlist": "",
    # 始终允许 127.0.0.1 / ::1（SSH 隧道、本机 nginx 需要）
    "access_allowlist_loopback": "1",
    # 是否同时限制 /sub/ 订阅接口（默认否，否则客户端拉不到订阅）
    "access_allowlist_sub": "0",
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at    INTEGER NOT NULL,
    last_login_at INTEGER
);

CREATE TABLE IF NOT EXISTS sessions (
    token      TEXT PRIMARY KEY,
    user_id    INTEGER NOT NULL,
    csrf       TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    expires_at INTEGER NOT NULL,
    ip         TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS servers (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT NOT NULL,
    kind         TEXT NOT NULL DEFAULT 'agent',
    address      TEXT NOT NULL DEFAULT '',
    agent_url    TEXT NOT NULL DEFAULT '',
    token        TEXT NOT NULL DEFAULT '',
    enabled      INTEGER NOT NULL DEFAULT 1,
    remark       TEXT NOT NULL DEFAULT '',
    last_seen_at INTEGER NOT NULL DEFAULT 0,
    last_status  TEXT NOT NULL DEFAULT '',
    last_error   TEXT NOT NULL DEFAULT '',
    created_at   INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS nodes (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    server_id    INTEGER NOT NULL DEFAULT 1,
    name         TEXT NOT NULL,
    transport    TEXT NOT NULL DEFAULT 'vision',
    listen       TEXT NOT NULL DEFAULT '0.0.0.0',
    port         INTEGER NOT NULL,
    sni          TEXT NOT NULL,
    dest         TEXT NOT NULL DEFAULT '127.0.0.1:8003',
    xver         INTEGER NOT NULL DEFAULT 1,
    private_key  TEXT NOT NULL,
    public_key   TEXT NOT NULL,
    short_ids    TEXT NOT NULL DEFAULT '[]',
    xhttp_path   TEXT NOT NULL DEFAULT '/',
    xhttp_mode   TEXT NOT NULL DEFAULT 'auto',
    fingerprint  TEXT NOT NULL DEFAULT 'chrome',
    enabled      INTEGER NOT NULL DEFAULT 1,
    remark       TEXT NOT NULL DEFAULT '',
    created_at   INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS subs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    token       TEXT NOT NULL UNIQUE,
    enabled     INTEGER NOT NULL DEFAULT 1,
    expires_at  INTEGER NOT NULL DEFAULT 0,
    quota_bytes INTEGER NOT NULL DEFAULT 0,
    note        TEXT NOT NULL DEFAULT '',
    created_at  INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS clients (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    sub_id       INTEGER NOT NULL REFERENCES subs(id) ON DELETE CASCADE,
    node_id      INTEGER NOT NULL REFERENCES nodes(id) ON DELETE CASCADE,
    uuid         TEXT NOT NULL,
    enabled      INTEGER NOT NULL DEFAULT 1,
    up_bytes     INTEGER NOT NULL DEFAULT 0,
    down_bytes   INTEGER NOT NULL DEFAULT 0,
    last_seen_at INTEGER NOT NULL DEFAULT 0,
    created_at   INTEGER NOT NULL,
    UNIQUE(sub_id, node_id)
);

CREATE INDEX IF NOT EXISTS idx_clients_sub ON clients(sub_id);
CREATE INDEX IF NOT EXISTS idx_clients_node ON clients(node_id);
CREATE INDEX IF NOT EXISTS idx_sessions_exp ON sessions(expires_at);

CREATE TABLE IF NOT EXISTS stat_marks (
    email TEXT PRIMARY KEY,
    value INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS audit (
    id     INTEGER PRIMARY KEY AUTOINCREMENT,
    at     INTEGER NOT NULL,
    actor  TEXT NOT NULL DEFAULT '',
    ip     TEXT NOT NULL DEFAULT '',
    action TEXT NOT NULL,
    target TEXT NOT NULL DEFAULT '',
    detail TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_audit_at ON audit(at);
"""


def detect_public_ip() -> str:
    """通过一次 UDP connect 探测本机出口 IPv4（不会真的发包）。"""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.settimeout(1.0)
            s.connect(("1.1.1.1", 80))
            ip = s.getsockname()[0]
        if ip and not ip.startswith(("127.", "169.254.", "0.")):
            return ip
    except OSError:
        pass
    return ""


class Database:
    def __init__(self, path: str | os.PathLike[str]):
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    @contextmanager
    def cursor(self) -> Iterator[sqlite3.Connection]:
        conn = self.connect()
        try:
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    def init(self) -> None:
        with self.cursor() as conn:
            conn.executescript(SCHEMA)

            # v2 -> v3：给老库补 servers / nodes.server_id
            columns = {row["name"] for row in conn.execute("PRAGMA table_info(nodes)")}
            if "server_id" not in columns:
                conn.execute("ALTER TABLE nodes ADD COLUMN server_id INTEGER NOT NULL DEFAULT 1")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_nodes_server ON nodes(server_id)")

            if conn.execute("SELECT COUNT(*) FROM servers").fetchone()[0] == 0:
                row = conn.execute("SELECT value FROM meta WHERE key='public_host'").fetchone()
                address = (row["value"] if row else "") or ""
                conn.execute(
                    "INSERT INTO servers(id, name, kind, address, agent_url, token, enabled, created_at)"
                    " VALUES(1, '本机', 'local', ?, '', '', 1, ?)",
                    (address, now()),
                )
            conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES('schema_version', '3')")


class Store:
    """面向业务的读写封装，全部返回普通 dict / list。"""

    def __init__(self, db: Database):
        self.db = db
        self._public_ip: str | None = None

    # ------------------------------------------------------------ 设置

    def settings(self) -> dict[str, str]:
        merged = dict(DEFAULT_SETTINGS)
        with self.db.cursor() as conn:
            for row in conn.execute("SELECT key, value FROM meta"):
                if row["key"] in merged:
                    merged[row["key"]] = row["value"]
        return merged

    def setting(self, key: str, default: str = "") -> str:
        with self.db.cursor() as conn:
            row = conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row["value"] if row else DEFAULT_SETTINGS.get(key, default)

    def meta(self, key: str, default: str = "") -> str:
        with self.db.cursor() as conn:
            row = conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default

    def set_meta(self, key: str, value: str) -> None:
        with self.db.cursor() as conn:
            conn.execute(
                "INSERT INTO meta(key, value) VALUES(?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, str(value)),
            )

    def save_settings(self, data: dict[str, Any]) -> dict[str, str]:
        with self.db.cursor() as conn:
            for key, value in data.items():
                if key not in DEFAULT_SETTINGS:
                    continue
                conn.execute(
                    "INSERT INTO meta(key, value) VALUES(?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                    (key, str(value)),
                )
        return self.settings()

    def public_host(self) -> str:
        configured = self.setting("public_host").strip()
        if configured:
            return configured
        if self._public_ip is None:
            self._public_ip = detect_public_ip()
        return self._public_ip or "127.0.0.1"

    # ------------------------------------------------------------ 服务器

    @staticmethod
    def _server(row: sqlite3.Row) -> dict:
        server = dict(row)
        server["enabled"] = bool(server.get("enabled"))
        return server

    def servers(self, only_enabled: bool = False) -> list[dict]:
        sql = (
            "SELECT s.*, (SELECT COUNT(*) FROM nodes n WHERE n.server_id=s.id) AS node_count"
            " FROM servers s"
        )
        if only_enabled:
            sql += " WHERE s.enabled=1"
        sql += " ORDER BY s.id"
        with self.db.cursor() as conn:
            return [self._server(r) for r in conn.execute(sql)]

    def server(self, server_id: int) -> dict | None:
        with self.db.cursor() as conn:
            row = conn.execute("SELECT * FROM servers WHERE id=?", (server_id,)).fetchone()
        return self._server(row) if row else None

    def local_server(self) -> dict | None:
        with self.db.cursor() as conn:
            row = conn.execute("SELECT * FROM servers WHERE kind='local' ORDER BY id LIMIT 1").fetchone()
        return self._server(row) if row else None

    def create_server(self, data: dict) -> dict:
        with self.db.cursor() as conn:
            cur = conn.execute(
                "INSERT INTO servers(name, kind, address, agent_url, token, enabled, remark, created_at)"
                " VALUES(?,?,?,?,?,?,?,?)",
                (
                    data["name"], data.get("kind") or "agent", data.get("address") or "",
                    data.get("agent_url") or "", data.get("token") or rand_token(24),
                    1 if data.get("enabled", True) else 0, data.get("remark") or "", now(),
                ),
            )
            server_id = int(cur.lastrowid)
        server = self.server(server_id)
        assert server is not None
        return server

    def update_server(self, server_id: int, data: dict) -> dict | None:
        fields, values = [], []
        allowed = {"name", "address", "agent_url", "token", "enabled", "remark"}
        for key, value in data.items():
            if key in allowed:
                fields.append(f"{key}=?")
                values.append(int(value) if key == "enabled" else value)
        if not fields:
            return self.server(server_id)
        values.append(server_id)
        with self.db.cursor() as conn:
            conn.execute(f"UPDATE servers SET {', '.join(fields)} WHERE id=?", values)
        return self.server(server_id)

    def delete_server(self, server_id: int) -> None:
        with self.db.cursor() as conn:
            conn.execute("DELETE FROM nodes WHERE server_id=?", (server_id,))
            conn.execute("DELETE FROM servers WHERE id=?", (server_id,))

    def touch_server(self, server_id: int, status: str, error: str = "") -> None:
        with self.db.cursor() as conn:
            conn.execute(
                "UPDATE servers SET last_seen_at=?, last_status=?, last_error=? WHERE id=?",
                (now(), status, error[:500], server_id),
            )

    def rotate_server_token(self, server_id: int) -> dict | None:
        with self.db.cursor() as conn:
            conn.execute("UPDATE servers SET token=? WHERE id=?", (rand_token(24), server_id))
        return self.server(server_id)

    # ------------------------------------------------------------ 用户/会话

    def user_count(self) -> int:
        with self.db.cursor() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM users").fetchone()[0])

    def create_user(self, username: str, password_hash: str) -> int:
        with self.db.cursor() as conn:
            cur = conn.execute(
                "INSERT INTO users(username, password_hash, created_at) VALUES(?,?,?)",
                (username, password_hash, now()),
            )
            return int(cur.lastrowid)

    def user_by_name(self, username: str) -> dict | None:
        with self.db.cursor() as conn:
            row = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        return dict(row) if row else None

    def user_by_id(self, uid: int) -> dict | None:
        with self.db.cursor() as conn:
            row = conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
        return dict(row) if row else None

    def touch_login(self, uid: int) -> None:
        with self.db.cursor() as conn:
            conn.execute("UPDATE users SET last_login_at=? WHERE id=?", (now(), uid))

    def set_password(self, uid: int, password_hash: str) -> None:
        with self.db.cursor() as conn:
            conn.execute("UPDATE users SET password_hash=? WHERE id=?", (password_hash, uid))

    def create_session(self, uid: int, ip: str, ttl: int = 7 * 86400) -> tuple[str, str]:
        token, csrf = rand_token(32), rand_token(24)
        ts = now()
        with self.db.cursor() as conn:
            conn.execute(
                "INSERT INTO sessions(token, user_id, csrf, created_at, expires_at, ip) "
                "VALUES(?,?,?,?,?,?)",
                (token, uid, csrf, ts, ts + ttl, ip),
            )
            conn.execute("DELETE FROM sessions WHERE expires_at < ?", (ts,))
        return token, csrf

    def session(self, token: str) -> dict | None:
        if not token:
            return None
        with self.db.cursor() as conn:
            row = conn.execute(
                "SELECT * FROM sessions WHERE token=? AND expires_at > ?", (token, now())
            ).fetchone()
        return dict(row) if row else None

    def drop_session(self, token: str) -> None:
        with self.db.cursor() as conn:
            conn.execute("DELETE FROM sessions WHERE token=?", (token,))

    def drop_all_sessions(self, uid: int) -> None:
        with self.db.cursor() as conn:
            conn.execute("DELETE FROM sessions WHERE user_id=?", (uid,))

    # ------------------------------------------------------------ 节点

    @staticmethod
    def _node(row: sqlite3.Row) -> dict:
        node = dict(row)
        try:
            node["short_ids"] = json.loads(node.get("short_ids") or "[]")
        except json.JSONDecodeError:
            node["short_ids"] = []
        node["enabled"] = bool(node.get("enabled"))
        return node

    def nodes(self, only_enabled: bool = False, server_id: int | None = None) -> list[dict]:
        sql = (
            "SELECT n.*, s.name AS server_name, s.kind AS server_kind,"
            " s.address AS server_address FROM nodes n JOIN servers s ON s.id=n.server_id"
        )
        clauses: list[str] = []
        args: list = []
        if only_enabled:
            clauses.append("n.enabled=1")
        if server_id is not None:
            clauses.append("n.server_id=?")
            args.append(server_id)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY n.id"
        with self.db.cursor() as conn:
            return [self._node(r) for r in conn.execute(sql, args)]

    def node(self, node_id: int) -> dict | None:
        with self.db.cursor() as conn:
            row = conn.execute(
                "SELECT n.*, s.name AS server_name, s.kind AS server_kind,"
                " s.address AS server_address FROM nodes n JOIN servers s ON s.id=n.server_id"
                " WHERE n.id=?",
                (node_id,),
            ).fetchone()
        return self._node(row) if row else None

    def node_by_port(self, port: int, server_id: int = 1, exclude_id: int | None = None) -> dict | None:
        with self.db.cursor() as conn:
            if exclude_id is None:
                row = conn.execute(
                    "SELECT * FROM nodes WHERE port=? AND server_id=?", (port, server_id)
                ).fetchone()
            else:
                row = conn.execute(
                    "SELECT * FROM nodes WHERE port=? AND server_id=? AND id<>?",
                    (port, server_id, exclude_id),
                ).fetchone()
        return self._node(row) if row else None

    def create_node(self, data: dict) -> dict:
        short_ids = json.dumps(data.get("short_ids") or [rand_hex(8)], ensure_ascii=False)
        with self.db.cursor() as conn:
            cur = conn.execute(
                "INSERT INTO nodes(server_id, name, transport, listen, port, sni, dest, xver, private_key,"
                " public_key, short_ids, xhttp_path, xhttp_mode, fingerprint, enabled, remark, created_at)"
                " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    int(data.get("server_id") or 1),
                    data["name"],
                    data["transport"],
                    data.get("listen") or "0.0.0.0",
                    int(data["port"]),
                    data["sni"],
                    data.get("dest") or self.setting("dest"),
                    int(data.get("xver", self.setting("xver") or 1)),
                    data["private_key"],
                    data["public_key"],
                    short_ids,
                    data.get("xhttp_path") or "/",
                    data.get("xhttp_mode") or "auto",
                    data.get("fingerprint") or self.setting("fingerprint"),
                    1 if data.get("enabled", True) else 0,
                    data.get("remark") or "",
                    now(),
                ),
            )
            node_id = int(cur.lastrowid)
        node = self.node(node_id)
        assert node is not None
        return node

    def update_node(self, node_id: int, data: dict) -> dict | None:
        fields, values = [], []
        allowed = {
            "server_id", "name", "transport", "listen", "port", "sni", "dest", "xver", "private_key",
            "public_key", "xhttp_path", "xhttp_mode", "fingerprint", "remark", "enabled",
        }
        for key, value in data.items():
            if key == "short_ids":
                fields.append("short_ids=?")
                values.append(json.dumps(value or [], ensure_ascii=False))
            elif key in allowed:
                fields.append(f"{key}=?")
                values.append(int(value) if key in ("enabled", "port", "xver", "server_id") else value)
        if not fields:
            return self.node(node_id)
        values.append(node_id)
        with self.db.cursor() as conn:
            conn.execute(f"UPDATE nodes SET {', '.join(fields)} WHERE id=?", values)
        return self.node(node_id)

    def delete_node(self, node_id: int) -> None:
        with self.db.cursor() as conn:
            conn.execute("DELETE FROM nodes WHERE id=?", (node_id,))

    # ------------------------------------------------------------ 订阅用户

    @staticmethod
    def _sub(row: sqlite3.Row) -> dict:
        sub = dict(row)
        sub["enabled"] = bool(sub.get("enabled"))
        return sub

    def subs(self) -> list[dict]:
        sql = (
            "SELECT s.*, "
            " (SELECT COUNT(*) FROM clients c WHERE c.sub_id=s.id) AS node_count,"
            " (SELECT COALESCE(SUM(c.up_bytes+c.down_bytes),0) FROM clients c WHERE c.sub_id=s.id) AS used_bytes"
            " FROM subs s ORDER BY s.id"
        )
        with self.db.cursor() as conn:
            return [self._sub(r) for r in conn.execute(sql)]

    def sub(self, sub_id: int) -> dict | None:
        with self.db.cursor() as conn:
            row = conn.execute("SELECT * FROM subs WHERE id=?", (sub_id,)).fetchone()
            if not row:
                return None
            sub = self._sub(row)
            stats = conn.execute(
                "SELECT COUNT(*) AS n, COALESCE(SUM(up_bytes+down_bytes),0) AS used"
                " FROM clients WHERE sub_id=?",
                (sub_id,),
            ).fetchone()
        sub["node_count"] = int(stats["n"])
        sub["used_bytes"] = int(stats["used"])
        return sub

    def create_sub(self, data: dict, node_ids: list[int]) -> dict:
        with self.db.cursor() as conn:
            cur = conn.execute(
                "INSERT INTO subs(name, token, enabled, expires_at, quota_bytes, note, created_at)"
                " VALUES(?,?,?,?,?,?,?)",
                (
                    data["name"],
                    rand_token(24),
                    1 if data.get("enabled", True) else 0,
                    int(data.get("expires_at") or 0),
                    int(data.get("quota_bytes") or 0),
                    data.get("note") or "",
                    now(),
                ),
            )
            sub_id = int(cur.lastrowid)
            for node_id in node_ids:
                conn.execute(
                    "INSERT OR IGNORE INTO clients(sub_id, node_id, uuid, enabled, created_at)"
                    " VALUES(?,?,?,1,?)",
                    (sub_id, int(node_id), new_uuid(), now()),
                )
        sub = self.sub(sub_id)
        assert sub is not None
        return sub

    def update_sub(self, sub_id: int, data: dict) -> dict | None:
        fields, values = [], []
        allowed = {"name", "enabled", "expires_at", "quota_bytes", "note"}
        for key, value in data.items():
            if key in allowed:
                fields.append(f"{key}=?")
                values.append(int(value) if key in ("enabled", "expires_at", "quota_bytes") else value)
        if not fields:
            return self.sub(sub_id)
        values.append(sub_id)
        with self.db.cursor() as conn:
            conn.execute(f"UPDATE subs SET {', '.join(fields)} WHERE id=?", values)
            # 禁用订阅时同步禁用其全部凭据
            if data.get("enabled") is False:
                conn.execute("UPDATE clients SET enabled=0 WHERE sub_id=?", (sub_id,))
            elif data.get("enabled") is True:
                conn.execute("UPDATE clients SET enabled=1 WHERE sub_id=?", (sub_id,))
        return self.sub(sub_id)

    def delete_sub(self, sub_id: int) -> None:
        with self.db.cursor() as conn:
            conn.execute("DELETE FROM subs WHERE id=?", (sub_id,))

    def rotate_sub(self, sub_id: int) -> dict | None:
        with self.db.cursor() as conn:
            conn.execute("UPDATE subs SET token=? WHERE id=?", (rand_token(24), sub_id))
            conn.execute("UPDATE clients SET uuid=? WHERE sub_id=?", (new_uuid(), sub_id))
        return self.sub(sub_id)

    def set_sub_nodes(self, sub_id: int, node_ids: list[int]) -> dict | None:
        wanted = {int(n) for n in node_ids}
        with self.db.cursor() as conn:
            existing = {
                int(r["node_id"])
                for r in conn.execute("SELECT node_id FROM clients WHERE sub_id=?", (sub_id,))
            }
            for node_id in wanted - existing:
                conn.execute(
                    "INSERT OR IGNORE INTO clients(sub_id, node_id, uuid, enabled, created_at)"
                    " VALUES(?,?,?,1,?)",
                    (sub_id, node_id, new_uuid(), now()),
                )
            for node_id in existing - wanted:
                conn.execute("DELETE FROM clients WHERE sub_id=? AND node_id=?", (sub_id, node_id))
        return self.sub(sub_id)

    # ------------------------------------------------------------ 凭据

    @staticmethod
    def _client(row: sqlite3.Row) -> dict:
        client = dict(row)
        client["enabled"] = bool(client.get("enabled"))
        client["used_bytes"] = int(client.get("up_bytes") or 0) + int(client.get("down_bytes") or 0)
        return client

    def clients(self, sub_id: int | None = None) -> list[dict]:
        sql = (
            "SELECT c.*, n.name AS node_name, n.transport AS node_transport, n.port AS node_port,"
            " n.sni AS node_sni, s.name AS sub_name, s.token AS sub_token,"
            " s.enabled AS sub_enabled, s.expires_at AS sub_expires_at,"
            " sv.name AS server_name, sv.address AS server_address"
            " FROM clients c JOIN nodes n ON n.id=c.node_id JOIN subs s ON s.id=c.sub_id"
            " JOIN servers sv ON sv.id=n.server_id"
        )
        args: tuple = ()
        if sub_id is not None:
            sql += " WHERE c.sub_id=?"
            args = (sub_id,)
        sql += " ORDER BY c.id"
        with self.db.cursor() as conn:
            return [self._client(r) for r in conn.execute(sql, args)]

    def client(self, client_id: int) -> dict | None:
        with self.db.cursor() as conn:
            row = conn.execute(
                "SELECT c.*, n.name AS node_name, n.transport AS node_transport,"
                " n.port AS node_port, n.sni AS node_sni, s.name AS sub_name,"
                " s.token AS sub_token, sv.name AS server_name, sv.address AS server_address"
                " FROM clients c JOIN nodes n ON n.id=c.node_id"
                " JOIN subs s ON s.id=c.sub_id JOIN servers sv ON sv.id=n.server_id WHERE c.id=?",
                (client_id,),
            ).fetchone()
        return self._client(row) if row else None

    def sub_by_token(self, token: str) -> dict | None:
        """订阅链接入口：返回订阅 + 所有可用凭据（含节点与服务器）。"""
        with self.db.cursor() as conn:
            row = conn.execute("SELECT * FROM subs WHERE token=?", (token,)).fetchone()
            if not row:
                return None
            sub = self._sub(row)
            rows = conn.execute(
                "SELECT c.*, n.name AS node_name, n.transport, n.listen, n.port, n.sni,"
                " n.dest, n.xver, n.private_key, n.public_key, n.short_ids, n.xhttp_path,"
                " n.xhttp_mode, n.fingerprint, n.enabled AS node_enabled,"
                " sv.name AS server_name, sv.address AS server_address, sv.enabled AS server_enabled"
                " FROM clients c JOIN nodes n ON n.id=c.node_id"
                " JOIN servers sv ON sv.id=n.server_id"
                " WHERE c.sub_id=? ORDER BY n.id",
                (sub["id"],),
            ).fetchall()
        sub["clients"] = [dict(r) for r in rows]
        sub["used_bytes"] = sum(int(c["up_bytes"]) + int(c["down_bytes"]) for c in sub["clients"])
        return sub

    def add_traffic(self, client_id: int, up: int, down: int) -> None:
        if up <= 0 and down <= 0:
            return
        with self.db.cursor() as conn:
            conn.execute(
                "UPDATE clients SET up_bytes=up_bytes+?, down_bytes=down_bytes+?, last_seen_at=? "
                "WHERE id=?",
                (max(0, up), max(0, down), now(), client_id),
            )

    def stat_mark(self, email: str) -> int:
        with self.db.cursor() as conn:
            row = conn.execute("SELECT value FROM stat_marks WHERE email=?", (email,)).fetchone()
        return int(row["value"]) if row else 0

    def set_stat_mark(self, email: str, value: int) -> None:
        with self.db.cursor() as conn:
            conn.execute(
                "INSERT INTO stat_marks(email, value) VALUES(?,?) "
                "ON CONFLICT(email) DO UPDATE SET value=excluded.value",
                (email, int(value)),
            )

    # ------------------------------------------------------------ 审计 / 维护

    def audit(self, action: str, target: str = "", detail: str = "", actor: str = "", ip: str = "") -> None:
        with self.db.cursor() as conn:
            conn.execute(
                "INSERT INTO audit(at, actor, ip, action, target, detail) VALUES(?,?,?,?,?,?)",
                (now(), actor or "system", ip or "", action, target or "", detail or ""),
            )
            # 只保留最近 2000 条，避免数据库无限增长
            conn.execute("DELETE FROM audit WHERE id <= (SELECT MAX(id) FROM audit) - 2000")

    def audit_log(self, limit: int = 200) -> list[dict]:
        limit = max(1, min(int(limit), 1000))
        with self.db.cursor() as conn:
            rows = conn.execute(
                "SELECT * FROM audit ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    def reset_sub_traffic(self, sub_id: int) -> None:
        with self.db.cursor() as conn:
            ids = [int(r["id"]) for r in conn.execute("SELECT id FROM clients WHERE sub_id=?", (sub_id,))]
            conn.execute("UPDATE clients SET up_bytes=0, down_bytes=0 WHERE sub_id=?", (sub_id,))
            for client_id in ids:
                conn.execute(
                    "DELETE FROM stat_marks WHERE email IN (?,?)",
                    (f"c{client_id}:up", f"c{client_id}:down"),
                )

    def import_backup(self, payload: dict) -> dict:
        """用备份覆盖服务器 / 节点 / 订阅 / 凭据。返回导入数量。"""
        nodes = payload.get("nodes") or []
        subs = payload.get("subs") or []
        clients = payload.get("clients") or []
        servers_payload = payload.get("servers") or []
        with self.db.cursor() as conn:
            conn.execute("DELETE FROM clients")
            conn.execute("DELETE FROM subs")
            conn.execute("DELETE FROM nodes")
            conn.execute("DELETE FROM stat_marks")

            local = conn.execute(
                "SELECT id FROM servers WHERE kind='local' ORDER BY id LIMIT 1"
            ).fetchone()
            local_id = int(local["id"]) if local else 1
            conn.execute("DELETE FROM servers WHERE kind<>'local'")

            server_map: dict[int, int] = {}
            for server in servers_payload:
                old_id = int(server.get("id") or 0)
                if server.get("kind") == "local" or old_id == local_id:
                    server_map[old_id] = local_id
                    if server.get("address"):
                        conn.execute(
                            "UPDATE servers SET name=?, address=? WHERE id=?",
                            (server.get("name") or "本机", server["address"], local_id),
                        )
                    continue
                cur = conn.execute(
                    "INSERT INTO servers(name, kind, address, agent_url, token, enabled, remark,"
                    " last_seen_at, last_status, last_error, created_at)"
                    " VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        server["name"], "agent", server.get("address") or "",
                        server.get("agent_url") or "", server.get("token") or rand_token(24),
                        1 if server.get("enabled", True) else 0, server.get("remark") or "",
                        int(server.get("last_seen_at") or 0), server.get("last_status") or "",
                        server.get("last_error") or "", int(server.get("created_at") or now()),
                    ),
                )
                server_map[old_id] = int(cur.lastrowid)

            node_map: dict[int, int] = {}
            for node in nodes:
                server_id = server_map.get(int(node.get("server_id") or 0), local_id)
                cur = conn.execute(
                    "INSERT INTO nodes(server_id, name, transport, listen, port, sni, dest, xver,"
                    " private_key, public_key, short_ids, xhttp_path, xhttp_mode, fingerprint,"
                    " enabled, remark, created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        server_id, node["name"], node["transport"], node.get("listen") or "0.0.0.0",
                        int(node["port"]), node["sni"], node["dest"], int(node.get("xver") or 0),
                        node["private_key"], node["public_key"],
                        json.dumps(node.get("short_ids") or [], ensure_ascii=False),
                        node.get("xhttp_path") or "/", node.get("xhttp_mode") or "auto",
                        node.get("fingerprint") or "chrome", 1 if node.get("enabled", True) else 0,
                        node.get("remark") or "", int(node.get("created_at") or now()),
                    ),
                )
                node_map[int(node.get("id") or 0)] = int(cur.lastrowid)

            sub_map: dict[int, int] = {}
            for sub in subs:
                cur = conn.execute(
                    "INSERT INTO subs(name, token, enabled, expires_at, quota_bytes, note, created_at)"
                    " VALUES(?,?,?,?,?,?,?)",
                    (
                        sub["name"], sub.get("token") or rand_token(24),
                        1 if sub.get("enabled", True) else 0, int(sub.get("expires_at") or 0),
                        int(sub.get("quota_bytes") or 0), sub.get("note") or "",
                        int(sub.get("created_at") or now()),
                    ),
                )
                sub_map[int(sub.get("id") or 0)] = int(cur.lastrowid)

            imported_clients = 0
            for client in clients:
                sub_id = sub_map.get(int(client.get("sub_id") or 0))
                node_id = node_map.get(int(client.get("node_id") or 0))
                if not sub_id or not node_id:
                    continue
                conn.execute(
                    "INSERT OR IGNORE INTO clients(sub_id, node_id, uuid, enabled, up_bytes,"
                    " down_bytes, last_seen_at, created_at) VALUES(?,?,?,?,?,?,?,?)",
                    (
                        sub_id, node_id, client.get("uuid") or new_uuid(),
                        1 if client.get("enabled", True) else 0,
                        int(client.get("up_bytes") or 0), int(client.get("down_bytes") or 0),
                        int(client.get("last_seen_at") or 0), int(client.get("created_at") or now()),
                    ),
                )
                imported_clients += 1
        return {
            "servers": len(server_map),
            "nodes": len(node_map),
            "subs": len(sub_map),
            "clients": imported_clients,
        }

    # ------------------------------------------------------------ 统计

    def summary(self) -> dict:
        with self.db.cursor() as conn:
            servers = conn.execute("SELECT COUNT(*) FROM servers").fetchone()[0]
            servers_on = conn.execute("SELECT COUNT(*) FROM servers WHERE enabled=1").fetchone()[0]
            nodes = conn.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
            nodes_on = conn.execute("SELECT COUNT(*) FROM nodes WHERE enabled=1").fetchone()[0]
            subs = conn.execute("SELECT COUNT(*) FROM subs").fetchone()[0]
            subs_on = conn.execute("SELECT COUNT(*) FROM subs WHERE enabled=1").fetchone()[0]
            up = conn.execute("SELECT COALESCE(SUM(up_bytes),0) FROM clients").fetchone()[0]
            down = conn.execute("SELECT COALESCE(SUM(down_bytes),0) FROM clients").fetchone()[0]
            expiring = conn.execute(
                "SELECT COUNT(*) FROM subs WHERE expires_at>0 AND expires_at<?",
                (now() + 3 * 86400,),
            ).fetchone()[0]
        return {
            "servers": int(servers),
            "servers_enabled": int(servers_on),
            "nodes": int(nodes),
            "nodes_enabled": int(nodes_on),
            "subs": int(subs),
            "subs_enabled": int(subs_on),
            "up_bytes": int(up),
            "down_bytes": int(down),
            "expiring_soon": int(expiring),
        }

    def sweep(self) -> bool:
        """停用已过期 / 超额的订阅，返回是否有改动（需要重载 Xray）。"""
        changed = False
        ts = now()
        with self.db.cursor() as conn:
            rows = conn.execute(
                "SELECT s.id, s.expires_at, s.quota_bytes,"
                " (SELECT COALESCE(SUM(up_bytes+down_bytes),0) FROM clients c WHERE c.sub_id=s.id) AS used"
                " FROM subs s WHERE s.enabled=1"
            ).fetchall()
            for row in rows:
                expired = bool(row["expires_at"]) and row["expires_at"] < ts
                over = bool(row["quota_bytes"]) and row["used"] >= row["quota_bytes"]
                if expired or over:
                    conn.execute("UPDATE subs SET enabled=0 WHERE id=?", (row["id"],))
                    conn.execute("UPDATE clients SET enabled=0 WHERE sub_id=?", (row["id"],))
                    changed = True
        return changed
