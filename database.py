import sqlite3
from pathlib import Path
from contextlib import contextmanager
from datetime import datetime, timezone


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "game.db"


def now():
    """UTC timestamp."""
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def get_connection():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row

    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA busy_timeout = 10000")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with get_connection() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS countries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            flag TEXT NOT NULL DEFAULT '',
            money REAL NOT NULL DEFAULT 0,
            factories INTEGER NOT NULL DEFAULT 0,
            banks INTEGER NOT NULL DEFAULT 0,
            universities INTEGER NOT NULL DEFAULT 0,
            daily_money_income REAL NOT NULL DEFAULT 0,
            daily_industry_income REAL NOT NULL DEFAULT 0,
            daily_knowledge_income REAL NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS groups (
            chat_id INTEGER PRIMARY KEY,
            country_id INTEGER NOT NULL UNIQUE,
            created_at TEXT NOT NULL,
            FOREIGN KEY (country_id) REFERENCES countries(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS weapons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            category TEXT NOT NULL,
            price REAL NOT NULL DEFAULT 0,
            attack_power REAL NOT NULL DEFAULT 0,
            defense_power REAL NOT NULL DEFAULT 0,
            industry_cost INTEGER NOT NULL DEFAULT 0,
            knowledge_cost INTEGER NOT NULL DEFAULT 0,
            description TEXT
        );

        CREATE TABLE IF NOT EXISTS country_weapons (
            country_id INTEGER NOT NULL,
            weapon_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (country_id, weapon_id),
            FOREIGN KEY (country_id) REFERENCES countries(id) ON DELETE CASCADE,
            FOREIGN KEY (weapon_id) REFERENCES weapons(id) ON DELETE CASCADE,
            CHECK (quantity >= 0)
        );

        CREATE TABLE IF NOT EXISTS country_weapon_capabilities (
            country_id INTEGER NOT NULL,
            weapon_id INTEGER NOT NULL,
            unlocked_at TEXT NOT NULL,
            PRIMARY KEY (country_id, weapon_id),
            FOREIGN KEY (country_id) REFERENCES countries(id) ON DELETE CASCADE,
            FOREIGN KEY (weapon_id) REFERENCES weapons(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS alliances (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            founder_country_id INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            created_at TEXT NOT NULL,
            FOREIGN KEY (founder_country_id) REFERENCES countries(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS alliance_members (
            alliance_id INTEGER NOT NULL,
            country_id INTEGER NOT NULL,
            joined_at TEXT NOT NULL,
            PRIMARY KEY (alliance_id, country_id),
            FOREIGN KEY (alliance_id) REFERENCES alliances(id) ON DELETE CASCADE,
            FOREIGN KEY (country_id) REFERENCES countries(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS alliance_join_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            alliance_id INTEGER NOT NULL,
            country_id INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            requested_at TEXT NOT NULL,
            message TEXT,
            FOREIGN KEY (alliance_id) REFERENCES alliances(id) ON DELETE CASCADE,
            FOREIGN KEY (country_id) REFERENCES countries(id) ON DELETE CASCADE,
            UNIQUE (alliance_id, country_id)
        );

        CREATE TABLE IF NOT EXISTS alliance_agreements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            alliance_a_id INTEGER NOT NULL,
            alliance_b_id INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            requested_at TEXT NOT NULL,
            accepted_at TEXT,
            FOREIGN KEY (alliance_a_id) REFERENCES alliances(id) ON DELETE CASCADE,
            FOREIGN KEY (alliance_b_id) REFERENCES alliances(id) ON DELETE CASCADE,
            UNIQUE (alliance_a_id, alliance_b_id)
        );

        CREATE TABLE IF NOT EXISTS negotiation_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            requester_country_id INTEGER NOT NULL,
            target_country_id INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            requested_at TEXT NOT NULL,
            FOREIGN KEY (requester_country_id) REFERENCES countries(id) ON DELETE CASCADE,
            FOREIGN KEY (target_country_id) REFERENCES countries(id) ON DELETE CASCADE,
            UNIQUE (requester_country_id, target_country_id)
        );

        CREATE TABLE IF NOT EXISTS negotiations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            country_a_id INTEGER NOT NULL,
            country_b_id INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            started_at TEXT NOT NULL,
            ended_at TEXT,
            FOREIGN KEY (country_a_id) REFERENCES countries(id) ON DELETE CASCADE,
            FOREIGN KEY (country_b_id) REFERENCES countries(id) ON DELETE CASCADE,
            UNIQUE (country_a_id, country_b_id)
        );

        CREATE TABLE IF NOT EXISTS spy_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            attacker_country_id INTEGER NOT NULL,
            target_country_id INTEGER NOT NULL,
            event_type TEXT NOT NULL,
            success INTEGER NOT NULL DEFAULT 0,
            details TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (attacker_country_id) REFERENCES countries(id) ON DELETE CASCADE,
            FOREIGN KEY (target_country_id) REFERENCES countries(id) ON DELETE CASCADE,
            CHECK (success IN (0, 1))
        );

        CREATE TABLE IF NOT EXISTS country_spy_levels (
            country_id INTEGER PRIMARY KEY,
            counter_espionage_level INTEGER NOT NULL DEFAULT 0,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (country_id) REFERENCES countries(id) ON DELETE CASCADE,
            CHECK (counter_espionage_level BETWEEN 0 AND 5)
        );

        CREATE TABLE IF NOT EXISTS sanctions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            imposer_country_id INTEGER NOT NULL,
            target_country_id INTEGER NOT NULL,
            sanctioned INTEGER NOT NULL DEFAULT 1,
            FOREIGN KEY (imposer_country_id) REFERENCES countries(id) ON DELETE CASCADE,
            FOREIGN KEY (target_country_id) REFERENCES countries(id) ON DELETE CASCADE,
            CHECK (sanctioned IN (0, 1)),
            UNIQUE (imposer_country_id, target_country_id)
        );

        CREATE TABLE IF NOT EXISTS weapon_requirements (
            country_id INTEGER NOT NULL,
            weapon_id INTEGER NOT NULL,
            min_factories INTEGER NOT NULL DEFAULT 0,
            min_banks INTEGER NOT NULL DEFAULT 0,
            min_universities INTEGER NOT NULL DEFAULT 0,
            min_money REAL NOT NULL DEFAULT 0,
            is_allowed INTEGER NOT NULL DEFAULT 1,
            FOREIGN KEY (country_id) REFERENCES countries(id) ON DELETE CASCADE,
            FOREIGN KEY (weapon_id) REFERENCES weapons(id) ON DELETE CASCADE,
            CHECK (is_allowed IN (0, 1)),
            PRIMARY KEY (country_id, weapon_id)
        );

        CREATE TABLE IF NOT EXISTS foreign_investments (
            investor_country_id INTEGER NOT NULL,
            target_country_id INTEGER NOT NULL,
            asset TEXT NOT NULL,
            quantity INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            PRIMARY KEY (investor_country_id, target_country_id, asset),
            FOREIGN KEY (investor_country_id) REFERENCES countries(id) ON DELETE CASCADE,
            FOREIGN KEY (target_country_id) REFERENCES countries(id) ON DELETE CASCADE,
            CHECK (asset IN ('factories', 'banks', 'universities')),
            CHECK (quantity >= 0)
        );

        CREATE TABLE IF NOT EXISTS wars (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            attacker_country_id INTEGER NOT NULL,
            defender_country_id INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            target TEXT,
            started_at TEXT NOT NULL,
            ended_at TEXT,
            FOREIGN KEY (attacker_country_id) REFERENCES countries(id) ON DELETE CASCADE,
            FOREIGN KEY (defender_country_id) REFERENCES countries(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS war_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            war_id INTEGER NOT NULL,
            attacker_country_id INTEGER NOT NULL,
            defender_country_id INTEGER NOT NULL,
            event_type TEXT NOT NULL,
            attacker_losses INTEGER NOT NULL DEFAULT 0,
            defender_losses INTEGER NOT NULL DEFAULT 0,
            description TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (war_id) REFERENCES wars(id) ON DELETE CASCADE,
            FOREIGN KEY (attacker_country_id) REFERENCES countries(id) ON DELETE CASCADE,
            FOREIGN KEY (defender_country_id) REFERENCES countries(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            seller_country_id INTEGER NOT NULL,
            buyer_country_id INTEGER NOT NULL,
            weapon_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL,
            total_price REAL NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL,
            FOREIGN KEY (seller_country_id) REFERENCES countries(id) ON DELETE CASCADE,
            FOREIGN KEY (buyer_country_id) REFERENCES countries(id) ON DELETE CASCADE,
            FOREIGN KEY (weapon_id) REFERENCES weapons(id) ON DELETE CASCADE,
            CHECK (quantity > 0),
            CHECK (total_price >= 0)
        );

        CREATE TABLE IF NOT EXISTS markets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            seller_country_id INTEGER NOT NULL,
            weapon_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL,
            price REAL NOT NULL,
            status TEXT NOT NULL DEFAULT 'open',
            created_at TEXT NOT NULL,
            FOREIGN KEY (seller_country_id) REFERENCES countries(id) ON DELETE CASCADE,
            FOREIGN KEY (weapon_id) REFERENCES weapons(id) ON DELETE CASCADE,
            CHECK (quantity > 0),
            CHECK (price >= 0)
        );

        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            from_country_id INTEGER,
            to_country_id INTEGER,
            amount REAL NOT NULL,
            type TEXT NOT NULL,
            reference_id INTEGER,
            created_at TEXT NOT NULL,
            FOREIGN KEY (from_country_id) REFERENCES countries(id) ON DELETE SET NULL,
            FOREIGN KEY (to_country_id) REFERENCES countries(id) ON DELETE SET NULL
        );

        CREATE INDEX IF NOT EXISTS idx_country_weapons_country ON country_weapons(country_id);
        CREATE INDEX IF NOT EXISTS idx_weapon_capabilities_country ON country_weapon_capabilities(country_id);
        CREATE INDEX IF NOT EXISTS idx_alliance_members_country ON alliance_members(country_id);
        CREATE INDEX IF NOT EXISTS idx_sanctions_target ON sanctions(target_country_id);
        CREATE INDEX IF NOT EXISTS idx_sanctions_imposer ON sanctions(imposer_country_id);
        CREATE INDEX IF NOT EXISTS idx_wars_attacker ON wars(attacker_country_id);
        CREATE INDEX IF NOT EXISTS idx_wars_defender ON wars(defender_country_id);
        CREATE INDEX IF NOT EXISTS idx_trades_buyer ON trades(buyer_country_id);
        CREATE INDEX IF NOT EXISTS idx_trades_seller ON trades(seller_country_id);
        CREATE INDEX IF NOT EXISTS idx_markets_status ON markets(status);
        CREATE INDEX IF NOT EXISTS idx_transactions_from ON transactions(from_country_id);
        CREATE INDEX IF NOT EXISTS idx_transactions_to ON transactions(to_country_id);
        """)

        columns = {row["name"] for row in conn.execute("PRAGMA table_info(countries)").fetchall()}
        if "flag" not in columns:
            conn.execute("ALTER TABLE countries ADD COLUMN flag TEXT NOT NULL DEFAULT ''")
            columns.add("flag")
        for column_name, default_value in {
            "daily_money_income": 0,
            "daily_industry_income": 0,
            "daily_knowledge_income": 0,
        }.items():
            if column_name not in columns:
                conn.execute(
                    f"ALTER TABLE countries ADD COLUMN {column_name} REAL NOT NULL DEFAULT {default_value}"
                )

        weapon_columns = {row["name"] for row in conn.execute("PRAGMA table_info(weapons)").fetchall()}
        for column_name, default_value in {
            "industry_cost": 0,
            "knowledge_cost": 0,
        }.items():
            if column_name not in weapon_columns:
                conn.execute(
                    f"ALTER TABLE weapons ADD COLUMN {column_name} INTEGER NOT NULL DEFAULT {default_value}"
                )


def create_country(name, flag="", money=0, factories=0, banks=0, universities=0, daily_money_income=0, daily_industry_income=0, daily_knowledge_income=0, daily_income=None):
    if daily_income is not None:
        daily_money_income = daily_income

    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO countries (name, flag, money, factories, banks, universities, daily_money_income, daily_industry_income, daily_knowledge_income, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (name, flag or "", money, factories, banks, universities, daily_money_income, daily_industry_income, daily_knowledge_income, now()),
        )
        return cursor.lastrowid


def country_label(country):
    if not country:
        return "کشور نامشخص"
    flag = str(country.get("flag", "") or "").strip()
    return f"{flag} {country['name']}" if flag else country["name"]


def get_country(country_id):
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM countries WHERE id = ?", (country_id,)).fetchone()
        return dict(row) if row else None


def get_country_by_name(name):
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM countries WHERE name = ?", (name,)).fetchone()
        return dict(row) if row else None


def get_all_countries():
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM countries ORDER BY name").fetchall()
        return [dict(row) for row in rows]


def update_country(country_id, **fields):
    allowed = {
        "name",
        "money",
        "factories",
        "banks",
        "universities",
        "daily_money_income",
        "daily_industry_income",
        "daily_knowledge_income",
        "daily_income",
    }
    normalized = {}
    for key, value in fields.items():
        if key not in allowed:
            continue
        if key == "daily_income":
            normalized["daily_money_income"] = value
        else:
            normalized[key] = value

    if not normalized:
        return False

    set_clause = ", ".join(f"{key} = ?" for key in normalized)
    values = list(normalized.values()) + [country_id]

    with get_connection() as conn:
        cursor = conn.execute(f"UPDATE countries SET {set_clause} WHERE id = ?", values)
        return cursor.rowcount > 0


def change_money(country_id, amount):
    with get_connection() as conn:
        row = conn.execute("SELECT money FROM countries WHERE id = ?", (country_id,)).fetchone()
        if not row:
            raise ValueError("Country does not exist.")
        new_money = row["money"] + amount
        if new_money < 0:
            raise ValueError("Country does not have enough money.")
        conn.execute("UPDATE countries SET money = ? WHERE id = ?", (new_money, country_id))
        return new_money


def assign_group_to_country(chat_id, country_id):
    with get_connection() as conn:
        country = conn.execute("SELECT id FROM countries WHERE id = ?", (country_id,)).fetchone()
        if not country:
            raise ValueError("Country does not exist.")

        existing_country = conn.execute("SELECT country_id FROM groups WHERE chat_id = ?", (chat_id,)).fetchone()
        if existing_country:
            conn.execute("UPDATE groups SET country_id = ? WHERE chat_id = ?", (country_id, chat_id))
            return

        already_assigned = conn.execute("SELECT chat_id FROM groups WHERE country_id = ?", (country_id,)).fetchone()
        if already_assigned:
            raise ValueError("This country is already assigned to another group.")

        conn.execute(
            "INSERT INTO groups (chat_id, country_id, created_at) VALUES (?, ?, ?)",
            (chat_id, country_id, now()),
        )


def get_country_by_group(chat_id):
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT c.*
            FROM countries c
            JOIN groups g ON g.country_id = c.id
            WHERE g.chat_id = ?
            """,
            (chat_id,),
        ).fetchone()
        return dict(row) if row else None


