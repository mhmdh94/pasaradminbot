import time
import httpx
from typing import Optional, Dict, Any, List
from bot.database import db


class PasarGuardAPI:
    def __init__(self, panel: Dict):
        self.panel = panel
        self.base_url = panel["url"].rstrip("/")
        self.username = panel["username"]
        self.password = panel["password"]
        self.token = panel.get("token")
        self.token_time = panel.get("token_time") or 0

    async def _get_token(self) -> Optional[str]:
        if self.token and (time.time() - self.token_time) < 3000:
            return self.token
        async with httpx.AsyncClient(verify=False, timeout=20.0) as client:
            try:
                resp = await client.post(
                    f"{self.base_url}/api/admin/token",
                    data={
                        "username": self.username,
                        "password": self.password,
                        "grant_type": "password",
                    },
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    self.token = data.get("access_token")
                    self.token_time = int(time.time())
                    await db.update_panel_token(self.panel["id"], self.token, self.token_time)
                    return self.token
                print(f"[PG] Token {resp.status_code}: {resp.text[:300]}")
                return None
            except Exception as e:
                print(f"[PG] Token error: {e}")
                return None

    async def _request(self, method: str, path: str, **kwargs) -> Optional[Dict]:
        token = await self._get_token()
        if not token:
            return {"error": True, "detail": "token failed"}
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {token}"
        headers["Accept"] = "application/json"
        if "json" in kwargs:
            headers["Content-Type"] = "application/json"
        async with httpx.AsyncClient(verify=False, timeout=25.0) as client:
            try:
                resp = await client.request(
                    method, f"{self.base_url}{path}", headers=headers, **kwargs
                )
                if resp.status_code in (200, 201):
                    if not resp.content:
                        return {}
                    return resp.json()
                print(f"[PG] {method} {path} -> {resp.status_code}: {resp.text[:400]}")
                return {"error": True, "status": resp.status_code, "detail": resp.text[:500]}
            except Exception as e:
                print(f"[PG] Request error: {e}")
                return {"error": True, "detail": str(e)}

    def _pick_admin(self, data: Any, username: str) -> Optional[Dict]:
        if not data or (isinstance(data, dict) and data.get("error")):
            return None
        items: List[Dict] = []
        if isinstance(data, list):
            items = data
        elif isinstance(data, dict):
            for key in ("admins", "items", "data", "results"):
                if isinstance(data.get(key), list):
                    items = data[key]
                    break
            if not items and data.get("username"):
                items = [data]
        uname = username.lower()
        for a in items:
            if isinstance(a, dict) and str(a.get("username", "")).lower() == uname:
                return a
        return None

    async def get_admin(self, username: str) -> Optional[Dict]:
        """Find panel admin by username via list API (official way)."""
        # Primary: GET /api/admins?username=
        for params in (
            {"username": username, "limit": 50},
            {"usernames": username, "limit": 50},
        ):
            result = await self._request("GET", "/api/admins", params=params)
            found = self._pick_admin(result, username)
            if found:
                return found

        # Fallback: simple list
        result = await self._request(
            "GET", "/api/admins/simple", params={"search": username, "limit": 50, "all": True}
        )
        found = self._pick_admin(result, username)
        if found:
            # simple may only have id/username — fetch full via list by id
            aid = found.get("id")
            if aid is not None:
                full = await self._request("GET", "/api/admins", params={"ids": aid})
                full_found = self._pick_admin(full, username)
                if full_found:
                    return full_found
            return found

        return {"error": True, "detail": "admin not found"}

    async def modify_admin(self, username: str, data: Dict) -> Optional[Dict]:
        for path in (
            f"/api/admin/by-username/{username}",
            f"/api/admin/{username}",
        ):
            result = await self._request("PUT", path, json=data)
            if result and not result.get("error"):
                return result
        return result

    async def add_volume_to_admin(self, username: str, extra_gb: int) -> Dict[str, Any]:
        admin = await self.get_admin(username)
        if not admin or admin.get("error"):
            return {"success": False, "message": f"ادمین «{username}» در پنل پیدا نشد."}

        current_limit = admin.get("data_limit")
        if current_limit is None:
            current_limit = 0
        extra_bytes = int(extra_gb) * 1024 * 1024 * 1024
        new_limit = int(current_limit or 0) + extra_bytes

        result = await self.modify_admin(username, {"data_limit": new_limit})
        if result and not result.get("error"):
            used = admin.get("used_traffic") or 0
            return {
                "success": True,
                "message": f"✅ {extra_gb} گیگ به ادمین «{username}» اضافه شد.",
                "old_limit_gb": round((current_limit or 0) / (1024**3), 2),
                "new_limit_gb": round(new_limit / (1024**3), 2),
                "used_gb": round(used / (1024**3), 2),
            }
        detail = (result or {}).get("detail", "unknown")
        return {"success": False, "message": f"خطا در افزودن حجم: {detail}"}

    async def test_connection(self) -> Dict[str, Any]:
        token = await self._get_token()
        if not token:
            return {"success": False, "message": "خطا در توکن. یوزرنیم/پسورد پنل را چک کنید."}
        me = await self._request("GET", "/api/admin")
        if me and not me.get("error"):
            return {
                "success": True,
                "message": f"✅ اتصال موفق — لاگین به عنوان: {me.get('username', '?')}",
            }
        return {"success": True, "message": "✅ توکن دریافت شد."}


async def get_panel_api(panel_id: int) -> Optional[PasarGuardAPI]:
    panel = await db.get_panel(panel_id)
    if not panel:
        return None
    return PasarGuardAPI(panel)
