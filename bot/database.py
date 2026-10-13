import aiosqlite
import os
from typing import Optional, List, Dict, Any
from bot.config import settings


class Database:
    def __init__(self):
        self.conn: Optional[aiosqlite.Connection] = None

    async def connect(self):
        os.makedirs(os.path.dirname(settings.DB_PATH), exist_ok=True)
        self.conn = await aiosqlite.connect(settings.DB_PATH)
        self.conn.row_factory = aiosqlite.Row
        await self.create_tables()

    async def close(self):
        if self.conn:
            await self.conn.close()

    async def create_tables(self):
        await self.conn.executescript("""
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
                plan_id INTEGER,
                volume_gb INTEGER NOT NULL,
                price INTEGER NOT NULL,
                status TEXT DEFAULT 'waiting_receipt',
                receipt_file_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            );

            CREATE TABLE IF NOT EXISTS bot_users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                full_name TEXT,
                phone TEXT,
                is_verified INTEGER DEFAULT 0,
                auto_approve INTEGER DEFAULT 0,
                total_paid INTEGER DEFAULT 0,
                total_volume_gb INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_start TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS user_panels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                panel_id INTEGER NOT NULL,
                admin_username TEXT NOT NULL,
                UNIQUE(user_id, panel_id, admin_username)
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

            CREATE TABLE IF NOT EXISTS volume_alerts_sent (
                user_id INTEGER NOT NULL,
                panel_id INTEGER NOT NULL,
                admin_username TEXT NOT NULL,
                threshold INTEGER NOT NULL,
                sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, panel_id, admin_username, threshold)
            );

            CREATE TABLE IF NOT EXISTS discount_codes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT UNIQUE NOT NULL,
                percent INTEGER NOT NULL,
                max_uses INTEGER DEFAULT 1,
                used_count INTEGER DEFAULT 0,
                is_active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS discount_uses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                order_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        await self.conn.commit()
        # defaults
        defaults = {
            "card_number": "6037-XXXX-XXXX-XXXX",
            "account_number": "",
            "card_owner": "نام صاحب کارت",
            "backup_interval_hours": "24",
            "bot_enabled": "1",
            "require_phone": "0",
            "require_iran_phone": "0",
            "require_verify": "0",
            "allow_buy": "1",
            "auto_approve_default": "0",
            "report_channel": "",
            "volume_check_hours": "6",
            "volume_thresholds": "80,85,90,95,100",
            "auto_approve_delay_minutes": "0",
        }
        for k, v in defaults.items():
            cur = await self.conn.execute("SELECT 1 FROM settings WHERE key=?", (k,))
            if not await cur.fetchone():
                await self.conn.execute(
                    "INSERT INTO settings (key, value) VALUES (?, ?)", (k, v)
                )
        await self.conn.commit()

    # settings
    async def get_setting(self, key: str, default: str = "") -> str:
        async with self.conn.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ) as c:
            row = await c.fetchone()
            return row["value"] if row else default

    async def set_setting(self, key: str, value: str):
        await self.conn.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value)
        )
        await self.conn.commit()

    # panels
    async def add_panel(self, name, url, username, password) -> int:
        cur = await self.conn.execute(
            "INSERT INTO panels (name, url, username, password) VALUES (?, ?, ?, ?)",
            (name, url, username, password),
        )
        await self.conn.commit()
        return cur.lastrowid

    async def get_panels(self, active_only=True) -> List[Dict]:
        q = "SELECT * FROM panels"
        if active_only:
            q += " WHERE is_active = 1"
        q += " ORDER BY id"
        async with self.conn.execute(q) as c:
            return [dict(r) for r in await c.fetchall()]

    async def get_panel(self, panel_id: int) -> Optional[Dict]:
        async with self.conn.execute(
            "SELECT * FROM panels WHERE id = ?", (panel_id,)
        ) as c:
            row = await c.fetchone()
            return dict(row) if row else None

    async def delete_panel(self, panel_id: int):
        await self.conn.execute("DELETE FROM panels WHERE id = ?", (panel_id,))
        await self.conn.commit()

    async def update_panel_token(self, panel_id: int, token: str, token_time: int):
        await self.conn.execute(
            "UPDATE panels SET token=?, token_time=? WHERE id=?",
            (token, token_time, panel_id),
        )
        await self.conn.commit()

    # plans
    async def add_plan(self, title, volume_gb, price) -> int:
        cur = await self.conn.execute(
            "INSERT INTO volume_plans (title, volume_gb, price) VALUES (?, ?, ?)",
            (title, volume_gb, price),
        )
        await self.conn.commit()
        return cur.lastrowid

    async def get_plans(self, active_only=True) -> List[Dict]:
        q = "SELECT * FROM volume_plans"
        if active_only:
            q += " WHERE is_active = 1"
        q += " ORDER BY volume_gb ASC"
        async with self.conn.execute(q) as c:
            return [dict(r) for r in await c.fetchall()]

    async def get_plan(self, plan_id: int) -> Optional[Dict]:
        async with self.conn.execute(
            "SELECT * FROM volume_plans WHERE id = ?", (plan_id,)
        ) as c:
            row = await c.fetchone()
            return dict(row) if row else None

    async def update_plan(self, plan_id: int, **kwargs):
        if not kwargs:
            return
        fields = ", ".join(f"{k}=?" for k in kwargs)
        await self.conn.execute(
            f"UPDATE volume_plans SET {fields} WHERE id=?",
            (*kwargs.values(), plan_id),
        )
        await self.conn.commit()

    async def delete_plan(self, plan_id: int):
        await self.conn.execute("DELETE FROM volume_plans WHERE id=?", (plan_id,))
        await self.conn.commit()

    # orders
    async def create_order(self, user_id, panel_id, username, plan_id, volume_gb, price) -> int:
        cur = await self.conn.execute(
            """INSERT INTO orders (user_id, panel_id, username, plan_id, volume_gb, price)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (user_id, panel_id, username, plan_id, volume_gb, price),
        )
        await self.conn.commit()
        return cur.lastrowid

    async def get_order(self, order_id: int) -> Optional[Dict]:
        async with self.conn.execute(
            "SELECT * FROM orders WHERE id=?", (order_id,)
        ) as c:
            row = await c.fetchone()
            return dict(row) if row else None

    async def update_order(self, order_id: int, **kwargs):
        if not kwargs:
            return
        fields = ", ".join(f"{k}=?" for k in kwargs)
        await self.conn.execute(
            f"UPDATE orders SET {fields}, updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (*kwargs.values(), order_id),
        )
        await self.conn.commit()

    async def get_pending_orders(self) -> List[Dict]:
        async with self.conn.execute(
            "SELECT * FROM orders WHERE status IN ('waiting_receipt','pending') ORDER BY created_at DESC"
        ) as c:
            return [dict(r) for r in await c.fetchall()]

    async def get_user_orders(self, user_id: int, limit=20) -> List[Dict]:
        async with self.conn.execute(
            "SELECT * FROM orders WHERE user_id=? ORDER BY created_at DESC LIMIT ?",
            (user_id, limit),
        ) as c:
            return [dict(r) for r in await c.fetchall()]

    async def user_stats(self, user_id: int) -> Dict:
        async with self.conn.execute(
            """SELECT COALESCE(SUM(CASE WHEN status='paid' THEN price ELSE 0 END),0) as total_paid,
                      COALESCE(SUM(CASE WHEN status='paid' THEN volume_gb ELSE 0 END),0) as total_volume,
                      COUNT(*) as order_count,
                      SUM(CASE WHEN status='paid' THEN 1 ELSE 0 END) as paid_count
               FROM orders WHERE user_id=?""",
            (user_id,),
        ) as c:
            row = await c.fetchone()
            return dict(row) if row else {"total_paid": 0, "total_volume": 0, "order_count": 0, "paid_count": 0}

    # bot users
    async def upsert_bot_user(self, user_id, username=None, full_name=None):
        await self.conn.execute(
            """INSERT INTO bot_users (user_id, username, full_name, last_start)
               VALUES (?, ?, ?, CURRENT_TIMESTAMP)
               ON CONFLICT(user_id) DO UPDATE SET
                 username=COALESCE(excluded.username, bot_users.username),
                 full_name=COALESCE(excluded.full_name, bot_users.full_name),
                 last_start=CURRENT_TIMESTAMP""",
            (user_id, username, full_name),
        )
        await self.conn.commit()

    async def get_bot_user(self, user_id: int) -> Optional[Dict]:
        async with self.conn.execute(
            "SELECT * FROM bot_users WHERE user_id=?", (user_id,)
        ) as c:
            row = await c.fetchone()
            return dict(row) if row else None

    async def update_bot_user(self, user_id: int, **kwargs):
        if not kwargs:
            return
        fields = ", ".join(f"{k}=?" for k in kwargs)
        await self.conn.execute(
            f"UPDATE bot_users SET {fields} WHERE user_id=?",
            (*kwargs.values(), user_id),
        )
        await self.conn.commit()

    # user panels assignment
    async def assign_user_panel(self, user_id, panel_id, admin_username):
        await self.conn.execute(
            """INSERT OR IGNORE INTO user_panels (user_id, panel_id, admin_username)
               VALUES (?, ?, ?)""",
            (user_id, panel_id, admin_username),
        )
        await self.conn.commit()

    async def remove_user_panel(self, user_id, panel_id, admin_username):
        await self.conn.execute(
            "DELETE FROM user_panels WHERE user_id=? AND panel_id=? AND admin_username=?",
            (user_id, panel_id, admin_username),
        )
        await self.conn.commit()

    async def get_user_panels(self, user_id: int) -> List[Dict]:
        async with self.conn.execute(
            """SELECT up.*, p.name as panel_name, p.url as panel_url
               FROM user_panels up JOIN panels p ON p.id = up.panel_id
               WHERE up.user_id=?""",
            (user_id,),
        ) as c:
            return [dict(r) for r in await c.fetchall()]

    async def get_all_user_panels(self) -> List[Dict]:
        async with self.conn.execute(
            """SELECT up.*, p.name as panel_name FROM user_panels up
               JOIN panels p ON p.id = up.panel_id"""
        ) as c:
            return [dict(r) for r in await c.fetchall()]

    # block / attempts
    async def is_blocked(self, user_id: int) -> bool:
        async with self.conn.execute(
            "SELECT 1 FROM blocked_users WHERE user_id=?", (user_id,)
        ) as c:
            return await c.fetchone() is not None

    async def block_user(self, user_id: int, reason: str = ""):
        await self.conn.execute(
            "INSERT OR REPLACE INTO blocked_users (user_id, reason, failed_attempts) VALUES (?,?,10)",
            (user_id, reason),
        )
        await self.conn.commit()

    async def unblock_user(self, user_id: int):
        await self.conn.execute("DELETE FROM blocked_users WHERE user_id=?", (user_id,))
        await self.conn.execute("DELETE FROM username_attempts WHERE user_id=?", (user_id,))
        await self.conn.commit()

    async def get_blocked_users(self):
        async with self.conn.execute(
            "SELECT * FROM blocked_users ORDER BY blocked_at DESC"
        ) as c:
            return [dict(r) for r in await c.fetchall()]

    async def get_attempts(self, user_id: int) -> int:
        async with self.conn.execute(
            "SELECT attempts FROM username_attempts WHERE user_id=?", (user_id,)
        ) as c:
            row = await c.fetchone()
            return int(row["attempts"]) if row else 0

    async def inc_attempts(self, user_id: int) -> int:
        cur = await self.get_attempts(user_id)
        new = cur + 1
        await self.conn.execute(
            "INSERT OR REPLACE INTO username_attempts (user_id, attempts) VALUES (?,?)",
            (user_id, new),
        )
        await self.conn.commit()
        return new

    async def reset_attempts(self, user_id: int):
        await self.conn.execute(
            "DELETE FROM username_attempts WHERE user_id=?", (user_id,)
        )
        await self.conn.commit()

    # volume alerts
    async def was_alert_sent(self, user_id, panel_id, admin_username, threshold) -> bool:
        async with self.conn.execute(
            """SELECT 1 FROM volume_alerts_sent
               WHERE user_id=? AND panel_id=? AND admin_username=? AND threshold=?""",
            (user_id, panel_id, admin_username, threshold),
        ) as c:
            return await c.fetchone() is not None

    async def mark_alert_sent(self, user_id, panel_id, admin_username, threshold):
        await self.conn.execute(
            """INSERT OR IGNORE INTO volume_alerts_sent
               (user_id, panel_id, admin_username, threshold) VALUES (?,?,?,?)""",
            (user_id, panel_id, admin_username, threshold),
        )
        await self.conn.commit()

    # discounts
    async def add_discount(self, code: str, percent: int, max_uses: int) -> int:
        cur = await self.conn.execute(
            "INSERT INTO discount_codes (code, percent, max_uses) VALUES (?,?,?)",
            (code.upper().strip(), percent, max_uses),
        )
        await self.conn.commit()
        return cur.lastrowid

    async def get_discounts(self):
        async with self.conn.execute("SELECT * FROM discount_codes ORDER BY id DESC") as c:
            return [dict(r) for r in await c.fetchall()]

    async def get_discount(self, disc_id: int):
        async with self.conn.execute("SELECT * FROM discount_codes WHERE id=?", (disc_id,)) as c:
            row = await c.fetchone()
            return dict(row) if row else None

    async def get_discount_by_code(self, code: str):
        async with self.conn.execute(
            "SELECT * FROM discount_codes WHERE code=? AND is_active=1",
            (code.upper().strip(),),
        ) as c:
            row = await c.fetchone()
            return dict(row) if row else None

    async def update_discount(self, disc_id: int, **kwargs):
        if not kwargs:
            return
        fields = ", ".join(f"{k}=?" for k in kwargs)
        await self.conn.execute(
            f"UPDATE discount_codes SET {fields} WHERE id=?",
            (*kwargs.values(), disc_id),
        )
        await self.conn.commit()

    async def delete_discount(self, disc_id: int):
        await self.conn.execute("DELETE FROM discount_codes WHERE id=?", (disc_id,))
        await self.conn.commit()

    async def use_discount(self, code_id: int, user_id: int, order_id: int):
        await self.conn.execute(
            "UPDATE discount_codes SET used_count = used_count + 1 WHERE id=?",
            (code_id,),
        )
        await self.conn.execute(
            "INSERT INTO discount_uses (code_id, user_id, order_id) VALUES (?,?,?)",
            (code_id, user_id, order_id),
        )
        await self.conn.commit()

    async def payment_stats(self):
        q = """
        SELECT
          COALESCE(SUM(CASE WHEN status='paid' AND date(created_at) >= date('now','weekday 0','-6 days') THEN price END),0) as this_week,
          COALESCE(SUM(CASE WHEN status='paid' AND date(created_at) >= date('now','weekday 0','-13 days')
                            AND date(created_at) < date('now','weekday 0','-6 days') THEN price END),0) as last_week,
          COALESCE(SUM(CASE WHEN status='paid' AND date(created_at) >= date('now','start of month') THEN price END),0) as this_month,
          COALESCE(SUM(CASE WHEN status='paid' AND date(created_at) >= date('now','start of month','-1 month')
                            AND date(created_at) < date('now','start of month') THEN price END),0) as last_month,
          COALESCE(SUM(CASE WHEN status='paid' THEN price END),0) as total_all,
          COUNT(CASE WHEN status='paid' THEN 1 END) as paid_count,
          COUNT(*) as all_orders
        FROM orders
        """
        async with self.conn.execute(q) as c:
            row = await c.fetchone()
            return dict(row) if row else {}


db = Database()