def get_country_spy_level(country_id):
    with get_connection() as conn:
        row = conn.execute(
            "SELECT counter_espionage_level FROM country_spy_levels WHERE country_id = ?",
            (country_id,),
        ).fetchone()
        return int(row["counter_espionage_level"]) if row else 0


def set_country_spy_level(country_id, level):
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO country_spy_levels (country_id, counter_espionage_level, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(country_id)
            DO UPDATE SET counter_espionage_level = excluded.counter_espionage_level,
                          updated_at = excluded.updated_at
            """,
            (country_id, max(0, min(5, int(level))), now()),
        )
        return max(0, min(5, int(level)))


def get_group_by_country(country_id):
    with get_connection() as conn:
        row = conn.execute("SELECT chat_id FROM groups WHERE country_id = ?", (country_id,)).fetchone()
        return row["chat_id"] if row else None


def create_weapon(name, category, price, attack_power=0, defense_power=0, industry_cost=0, knowledge_cost=0, description=""):
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO weapons (name, category, price, attack_power, defense_power, industry_cost, knowledge_cost, description)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (name, category, price, attack_power, defense_power, int(industry_cost), int(knowledge_cost), description),
        )
        return cursor.lastrowid


def restrict_weapon_by_default(weapon_id):
    with get_connection() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO weapon_requirements
                (country_id, weapon_id, min_factories, min_banks, min_universities, min_money, is_allowed)
            SELECT id, ?, 0, 0, 0, 0, 0
            FROM countries
            """,
            (weapon_id,),
        )


