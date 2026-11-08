"""多服务器下发与流量汇总。

- 本机：直接走 panel.xray（写配置 + systemctl 重启）
- 远程：把同一份 server 级配置推给节点 agent
"""

from __future__ import annotations

from .remote import AgentClient
from .xray import build_config


class Deployer:
    def __init__(self, store, xray):
        self.store = store
        self.xray = xray

    def apply_all(self) -> dict:
        results: list[dict] = []
        for server in self.store.servers():
            nodes = self.store.nodes(server_id=server["id"])

            if server["kind"] == "local":
                result = self.xray.apply(server_id=server["id"])
            else:
                if not nodes:
                    continue
                if server["enabled"]:
                    config, _ = self.xray.render(server["id"])
                else:
                    # 停用的服务器：推一份只剩 API 入站的空配置，让它立刻停止服务
                    config = build_config([], [], self.store.settings())
                result = AgentClient(server).apply(config)
                if not server["enabled"]:
                    result["purged"] = True
                    result["warnings"] = (result.get("warnings") or []) + ["该服务器已停用，配置已清空"]

            result["server_id"] = server["id"]
            result["server_name"] = server["name"]
            result["server_kind"] = server["kind"]
            ok = bool(result.get("ok"))
            detail = ""
            if not ok:
                detail = (
                    result.get("error")
                    or result.get("test_output")
                    or result.get("restart_output")
                    or "未知错误"
                )
            self.store.touch_server(server["id"], "ok" if ok else "error", detail)
            results.append(result)

        warnings: list[str] = []
        for result in results:
            warnings.extend(result.get("warnings") or [])
        return {
            "ok": bool(results) and all(bool(r.get("ok")) for r in results),
            "servers": results,
            "warnings": warnings,
        }

    def collect_stats(self) -> int:
        updated = 0
        for server in self.store.servers(only_enabled=True):
            if server["kind"] == "local":
                raw = self.xray.stats()
                ok = True
                error = ""
            else:
                data = AgentClient(server).stats()
                ok = bool(data.get("ok"))
                raw = data.get("users") or {}
                error = data.get("error") or ""

            if raw:
                updated += self.xray.collect_from(raw)
            if ok:
                self.store.touch_server(server["id"], "ok")
            else:
                self.store.touch_server(server["id"], "error", error or "统计失败")
        return updated

    def push_nginx(self, server: dict, conf: str, path: str) -> dict:
        if server["kind"] == "local":
            return {"ok": False, "error": "本机配置请按向导写入（面板没有 nginx 写权限）"}
        result = AgentClient(server).nginx(conf, path)
        self.store.touch_server(
            server["id"],
            "ok" if result.get("ok") else "error",
            "" if result.get("ok") else (result.get("error") or result.get("test_output") or ""),
        )
        return result
