"""
database.py
------------
Toda la persistencia del bot vive aquí: una sola clase Database que envuelve
aiosqlite. Cada cog importa la instancia global `db` y llama a sus métodos
en vez de escribir SQL suelto por todo el proyecto.
"""

import os
import time
import aiosqlite

from config import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id     INTEGER NOT NULL,
    guild_id    INTEGER NOT NULL,
    balance     INTEGER NOT NULL DEFAULT 0,
    bank        INTEGER NOT NULL DEFAULT 0,
    xp          INTEGER NOT NULL DEFAULT 0,
    level       INTEGER NOT NULL DEFAULT 0,
    last_daily  INTEGER NOT NULL DEFAULT 0,
    last_xp     INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, guild_id)
);

CREATE TABLE IF NOT EXISTS guild_config (
    guild_id            INTEGER PRIMARY KEY,
    welcome_channel_id  INTEGER,
    welcome_message     TEXT,
    leave_channel_id    INTEGER,
    leave_message       TEXT,
    log_channel_id      INTEGER,
    autorole_id         INTEGER,
    mute_role_id        INTEGER,
    jail_role_id        INTEGER,
    jail_channel_id     INTEGER,
    vm_category_id      INTEGER,
    vm_join_channel_id  INTEGER,
    vm_interface_channel_id INTEGER
);