def get_weapon(weapon_id):
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM weapons WHERE id = ?", (weapon_id,)).fetchone()
        return dict(row) if row else None


def get_weapon_by_name(name):
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM weapons WHERE name = ?", (name,)).fetchone()
        return dict(row) if row else None


def get_all_weapons():
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM weapons ORDER BY category, name").fetchall()
        return [dict(row) for row in rows]


def add_weapon(country_id, weapon_id, quantity):
    if quantity <= 0:
        raise ValueError("Quantity must be greater than zero.")

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO country_weapons (country_id, weapon_id, quantity)
            VALUES (?, ?, ?)
            ON CONFLICT(country_id, weapon_id)
            DO UPDATE SET quantity = country_weapons.quantity + excluded.quantity
            """,
            (country_id, weapon_id, quantity),
        )


def remove_weapon(country_id, weapon_id, quantity):
    if quantity <= 0:
        raise ValueError("Quantity must be greater than zero.")

    with get_connection() as conn:
        row = conn.execute(
            "SELECT quantity FROM country_weapons WHERE country_id = ? AND weapon_id = ?",
            (country_id, weapon_id),
        ).fetchone()

        if not row:
            raise ValueError("Weapon does not exist in inventory.")
        if row["quantity"] < quantity:
            raise ValueError("Not enough weapons.")

        new_quantity = row["quantity"] - quantity
        conn.execute(
            "UPDATE country_weapons SET quantity = ? WHERE country_id = ? AND weapon_id = ?",
            (new_quantity, country_id, weapon_id),
        )
        return new_quantity


def get_weapon_quantity(country_id, weapon_id):
    with get_connection() as conn:
        row = conn.execute(
            "SELECT quantity FROM country_weapons WHERE country_id = ? AND weapon_id = ?",
            (country_id, weapon_id),
        ).fetchone()
        return row["quantity"] if row else 0


def get_country_inventory(country_id):
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT w.id, w.name, w.category, w.price, w.attack_power, w.defense_power, cw.quantity
            FROM country_weapons cw
            JOIN weapons w ON w.id = cw.weapon_id
            WHERE cw.country_id = ? AND cw.quantity > 0
            ORDER BY w.category, w.name
            """,
            (country_id,),
        ).fetchall()
        return [dict(row) for row in rows]


