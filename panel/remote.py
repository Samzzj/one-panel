"""主控到节点 agent 的 HTTP 客户端。"""

from __future__ import annotations

import json
import urllib.error
import urllib.request


class AgentClient:
    def __init__(self, server: dict):
        self.base = (server.get("agent_url") or "").rstrip("/")
        self.token = server.get("token") or ""

    def _call(self, method: str, path: str, payload: dict | None = None, timeout: int = 30) -> dict:
        if not self.base:
            return {"ok": False, "error": "该服务器还没有配置 agent 地址"}
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = urllib.request.Request(
            self.base + path,
            data=data,
            method=method,
            headers={
                "X-Agent-Token": self.token,
                "Content-Type": "application/json",
                "User-Agent": "one-panel-master",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read()
                result = json.loads(raw or b"{}")
                if isinstance(result, dict):
                    result.setdefault("ok", True)
                    return result
                return {"ok": False, "error": "节点返回了非对象 JSON"}
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", "replace")
            try:
                body = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                body = {}
            return {
                "ok": False,
                "error": body.get("error") or f"节点返回 HTTP {exc.code}",
                "status": exc.code,
            }
        except (urllib.error.URLError, OSError, TimeoutError, json.JSONDecodeError) as exc:
            return {"ok": False, "error": f"连接节点失败：{exc}"}

    def health(self) -> dict:
        return self._call("GET", "/health", timeout=10)

    def apply(self, config: dict) -> dict:
        return self._call("POST", "/apply", {"config": config}, timeout=60)

    def stats(self) -> dict:
        return self._call("GET", "/stats", timeout=20)

    def nginx(self, conf: str, path: str) -> dict:
        return self._call("POST", "/nginx", {"conf": conf, "path": path}, timeout=40)
