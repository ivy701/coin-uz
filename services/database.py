"""Database layer with PostgreSQL (asyncpg) and SQLite (aiosqlite) support"""
import asyncio
import logging
import os
import re
from typing import Any
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Read DATABASE_URL from env (default to sqlite:///database.db if not postgres)
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://neondb_owner:npg_FOH4kIY9gEte@ep-dawn-pond-axw9wntv-pooler.c-4.us-east-2.aws.neon.tech/neondb?sslmode=require")
if DATABASE_URL:
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    if "channel_binding" in DATABASE_URL:
        DATABASE_URL = DATABASE_URL.replace("&channel_binding=require", "").replace("channel_binding=require&", "").replace("?channel_binding=require", "")

IS_SQLITE = not (DATABASE_URL and DATABASE_URL.startswith("postgres"))
_base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SQLITE_DB_PATH = os.environ.get("SQLITE_DB_PATH", os.path.join(_base_dir, "database.db"))



# Global pool / connection
_pg_pool = None
_sqlite_conn = None


def _format_sql(sql: str, is_sqlite: bool = False) -> str:
    """Format SQL query for SQLite vs Postgres"""
    if not is_sqlite:
        return sql
    # Replace $1, $2... with ?
    sql = re.sub(r'\$\d+', '?', sql)
    sql = sql.replace('TIMESTAMPTZ', 'DATETIME').replace('NOW()', 'CURRENT_TIMESTAMP')
    sql = sql.replace('SERIAL', 'INTEGER')
    sql = re.sub(r'\bILIKE\b', 'LIKE', sql, flags=re.IGNORECASE)
    return sql


class DBConnection:
    """Unified wrapper around asyncpg pool / aiosqlite connection"""
    def __init__(self, is_sqlite: bool, pg_pool=None, sqlite_db=None):
        self.is_sqlite = is_sqlite
        self.pg_pool = pg_pool
        self.sqlite_db = sqlite_db

    def acquire(self):
        class _ConnCtx:
            def __init__(self, parent):
                self.parent = parent
            async def __aenter__(self):
                return self.parent
            async def __aexit__(self, exc_type, exc, tb):
                pass
        return _ConnCtx(self)

    async def execute(self, sql: str, *args) -> str:

        formatted_sql = _format_sql(sql, self.is_sqlite)
        if self.is_sqlite:
            import aiosqlite
            async with aiosqlite.connect(self.sqlite_db) as db:
                db.row_factory = aiosqlite.Row
                # Handle multi-statement executes for SQLite
                statements = [s.strip() for s in formatted_sql.split(';') if s.strip()]
                last_res = ""
                for stmt in statements:
                    cursor = await db.execute(stmt, args if len(statements) == 1 else ())
                    last_res = f"UPDATE {cursor.rowcount}"
                await db.commit()
                return last_res
        else:
            async with self.pg_pool.acquire() as conn:
                return await conn.execute(formatted_sql, *args)

    async def fetchrow(self, sql: str, *args) -> dict[str, Any] | None:
        formatted_sql = _format_sql(sql, self.is_sqlite)
        if self.is_sqlite:
            import aiosqlite
            async with aiosqlite.connect(self.sqlite_db) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(formatted_sql, args) as cursor:
                    row = await cursor.fetchone()
                    return dict(row) if row else None
        else:
            async with self.pg_pool.acquire() as conn:
                row = await conn.fetchrow(formatted_sql, *args)
                return dict(row) if row else None

    async def fetch(self, sql: str, *args) -> list[dict[str, Any]]:
        formatted_sql = _format_sql(sql, self.is_sqlite)
        if self.is_sqlite:
            import aiosqlite
            async with aiosqlite.connect(self.sqlite_db) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(formatted_sql, args) as cursor:
                    rows = await cursor.fetchall()
                    return [dict(r) for r in rows]
        else:
            async with self.pg_pool.acquire() as conn:
                rows = await conn.fetch(formatted_sql, *args)
                return [dict(r) for r in rows]

    async def fetchval(self, sql: str, *args) -> Any:
        formatted_sql = _format_sql(sql, self.is_sqlite)
        if self.is_sqlite:
            import aiosqlite
            async with aiosqlite.connect(self.sqlite_db) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(formatted_sql, args) as cursor:
                    row = await cursor.fetchone()
                    return row[0] if row else None
        else:
            async with self.pg_pool.acquire() as conn:
                return await conn.fetchval(formatted_sql, *args)


db_conn = DBConnection(is_sqlite=IS_SQLITE, sqlite_db=SQLITE_DB_PATH)


async def get_pool():
    return db_conn


async def init_db() -> None:
    global _pg_pool, db_conn, IS_SQLITE, DATABASE_URL
    DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://neondb_owner:npg_FOH4kIY9gEte@ep-dawn-pond-axw9wntv-pooler.c-4.us-east-2.aws.neon.tech/neondb?sslmode=require")
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    if "channel_binding" in DATABASE_URL:
        DATABASE_URL = DATABASE_URL.replace("&channel_binding=require", "").replace("channel_binding=require&", "").replace("?channel_binding=require", "")

    IS_SQLITE = not (DATABASE_URL and DATABASE_URL.startswith("postgres"))
    db_conn.is_sqlite = IS_SQLITE

    if not IS_SQLITE:
        import asyncpg
        _pg_pool = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=10)
        db_conn.pg_pool = _pg_pool
    else:
        logger.info("Using SQLite database: %s", SQLITE_DB_PATH)

    await db_conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            telegram_id BIGINT PRIMARY KEY,
            sp_id INTEGER,
            username TEXT,
            full_name TEXT,
            balance INTEGER NOT NULL DEFAULT 0,
            referrals INTEGER NOT NULL DEFAULT 0,
            referred_by BIGINT,
            language TEXT NOT NULL DEFAULT 'uz',
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """ if IS_SQLITE else
        """
        CREATE TABLE IF NOT EXISTS users (
            telegram_id BIGINT PRIMARY KEY,
            sp_id SERIAL UNIQUE,
            username TEXT,
            full_name TEXT,
            balance INTEGER NOT NULL DEFAULT 0,
            referrals INTEGER NOT NULL DEFAULT 0,
            referred_by BIGINT,
            language TEXT NOT NULL DEFAULT 'uz',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )

    await db_conn.execute(
        """
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id BIGINT NOT NULL,
            product_type TEXT NOT NULL,
            target_username TEXT,
            quantity INTEGER,
            amount INTEGER,
            status TEXT NOT NULL DEFAULT 'pending',
            external_id TEXT,
            elderpay_order_id TEXT,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """ if IS_SQLITE else
        """
        CREATE TABLE IF NOT EXISTS orders (
            id SERIAL PRIMARY KEY,
            telegram_id BIGINT NOT NULL,
            product_type TEXT NOT NULL,
            target_username TEXT,
            quantity INTEGER,
            amount INTEGER,
            status TEXT NOT NULL DEFAULT 'pending',
            external_id TEXT,
            elderpay_order_id TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    if not IS_SQLITE:
        await db_conn.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS elderpay_order_id TEXT")
    
    await db_conn.execute(
        """
        CREATE TABLE IF NOT EXISTS admin_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_id BIGINT NOT NULL,
            action TEXT NOT NULL,
            details TEXT,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """ if IS_SQLITE else
        """
        CREATE TABLE IF NOT EXISTS admin_logs (
            id SERIAL PRIMARY KEY,
            admin_id BIGINT NOT NULL,
            action TEXT NOT NULL,
            details TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    await db_conn.execute(
        """
        CREATE TABLE IF NOT EXISTS balance_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id BIGINT NOT NULL,
            amount INTEGER NOT NULL,
            type TEXT NOT NULL,
            balance_before INTEGER NOT NULL DEFAULT 0,
            balance_after INTEGER NOT NULL DEFAULT 0,
            reason TEXT,
            admin_id BIGINT,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """ if IS_SQLITE else
        """
        CREATE TABLE IF NOT EXISTS balance_history (
            id SERIAL PRIMARY KEY,
            telegram_id BIGINT NOT NULL,
            amount INTEGER NOT NULL,
            type TEXT NOT NULL,
            balance_before INTEGER NOT NULL DEFAULT 0,
            balance_after INTEGER NOT NULL DEFAULT 0,
            reason TEXT,
            admin_id BIGINT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    await db_conn.execute(
        """
        CREATE TABLE IF NOT EXISTS payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id BIGINT,
            shop_order_id TEXT UNIQUE,
            amount INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            raw_payload TEXT,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """ if IS_SQLITE else
        """
        CREATE TABLE IF NOT EXISTS payments (
            id SERIAL PRIMARY KEY,
            telegram_id BIGINT,
            shop_order_id TEXT UNIQUE,
            amount INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            raw_payload TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )

    await db_conn.execute(
        """
        CREATE TABLE IF NOT EXISTS giveaways (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            winners_count INTEGER NOT NULL DEFAULT 1,
            required_channel TEXT NOT NULL DEFAULT '@CoinStatUz',
            status TEXT NOT NULL DEFAULT 'active',
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            finished_at DATETIME
        )
        """ if IS_SQLITE else
        """
        CREATE TABLE IF NOT EXISTS giveaways (
            id SERIAL PRIMARY KEY,
            title TEXT NOT NULL,
            description TEXT,
            winners_count INTEGER NOT NULL DEFAULT 1,
            required_channel TEXT NOT NULL DEFAULT '@CoinStatUz',
            status TEXT NOT NULL DEFAULT 'active',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            finished_at TIMESTAMPTZ
        )
        """
    )

    await db_conn.execute(
        """
        CREATE TABLE IF NOT EXISTS giveaway_participants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            giveaway_id INTEGER NOT NULL,
            telegram_id BIGINT NOT NULL,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(giveaway_id, telegram_id)
        )
        """ if IS_SQLITE else
        """
        CREATE TABLE IF NOT EXISTS giveaway_participants (
            id SERIAL PRIMARY KEY,
            giveaway_id INTEGER NOT NULL,
            telegram_id BIGINT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE(giveaway_id, telegram_id)
        )
        """
    )

    await db_conn.execute(
        """
        CREATE TABLE IF NOT EXISTS giveaway_winners (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            giveaway_id INTEGER NOT NULL,
            telegram_id BIGINT NOT NULL,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """ if IS_SQLITE else
        """
        CREATE TABLE IF NOT EXISTS giveaway_winners (
            id SERIAL PRIMARY KEY,
            giveaway_id INTEGER NOT NULL,
            telegram_id BIGINT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )

    await db_conn.execute(
        """
        CREATE TABLE IF NOT EXISTS lucky_wheel_spins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_id BIGINT NOT NULL,
            prize_key TEXT NOT NULL,
            prize_title TEXT NOT NULL,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """ if IS_SQLITE else
        """
        CREATE TABLE IF NOT EXISTS lucky_wheel_spins (
            id SERIAL PRIMARY KEY,
            telegram_id BIGINT NOT NULL,
            prize_key TEXT NOT NULL,
            prize_title TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )

    await db_conn.execute(
        """
        CREATE TABLE IF NOT EXISTS lucky_promocodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            is_used INTEGER NOT NULL DEFAULT 0,
            used_by_id BIGINT,
            used_by_username TEXT,
            used_by_name TEXT,
            used_at DATETIME,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """ if IS_SQLITE else
        """
        CREATE TABLE IF NOT EXISTS lucky_promocodes (
            id SERIAL PRIMARY KEY,
            code TEXT UNIQUE NOT NULL,
            is_used BOOLEAN NOT NULL DEFAULT FALSE,
            used_by_id BIGINT,
            used_by_username TEXT,
            used_by_name TEXT,
            used_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )

    await db_conn.execute(
        """
        CREATE TABLE IF NOT EXISTS user_bonus_spins (
            telegram_id BIGINT PRIMARY KEY,
            spins_left INTEGER NOT NULL DEFAULT 0
        )
        """
    )


async def ensure_user(
    telegram_id: int,
    username: str | None,
    full_name: str | None,
    referred_by: int | None = None,
) -> dict[str, Any]:
    row = await db_conn.fetchrow("SELECT * FROM users WHERE telegram_id = $1", telegram_id)
    if row:
        if (username and username != row.get("username")) or (full_name and full_name != row.get("full_name")):
            await db_conn.execute(
                "UPDATE users SET username = COALESCE($1, username), full_name = COALESCE($2, full_name) WHERE telegram_id = $3",
                username, full_name, telegram_id
            )
            row = await db_conn.fetchrow("SELECT * FROM users WHERE telegram_id = $1", telegram_id)
        return row

    if IS_SQLITE:
        max_sp = await db_conn.fetchval("SELECT COALESCE(MAX(sp_id), 0) FROM users") or 0
        new_sp = max_sp + 1
        await db_conn.execute(
            """
            INSERT INTO users (telegram_id, sp_id, username, full_name, referred_by)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (telegram_id) DO UPDATE SET
                username = COALESCE(EXCLUDED.username, users.username),
                full_name = COALESCE(EXCLUDED.full_name, users.full_name)
            """,
            telegram_id, new_sp, username, full_name, referred_by,
        )
    else:
        await db_conn.execute(
            """
            INSERT INTO users (telegram_id, username, full_name, referred_by)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (telegram_id) DO UPDATE SET
                username = COALESCE(EXCLUDED.username, users.username),
                full_name = COALESCE(EXCLUDED.full_name, users.full_name)
            """,
            telegram_id, username, full_name, referred_by,
        )

    if referred_by:
        await db_conn.execute(
            "UPDATE users SET referrals = referrals + 1 WHERE telegram_id = $1", referred_by
        )
        await db_conn.execute(
            "UPDATE users SET balance = balance + 300 WHERE telegram_id = $1", referred_by
        )
    row = await db_conn.fetchrow("SELECT * FROM users WHERE telegram_id = $1", telegram_id)
    return row if row else {}


async def get_user(telegram_id: int) -> dict[str, Any] | None:
    return await db_conn.fetchrow("SELECT * FROM users WHERE telegram_id = $1", telegram_id)


async def get_user_by_sp_id(sp_id: int) -> dict[str, Any] | None:
    return await db_conn.fetchrow("SELECT * FROM users WHERE sp_id = $1", sp_id)


async def update_balance_by_sp_id(
    sp_id: int, amount: int, operation: str = "add"
) -> dict[str, Any] | None:
    user = await get_user_by_sp_id(sp_id)
    if not user:
        return None
    if operation == "add":
        await add_balance(user["telegram_id"], amount)
    else:
        ok = await deduct_balance(user["telegram_id"], amount)
        if not ok:
            return None
    return await get_user_by_sp_id(sp_id)


async def add_balance(telegram_id: int, amount: int) -> int:
    await ensure_user(telegram_id, None, "User")
    await db_conn.execute(
        "UPDATE users SET balance = balance + $1 WHERE telegram_id = $2", amount, telegram_id
    )
    user = await get_user(telegram_id)
    return user["balance"] if user else 0



async def reset_balance(telegram_id: int) -> int:
    await db_conn.execute("UPDATE users SET balance = 0 WHERE telegram_id = $1", telegram_id)
    return 0


async def deduct_balance(telegram_id: int, amount: int) -> bool:
    await ensure_user(telegram_id, None, "User")
    user = await get_user(telegram_id)
    if not user or user["balance"] < amount:
        return False
    await db_conn.execute(
        "UPDATE users SET balance = balance - $1 WHERE telegram_id = $2",
        amount, telegram_id
    )
    return True



async def set_language(telegram_id: int, lang: str) -> None:
    await db_conn.execute("UPDATE users SET language = $1 WHERE telegram_id = $2", lang, telegram_id)


async def create_order(
    telegram_id: int,
    product_type: str,
    target_username: str,
    quantity: int | None,
    amount: int | None,
    external_id: str | None = None,
    status: str = "pending",
) -> int:
    await db_conn.execute(
        """
        INSERT INTO orders (telegram_id, product_type, target_username, quantity, amount, status, external_id)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        """,
        telegram_id, product_type, target_username, quantity, amount, status, external_id,
    )
    row = await db_conn.fetchrow(
        "SELECT id FROM orders WHERE telegram_id = $1 ORDER BY id DESC LIMIT 1", telegram_id
    )
    return row["id"] if row else 0


async def get_user_orders(telegram_id: int, limit: int = 10) -> list[dict[str, Any]]:
    return await db_conn.fetch(
        "SELECT * FROM orders WHERE telegram_id = $1 ORDER BY id DESC LIMIT $2",
        telegram_id, limit
    )


async def record_payment(
    shop_order_id: str,
    telegram_id: int | None,
    amount: int,
    status: str,
    raw_payload: str,
) -> bool:
    try:
        await db_conn.execute(
            """
            INSERT INTO payments (shop_order_id, telegram_id, amount, status, raw_payload)
            VALUES ($1, $2, $3, $4, $5)
            """,
            shop_order_id, telegram_id, amount, status, raw_payload,
        )
        return True
    except Exception:
        return False


async def get_users_paginated(page: int = 1, page_size: int = 20) -> tuple[list[dict], int]:
    total = await db_conn.fetchval("SELECT COUNT(*) FROM users") or 0
    offset = (page - 1) * page_size
    rows = await db_conn.fetch(
        "SELECT * FROM users ORDER BY created_at DESC LIMIT $1 OFFSET $2", page_size, offset
    )
    return rows, total


async def search_users_db(query: str, search_by: str = "telegram_id") -> list[dict]:
    if search_by == "telegram_id" and query.isdigit():
        row = await db_conn.fetchrow("SELECT * FROM users WHERE telegram_id = $1", int(query))
        return [row] if row else []
    elif search_by == "sp_id" and query.isdigit():
        row = await db_conn.fetchrow("SELECT * FROM users WHERE sp_id = $1", int(query))
        return [row] if row else []
    else:
        rows = await db_conn.fetch(
            "SELECT * FROM users WHERE username LIKE $1 ORDER BY created_at DESC LIMIT 20",
            f"%{query}%"
        )
        return rows


async def block_user_db(telegram_id: int) -> bool:
    try:
        await db_conn.execute("ALTER TABLE users ADD COLUMN is_blocked BOOLEAN DEFAULT 0")
    except Exception:
        pass
    await db_conn.execute("UPDATE users SET is_blocked = 1 WHERE telegram_id = $1", telegram_id)
    return True


async def unblock_user_db(telegram_id: int) -> bool:
    await db_conn.execute("UPDATE users SET is_blocked = 0 WHERE telegram_id = $1", telegram_id)
    return True


async def delete_user_db(telegram_id: int) -> bool:
    await db_conn.execute("DELETE FROM users WHERE telegram_id = $1", telegram_id)
    return True


async def get_orders_paginated(
    page: int = 1, page_size: int = 20,
    status: str | None = None, product_type: str | None = None, telegram_id: int | None = None,
) -> tuple[list[dict], int]:
    where = []
    params = []
    if status:
        where.append("status = $1")
        params.append(status)
    if product_type:
        where.append("product_type = $2" if status else "product_type = $1")
        params.append(product_type)
    if telegram_id:
        where.append("telegram_id = $" + str(len(params) + 1))
        params.append(telegram_id)

    where_sql = " WHERE " + " AND ".join(where) if where else ""
    total = await db_conn.fetchval(f"SELECT COUNT(*) FROM orders{where_sql}", *params) or 0
    offset = (page - 1) * page_size
    params.extend([page_size, offset])
    rows = await db_conn.fetch(
        f"SELECT * FROM orders{where_sql} ORDER BY id DESC LIMIT ${len(params)-1} OFFSET ${len(params)}",
        *params
    )
    return rows, total


async def update_order_status(order_id: int, new_status: str) -> bool:
    await db_conn.execute("UPDATE orders SET status = $1 WHERE id = $2", new_status, order_id)
    return True


async def get_dashboard_stats() -> dict:
    total_users = await db_conn.fetchval("SELECT COUNT(*) FROM users") or 0
    total_balance = await db_conn.fetchval("SELECT COALESCE(SUM(balance), 0) FROM users") or 0
    total_orders = await db_conn.fetchval("SELECT COUNT(*) FROM orders") or 0
    return {
        "total_users": total_users,
        "total_balance": total_balance,
        "total_orders": total_orders,
        "new_today": total_users,
        "new_week": total_users,
        "new_month": total_users,
    }


async def admin_broadcast_save(
    admin_id: int, message_type: str, content: str | None,
    file_id: str | None = None, filters: str | None = None
) -> int:
    await db_conn.execute(
        "INSERT INTO admin_logs (admin_id, action, details) VALUES ($1, 'broadcast', $2)",
        admin_id, f"type={message_type}, content={content or ''}, filters={filters or ''}"
    )
    row = await db_conn.fetchrow(
        "SELECT id FROM admin_logs WHERE admin_id = $1 ORDER BY id DESC LIMIT 1", admin_id
    )
    return row["id"] if row else 0


async def get_order_by_id(order_id: int) -> dict | None:
    return await db_conn.fetchrow("SELECT * FROM orders WHERE id = $1", order_id)


async def add_balance_history(
    telegram_id: int, amount: int, tx_type: str,
    balance_before: int, balance_after: int,
    reason: str | None = None, admin_id: int | None = None,
):
    await db_conn.execute(
        """
        INSERT INTO balance_history (telegram_id, amount, type, balance_before, balance_after, reason, admin_id)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        """,
        telegram_id, amount, tx_type, balance_before, balance_after, reason, admin_id,
    )


async def get_all_users_telegram_ids() -> list[int]:
    rows = await db_conn.fetch("SELECT telegram_id FROM users")
    return [r["telegram_id"] for r in rows]


class _LegacyDB:
    """Compatibility wrapper matching old database API"""
    async def init_db(self):
        await init_db()

    async def get_user(self, user_id: int):
        return await get_user(user_id)

    async def create_user(self, user_id: int, username: str = None, first_name: str = None, referrer_id: int = None):
        return await ensure_user(user_id, username, first_name or "", referred_by=referrer_id)

    async def add_balance(self, user_id: int, amount: int):
        return await add_balance(user_id, amount)

    async def add_balance_history(self, telegram_id: int, amount: int, tx_type: str, balance_before: int, balance_after: int, reason: str = None, admin_id: int = None):
        return await add_balance_history(telegram_id, amount, tx_type, balance_before, balance_after, reason, admin_id)

    async def update_balance(self, user_id: int, amount: int, operation: str = "add"):

        if operation == "add":
            await add_balance(user_id, amount)
        else:
            await deduct_balance(user_id, amount)

    async def get_user_by_sp_id(self, sp_id: int):
        return await get_user_by_sp_id(sp_id)

    async def update_balance_by_sp_id(self, sp_id: int, amount: int, operation: str = "add"):
        return await update_balance_by_sp_id(sp_id, amount, operation)

    async def update_user_activity(self, user_id: int):
        pass

    async def create_order(self, order_id: str, user_id: int, product_type: str, amount: int, price: int):
        return await create_order(user_id, product_type, "", None, amount, external_id=order_id)

    async def get_order(self, order_id: str | int):
        oid_str = str(order_id)
        logger.info("[GET_ORDER] Searching for order_id=%s", oid_str)
        row = await db_conn.fetchrow("SELECT * FROM orders WHERE external_id = $1", oid_str)
        if not row and oid_str.isdigit():
            row = await db_conn.fetchrow("SELECT * FROM orders WHERE id = $1", int(oid_str))
        if not row:
            row = await db_conn.fetchrow("SELECT * FROM orders WHERE external_id LIKE $1", f"%{oid_str}%")
        if not row:
            # Log all recent orders to help debug
            recent = await db_conn.fetch("SELECT id, telegram_id, external_id, status FROM orders ORDER BY id DESC LIMIT 5")
            logger.warning("[GET_ORDER] NOT FOUND! Recent 5 orders: %s", recent)
        else:
            logger.info("[GET_ORDER] Found: id=%s external_id=%s status=%s", row.get("id"), row.get("external_id"), row.get("status"))
        return row

    async def update_order(self, order_id: str | int, **kwargs):
        oid_str = str(order_id)
        if "status" in kwargs:
            new_st = kwargs["status"]
            await db_conn.execute("UPDATE orders SET status = $1 WHERE external_id = $2", new_st, oid_str)
            if oid_str.isdigit():
                await db_conn.execute("UPDATE orders SET status = $1 WHERE id = $2", new_st, int(oid_str))
            await db_conn.execute("UPDATE orders SET status = $1 WHERE external_id LIKE $2", new_st, f"%{oid_str}%")

    async def get_user_orders(self, user_id: int, limit: int = 10):
        return await get_user_orders(user_id, limit)

    async def get_referrals(self, user_id: int):
        return []


async def create_giveaway(title: str, description: str, winners_count: int = 1, required_channel: str = "@CoinStatUz") -> int:
    if IS_SQLITE:
        await db_conn.execute(
            """
            INSERT INTO giveaways (title, description, winners_count, required_channel, status)
            VALUES ($1, $2, $3, $4, 'active')
            """,
            title, description, winners_count, required_channel
        )
        res = await db_conn.fetchval("SELECT MAX(id) FROM giveaways")
        return res or 1
    else:
        res = await db_conn.fetchval(
            """
            INSERT INTO giveaways (title, description, winners_count, required_channel, status)
            VALUES ($1, $2, $3, $4, 'active')
            RETURNING id
            """,
            title, description, winners_count, required_channel
        )
        return res or 1


async def get_latest_active_giveaway() -> dict | None:
    row = await db_conn.fetchrow(
        "SELECT * FROM giveaways WHERE status = 'active' ORDER BY id DESC LIMIT 1"
    )
    return dict(row) if row else None


async def get_giveaway_by_id(giveaway_id: int) -> dict | None:
    row = await db_conn.fetchrow(
        "SELECT * FROM giveaways WHERE id = $1", giveaway_id
    )
    return dict(row) if row else None


async def join_giveaway(giveaway_id: int, telegram_id: int) -> bool:
    try:
        if IS_SQLITE:
            await db_conn.execute(
                "INSERT OR IGNORE INTO giveaway_participants (giveaway_id, telegram_id) VALUES ($1, $2)",
                giveaway_id, telegram_id
            )
        else:
            await db_conn.execute(
                "INSERT INTO giveaway_participants (giveaway_id, telegram_id) VALUES ($1, $2) ON CONFLICT DO NOTHING",
                giveaway_id, telegram_id
            )
        return True
    except Exception as e:
        logger.error(f"Error joining giveaway: {e}")
        return False


async def is_participant(giveaway_id: int, telegram_id: int) -> bool:
    row = await db_conn.fetchrow(
        "SELECT 1 FROM giveaway_participants WHERE giveaway_id = $1 AND telegram_id = $2",
        giveaway_id, telegram_id
    )
    return bool(row)


async def get_participants_count(giveaway_id: int) -> int:
    cnt = await db_conn.fetchval(
        "SELECT COUNT(*) FROM giveaway_participants WHERE giveaway_id = $1",
        giveaway_id
    )
    return cnt or 0


async def finish_giveaway_and_pick_winners(giveaway_id: int) -> list[dict]:
    import random
    giveaway = await get_giveaway_by_id(giveaway_id)
    if not giveaway or giveaway.get("status") != "active":
        return []

    winners_count = giveaway.get("winners_count", 1)
    
    rows = await db_conn.fetch(
        """
        SELECT gp.telegram_id, u.username, u.full_name
        FROM giveaway_participants gp
        LEFT JOIN users u ON gp.telegram_id = u.telegram_id
        WHERE gp.giveaway_id = $1
        """,
        giveaway_id
    )

    if not rows:
        await db_conn.execute(
            "UPDATE giveaways SET status = 'finished', finished_at = CURRENT_TIMESTAMP WHERE id = $1" if IS_SQLITE else
            "UPDATE giveaways SET status = 'finished', finished_at = NOW() WHERE id = $1",
            giveaway_id
        )
        return []

    selected = random.sample(rows, min(len(rows), winners_count))
    winners = []
    for s in selected:
        t_id = s["telegram_id"]
        await db_conn.execute(
            "INSERT INTO giveaway_winners (giveaway_id, telegram_id) VALUES ($1, $2)",
            giveaway_id, t_id
        )
        winners.append({
            "telegram_id": t_id,
            "username": s["username"],
            "full_name": s["full_name"]
        })

    await db_conn.execute(
        "UPDATE giveaways SET status = 'finished', finished_at = CURRENT_TIMESTAMP WHERE id = $1" if IS_SQLITE else
        "UPDATE giveaways SET status = 'finished', finished_at = NOW() WHERE id = $1",
        giveaway_id
    )
    return winners


async def get_last_lucky_spin(telegram_id: int) -> dict[str, Any] | None:
    return await db_conn.fetchrow(
        """
        SELECT * FROM lucky_wheel_spins 
        WHERE telegram_id = $1 
        ORDER BY created_at DESC 
        LIMIT 1
        """,
        telegram_id
    )


async def record_lucky_spin(telegram_id: int, prize_key: str, prize_title: str) -> None:
    await db_conn.execute(
        """
        INSERT INTO lucky_wheel_spins (telegram_id, prize_key, prize_title)
        VALUES ($1, $2, $3)
        """,
        telegram_id, prize_key, prize_title
    )


async def get_promocode(code: str) -> dict[str, Any] | None:
    code_clean = code.strip().upper()
    try:
        row = await db_conn.fetchrow(
            "SELECT * FROM lucky_promocodes WHERE UPPER(code) = UPPER($1)",
            code_clean
        )
        if row:
            return row
    except Exception:
        # Table might not exist yet, create it
        pass

    try:
        await db_conn.execute(
            """
            CREATE TABLE IF NOT EXISTS lucky_promocodes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT UNIQUE NOT NULL,
                is_used INTEGER NOT NULL DEFAULT 0,
                used_by_id BIGINT,
                used_by_username TEXT,
                used_by_name TEXT,
                used_at DATETIME,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """ if IS_SQLITE else
            """
            CREATE TABLE IF NOT EXISTS lucky_promocodes (
                id SERIAL PRIMARY KEY,
                code TEXT UNIQUE NOT NULL,
                is_used BOOLEAN NOT NULL DEFAULT FALSE,
                used_by_id BIGINT,
                used_by_username TEXT,
                used_by_name TEXT,
                used_at TIMESTAMPTZ,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        # Default promo codes
        default_codes = [
            "CS-7711", "CS-781", "BEAR-99", "TEDDY2026", "BEAR777",
            "CS-8822", "CS-892", "GOLD-77", "VINO2026",
            "CS-3399", "CS-345", "RUBY-44", "ROSE2026",
            "CS-9900", "CS-911", "DIAMOND-7", "PREMIUM2026",
            "CS-5544", "CS-567", "TURBO-88", "ROCKET2026",
            "CS-1122", "CS-123", "MEGA-50", "STARS2026",
            "CS-4433", "CS-456", "CASH-20", "MONEY2026",
            "CS-2026", "WIN-777", "SPIN777", "LUCKY-VIP", "LUCKY2026",
            "COINSTATVIP", "GIFT2026", "VIP2026", "TOP1", "TOP2", "TOP3"
        ]
        if code_clean in default_codes:
            try:
                await db_conn.execute(
                    "INSERT INTO lucky_promocodes (code) VALUES ($1) ON CONFLICT DO NOTHING" if not IS_SQLITE else
                    "INSERT OR IGNORE INTO lucky_promocodes (code) VALUES ($1)",
                    code_clean
                )
            except Exception:
                pass

        return await db_conn.fetchrow(
            "SELECT * FROM lucky_promocodes WHERE UPPER(code) = UPPER($1)",
            code_clean
        )
    except Exception:
        return None


async def use_promocode(code: str, telegram_id: int, username: str | None, full_name: str | None) -> bool:
    promo = await get_promocode(code)
    if not promo or promo.get("is_used"):
        return False

    ptype = promo.get("prize_type", "bear") if promo else "bear"
    if IS_SQLITE:
        await db_conn.execute(
            """
            UPDATE lucky_promocodes 
            SET is_used = 1, used_by_id = $1, used_by_username = $2, used_by_name = $3, used_at = CURRENT_TIMESTAMP 
            WHERE code = $4 AND is_used = 0
            """,
            telegram_id, username or "", full_name or "", code.strip()
        )
    else:
        await db_conn.execute(
            """
            UPDATE lucky_promocodes 
            SET is_used = TRUE, used_by_id = $1, used_by_username = $2, used_by_name = $3, used_at = NOW() 
            WHERE UPPER(code) = UPPER($4) AND is_used = FALSE
            """,
            telegram_id, username or "", full_name or "", code.strip()
        )

    await add_user_bonus_spins(telegram_id, 1, forced_prize=ptype)
    return True


async def get_user_bonus_spins(telegram_id: int) -> int:
    row = await db_conn.fetchrow(
        "SELECT spins_left FROM user_bonus_spins WHERE telegram_id = $1",
        telegram_id
    )
    return int(row["spins_left"]) if row and row.get("spins_left") else 0


async def get_user_bonus_info(telegram_id: int) -> dict[str, Any] | None:
    row = await db_conn.fetchrow(
        "SELECT spins_left, forced_prize FROM user_bonus_spins WHERE telegram_id = $1",
        telegram_id
    )
    if row:
        return {"spins_left": int(row.get("spins_left") or 0), "forced_prize": row.get("forced_prize") or "bear"}
    return None


async def add_user_bonus_spins(telegram_id: int, count: int = 1, forced_prize: str = "bear") -> None:
    row = await db_conn.fetchrow("SELECT spins_left FROM user_bonus_spins WHERE telegram_id = $1", telegram_id)
    if row:
        await db_conn.execute(
            "UPDATE user_bonus_spins SET spins_left = spins_left + $1, forced_prize = $3 WHERE telegram_id = $2",
            count, telegram_id, forced_prize
        )
    else:
        await db_conn.execute(
            "INSERT INTO user_bonus_spins (telegram_id, spins_left, forced_prize) VALUES ($1, $2, $3)",
            telegram_id, count, forced_prize
        )


async def consume_user_bonus_spin(telegram_id: int) -> dict[str, Any] | None:
    row = await db_conn.fetchrow("SELECT spins_left, forced_prize FROM user_bonus_spins WHERE telegram_id = $1", telegram_id)
    if row and int(row.get("spins_left") or 0) > 0:
        await db_conn.execute(
            "UPDATE user_bonus_spins SET spins_left = spins_left - 1 WHERE telegram_id = $1",
            telegram_id
        )
        return {"ok": True, "forced_prize": row.get("forced_prize") or "bear"}
    return None


async def create_promocode(code: str, prize_type: str = "bear") -> bool:
    code_clean = code.strip().upper()
    ptype_clean = prize_type.strip().lower()
    try:
        if IS_SQLITE:
            await db_conn.execute("INSERT OR REPLACE INTO lucky_promocodes (code, is_used, prize_type) VALUES ($1, 0, $2)", code_clean, ptype_clean)
        else:
            await db_conn.execute(
                """
                INSERT INTO lucky_promocodes (code, is_used, prize_type) 
                VALUES ($1, FALSE, $2) 
                ON CONFLICT (code) 
                DO UPDATE SET is_used = FALSE, used_by_id = NULL, used_by_username = NULL, used_by_name = NULL, used_at = NULL, prize_type = $2
                """,
                code_clean, ptype_clean
            )
        return True
    except Exception as e:
        logger.error(f"create_promocode error: {e}")
        return False


async def get_all_promocodes(limit: int = 30) -> list[dict[str, Any]]:
    try:
        rows = await db_conn.fetch("SELECT * FROM lucky_promocodes ORDER BY id DESC LIMIT $1", limit)
        return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"get_all_promocodes error: {e}")
        return []


async def delete_promocode(code: str) -> bool:
    try:
        await db_conn.execute("DELETE FROM lucky_promocodes WHERE UPPER(code) = $1", code.strip().upper())
        return True
    except Exception as e:
        logger.error(f"delete_promocode error: {e}")
        return False


db = _LegacyDB()