def set_weapon_requirement(country_id, weapon_id, min_factories=0, min_banks=0, min_universities=0, min_money=0, is_allowed=True):
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO weapon_requirements (country_id, weapon_id, min_factories, min_banks, min_universities, min_money, is_allowed)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(country_id, weapon_id)
            DO UPDATE SET min_factories = excluded.min_factories,
                          min_banks = excluded.min_banks,
                          min_universities = excluded.min_universities,
                          min_money = excluded.min_money,
                          is_allowed = excluded.is_allowed
            """,
            (country_id, weapon_id, int(min_factories), int(min_banks), int(min_universities), float(min_money), 1 if is_allowed else 0),
        )


def get_weapon_requirement(country_id, weapon_id):
    with get_connection() as conn:
        row = conn.execute(
            "SELECT min_factories, min_banks, min_universities, min_money, is_allowed FROM weapon_requirements WHERE country_id = ? AND weapon_id = ?",
            (country_id, weapon_id),
        ).fetchone()
        return dict(row) if row else None


def country_can_make_weapon(country_id, weapon_id):
    req = get_weapon_requirement(country_id, weapon_id)
    if req is None:
        return False
    if req["is_allowed"] == 0:
        return False
    return True


def get_country_buildable_weapons(country_id):
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT w.*
            FROM weapons w
            LEFT JOIN weapon_requirements wr ON wr.weapon_id = w.id AND wr.country_id = ?
            WHERE wr.is_allowed IS NULL OR wr.is_allowed = 1
            ORDER BY w.category, w.name
            """,
            (country_id,),
        ).fetchall()
        return [dict(row) for row in rows]


