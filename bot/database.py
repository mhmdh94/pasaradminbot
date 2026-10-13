import aiosqlite
import json
from typing import Optional, List, Dict, Any
from bot.config import settings


class Database:
    def __init__(self, db_path: str = settings.DB_PATH):
        self.db_path = db_path

    async def connect(self):
        self.conn = await aiosqlite.connect(self.db_path)
        self.conn.row_factory = aiosqlite.Row
        await self.create_tables()

    async def close(self):
        if hasattr(self, "conn"):
            await self.conn.close()

    async def create_tables(self):
        await self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            );

            CREATE TABLE IF NOT EXISTS panels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                url TEXT NOT NULL,
                username TEXT NOT NULL,
                password TEXT NOT NULL,
                token TEXT,
                token_time INTEGER DEFAULT 0,
                is_active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS volume_plans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                volume_gb INTEGER NOT NULL,
                price INTEGER NOT NULL,
                is_active INTEGER DEFAULT 1,
                sort_order INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                panel_id INTEGER NOT NULL,
                username TEXT NOT NULL,
                plan_id INTEGER NOT NULL,
                volume_gb INTEGER NOT NULL,
                price INTEGER NOT NULL,
                status TEXT DEFAULT 'pending',  -- pending, waiting_receipt, paid, rejected, cancelled
                receipt_file_id TEXT,
                admin_note TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (panel_id) REFERENCES panels(id),
                FOREIGN KEY (plan_id) REFERENCES volume_plans(id)
            );

            CREATE TABLE IF NOT EXISTS users_state (
                user_id INTEGER PRIMARY KEY,
                state TEXT,
                data TEXT
            );

            CREATE TABLE IF NOT EXISTS blocked_users (
                user_id INTEGER PRIMARY KEY,
                reason TEXT,
                failed_attempts INTEGER DEFAULT 0,
                blocked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS username_attempts (
                user_id INTEGER PRIMARY KEY,
                attempts INTEGER DEFAULT 0
            );
        """)
        await self.conn.commit()

        # Default settings
        await self.set_setting("card_number", settings.CARD_NUMBER)
        await self.set_setting("card_owner", settings.CARD_OWNER)

    # ---------- Settings ----------
    async def set_setting(self, key: str, value: str):
        await self.conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (key, value)
        )
        await self.conn.commit()

    async def get_setting(self, key: str, default: str = "") -> str:
        async with self.conn.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ) as cursor:
            row = await cursor.fetchone()
            return row["value"] if row else default

    # ---------- Panels ----------
    async def add_panel(self, name: str, url: str, username: str, password: str) -> int:
        cursor = await self.conn.execute(
            "INSERT INTO panels (name, url, username, password) VALUES (?, ?, ?, ?)",
            (name, url.rstrip("/"), username, password)
        )
        await self.conn.commit()
        return cursor.lastrowid

    async def get_panels(self, active_only: bool = True) -> List[Dict]:
        query = "SELECT * FROM panels"
        if active_only:
            query += " WHERE is_active = 1"
        query += " ORDER BY id"
        async with self.conn.execute(query) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def get_panel(self, panel_id: int) -> Optional[Dict]:
        async with self.conn.execute(
            "SELECT * FROM panels WHERE id = ?", (panel_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def update_panel_token(self, panel_id: int, token: str, token_time: int):
        await self.conn.execute(
            "UPDATE panels SET token = ?, token_time = ? WHERE id = ?",
            (token, token_time, panel_id)
        )
        await self.conn.commit()

    async def delete_panel(self, panel_id: int):
        await self.conn.execute("DELETE FROM panels WHERE id = ?", (panel_id,))
        await self.conn.commit()

    # ---------- Volume Plans ----------
    async def add_plan(self, title: str, volume_gb: int, price: int, sort_order: int = 0) -> int:
        cursor = await self.conn.execute(
            "INSERT INTO volume_plans (title, volume_gb, price, sort_order) VALUES (?, ?, ?, ?)",
            (title, volume_gb, price, sort_order)
        )
        await self.conn.commit()
        return cursor.lastrowid

    async def get_plans(self, active_only: bool = True) -> List[Dict]:
        query = "SELECT * FROM volume_plans"
        if active_only:
            query += " WHERE is_active = 1"
        query += " ORDER BY volume_gb ASC"
        async with self.conn.execute(query) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def get_plan(self, plan_id: int) -> Optional[Dict]:
        async with self.conn.execute(
            "SELECT * FROM volume_plans WHERE id = ?", (plan_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def update_plan(self, plan_id: int, **kwargs):
        fields = []
        values = []
        for k, v in kwargs.items():
            fields.append(f"{k} = ?")
            values.append(v)
        values.append(plan_id)
        await self.conn.execute(
            f"UPDATE volume_plans SET {', '.join(fields)} WHERE id = ?",
            values
        )
        await self.conn.commit()

    async def delete_plan(self, plan_id: int):
        await self.conn.execute("DELETE FROM volume_plans WHERE id = ?", (plan_id,))
        await self.conn.commit()

    # ---------- Orders ----------
    async def create_order(
        self, user_id: int, panel_id: int, username: str,
        plan_id: int, volume_gb: int, price: int
    ) -> int:
        cursor = await self.conn.execute(
            """INSERT INTO orders 
               (user_id, panel_id, username, plan_id, volume_gb, price, status)
               VALUES (?, ?, ?, ?, ?, ?, 'waiting_receipt')""",
            (user_id, panel_id, username, plan_id, volume_gb, price)
        )
        await self.conn.commit()
        return cursor.lastrowid

    async def get_order(self, order_id: int) -> Optional[Dict]:
        async with self.conn.execute(
            "SELECT * FROM orders WHERE id = ?", (order_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None

    async def update_order(self, order_id: int, **kwargs):
        fields = ["updated_at = CURRENT_TIMESTAMP"]
        values = []
        for k, v in kwargs.items():
            fields.append(f"{k} = ?")
            values.append(v)
        values.append(order_id)
        await self.conn.execute(
            f"UPDATE orders SET {', '.join(fields)} WHERE id = ?",
            values
        )
        await self.conn.commit()

    async def get_pending_orders(self) -> List[Dict]:
        async with self.conn.execute(
            "SELECT * FROM orders WHERE status IN ('waiting_receipt', 'pending') ORDER BY created_at DESC"
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def get_user_orders(self, user_id: int, limit: int = 10) -> List[Dict]:
        async with self.conn.execute(
            "SELECT * FROM orders WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
            (user_id, limit)
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    # ---------- User State (FSM simple) ----------
    async def set_state(self, user_id: int, state: str, data: dict = None):
        data_json = json.dumps(data or {}, ensure_ascii=False)
        await self.conn.execute(
            "INSERT OR REPLACE INTO users_state (user_id, state, data) VALUES (?, ?, ?)",
            (user_id, state, data_json)
        )
        await self.conn.commit()

    async def get_state(self, user_id: int) -> tuple[Optional[str], dict]:
        async with self.conn.execute(
            "SELECT state, data FROM users_state WHERE user_id = ?", (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return row["state"], json.loads(row["data"] or "{}")
            return None, {}

    async def clear_state(self, user_id: int):
        await self.conn.execute("DELETE FROM users_state WHERE user_id = ?", (user_id,))
        await self.conn.commit()

    # ---------- Block / attempts ----------
    async def is_blocked(self, user_id: int) -> bool:
        async with self.conn.execute(
            "SELECT 1 FROM blocked_users WHERE user_id = ?", (user_id,)
        ) as c:
            return await c.fetchone() is not None

    async def block_user(self, user_id: int, reason: str = ""):
        await self.conn.execute(
            "INSERT OR REPLACE INTO blocked_users (user_id, reason, failed_attempts) VALUES (?, ?, ?)",
            (user_id, reason, 10)
        )
        await self.conn.commit()

    async def unblock_user(self, user_id: int):
        await self.conn.execute("DELETE FROM blocked_users WHERE user_id = ?", (user_id,))
        await self.conn.execute("DELETE FROM username_attempts WHERE user_id = ?", (user_id,))
        await self.conn.commit()

    async def get_blocked_users(self):
        async with self.conn.execute("SELECT * FROM blocked_users ORDER BY blocked_at DESC") as c:
            return [dict(r) for r in await c.fetchall()]

    async def get_attempts(self, user_id: int) -> int:
        async with self.conn.execute(
            "SELECT attempts FROM username_attempts WHERE user_id = ?", (user_id,)
        ) as c:
            row = await c.fetchone()
            return int(row["attempts"]) if row else 0

    async def inc_attempts(self, user_id: int) -> int:
        current = await self.get_attempts(user_id)
        new_val = current + 1
        await self.conn.execute(
            "INSERT OR REPLACE INTO username_attempts (user_id, attempts) VALUES (?, ?)",
            (user_id, new_val)
        )
        await self.conn.commit()
        return new_val

    async def reset_attempts(self, user_id: int):
        await self.conn.execute("DELETE FROM username_attempts WHERE user_id = ?", (user_id,))
        await self.conn.commit()



db = Database()