CREATE TABLE IF NOT EXISTS voice_channels (
    channel_id  INTEGER PRIMARY KEY,
    guild_id    INTEGER NOT NULL,
    owner_id    INTEGER NOT NULL,
    locked      INTEGER NOT NULL DEFAULT 0,
    ghosted     INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS reaction_roles (
    guild_id    INTEGER NOT NULL,
    message_id  INTEGER NOT NULL,
    emoji       TEXT NOT NULL,
    role_id     INTEGER NOT NULL,
    PRIMARY KEY (message_id, emoji)
);

CREATE TABLE IF NOT EXISTS sticky_messages (
    channel_id      INTEGER PRIMARY KEY,
    guild_id        INTEGER NOT NULL,
    content         TEXT NOT NULL,
    last_message_id INTEGER
);

CREATE TABLE IF NOT EXISTS tickets (
    channel_id  INTEGER PRIMARY KEY,
    guild_id    INTEGER NOT NULL,
    user_id     INTEGER NOT NULL,
    status      TEXT NOT NULL DEFAULT 'open',
    created_at  INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS warnings (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id    INTEGER NOT NULL,
    user_id     INTEGER NOT NULL,
    moderator_id INTEGER NOT NULL,
    reason      TEXT,
    created_at  INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS autoresponders (
    guild_id      INTEGER NOT NULL,
    trigger       TEXT NOT NULL,
    response      TEXT NOT NULL,
    match_type    TEXT NOT NULL DEFAULT 'contains',   -- 'strict' o 'contains'
    created_by    INTEGER NOT NULL,
    created_at    INTEGER NOT NULL,
    PRIMARY KEY (guild_id, trigger)
);

CREATE TABLE IF NOT EXISTS shop_items (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id      INTEGER NOT NULL,
    name          TEXT NOT NULL,
    price         INTEGER NOT NULL,
    description   TEXT,
    role_id       INTEGER,
    stock         INTEGER NOT NULL DEFAULT -1,   -- -1 = ilimitado
    UNIQUE(guild_id, name)
);

CREATE TABLE IF NOT EXISTS inventory (
    guild_id      INTEGER NOT NULL,
    user_id       INTEGER NOT NULL,
    item_id       INTEGER NOT NULL,
    quantity      INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (guild_id, user_id, item_id)
);

CREATE TABLE IF NOT EXISTS cooldowns (
    guild_id      INTEGER NOT NULL,
    user_id       INTEGER NOT NULL,
    action        TEXT NOT NULL,
    last_used     INTEGER NOT NULL,
    PRIMARY KEY (guild_id, user_id, action)
);

CREATE TABLE IF NOT EXISTS reaction_triggers (
    guild_id      INTEGER NOT NULL,
    trigger       TEXT NOT NULL,
    emoji         TEXT NOT NULL,
    match_type    TEXT NOT NULL DEFAULT 'contains',
    created_by    INTEGER NOT NULL,
    created_at    INTEGER NOT NULL,
    PRIMARY KEY (guild_id, trigger)
);

CREATE TABLE IF NOT EXISTS giveaways (
    message_id    INTEGER PRIMARY KEY,
    channel_id    INTEGER NOT NULL,
    guild_id      INTEGER NOT NULL,
    host_id       INTEGER NOT NULL,
    prize         TEXT NOT NULL,
    winners       INTEGER NOT NULL DEFAULT 1,
    ends_at       INTEGER NOT NULL,
    ended         INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS counters (
    guild_id      INTEGER NOT NULL,
    channel_id    INTEGER NOT NULL,
    kind          TEXT NOT NULL,   -- 'members', 'bots', 'voice'
    template      TEXT NOT NULL,   -- ej: "👥 Miembros: {count}"
    PRIMARY KEY (guild_id, kind)
);

CREATE TABLE IF NOT EXISTS bump_config (
    guild_id      INTEGER PRIMARY KEY,
    channel_id    INTEGER,
    role_id       INTEGER,
    last_bump     INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS level_roles (
    guild_id      INTEGER NOT NULL,
    level         INTEGER NOT NULL,
    role_id       INTEGER NOT NULL,
    PRIMARY KEY (guild_id, level)
);

CREATE TABLE IF NOT EXISTS level_settings (
    guild_id      INTEGER PRIMARY KEY,
    xp_rate       REAL NOT NULL DEFAULT 1.0,
    stack_roles   INTEGER NOT NULL DEFAULT 1,
    announce_mode TEXT NOT NULL DEFAULT 'channel',  -- 'channel', 'dm' o 'silent'
    announce_message TEXT
);

CREATE TABLE IF NOT EXISTS level_ignored_channels (
    guild_id      INTEGER NOT NULL,
    channel_id    INTEGER NOT NULL,
    PRIMARY KEY (guild_id, channel_id)
);

CREATE TABLE IF NOT EXISTS antiraid_config (
    guild_id       INTEGER PRIMARY KEY,
    enabled        INTEGER NOT NULL DEFAULT 0,
    min_age_hours  INTEGER NOT NULL DEFAULT 24,
    join_burst     INTEGER NOT NULL DEFAULT 8,
    join_window    INTEGER NOT NULL DEFAULT 10,
    action         TEXT NOT NULL DEFAULT 'kick'
);

-- FASE 2 --

CREATE TABLE IF NOT EXISTS giveaway_entrants (
    message_id    INTEGER NOT NULL,
    user_id       INTEGER NOT NULL,
    PRIMARY KEY (message_id, user_id)
);

CREATE TABLE IF NOT EXISTS reminders (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id      INTEGER NOT NULL,
    channel_id    INTEGER NOT NULL,
    user_id       INTEGER NOT NULL,
    message       TEXT NOT NULL,
    remind_at     INTEGER NOT NULL,
    created_at    INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS automod_config (
    guild_id        INTEGER PRIMARY KEY,
    enabled         INTEGER NOT NULL DEFAULT 1,
    block_invites   INTEGER NOT NULL DEFAULT 1,
    max_mentions    INTEGER NOT NULL DEFAULT 6,
    blacklist_action TEXT NOT NULL DEFAULT 'delete'
);

CREATE TABLE IF NOT EXISTS automod_whitelist (
    guild_id      INTEGER NOT NULL,
    domain        TEXT NOT NULL,
    PRIMARY KEY (guild_id, domain)
);

CREATE TABLE IF NOT EXISTS automod_blacklist (
    guild_id      INTEGER NOT NULL,
    word          TEXT NOT NULL,
    PRIMARY KEY (guild_id, word)
);
"""

# Columnas nuevas agregadas a tablas que ya existían desde la FASE 1.
# Como CREATE TABLE IF NOT EXISTS no modifica una tabla que ya existe en un
# bot.sqlite3 previo, estas columnas se agregan a mano (una sola vez) en
# _run_migrations(). Si la columna ya existe, simplemente se ignora.
MIGRATIONS = [
    ("autoresponders", "enabled", "INTEGER NOT NULL DEFAULT 1"),
    ("autoresponders", "channel_id", "INTEGER"),
    ("guild_config", "welcome_enabled", "INTEGER NOT NULL DEFAULT 1"),
    ("guild_config", "leave_enabled", "INTEGER NOT NULL DEFAULT 1"),
    ("giveaways", "required_role_id", "INTEGER"),
    ("giveaways", "winners_ids", "TEXT"),
]


class Database:
    def __init__(self, path: str):
        self.path = path
        self._conn: aiosqlite.Connection | None = None

    async def connect(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self._conn = await aiosqlite.connect(self.path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.executescript(SCHEMA)
        await self._conn.commit()
        await self._run_migrations()

    async def _run_migrations(self):
        """Agrega columnas nuevas (FASE 2) a tablas viejas sin borrar datos."""
        for table, column, decl in MIGRATIONS:
            cur = await self._conn.execute(f"PRAGMA table_info({table})")
            existing = {row[1] for row in await cur.fetchall()}
            if column not in existing:
                await self._conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")
        await self._conn.commit()

    async def close(self):
        if self._conn:
            await self._conn.close()

    @property
    def conn(self) -> aiosqlite.Connection:
        assert self._conn is not None, "La base de datos no está conectada todavía"
        return self._conn

    # ---------------- USERS / ECONOMÍA ----------------

    async def get_user(self, user_id: int, guild_id: int) -> aiosqlite.Row:
        cur = await self.conn.execute(
            "SELECT * FROM users WHERE user_id = ? AND guild_id = ?", (user_id, guild_id)
        )
        row = await cur.fetchone()
        if row is None:
            await self.conn.execute(
                "INSERT INTO users (user_id, guild_id, balance) VALUES (?, ?, ?)",
                (user_id, guild_id, config.STARTING_BALANCE),
            )
            await self.conn.commit()
            cur = await self.conn.execute(
                "SELECT * FROM users WHERE user_id = ? AND guild_id = ?", (user_id, guild_id)
            )
            row = await cur.fetchone()
        return row

    async def update_balance(self, user_id: int, guild_id: int, delta: int) -> int:
        """Suma (o resta si delta es negativo) al balance y devuelve el nuevo balance."""
        await self.get_user(user_id, guild_id)  # asegura que la fila exista
        await self.conn.execute(
            "UPDATE users SET balance = balance + ? WHERE user_id = ? AND guild_id = ?",
            (delta, user_id, guild_id),
        )
        await self.conn.commit()
        row = await self.get_user(user_id, guild_id)
        return row["balance"]

    async def set_last_daily(self, user_id: int, guild_id: int, ts: int):
        await self.conn.execute(
            "UPDATE users SET last_daily = ? WHERE user_id = ? AND guild_id = ?",
            (ts, user_id, guild_id),
        )
        await self.conn.commit()

    async def add_xp(self, user_id: int, guild_id: int, amount: int) -> aiosqlite.Row:
        await self.get_user(user_id, guild_id)
        await self.conn.execute(
            "UPDATE users SET xp = xp + ? WHERE user_id = ? AND guild_id = ?",
            (amount, user_id, guild_id),
        )
        await self.conn.commit()
        return await self.get_user(user_id, guild_id)

    async def set_level(self, user_id: int, guild_id: int, level: int):
        await self.conn.execute(
            "UPDATE users SET level = ? WHERE user_id = ? AND guild_id = ?",
            (level, user_id, guild_id),
        )
        await self.conn.commit()

    async def leaderboard(self, guild_id: int, limit: int = 10):
        cur = await self.conn.execute(
            "SELECT * FROM users WHERE guild_id = ? ORDER BY balance DESC LIMIT ?",
            (guild_id, limit),
        )
        return await cur.fetchall()

    # ---------------- GUILD CONFIG ----------------

    async def get_guild_config(self, guild_id: int) -> aiosqlite.Row:
        cur = await self.conn.execute("SELECT * FROM guild_config WHERE guild_id = ?", (guild_id,))
        row = await cur.fetchone()
        if row is None:
            await self.conn.execute("INSERT INTO guild_config (guild_id) VALUES (?)", (guild_id,))
            await self.conn.commit()
            cur = await self.conn.execute("SELECT * FROM guild_config WHERE guild_id = ?", (guild_id,))
            row = await cur.fetchone()
        return row

    async def set_guild_field(self, guild_id: int, field: str, value):
        await self.get_guild_config(guild_id)
        await self.conn.execute(
            f"UPDATE guild_config SET {field} = ? WHERE guild_id = ?", (value, guild_id)
        )
        await self.conn.commit()

    # ---------------- VOICEMASTER ----------------

    async def create_voice_channel(self, channel_id: int, guild_id: int, owner_id: int):
        await self.conn.execute(
            "INSERT OR REPLACE INTO voice_channels (channel_id, guild_id, owner_id) VALUES (?, ?, ?)",
            (channel_id, guild_id, owner_id),
        )
        await self.conn.commit()

    async def get_voice_channel(self, channel_id: int):
        cur = await self.conn.execute("SELECT * FROM voice_channels WHERE channel_id = ?", (channel_id,))
        return await cur.fetchone()

    async def delete_voice_channel(self, channel_id: int):
        await self.conn.execute("DELETE FROM voice_channels WHERE channel_id = ?", (channel_id,))
        await self.conn.commit()

    async def set_voice_owner(self, channel_id: int, owner_id: int):
        await self.conn.execute(
            "UPDATE voice_channels SET owner_id = ? WHERE channel_id = ?", (owner_id, channel_id)
        )
        await self.conn.commit()

    async def set_voice_flag(self, channel_id: int, field: str, value: int):
        await self.conn.execute(
            f"UPDATE voice_channels SET {field} = ? WHERE channel_id = ?", (value, channel_id)
        )
        await self.conn.commit()

    # ---------------- REACTION ROLES ----------------

    async def add_reaction_role(self, guild_id: int, message_id: int, emoji: str, role_id: int):
        await self.conn.execute(
            "INSERT OR REPLACE INTO reaction_roles (guild_id, message_id, emoji, role_id) VALUES (?, ?, ?, ?)",
            (guild_id, message_id, emoji, role_id),
        )
        await self.conn.commit()

    async def get_reaction_role(self, message_id: int, emoji: str):
        cur = await self.conn.execute(
            "SELECT * FROM reaction_roles WHERE message_id = ? AND emoji = ?", (message_id, emoji)
        )
        return await cur.fetchone()

    async def remove_reaction_role(self, message_id: int, emoji: str) -> bool:
        cur = await self.conn.execute(
            "DELETE FROM reaction_roles WHERE message_id = ? AND emoji = ?", (message_id, emoji)
        )
        await self.conn.commit()
        return cur.rowcount > 0

    async def get_reaction_roles(self, guild_id: int):
        cur = await self.conn.execute(
            "SELECT * FROM reaction_roles WHERE guild_id = ?", (guild_id,)
        )
        return await cur.fetchall()

    # ---------------- STICKY MESSAGES ----------------

    async def set_sticky(self, channel_id: int, guild_id: int, content: str):
        await self.conn.execute(
            "INSERT OR REPLACE INTO sticky_messages (channel_id, guild_id, content, last_message_id) "
            "VALUES (?, ?, ?, NULL)",
            (channel_id, guild_id, content),
        )
        await self.conn.commit()

    async def get_sticky(self, channel_id: int):
        cur = await self.conn.execute("SELECT * FROM sticky_messages WHERE channel_id = ?", (channel_id,))
        return await cur.fetchone()

    async def remove_sticky(self, channel_id: int):
        await self.conn.execute("DELETE FROM sticky_messages WHERE channel_id = ?", (channel_id,))
        await self.conn.commit()

    async def set_sticky_last_id(self, channel_id: int, message_id: int):
        await self.conn.execute(
            "UPDATE sticky_messages SET last_message_id = ? WHERE channel_id = ?",
            (message_id, channel_id),
        )
        await self.conn.commit()

    # ---------------- TICKETS ----------------

    async def create_ticket(self, channel_id: int, guild_id: int, user_id: int):
        await self.conn.execute(
            "INSERT INTO tickets (channel_id, guild_id, user_id, created_at) VALUES (?, ?, ?, ?)",
            (channel_id, guild_id, user_id, int(time.time())),
        )
        await self.conn.commit()

    async def close_ticket(self, channel_id: int):
        await self.conn.execute(
            "UPDATE tickets SET status = 'closed' WHERE channel_id = ?", (channel_id,)
        )
        await self.conn.commit()

    # ---------------- WARNINGS ----------------

    async def add_warning(self, guild_id: int, user_id: int, moderator_id: int, reason: str):
        await self.conn.execute(
            "INSERT INTO warnings (guild_id, user_id, moderator_id, reason, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (guild_id, user_id, moderator_id, reason, int(time.time())),
        )
        await self.conn.commit()

    async def get_warnings(self, guild_id: int, user_id: int):
        cur = await self.conn.execute(
            "SELECT * FROM warnings WHERE guild_id = ? AND user_id = ? ORDER BY created_at DESC",
            (guild_id, user_id),
        )
        return await cur.fetchall()

    # ---------------- AUTORESPONDER ----------------

    async def add_autoresponder(self, guild_id: int, trigger: str, response: str,
                                 match_type: str, created_by: int):
        await self.conn.execute(
            "INSERT OR REPLACE INTO autoresponders "
            "(guild_id, trigger, response, match_type, created_by, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (guild_id, trigger.lower(), response, match_type, created_by, int(time.time())),
        )
        await self.conn.commit()

    async def remove_autoresponder(self, guild_id: int, trigger: str) -> bool:
        cur = await self.conn.execute(
            "DELETE FROM autoresponders WHERE guild_id = ? AND trigger = ?",
            (guild_id, trigger.lower()),
        )
        await self.conn.commit()
        return cur.rowcount > 0

    async def get_autoresponders(self, guild_id: int):
        cur = await self.conn.execute(
            "SELECT * FROM autoresponders WHERE guild_id = ?", (guild_id,)
        )
        return await cur.fetchall()

    async def get_autoresponder(self, guild_id: int, trigger: str):
        cur = await self.conn.execute(
            "SELECT * FROM autoresponders WHERE guild_id = ? AND trigger = ?",
            (guild_id, trigger.lower()),
        )
        return await cur.fetchone()

    async def edit_autoresponder_response(self, guild_id: int, trigger: str, response: str) -> bool:
        cur = await self.conn.execute(
            "UPDATE autoresponders SET response = ? WHERE guild_id = ? AND trigger = ?",
            (response, guild_id, trigger.lower()),
        )
        await self.conn.commit()
        return cur.rowcount > 0

    async def set_autoresponder_enabled(self, guild_id: int, trigger: str, enabled: bool) -> bool:
        cur = await self.conn.execute(
            "UPDATE autoresponders SET enabled = ? WHERE guild_id = ? AND trigger = ?",
            (int(enabled), guild_id, trigger.lower()),
        )
        await self.conn.commit()
        return cur.rowcount > 0

    async def set_autoresponder_channel(self, guild_id: int, trigger: str, channel_id: int | None) -> bool:
        cur = await self.conn.execute(
            "UPDATE autoresponders SET channel_id = ? WHERE guild_id = ? AND trigger = ?",
            (channel_id, guild_id, trigger.lower()),
        )
        await self.conn.commit()
        return cur.rowcount > 0

    # ---------------- TIENDA / SHOP ----------------

    async def add_shop_item(self, guild_id: int, name: str, price: int,
                             description: str | None, role_id: int | None, stock: int) -> bool:
        try:
            await self.conn.execute(
                "INSERT INTO shop_items (guild_id, name, price, description, role_id, stock) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (guild_id, name, price, description, role_id, stock),
            )
            await self.conn.commit()
            return True
        except Exception:
            return False

    async def remove_shop_item(self, guild_id: int, name: str) -> bool:
        cur = await self.conn.execute(
            "DELETE FROM shop_items WHERE guild_id = ? AND name = ?", (guild_id, name)
        )
        await self.conn.commit()
        return cur.rowcount > 0

    async def get_shop_items(self, guild_id: int):
        cur = await self.conn.execute(
            "SELECT * FROM shop_items WHERE guild_id = ? ORDER BY price ASC", (guild_id,)
        )
        return await cur.fetchall()

    async def get_shop_item(self, guild_id: int, item_id: int):
        cur = await self.conn.execute(
            "SELECT * FROM shop_items WHERE guild_id = ? AND id = ?", (guild_id, item_id)
        )
        return await cur.fetchone()

    async def get_shop_item_by_name(self, guild_id: int, name: str):
        cur = await self.conn.execute(
            "SELECT * FROM shop_items WHERE guild_id = ? AND LOWER(name) = LOWER(?)",
            (guild_id, name),
        )
        return await cur.fetchone()

    async def decrement_stock(self, item_id: int):
        await self.conn.execute(
            "UPDATE shop_items SET stock = stock - 1 WHERE id = ? AND stock > 0", (item_id,)
        )
        await self.conn.commit()

    async def add_inventory_item(self, guild_id: int, user_id: int, item_id: int, quantity: int = 1):
        await self.conn.execute(
            "INSERT INTO inventory (guild_id, user_id, item_id, quantity) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(guild_id, user_id, item_id) DO UPDATE SET quantity = quantity + excluded.quantity",
            (guild_id, user_id, item_id, quantity),
        )
        await self.conn.commit()

    async def get_inventory(self, guild_id: int, user_id: int):
        cur = await self.conn.execute(
            "SELECT inventory.quantity, shop_items.* FROM inventory "
            "JOIN shop_items ON inventory.item_id = shop_items.id "
            "WHERE inventory.guild_id = ? AND inventory.user_id = ? AND inventory.quantity > 0",
            (guild_id, user_id),
        )
        return await cur.fetchall()

    # ---------------- COOLDOWNS (work / rob / etc) ----------------

    async def get_cooldown(self, guild_id: int, user_id: int, action: str) -> int:
        cur = await self.conn.execute(
            "SELECT last_used FROM cooldowns WHERE guild_id = ? AND user_id = ? AND action = ?",
            (guild_id, user_id, action),
        )
        row = await cur.fetchone()
        return row["last_used"] if row else 0

    async def set_cooldown(self, guild_id: int, user_id: int, action: str, ts: int):
        await self.conn.execute(
            "INSERT OR REPLACE INTO cooldowns (guild_id, user_id, action, last_used) VALUES (?, ?, ?, ?)",
            (guild_id, user_id, action, ts),
        )
        await self.conn.commit()

    # ---------------- REACTION TRIGGERS ----------------

    async def add_reaction_trigger(self, guild_id: int, trigger: str, emoji: str,
                                    match_type: str, created_by: int):
        await self.conn.execute(
            "INSERT OR REPLACE INTO reaction_triggers "
            "(guild_id, trigger, emoji, match_type, created_by, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (guild_id, trigger.lower(), emoji, match_type, created_by, int(time.time())),
        )
        await self.conn.commit()

    async def remove_reaction_trigger(self, guild_id: int, trigger: str) -> bool:
        cur = await self.conn.execute(
            "DELETE FROM reaction_triggers WHERE guild_id = ? AND trigger = ?",
            (guild_id, trigger.lower()),
        )
        await self.conn.commit()
        return cur.rowcount > 0

    async def get_reaction_triggers(self, guild_id: int):
        cur = await self.conn.execute(
            "SELECT * FROM reaction_triggers WHERE guild_id = ?", (guild_id,)
        )
        return await cur.fetchall()

    # ---------------- GIVEAWAYS ----------------

    async def create_giveaway(self, message_id: int, channel_id: int, guild_id: int,
                               host_id: int, prize: str, winners: int, ends_at: int,
                               required_role_id: int | None = None):
        await self.conn.execute(
            "INSERT INTO giveaways (message_id, channel_id, guild_id, host_id, prize, winners, ends_at, required_role_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (message_id, channel_id, guild_id, host_id, prize, winners, ends_at, required_role_id),
        )
        await self.conn.commit()

    async def get_giveaway(self, message_id: int):
        cur = await self.conn.execute("SELECT * FROM giveaways WHERE message_id = ?", (message_id,))
        return await cur.fetchone()

    async def get_active_giveaways(self):
        cur = await self.conn.execute("SELECT * FROM giveaways WHERE ended = 0")
        return await cur.fetchall()

    async def get_guild_giveaways(self, guild_id: int, limit: int = 10):
        cur = await self.conn.execute(
            "SELECT * FROM giveaways WHERE guild_id = ? ORDER BY ends_at DESC LIMIT ?",
            (guild_id, limit),
        )
        return await cur.fetchall()

    async def end_giveaway(self, message_id: int, winners_ids: str | None = None):
        await self.conn.execute(
            "UPDATE giveaways SET ended = 1, winners_ids = ? WHERE message_id = ?",
            (winners_ids, message_id),
        )
        await self.conn.commit()

    async def cancel_giveaway(self, message_id: int):
        await self.conn.execute("DELETE FROM giveaways WHERE message_id = ?", (message_id,))
        await self.conn.execute("DELETE FROM giveaway_entrants WHERE message_id = ?", (message_id,))
        await self.conn.commit()

    async def add_giveaway_entrant(self, message_id: int, user_id: int):
        await self.conn.execute(
            "INSERT OR IGNORE INTO giveaway_entrants (message_id, user_id) VALUES (?, ?)",
            (message_id, user_id),
        )
        await self.conn.commit()

    async def remove_giveaway_entrant(self, message_id: int, user_id: int):
        await self.conn.execute(
            "DELETE FROM giveaway_entrants WHERE message_id = ? AND user_id = ?",
            (message_id, user_id),
        )
        await self.conn.commit()

    async def is_giveaway_entrant(self, message_id: int, user_id: int) -> bool:
        cur = await self.conn.execute(
            "SELECT 1 FROM giveaway_entrants WHERE message_id = ? AND user_id = ?",
            (message_id, user_id),
        )
        return await cur.fetchone() is not None

    async def get_giveaway_entrants(self, message_id: int) -> list[int]:
        cur = await self.conn.execute(
            "SELECT user_id FROM giveaway_entrants WHERE message_id = ?", (message_id,)
        )
        rows = await cur.fetchall()
        return [r["user_id"] for r in rows]

    # ---------------- COUNTERS ----------------

    async def set_counter(self, guild_id: int, channel_id: int, kind: str, template: str):
        await self.conn.execute(
            "INSERT OR REPLACE INTO counters (guild_id, channel_id, kind, template) VALUES (?, ?, ?, ?)",
            (guild_id, channel_id, kind, template),
        )
        await self.conn.commit()

    async def get_counters(self, guild_id: int):
        cur = await self.conn.execute("SELECT * FROM counters WHERE guild_id = ?", (guild_id,))
        return await cur.fetchall()

    async def remove_counter(self, guild_id: int, kind: str) -> bool:
        cur = await self.conn.execute(
            "DELETE FROM counters WHERE guild_id = ? AND kind = ?", (guild_id, kind)
        )
        await self.conn.commit()
        return cur.rowcount > 0

    # ---------------- BUMP REMINDER ----------------

    async def get_bump_config(self, guild_id: int):
        cur = await self.conn.execute("SELECT * FROM bump_config WHERE guild_id = ?", (guild_id,))
        row = await cur.fetchone()
        if row is None:
            await self.conn.execute("INSERT INTO bump_config (guild_id) VALUES (?)", (guild_id,))
            await self.conn.commit()
            cur = await self.conn.execute("SELECT * FROM bump_config WHERE guild_id = ?", (guild_id,))
            row = await cur.fetchone()
        return row

    async def set_bump_field(self, guild_id: int, field: str, value):
        await self.get_bump_config(guild_id)
        await self.conn.execute(
            f"UPDATE bump_config SET {field} = ? WHERE guild_id = ?", (value, guild_id)
        )
        await self.conn.commit()

    # ---------------- LEVEL ROLES / CONFIG ----------------

    async def add_level_role(self, guild_id: int, level: int, role_id: int):
        await self.conn.execute(
            "INSERT OR REPLACE INTO level_roles (guild_id, level, role_id) VALUES (?, ?, ?)",
            (guild_id, level, role_id),
        )
        await self.conn.commit()

    async def remove_level_role(self, guild_id: int, level: int) -> bool:
        cur = await self.conn.execute(
            "DELETE FROM level_roles WHERE guild_id = ? AND level = ?", (guild_id, level)
        )
        await self.conn.commit()
        return cur.rowcount > 0

    async def get_level_roles(self, guild_id: int):
        cur = await self.conn.execute(
            "SELECT * FROM level_roles WHERE guild_id = ? ORDER BY level ASC", (guild_id,)
        )
        return await cur.fetchall()

    async def get_level_settings(self, guild_id: int):
        cur = await self.conn.execute("SELECT * FROM level_settings WHERE guild_id = ?", (guild_id,))
        row = await cur.fetchone()
        if row is None:
            await self.conn.execute("INSERT INTO level_settings (guild_id) VALUES (?)", (guild_id,))
            await self.conn.commit()
            cur = await self.conn.execute("SELECT * FROM level_settings WHERE guild_id = ?", (guild_id,))
            row = await cur.fetchone()
        return row

    async def set_level_setting(self, guild_id: int, field: str, value):
        await self.get_level_settings(guild_id)
        await self.conn.execute(
            f"UPDATE level_settings SET {field} = ? WHERE guild_id = ?", (value, guild_id)
        )
        await self.conn.commit()

    async def ignore_level_channel(self, guild_id: int, channel_id: int):
        await self.conn.execute(
            "INSERT OR IGNORE INTO level_ignored_channels (guild_id, channel_id) VALUES (?, ?)",
            (guild_id, channel_id),
        )
        await self.conn.commit()

    async def unignore_level_channel(self, guild_id: int, channel_id: int) -> bool:
        cur = await self.conn.execute(
            "DELETE FROM level_ignored_channels WHERE guild_id = ? AND channel_id = ?",
            (guild_id, channel_id),
        )
        await self.conn.commit()
        return cur.rowcount > 0

    async def get_ignored_level_channels(self, guild_id: int):
        cur = await self.conn.execute(
            "SELECT channel_id FROM level_ignored_channels WHERE guild_id = ?", (guild_id,)
        )
        rows = await cur.fetchall()
        return {r["channel_id"] for r in rows}

    async def set_xp_and_level(self, user_id: int, guild_id: int, xp: int, level: int):
        await self.get_user(user_id, guild_id)
        await self.conn.execute(
            "UPDATE users SET xp = ?, level = ? WHERE user_id = ? AND guild_id = ?",
            (xp, level, user_id, guild_id),
        )
        await self.conn.commit()

    # ---------------- ANTIRAID ----------------

    async def get_antiraid_config(self, guild_id: int):
        cur = await self.conn.execute("SELECT * FROM antiraid_config WHERE guild_id = ?", (guild_id,))
        row = await cur.fetchone()
        if row is None:
            await self.conn.execute("INSERT INTO antiraid_config (guild_id) VALUES (?)", (guild_id,))
            await self.conn.commit()
            cur = await self.conn.execute("SELECT * FROM antiraid_config WHERE guild_id = ?", (guild_id,))
            row = await cur.fetchone()
        return row

    async def set_antiraid_field(self, guild_id: int, field: str, value):
        await self.get_antiraid_config(guild_id)
        await self.conn.execute(
            f"UPDATE antiraid_config SET {field} = ? WHERE guild_id = ?", (value, guild_id)
        )
        await self.conn.commit()

    # ---------------- REMINDERS ----------------

    async def add_reminder(self, guild_id: int, channel_id: int, user_id: int,
                            message: str, remind_at: int) -> int:
        cur = await self.conn.execute(
            "INSERT INTO reminders (guild_id, channel_id, user_id, message, remind_at, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (guild_id, channel_id, user_id, message, remind_at, int(time.time())),
        )
        await self.conn.commit()
        return cur.lastrowid

    async def get_due_reminders(self, now: int):
        cur = await self.conn.execute("SELECT * FROM reminders WHERE remind_at <= ?", (now,))
        return await cur.fetchall()

    async def get_user_reminders(self, guild_id: int, user_id: int):
        cur = await self.conn.execute(
            "SELECT * FROM reminders WHERE guild_id = ? AND user_id = ? ORDER BY remind_at ASC",
            (guild_id, user_id),
        )
        return await cur.fetchall()

    async def get_reminder(self, reminder_id: int):
        cur = await self.conn.execute("SELECT * FROM reminders WHERE id = ?", (reminder_id,))
        return await cur.fetchone()

    async def delete_reminder(self, reminder_id: int) -> bool:
        cur = await self.conn.execute("DELETE FROM reminders WHERE id = ?", (reminder_id,))
        await self.conn.commit()
        return cur.rowcount > 0

    # ---------------- AUTOMOD ----------------

    async def get_automod_config(self, guild_id: int):
        cur = await self.conn.execute("SELECT * FROM automod_config WHERE guild_id = ?", (guild_id,))
        row = await cur.fetchone()
        if row is None:
            await self.conn.execute("INSERT INTO automod_config (guild_id) VALUES (?)", (guild_id,))
            await self.conn.commit()
            cur = await self.conn.execute("SELECT * FROM automod_config WHERE guild_id = ?", (guild_id,))
            row = await cur.fetchone()
        return row

    async def set_automod_field(self, guild_id: int, field: str, value):
        await self.get_automod_config(guild_id)
        await self.conn.execute(
            f"UPDATE automod_config SET {field} = ? WHERE guild_id = ?", (value, guild_id)
        )
        await self.conn.commit()

    async def add_automod_whitelist(self, guild_id: int, domain: str):
        await self.conn.execute(
            "INSERT OR IGNORE INTO automod_whitelist (guild_id, domain) VALUES (?, ?)",
            (guild_id, domain.lower()),
        )
        await self.conn.commit()

    async def remove_automod_whitelist(self, guild_id: int, domain: str) -> bool:
        cur = await self.conn.execute(
            "DELETE FROM automod_whitelist WHERE guild_id = ? AND domain = ?", (guild_id, domain.lower())
        )
        await self.conn.commit()
        return cur.rowcount > 0

    async def get_automod_whitelist(self, guild_id: int) -> set[str]:
        cur = await self.conn.execute("SELECT domain FROM automod_whitelist WHERE guild_id = ?", (guild_id,))
        rows = await cur.fetchall()
        return {r["domain"] for r in rows}

    async def add_automod_blacklist(self, guild_id: int, word: str):
        await self.conn.execute(
            "INSERT OR IGNORE INTO automod_blacklist (guild_id, word) VALUES (?, ?)",
            (guild_id, word.lower()),
        )
        await self.conn.commit()

    async def remove_automod_blacklist(self, guild_id: int, word: str) -> bool:
        cur = await self.conn.execute(
            "DELETE FROM automod_blacklist WHERE guild_id = ? AND word = ?", (guild_id, word.lower())
        )
        await self.conn.commit()
        return cur.rowcount > 0

    async def get_automod_blacklist(self, guild_id: int) -> set[str]:
        cur = await self.conn.execute("SELECT word FROM automod_blacklist WHERE guild_id = ?", (guild_id,))
        rows = await cur.fetchall()
        return {r["word"] for r in rows}


db = Database(config.DB_PATH)