def get_country_restricted_weapons(country_id):
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT w.*, wr.min_factories, wr.min_banks, wr.min_universities, wr.min_money, wr.is_allowed
            FROM weapons w
            JOIN weapon_requirements wr ON wr.weapon_id = w.id
            WHERE wr.country_id = ?
            ORDER BY w.category, w.name
            """,
            (country_id,),
        ).fetchall()
        return [dict(row) for row in rows]


def unlock_weapon_capability(country_id, weapon_id):
    with get_connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO country_weapon_capabilities (country_id, weapon_id, unlocked_at) VALUES (?, ?, ?)",
            (country_id, weapon_id, now()),
        )


def has_weapon_capability(country_id, weapon_id):
    with get_connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM country_weapon_capabilities WHERE country_id = ? AND weapon_id = ?",
            (country_id, weapon_id),
        ).fetchone()
        return row is not None


def get_country_weapon_capabilities(country_id):
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT w.*, cwc.unlocked_at
            FROM country_weapon_capabilities cwc
            JOIN weapons w ON w.id = cwc.weapon_id
            WHERE cwc.country_id = ?
            ORDER BY w.category, w.name
            """,
            (country_id,),
        ).fetchall()
        return [dict(row) for row in rows]


def create_alliance(name, founder_country_id):
    with get_connection() as conn:
        cursor = conn.execute(
            "INSERT INTO alliances (name, founder_country_id, status, created_at) VALUES (?, ?, 'active', ?)",
            (name, founder_country_id, now()),
        )
        alliance_id = cursor.lastrowid
        conn.execute(
            "INSERT INTO alliance_members (alliance_id, country_id, joined_at) VALUES (?, ?, ?)",
            (alliance_id, founder_country_id, now()),
        )
        return alliance_id


def get_alliance(alliance_id):
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM alliances WHERE id = ?", (alliance_id,)).fetchone()
        return dict(row) if row else None


def get_alliances():
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM alliances ORDER BY name").fetchall()
        return [dict(row) for row in rows]


def get_country_alliances(country_id):
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT a.*
            FROM alliance_members am
            JOIN alliances a ON a.id = am.alliance_id
            WHERE am.country_id = ?
            ORDER BY a.name
            """,
            (country_id,),
        ).fetchall()
        return [dict(row) for row in rows]


def add_country_to_alliance(alliance_id, country_id):
    with get_connection() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO alliance_members (alliance_id, country_id, joined_at) VALUES (?, ?, ?)",
            (alliance_id, country_id, now()),
        )


def create_alliance_join_request(alliance_id, country_id, message=""):
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO alliance_join_requests (alliance_id, country_id, status, requested_at, message)
            VALUES (?, ?, 'pending', ?, ?)
            ON CONFLICT(alliance_id, country_id)
            DO UPDATE SET status = 'pending', requested_at = excluded.requested_at, message = excluded.message
            """,
            (alliance_id, country_id, now(), message),
        )


def get_pending_join_requests_for_alliance(alliance_id):
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT ajr.*, c.name AS country_name
            FROM alliance_join_requests ajr
            JOIN countries c ON c.id = ajr.country_id
            WHERE ajr.alliance_id = ? AND ajr.status = 'pending'
            ORDER BY ajr.requested_at DESC
            """,
            (alliance_id,),
        ).fetchall()
        return [dict(row) for row in rows]


def accept_alliance_join_request(request_id):
    with get_connection() as conn:
        row = conn.execute(
            "SELECT alliance_id, country_id FROM alliance_join_requests WHERE id = ? AND status = 'pending'",
            (request_id,),
        ).fetchone()
        if not row:
            return False
        conn.execute(
            "INSERT OR IGNORE INTO alliance_members (alliance_id, country_id, joined_at) VALUES (?, ?, ?)",
            (row["alliance_id"], row["country_id"], now()),
        )
        conn.execute(
            "UPDATE alliance_join_requests SET status = 'accepted' WHERE id = ?",
            (request_id,),
        )
        return True


def create_alliance_agreement(alliance_a_id, alliance_b_id):
    if alliance_a_id == alliance_b_id:
        raise ValueError("An alliance cannot agree with itself.")

    with get_connection() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO alliance_agreements (alliance_a_id, alliance_b_id, status, requested_at)
            VALUES (?, ?, 'pending', ?)
            """,
            (alliance_a_id, alliance_b_id, now()),
        )


