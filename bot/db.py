import asyncpg

pool: asyncpg.Pool

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id BIGINT PRIMARY KEY,
    full_name TEXT,
    username TEXT,
    joined_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    is_blocked BOOLEAN NOT NULL DEFAULT FALSE
);
CREATE TABLE IF NOT EXISTS movies (
    code SERIAL PRIMARY KEY,
    title TEXT NOT NULL,
    storage_msg_id BIGINT NOT NULL,
    is_paid BOOLEAN NOT NULL DEFAULT FALSE,
    price INTEGER NOT NULL DEFAULT 0,
    views INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS channels (
    chat_id BIGINT PRIMARY KEY,
    title TEXT NOT NULL,
    link TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS purchases (
    id SERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    movie_code INTEGER NOT NULL,
    amount INTEGER NOT NULL,
    charge_id TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, movie_code)
);
-- price: Stars narxi, price_uzs: so'mdagi narx (0 = shu usulda sotilmaydi)
ALTER TABLE movies ADD COLUMN IF NOT EXISTS price_uzs INTEGER NOT NULL DEFAULT 0;
-- amount: Stars yoki so'm (tiyinsiz)
ALTER TABLE purchases ADD COLUMN IF NOT EXISTS currency TEXT NOT NULL DEFAULT 'XTR';
"""


async def init(dsn: str) -> None:
    global pool
    pool = await asyncpg.create_pool(dsn, min_size=1, max_size=5)
    await pool.execute(SCHEMA)


async def close() -> None:
    await pool.close()


# ---------- users ----------

async def add_user(user_id: int, full_name: str, username: str | None) -> None:
    await pool.execute(
        """INSERT INTO users (id, full_name, username) VALUES ($1, $2, $3)
           ON CONFLICT (id) DO UPDATE
           SET full_name = EXCLUDED.full_name, username = EXCLUDED.username, is_blocked = FALSE""",
        user_id, full_name, username,
    )


async def active_user_ids() -> list[int]:
    rows = await pool.fetch("SELECT id FROM users WHERE NOT is_blocked")
    return [r["id"] for r in rows]


async def mark_blocked(user_id: int) -> None:
    await pool.execute("UPDATE users SET is_blocked = TRUE WHERE id = $1", user_id)


# ---------- movies ----------

async def add_movie(title: str, storage_msg_id: int, is_paid: bool, price: int, price_uzs: int) -> int:
    return await pool.fetchval(
        """INSERT INTO movies (title, storage_msg_id, is_paid, price, price_uzs)
           VALUES ($1, $2, $3, $4, $5) RETURNING code""",
        title, storage_msg_id, is_paid, price, price_uzs,
    )


async def get_movie(code: int) -> asyncpg.Record | None:
    return await pool.fetchrow("SELECT * FROM movies WHERE code = $1", code)


async def delete_movie(code: int) -> None:
    await pool.execute("DELETE FROM movies WHERE code = $1", code)


async def inc_views(code: int) -> None:
    await pool.execute("UPDATE movies SET views = views + 1 WHERE code = $1", code)


async def search_movies(query: str, limit: int = 10) -> list[asyncpg.Record]:
    return await pool.fetch(
        "SELECT code, title, is_paid FROM movies WHERE title ILIKE '%' || $1 || '%' ORDER BY views DESC LIMIT $2",
        query, limit,
    )


async def top_movies(limit: int = 10) -> list[asyncpg.Record]:
    return await pool.fetch(
        "SELECT code, title, is_paid, views FROM movies ORDER BY views DESC LIMIT $1", limit
    )


# ---------- channels ----------

async def add_channel(chat_id: int, title: str, link: str) -> None:
    await pool.execute(
        """INSERT INTO channels (chat_id, title, link) VALUES ($1, $2, $3)
           ON CONFLICT (chat_id) DO UPDATE SET title = EXCLUDED.title, link = EXCLUDED.link""",
        chat_id, title, link,
    )


async def delete_channel(chat_id: int) -> None:
    await pool.execute("DELETE FROM channels WHERE chat_id = $1", chat_id)


async def get_channels() -> list[asyncpg.Record]:
    return await pool.fetch("SELECT * FROM channels ORDER BY title")


# ---------- purchases ----------

async def has_purchase(user_id: int, code: int) -> bool:
    return bool(await pool.fetchval(
        "SELECT 1 FROM purchases WHERE user_id = $1 AND movie_code = $2", user_id, code
    ))


async def add_purchase(user_id: int, code: int, amount: int, currency: str, charge_id: str) -> None:
    await pool.execute(
        """INSERT INTO purchases (user_id, movie_code, amount, currency, charge_id) VALUES ($1, $2, $3, $4, $5)
           ON CONFLICT DO NOTHING""",
        user_id, code, amount, currency, charge_id,
    )


# ---------- stats ----------

async def stats() -> asyncpg.Record:
    return await pool.fetchrow(
        """SELECT
             (SELECT count(*) FROM users) AS users,
             (SELECT count(*) FROM users
               WHERE joined_at >= date_trunc('day', now() AT TIME ZONE 'Asia/Tashkent') AT TIME ZONE 'Asia/Tashkent') AS today,
             (SELECT count(*) FROM users WHERE is_blocked) AS blocked,
             (SELECT count(*) FROM movies) AS movies,
             (SELECT count(*) FROM movies WHERE is_paid) AS paid_movies,
             (SELECT count(*) FROM purchases) AS sales,
             (SELECT coalesce(sum(amount), 0) FROM purchases WHERE currency = 'XTR') AS stars,
             (SELECT coalesce(sum(amount), 0) FROM purchases WHERE currency = 'UZS') AS uzs"""
    )
