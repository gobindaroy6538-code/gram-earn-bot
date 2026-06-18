import sqlite3
from datetime import datetime


class Database:
    def __init__(self, db_path="earnbd.db"):
        self.db_path = db_path
        self._init_db()

    def _conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id     INTEGER PRIMARY KEY,
                    name        TEXT,
                    username    TEXT,
                    balance     REAL DEFAULT 0,
                    referrer_id INTEGER,
                    joined_date TEXT,
                    banned      INTEGER DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS tasks (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    title       TEXT,
                    description TEXT,
                    link        TEXT,
                    reward      REAL,
                    task_type   TEXT DEFAULT 'telegram',
                    active      INTEGER DEFAULT 1
                );
                CREATE TABLE IF NOT EXISTS completions (
                    user_id INTEGER,
                    task_id INTEGER,
                    done_at TEXT,
                    PRIMARY KEY (user_id, task_id)
                );
                CREATE TABLE IF NOT EXISTS withdrawals (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id    INTEGER,
                    amount     REAL,
                    method     TEXT,
                    number     TEXT,
                    status     TEXT DEFAULT 'pending',
                    created_at TEXT
                );
            """)

    def register_user(self, user_id, name, username, referrer_id=None):
        with self._conn() as conn:
            existing = conn.execute("SELECT user_id FROM users WHERE user_id=?", (user_id,)).fetchone()
            if existing:
                return False
            conn.execute(
                "INSERT INTO users (user_id, name, username, referrer_id, joined_date) VALUES (?,?,?,?,?)",
                (user_id, name, username, referrer_id, datetime.now().strftime("%d/%m/%Y"))
            )
            return True

    def get_user(self, user_id):
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
            return dict(row) if row else None

    def get_all_users(self):
        with self._conn() as conn:
            rows = conn.execute("SELECT * FROM users").fetchall()
            return [dict(r) for r in rows]

    def add_balance(self, user_id, amount):
        with self._conn() as conn:
            conn.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (amount, user_id))

    def deduct_balance(self, user_id, amount):
        with self._conn() as conn:
            conn.execute("UPDATE users SET balance = balance - ? WHERE user_id=?", (amount, user_id))

    def get_referral_count(self, user_id):
        with self._conn() as conn:
            row = conn.execute("SELECT COUNT(*) as cnt FROM users WHERE referrer_id=?", (user_id,)).fetchone()
            return row["cnt"]

    def get_leaderboard(self):
        with self._conn() as conn:
            rows = conn.execute("SELECT name, balance FROM users ORDER BY balance DESC LIMIT 10").fetchall()
            return [dict(r) for r in rows]

    def ban_user(self, user_id):
        with self._conn() as conn:
            conn.execute("UPDATE users SET banned=1 WHERE user_id=?", (user_id,))

    def unban_user(self, user_id):
        with self._conn() as conn:
            conn.execute("UPDATE users SET banned=0 WHERE user_id=?", (user_id,))

    def add_task(self, title, description, link, reward, task_type="telegram"):
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO tasks (title, description, link, reward, task_type) VALUES (?,?,?,?,?)",
                (title, description, link, reward, task_type)
            )

    def get_all_tasks(self):
        with self._conn() as conn:
            rows = conn.execute("SELECT * FROM tasks WHERE active=1").fetchall()
            return [dict(r) for r in rows]

    def get_task(self, task_id):
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
            return dict(row) if row else None

    def complete_task(self, user_id, task_id, reward):
        with self._conn() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO completions (user_id, task_id, done_at) VALUES (?,?,?)",
                (user_id, task_id, datetime.now().isoformat())
            )
            conn.execute("UPDATE users SET balance = balance + ? WHERE user_id=?", (reward, user_id))

    def is_task_completed(self, user_id, task_id):
        with self._conn() as conn:
            row = conn.execute(
                "SELECT 1 FROM completions WHERE user_id=? AND task_id=?", (user_id, task_id)
            ).fetchone()
            return row is not None

    def get_completed_tasks(self, user_id):
        with self._conn() as conn:
            rows = conn.execute("SELECT task_id FROM completions WHERE user_id=?", (user_id,)).fetchall()
            return [r["task_id"] for r in rows]

    def create_withdrawal(self, user_id, amount, method, number):
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO withdrawals (user_id, amount, method, number, created_at) VALUES (?,?,?,?,?)",
                (user_id, amount, method, number, datetime.now().isoformat())
            )

    def update_withdrawal_status(self, user_id, amount, status):
        with self._conn() as conn:
            conn.execute(
                "UPDATE withdrawals SET status=? WHERE user_id=? AND amount=? AND status='pending'",
                (status, user_id, amount)
            )

    def get_stats(self):
        with self._conn() as conn:
            total_users = conn.execute("SELECT COUNT(*) as c FROM users").fetchone()["c"]
            total_completions = conn.execute("SELECT COUNT(*) as c FROM completions").fetchone()["c"]
            pending_withdrawals = conn.execute(
                "SELECT COUNT(*) as c FROM withdrawals WHERE status='pending'"
            ).fetchone()["c"]
            total_paid_row = conn.execute(
                "SELECT SUM(amount) as s FROM withdrawals WHERE status='approved'"
            ).fetchone()["s"]
            total_paid = total_paid_row if total_paid_row else 0
            return {
                "total_users": total_users,
                "total_completions": total_completions,
                "pending_withdrawals": pending_withdrawals,
                "total_paid": total_paid,
            }