def get_pending_agreements_for_alliance(alliance_id):
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT aa.*, a1.name AS alliance_a_name, a2.name AS alliance_b_name
            FROM alliance_agreements aa
            JOIN alliances a1 ON a1.id = aa.alliance_a_id
            JOIN alliances a2 ON a2.id = aa.alliance_b_id
            WHERE aa.status = 'pending'
              AND (aa.alliance_a_id = ? OR aa.alliance_b_id = ?)
            ORDER BY aa.requested_at DESC
            """,
            (alliance_id, alliance_id),
        ).fetchall()
        return [dict(row) for row in rows]


def accept_alliance_agreement(agreement_id, alliance_id):
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM alliance_agreements WHERE id = ? AND status = 'pending'",
            (agreement_id,),
        ).fetchone()
        if not row:
            return False
        if row["alliance_a_id"] != alliance_id and row["alliance_b_id"] != alliance_id:
            return False
        conn.execute(
            "UPDATE alliance_agreements SET status = 'active', accepted_at = ? WHERE id = ?",
            (now(), agreement_id),
        )
        return True


def create_negotiation_request(requester_country_id, target_country_id):
    if requester_country_id == target_country_id:
        raise ValueError("A country cannot negotiate with itself.")
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO negotiation_requests (requester_country_id, target_country_id, status, requested_at)
            VALUES (?, ?, 'pending', ?)
            ON CONFLICT(requester_country_id, target_country_id)
            DO UPDATE SET status = 'pending', requested_at = excluded.requested_at
            """,
            (requester_country_id, target_country_id, now()),
        )


def get_pending_negotiation_requests_for_country(country_id):
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT nr.*, c1.name AS requester_name, c2.name AS target_name
            FROM negotiation_requests nr
            JOIN countries c1 ON c1.id = nr.requester_country_id
            JOIN countries c2 ON c2.id = nr.target_country_id
            WHERE nr.target_country_id = ? AND nr.status = 'pending'
            ORDER BY nr.requested_at DESC
            """,
            (country_id,),
        ).fetchall()
        return [dict(row) for row in rows]


def accept_negotiation_request(request_id):
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM negotiation_requests WHERE id = ? AND status = 'pending'",
            (request_id,),
        ).fetchone()
        if not row:
            return None

        country_a_id = row["requester_country_id"]
        country_b_id = row["target_country_id"]
        conn.execute(
            "UPDATE negotiation_requests SET status = 'accepted' WHERE id = ?",
            (request_id,),
        )
        conn.execute(
            """
            INSERT INTO negotiations (country_a_id, country_b_id, status, started_at)
            VALUES (?, ?, 'active', ?)
            ON CONFLICT(country_a_id, country_b_id)
            DO UPDATE SET status = 'active', started_at = excluded.started_at, ended_at = NULL
            """,
            (country_a_id, country_b_id, now()),
        )
        return {"country_a_id": country_a_id, "country_b_id": country_b_id}


def get_active_negotiation_for_country(country_id):
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT *
            FROM negotiations
            WHERE status = 'active' AND (country_a_id = ? OR country_b_id = ?)
            LIMIT 1
            """,
            (country_id, country_id),
        ).fetchone()
        return dict(row) if row else None


def end_negotiation_for_country(country_id):
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT *
            FROM negotiations
            WHERE status = 'active' AND (country_a_id = ? OR country_b_id = ?)
            LIMIT 1
            """,
            (country_id, country_id),
        ).fetchone()
        if not row:
            return False
        conn.execute(
            "UPDATE negotiations SET status = 'ended', ended_at = ? WHERE id = ?",
            (now(), row["id"]),
        )
        return True


def remove_country_from_alliance(alliance_id, country_id):
    with get_connection() as conn:
        conn.execute(
            "DELETE FROM alliance_members WHERE alliance_id = ? AND country_id = ?",
            (alliance_id, country_id),
        )


def get_alliance_members(alliance_id):
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT c.*
            FROM alliance_members am
            JOIN countries c ON c.id = am.country_id
            WHERE am.alliance_id = ?
            ORDER BY c.name
            """,
            (alliance_id,),
        ).fetchall()
        return [dict(row) for row in rows]


def dissolve_alliance(alliance_id):
    with get_connection() as conn:
        conn.execute("UPDATE alliances SET status = 'dissolved' WHERE id = ?", (alliance_id,))


def record_foreign_investment(investor_country_id, target_country_id, asset, quantity):
    if asset not in {"factories", "banks", "universities"}:
        raise ValueError("Invalid asset for foreign investment.")
    if quantity <= 0:
        raise ValueError("Investment quantity must be greater than zero.")

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO foreign_investments (investor_country_id, target_country_id, asset, quantity, created_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(investor_country_id, target_country_id, asset)
            DO UPDATE SET quantity = foreign_investments.quantity + excluded.quantity
            """,
            (investor_country_id, target_country_id, asset, quantity, now()),
        )


def get_foreign_investments_in_country(country_id):
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT investor_country_id, target_country_id, asset, quantity
            FROM foreign_investments
            WHERE target_country_id = ? AND quantity > 0
            ORDER BY investor_country_id, asset
            """,
            (country_id,),
        ).fetchall()
        return [dict(row) for row in rows]


