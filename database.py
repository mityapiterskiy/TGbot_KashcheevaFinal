import sqlite3
import datetime

class Database:
    def __init__(self, db_name="bot_database.db"):
        self.conn = sqlite3.connect(db_name)
        self.cursor = self.conn.cursor()
        self.create_tables()

    def create_tables(self):
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                joined_at TEXT,
                last_interaction TEXT,
                is_finished BOOLEAN DEFAULT 0,
                reminded BOOLEAN DEFAULT 0
            )
        """)
        self.cursor.execute("""
            CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                event_type TEXT,
                content TEXT,
                timestamp TEXT
            )
        """)
        self.conn.commit()

    def add_or_update_user(self, user_id, username, first_name):
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
        if self.cursor.fetchone():
            self.cursor.execute("""
                UPDATE users SET last_interaction = ?, username = ?, first_name = ? 
                WHERE user_id = ?
            """, (now, username, first_name, user_id))
        else:
            self.cursor.execute("""
                INSERT INTO users (user_id, username, first_name, joined_at, last_interaction)
                VALUES (?, ?, ?, ?, ?)
            """, (user_id, username, first_name, now, now))
        self.conn.commit()

    def log_event(self, user_id, event_type, content):
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.cursor.execute("""
            INSERT INTO logs (user_id, event_type, content, timestamp)
            VALUES (?, ?, ?, ?)
        """, (user_id, event_type, content, now))
        self.conn.commit()

    def mark_finished(self, user_id):
        self.cursor.execute("UPDATE users SET is_finished = 1 WHERE user_id = ?", (user_id,))
        self.conn.commit()

    def get_users_for_reminder(self):
        limit_time = (datetime.datetime.now() - datetime.timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
        self.cursor.execute("""
            SELECT user_id FROM users 
            WHERE is_finished = 0 AND reminded = 0 AND last_interaction < ?
        """, (limit_time,))
        return [row[0] for row in self.cursor.fetchall()]

    def set_reminded(self, user_id):
        self.cursor.execute("UPDATE users SET reminded = 1 WHERE user_id = ?", (user_id,))
        self.conn.commit()

    def update_interaction(self, user_id):
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.cursor.execute("UPDATE users SET last_interaction = ? WHERE user_id = ?", (now, user_id))
        self.conn.commit()

    def get_all_users_paginated(self, page, limit=10):
        offset = page * limit
        self.cursor.execute("""
            SELECT user_id, first_name, username, joined_at 
            FROM users ORDER BY joined_at DESC LIMIT ? OFFSET ?
        """, (limit, offset))
        return self.cursor.fetchall()

    def get_user_count(self):
        self.cursor.execute("SELECT COUNT(*) FROM users")
        return self.cursor.fetchone()[0]

    def get_user_logs(self, user_id):
        self.cursor.execute("""
            SELECT event_type, content, timestamp FROM logs 
            WHERE user_id = ? ORDER BY timestamp ASC
        """, (user_id,))
        return self.cursor.fetchall()

    def get_user_info(self, user_id):
        self.cursor.execute("SELECT username, first_name FROM users WHERE user_id = ?", (user_id,))
        return self.cursor.fetchone()

db = Database()