import time
import httpx
from typing import Optional, Dict, Any
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
        # Token valid for ~1 hour, refresh if older than 50 min
        if self.token and (time.time() - self.token_time) < 3000:
            return self.token

        async with httpx.AsyncClient(verify=False, timeout=15.0) as client:
            try:
                resp = await client.post(
                    f"{self.base_url}/api/admin/token",
                    data={
                        "username": self.username,
                        "password": self.password
                    },
                    headers={"Content-Type": "application/x-www-form-urlencoded"}
                )
                if resp.status_code == 200:
                    data = resp.json()
                    self.token = data.get("access_token")
                    self.token_time = int(time.time())
                    await db.update_panel_token(
                        self.panel["id"], self.token, self.token_time
                    )
                    return self.token
                else:
                    print(f"[PasarGuard] Token error: {resp.status_code} - {resp.text}")
                    return None
            except Exception as e:
                print(f"[PasarGuard] Token exception: {e}")
                return None

    async def _request(self, method: str, path: str, **kwargs) -> Optional[Dict]:
        token = await self._get_token()
        if not token:
            return None

        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {token}"
        headers["Accept"] = "application/json"
        if "json" in kwargs:
            headers["Content-Type"] = "application/json"

        async with httpx.AsyncClient(verify=False, timeout=20.0) as client:
            try:
                resp = await client.request(
                    method,
                    f"{self.base_url}{path}",
                    headers=headers,
                    **kwargs
                )
                if resp.status_code in (200, 201):
                    return resp.json()
                else:
                    print(f"[PasarGuard] {method} {path} -> {resp.status_code}: {resp.text}")
                    return {"error": True, "status": resp.status_code, "detail": resp.text}
            except Exception as e:
                print(f"[PasarGuard] Request exception: {e}")
                return {"error": True, "detail": str(e)}

    async def get_user(self, username: str) -> Optional[Dict]:
        return await self._request("GET", f"/api/user/{username}")

    async def modify_user(self, username: str, data: Dict) -> Optional[Dict]:
        return await self._request("PUT", f"/api/user/{username}", json=data)

    async def add_volume(self, username: str, extra_gb: int) -> Dict[str, Any]:
        """
        Add volume (in GB) to existing user.
        Returns dict with success status and message.
        """
        user = await self.get_user(username)
        if not user or user.get("error"):
            return {
                "success": False,
                "message": f"کاربر «{username}» در پنل پیدا نشد."
            }

        current_limit = user.get("data_limit") or 0  # bytes
        # 0 means unlimited
        if current_limit == 0:
            return {
                "success": False,
                "message": "حجم کاربر نامحدود است. نمی‌توان حجم اضافه کرد."
            }

        extra_bytes = extra_gb * 1024 * 1024 * 1024
        new_limit = current_limit + extra_bytes

        result = await self.modify_user(username, {"data_limit": new_limit})
        if result and not result.get("error"):
            return {
                "success": True,
                "message": f"✅ حجم {extra_gb} گیگابایت با موفقیت اضافه شد.",
                "old_limit_gb": round(current_limit / (1024**3), 2),
                "new_limit_gb": round(new_limit / (1024**3), 2),
                "used_gb": round((user.get("used_traffic") or 0) / (1024**3), 2)
            }
        else:
            detail = result.get("detail", "خطای ناشناخته") if result else "خطا در ارتباط با پنل"
            return {
                "success": False,
                "message": f"خطا در افزودن حجم: {detail}"
            }

    async def test_connection(self) -> Dict[str, Any]:
        token = await self._get_token()
        if token:
            return {"success": True, "message": "اتصال به پنل موفق بود."}
        return {"success": False, "message": "خطا در دریافت توکن. یوزرنیم یا پسورد اشتباه است."}


async def get_panel_api(panel_id: int) -> Optional[PasarGuardAPI]:
    panel = await db.get_panel(panel_id)
    if not panel:
        return None
    return PasarGuardAPI(panel)