def get_foreign_investments_by_investor(investor_country_id):
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT fi.target_country_id, c.name AS target_name, fi.asset, fi.quantity
            FROM foreign_investments fi
            JOIN countries c ON c.id = fi.target_country_id
            WHERE fi.investor_country_id = ? AND fi.quantity > 0
            ORDER BY c.name, fi.asset
            """,
            (investor_country_id,),
        ).fetchall()
        return [dict(row) for row in rows]


def clear_foreign_investments(investor_country_id, target_country_id):
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT asset, quantity FROM foreign_investments WHERE investor_country_id = ? AND target_country_id = ? AND quantity > 0",
            (investor_country_id, target_country_id),
        ).fetchall()
        conn.execute(
            "DELETE FROM foreign_investments WHERE investor_country_id = ? AND target_country_id = ?",
            (investor_country_id, target_country_id),
        )
        return [dict(row) for row in rows]


def impose_sanction(imposer_country_id, target_country_id, sanctioned=True):
    if imposer_country_id == target_country_id:
        raise ValueError("A country cannot sanction itself.")

    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO sanctions (imposer_country_id, target_country_id, sanctioned)
            VALUES (?, ?, ?)
            ON CONFLICT(imposer_country_id, target_country_id)
            DO UPDATE SET sanctioned = excluded.sanctioned
            """,
            (imposer_country_id, target_country_id, 1 if sanctioned else 0),
        )


def lift_sanction(imposer_country_id, target_country_id):
    with get_connection() as conn:
        conn.execute(
            "UPDATE sanctions SET sanctioned = 0 WHERE imposer_country_id = ? AND target_country_id = ?",
            (imposer_country_id, target_country_id),
        )


def has_active_sanction(imposer_country_id, target_country_id):
    with get_connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM sanctions WHERE imposer_country_id = ? AND target_country_id = ? AND sanctioned = 1 LIMIT 1",
            (imposer_country_id, target_country_id),
        ).fetchone()
        return row is not None


def get_active_sanctions_against(country_id):
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM sanctions WHERE target_country_id = ? AND sanctioned = 1 ORDER BY id DESC",
            (country_id,),
        ).fetchall()
        return [dict(row) for row in rows]


def record_spy_event(attacker_country_id, target_country_id, event_type, success, details=""):
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO spy_events (attacker_country_id, target_country_id, event_type, success, details, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (attacker_country_id, target_country_id, event_type, 1 if success else 0, details, now()),
        )


def get_spy_events_for_country(country_id):
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT se.*, c.name AS target_name
            FROM spy_events se
            JOIN countries c ON c.id = se.target_country_id
            WHERE se.attacker_country_id = ?
            ORDER BY se.created_at DESC
            LIMIT 20
            """,
            (country_id,),
        ).fetchall()
        return [dict(row) for row in rows]


def create_war(attacker_country_id, defender_country_id, target=None):
    if attacker_country_id == defender_country_id:
        raise ValueError("A country cannot attack itself.")

    with get_connection() as conn:
        cursor = conn.execute(
            "INSERT INTO wars (attacker_country_id, defender_country_id, status, target, started_at) VALUES (?, ?, 'active', ?, ?)",
            (attacker_country_id, defender_country_id, target, now()),
        )
        return cursor.lastrowid


def get_war(war_id):
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM wars WHERE id = ?", (war_id,)).fetchone()
        return dict(row) if row else None


def end_war(war_id):
    with get_connection() as conn:
        conn.execute(
            "UPDATE wars SET status = 'ended', ended_at = ? WHERE id = ?",
            (now(), war_id),
        )


def add_war_event(war_id, attacker_country_id, defender_country_id, event_type, attacker_losses=0, defender_losses=0, description=""):
    with get_connection() as conn:
        cursor = conn.execute(
            """
            INSERT INTO war_events (war_id, attacker_country_id, defender_country_id, event_type, attacker_losses, defender_losses, description, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (war_id, attacker_country_id, defender_country_id, event_type, attacker_losses, defender_losses, description, now()),
        )
        return cursor.lastrowid


def get_war_events(war_id):
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM war_events WHERE war_id = ? ORDER BY id", (war_id,)).fetchall()
        return [dict(row) for row in rows]


def create_trade(seller_country_id, buyer_country_id, weapon_id, quantity, total_price):
    if seller_country_id == buyer_country_id:
        raise ValueError("Seller and buyer cannot be the same country.")
    if quantity <= 0:
        raise ValueError("Quantity must be greater than zero.")
    if total_price < 0:
        raise ValueError("Price cannot be negative.")

    with get_connection() as conn:
        cursor = conn.execute(
            "INSERT INTO trades (seller_country_id, buyer_country_id, weapon_id, quantity, total_price, status, created_at) VALUES (?, ?, ?, ?, ?, 'pending', ?)",
            (seller_country_id, buyer_country_id, weapon_id, quantity, total_price, now()),
        )
        return cursor.lastrowid


def execute_trade(trade_id):
    with get_connection() as conn:
        trade = conn.execute("SELECT * FROM trades WHERE id = ?", (trade_id,)).fetchone()
        if not trade:
            raise ValueError("Trade does not exist.")
        if trade["status"] != "pending":
            raise ValueError("Trade is not pending.")

        seller_id = trade["seller_country_id"]
        buyer_id = trade["buyer_country_id"]
        weapon_id = trade["weapon_id"]
        quantity = trade["quantity"]
        total_price = trade["total_price"]

        seller = conn.execute("SELECT * FROM countries WHERE id = ?", (seller_id,)).fetchone()
        buyer = conn.execute("SELECT * FROM countries WHERE id = ?", (buyer_id,)).fetchone()
        weapon = conn.execute("SELECT * FROM weapons WHERE id = ?", (weapon_id,)).fetchone()

        if not seller or not buyer:
            raise ValueError("Seller or buyer does not exist.")
        if not weapon:
            raise ValueError("Weapon does not exist.")
        if buyer["money"] < total_price:
            raise ValueError("Buyer does not have enough money.")

        inventory = conn.execute(
            "SELECT quantity FROM country_weapons WHERE country_id = ? AND weapon_id = ?",
            (seller_id, weapon_id),
        ).fetchone()

        seller_quantity = inventory["quantity"] if inventory else 0
        if seller_quantity < quantity:
            raise ValueError("Seller does not have enough weapons.")

        conn.execute("UPDATE countries SET money = money - ? WHERE id = ?", (total_price, buyer_id))
        conn.execute("UPDATE countries SET money = money + ? WHERE id = ?", (total_price, seller_id))

        conn.execute(
            "UPDATE country_weapons SET quantity = quantity - ? WHERE country_id = ? AND weapon_id = ?",
            (quantity, seller_id, weapon_id),
        )

        conn.execute(
            """
            INSERT INTO country_weapons (country_id, weapon_id, quantity)
            VALUES (?, ?, ?)
            ON CONFLICT(country_id, weapon_id)
            DO UPDATE SET quantity = country_weapons.quantity + excluded.quantity
            """,
            (buyer_id, weapon_id, quantity),
        )

        conn.execute("UPDATE trades SET status = 'completed' WHERE id = ?", (trade_id,))

        conn.execute(
            "INSERT INTO transactions (from_country_id, to_country_id, amount, type, reference_id, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (buyer_id, seller_id, total_price, "weapon_trade", trade_id, now()),
        )

        return True


def cancel_trade(trade_id):
    with get_connection() as conn:
        conn.execute("UPDATE trades SET status = 'cancelled' WHERE id = ? AND status = 'pending'", (trade_id,))


def get_trade(trade_id):
    with get_connection() as conn:
        row = conn.execute(
            """
            SELECT t.*, s.name AS seller_name, b.name AS buyer_name, w.name AS weapon_name
            FROM trades t
            JOIN countries s ON s.id = t.seller_country_id
            JOIN countries b ON b.id = t.buyer_country_id
            JOIN weapons w ON w.id = t.weapon_id
            WHERE t.id = ?
            """,
            (trade_id,),
        ).fetchone()
        return dict(row) if row else None


def create_market_listing(seller_country_id, weapon_id, quantity, price):
    if quantity <= 0:
        raise ValueError("Quantity must be greater than zero.")
    if price < 0:
        raise ValueError("Price cannot be negative.")

    with get_connection() as conn:
        inventory = conn.execute(
            "SELECT quantity FROM country_weapons WHERE country_id = ? AND weapon_id = ?",
            (seller_country_id, weapon_id),
        ).fetchone()

        current_quantity = inventory["quantity"] if inventory else 0
        if current_quantity < quantity:
            raise ValueError("Not enough weapons.")

        conn.execute(
            "UPDATE country_weapons SET quantity = quantity - ? WHERE country_id = ? AND weapon_id = ?",
            (quantity, seller_country_id, weapon_id),
        )

        cursor = conn.execute(
            "INSERT INTO markets (seller_country_id, weapon_id, quantity, price, status, created_at) VALUES (?, ?, ?, ?, 'open', ?)",
            (seller_country_id, weapon_id, quantity, price, now()),
        )
        return cursor.lastrowid


def get_open_market():
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT m.*, c.name AS seller_name, w.name AS weapon_name, w.category
            FROM markets m
            JOIN countries c ON c.id = m.seller_country_id
            JOIN weapons w ON w.id = m.weapon_id
            WHERE m.status = 'open'
            ORDER BY m.created_at DESC
            """,
        ).fetchall()
        return [dict(row) for row in rows]


def add_transaction(from_country_id, to_country_id, amount, transaction_type, reference_id=None):
    with get_connection() as conn:
        cursor = conn.execute(
            "INSERT INTO transactions (from_country_id, to_country_id, amount, type, reference_id, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (from_country_id, to_country_id, amount, transaction_type, reference_id, now()),
        )
        return cursor.lastrowid


def get_country_transactions(country_id, limit=100):
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM transactions WHERE from_country_id = ? OR to_country_id = ? ORDER BY id DESC LIMIT ?",
            (country_id, country_id, limit),
        ).fetchall()
        return [dict(row) for row in rows]


init_db()


if __name__ == "__main__":
    print("========================================")
    print("Game database initialized successfully.")
    print(f"Database: {DB_PATH}")
    print("========================================")
