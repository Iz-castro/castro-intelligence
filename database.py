# -*- coding: utf-8 -*-

import sqlite3
import logging
from datetime import datetime, timezone
from contextlib import contextmanager

from config import DATABASE_PATH

logger = logging.getLogger("castro_crm.database")


def get_connection():
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


@contextmanager
def db_session():
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_database():
    with db_session() as conn:
        c = conn.cursor()

        c.execute("""
            CREATE TABLE IF NOT EXISTS departments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                description TEXT DEFAULT '',
                is_active INTEGER DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                display_name TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                department_id INTEGER,
                role TEXT DEFAULT 'operador',
                avatar_path TEXT DEFAULT '',
                is_active INTEGER DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                last_login TEXT,
                failed_attempts INTEGER DEFAULT 0,
                locked_until TEXT,
                FOREIGN KEY (department_id) REFERENCES departments(id)
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sender_id INTEGER NOT NULL,
                receiver_id INTEGER NOT NULL,
                content TEXT NOT NULL,
                msg_type TEXT NOT NULL DEFAULT 'text',
                is_read INTEGER DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (sender_id) REFERENCES users(id),
                FOREIGN KEY (receiver_id) REFERENCES users(id)
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS wa_contacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                wa_id TEXT NOT NULL UNIQUE,
                display_name TEXT DEFAULT '',
                phone_formatted TEXT DEFAULT '',
                profile_picture_url TEXT DEFAULT '',
                contact_avatar_path TEXT DEFAULT '',
                qualification TEXT DEFAULT 'novo',
                notes TEXT DEFAULT '',
                assigned_to INTEGER,
                department_id INTEGER,
                is_archived INTEGER DEFAULT 0,
                first_seen_at TEXT NOT NULL DEFAULT (datetime('now')),
                last_message_at TEXT,
                FOREIGN KEY (assigned_to) REFERENCES users(id),
                FOREIGN KEY (department_id) REFERENCES departments(id)
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS wa_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                wa_message_id TEXT UNIQUE,
                contact_id INTEGER NOT NULL,
                direction TEXT NOT NULL DEFAULT 'inbound',
                msg_type TEXT NOT NULL DEFAULT 'text',
                content TEXT DEFAULT '',
                media_path TEXT DEFAULT '',
                media_mime TEXT DEFAULT '',
                media_id TEXT DEFAULT '',
                latitude REAL,
                longitude REAL,
                filename TEXT DEFAULT '',
                status TEXT DEFAULT 'received',
                operator_id INTEGER,
                timestamp_wa TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (contact_id) REFERENCES wa_contacts(id),
                FOREIGN KEY (operator_id) REFERENCES users(id)
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS wa_message_status (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                wa_message_id TEXT NOT NULL,
                status TEXT NOT NULL,
                timestamp_wa TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS wa_transfer_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                contact_id INTEGER NOT NULL,
                from_user_id INTEGER,
                to_user_id INTEGER,
                from_department_id INTEGER,
                to_department_id INTEGER,
                reason TEXT DEFAULT '',
                summary TEXT DEFAULT '',
                transferred_by INTEGER NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (contact_id) REFERENCES wa_contacts(id),
                FOREIGN KEY (from_user_id) REFERENCES users(id),
                FOREIGN KEY (to_user_id) REFERENCES users(id),
                FOREIGN KEY (transferred_by) REFERENCES users(id)
            )
        """)

        c.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                action TEXT NOT NULL,
                detail TEXT DEFAULT '',
                ip_address TEXT DEFAULT '',
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)

        c.execute("CREATE INDEX IF NOT EXISTS idx_msg_sender ON messages(sender_id, created_at)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_msg_receiver ON messages(receiver_id, created_at)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_wa_contact ON wa_contacts(wa_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_wa_contact_assigned ON wa_contacts(assigned_to)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_wa_msg_contact ON wa_messages(contact_id, created_at)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_wa_msg_wamid ON wa_messages(wa_message_id)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_wa_transfer ON wa_transfer_log(contact_id, created_at)")
        c.execute("CREATE INDEX IF NOT EXISTS idx_audit ON audit_log(user_id, created_at)")

        # Migracoes para bancos existentes
        _migrate(c, "wa_contacts", "assigned_to", "INTEGER")
        _migrate(c, "wa_contacts", "department_id", "INTEGER")
        _migrate(c, "wa_contacts", "qualification", "TEXT DEFAULT 'novo'")
        _migrate(c, "wa_contacts", "notes", "TEXT DEFAULT ''")
        _migrate(c, "wa_contacts", "is_archived", "INTEGER DEFAULT 0")
        _migrate(c, "wa_contacts", "contact_avatar_path", "TEXT DEFAULT ''")
        _migrate(c, "users", "department_id", "INTEGER")
        _migrate(c, "users", "avatar_path", "TEXT DEFAULT ''")
        _migrate(c, "users", "role", "TEXT DEFAULT 'operador'")
        _migrate(c, "wa_transfer_log", "summary", "TEXT DEFAULT ''")

    logger.info("Banco de dados inicializado")


def _migrate(cursor, table, column, col_type):
    try:
        cursor.execute(f"SELECT {column} FROM {table} LIMIT 1")
    except sqlite3.OperationalError:
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
        logger.info("Migrado: %s.%s", table, column)


# -- Departamentos --

def create_department(name, description=""):
    with db_session() as conn:
        existing = conn.execute("SELECT id FROM departments WHERE name = ?", (name,)).fetchone()
        if existing:
            return existing["id"]
        cursor = conn.execute(
            "INSERT INTO departments (name, description) VALUES (?, ?)", (name, description)
        )
        return cursor.lastrowid


def get_all_departments():
    with db_session() as conn:
        rows = conn.execute("SELECT * FROM departments WHERE is_active = 1 ORDER BY name").fetchall()
        return [dict(r) for r in rows]


# -- Usuarios --

def get_user_by_username(username):
    with db_session() as conn:
        row = conn.execute("SELECT * FROM users WHERE username = ? AND is_active = 1", (username,)).fetchone()
        return dict(row) if row else None


def get_user_by_id(user_id):
    with db_session() as conn:
        row = conn.execute(
            "SELECT id, username, display_name, department_id, role, is_active, "
            "created_at, last_login, avatar_path "
            "FROM users WHERE id = ? AND is_active = 1", (user_id,)
        ).fetchone()
        return dict(row) if row else None


def get_all_users():
    with db_session() as conn:
        rows = conn.execute(
            """SELECT u.id, u.username, u.display_name, u.is_active, u.last_login,
                      u.department_id, u.avatar_path, u.role, d.name as department_name
               FROM users u LEFT JOIN departments d ON d.id = u.department_id"""
        ).fetchall()
        return [dict(r) for r in rows]


def create_user(username, display_name, password_hash, department_id=None, role="operador"):
    with db_session() as conn:
        existing = conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
        if existing:
            return None
        cursor = conn.execute(
            "INSERT INTO users (username, display_name, password_hash, department_id, role) "
            "VALUES (?, ?, ?, ?, ?)",
            (username, display_name, password_hash, department_id, role)
        )
        return cursor.lastrowid


def update_user(user_id, display_name=None, department_id=None, role=None):
    with db_session() as conn:
        fields = []
        values = []
        if display_name is not None:
            fields.append("display_name = ?")
            values.append(display_name)
        if department_id is not None:
            fields.append("department_id = ?")
            values.append(department_id if department_id else None)
        if role is not None:
            fields.append("role = ?")
            values.append(role)
        if not fields:
            return False
        values.append(user_id)
        conn.execute(f"UPDATE users SET {', '.join(fields)} WHERE id = ?", values)
        return True


def deactivate_user(user_id):
    with db_session() as conn:
        conn.execute("UPDATE users SET is_active = 0 WHERE id = ?", (user_id,))


def update_last_login(user_id):
    now = datetime.now(timezone.utc).isoformat()
    with db_session() as conn:
        conn.execute(
            "UPDATE users SET last_login = ?, failed_attempts = 0, locked_until = NULL WHERE id = ?",
            (now, user_id)
        )


def increment_failed_attempts(username, lockout_until=None):
    with db_session() as conn:
        if lockout_until:
            conn.execute(
                "UPDATE users SET failed_attempts = failed_attempts + 1, locked_until = ? WHERE username = ?",
                (lockout_until, username)
            )
        else:
            conn.execute(
                "UPDATE users SET failed_attempts = failed_attempts + 1 WHERE username = ?",
                (username,)
            )


def update_user_avatar(user_id, avatar_path):
    with db_session() as conn:
        conn.execute("UPDATE users SET avatar_path = ? WHERE id = ?", (avatar_path, user_id))


def get_user_avatar(user_id):
    with db_session() as conn:
        row = conn.execute(
            "SELECT avatar_path FROM users WHERE id = ? AND is_active = 1", (user_id,)
        ).fetchone()
        if row and row["avatar_path"]:
            return row["avatar_path"]
        return ""


# -- Mensagens internas --

def save_internal_message(sender_id, receiver_id, content, msg_type="text"):
    with db_session() as conn:
        cursor = conn.execute(
            "INSERT INTO messages (sender_id, receiver_id, content, msg_type) VALUES (?, ?, ?, ?)",
            (sender_id, receiver_id, content, msg_type)
        )
        return cursor.lastrowid


def get_internal_conversation(user_a, user_b, limit=100, offset=0):
    with db_session() as conn:
        rows = conn.execute(
            """SELECT m.id, m.sender_id, m.receiver_id, m.content, m.msg_type,
                      m.is_read, m.created_at, u.display_name as sender_name
               FROM messages m JOIN users u ON u.id = m.sender_id
               WHERE (m.sender_id = ? AND m.receiver_id = ?) OR (m.sender_id = ? AND m.receiver_id = ?)
               ORDER BY m.created_at ASC LIMIT ? OFFSET ?""",
            (user_a, user_b, user_b, user_a, limit, offset)
        ).fetchall()
        return [dict(r) for r in rows]


def mark_messages_as_read(reader_id, sender_id):
    with db_session() as conn:
        conn.execute(
            "UPDATE messages SET is_read = 1 WHERE receiver_id = ? AND sender_id = ? AND is_read = 0",
            (reader_id, sender_id)
        )


def get_unread_count(user_id):
    with db_session() as conn:
        rows = conn.execute(
            "SELECT sender_id, COUNT(*) as count FROM messages WHERE receiver_id = ? AND is_read = 0 GROUP BY sender_id",
            (user_id,)
        ).fetchall()
        return {r["sender_id"]: r["count"] for r in rows}


# -- Contatos WhatsApp --

def upsert_wa_contact(wa_id, display_name=""):
    phone_formatted = format_phone_br(wa_id)
    now = datetime.now(timezone.utc).isoformat()
    with db_session() as conn:
        existing = conn.execute("SELECT id FROM wa_contacts WHERE wa_id = ?", (wa_id,)).fetchone()
        if existing:
            conn.execute(
                "UPDATE wa_contacts SET display_name = ?, last_message_at = ? WHERE wa_id = ?",
                (display_name or "", now, wa_id)
            )
            return existing["id"]
        else:
            cursor = conn.execute(
                "INSERT INTO wa_contacts (wa_id, display_name, phone_formatted, last_message_at) VALUES (?, ?, ?, ?)",
                (wa_id, display_name or "", phone_formatted, now)
            )
            return cursor.lastrowid


def get_wa_contact(contact_id):
    with db_session() as conn:
        row = conn.execute(
            """SELECT wc.*, u.display_name as assigned_name, u.role as assigned_role,
                      d.name as department_name
               FROM wa_contacts wc
               LEFT JOIN users u ON u.id = wc.assigned_to
               LEFT JOIN departments d ON d.id = wc.department_id
               WHERE wc.id = ?""", (contact_id,)
        ).fetchone()
        return dict(row) if row else None


def get_all_wa_contacts(include_archived=False):
    with db_session() as conn:
        where = "" if include_archived else "WHERE wc.is_archived = 0"
        rows = conn.execute(
            f"""SELECT wc.*, u.display_name as assigned_name, u.role as assigned_role,
                       d.name as department_name
                FROM wa_contacts wc
                LEFT JOIN users u ON u.id = wc.assigned_to
                LEFT JOIN departments d ON d.id = wc.department_id
                {where}
                ORDER BY wc.last_message_at DESC"""
        ).fetchall()
        return [dict(r) for r in rows]


def update_wa_contact_qualification(contact_id, qualification, notes=""):
    with db_session() as conn:
        fields = ["qualification = ?"]
        values = [qualification]
        if notes is not None:
            fields.append("notes = ?")
            values.append(notes)
        values.append(contact_id)
        conn.execute(
            f"UPDATE wa_contacts SET {', '.join(fields)} WHERE id = ?", values
        )


def archive_wa_contact(contact_id):
    with db_session() as conn:
        conn.execute("UPDATE wa_contacts SET is_archived = 1 WHERE id = ?", (contact_id,))


def restore_wa_contact(contact_id):
    with db_session() as conn:
        conn.execute("UPDATE wa_contacts SET is_archived = 0 WHERE id = ?", (contact_id,))


def update_contact_avatar(contact_id, avatar_path):
    with db_session() as conn:
        conn.execute(
            "UPDATE wa_contacts SET contact_avatar_path = ? WHERE id = ?",
            (avatar_path, contact_id)
        )


# -- Transferencia / Atribuicao --

def assign_wa_contact(contact_id, to_user_id, to_department_id, transferred_by, reason="", summary=""):
    with db_session() as conn:
        current = conn.execute(
            "SELECT assigned_to, department_id FROM wa_contacts WHERE id = ?", (contact_id,)
        ).fetchone()
        if not current:
            return None

        from_user = current["assigned_to"]
        from_dept = current["department_id"]

        conn.execute(
            "UPDATE wa_contacts SET assigned_to = ?, department_id = ? WHERE id = ?",
            (to_user_id, to_department_id, contact_id)
        )
        conn.execute(
            """INSERT INTO wa_transfer_log
               (contact_id, from_user_id, to_user_id, from_department_id, to_department_id,
                reason, summary, transferred_by)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (contact_id, from_user, to_user_id, from_dept, to_department_id,
             reason, summary, transferred_by)
        )
        return {"from_user_id": from_user, "to_user_id": to_user_id}


def insert_transfer_system_message(contact_id, content, operator_id=None):
    """Insere mensagem de sistema na conversa para marcar transferencia."""
    now = datetime.now(timezone.utc).isoformat()
    with db_session() as conn:
        cursor = conn.execute(
            """INSERT INTO wa_messages
               (wa_message_id, contact_id, direction, msg_type, content, status, timestamp_wa, operator_id)
               VALUES (?, ?, 'system', 'system', ?, 'delivered', ?, ?)""",
            (f"sys_{now}_{contact_id}", contact_id, content, now, operator_id)
        )
        return cursor.lastrowid


def get_transfer_history(contact_id, limit=50):
    with db_session() as conn:
        rows = conn.execute(
            """SELECT tl.*,
                      fu.display_name as from_user_name, tu.display_name as to_user_name,
                      fd.name as from_dept_name, td.name as to_dept_name,
                      tb.display_name as transferred_by_name
               FROM wa_transfer_log tl
               LEFT JOIN users fu ON fu.id = tl.from_user_id
               LEFT JOIN users tu ON tu.id = tl.to_user_id
               LEFT JOIN departments fd ON fd.id = tl.from_department_id
               LEFT JOIN departments td ON td.id = tl.to_department_id
               LEFT JOIN users tb ON tb.id = tl.transferred_by
               WHERE tl.contact_id = ? ORDER BY tl.created_at DESC LIMIT ?""",
            (contact_id, limit)
        ).fetchall()
        return [dict(r) for r in rows]


# -- Mensagens WhatsApp --

def save_wa_message(wa_message_id, contact_id, direction, msg_type, content="",
                    media_path="", media_mime="", media_id="",
                    latitude=None, longitude=None, filename="",
                    status="received", timestamp_wa="", operator_id=None):
    with db_session() as conn:
        existing = conn.execute("SELECT id FROM wa_messages WHERE wa_message_id = ?", (wa_message_id,)).fetchone()
        if existing:
            return existing["id"]
        cursor = conn.execute(
            """INSERT INTO wa_messages
               (wa_message_id, contact_id, direction, msg_type, content,
                media_path, media_mime, media_id, latitude, longitude, filename, status, timestamp_wa, operator_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (wa_message_id, contact_id, direction, msg_type, content,
             media_path, media_mime, media_id, latitude, longitude, filename, status, timestamp_wa, operator_id)
        )
        return cursor.lastrowid


def get_wa_conversation(contact_id, limit=200, offset=0):
    with db_session() as conn:
        rows = conn.execute(
            """SELECT wm.*, wc.display_name as contact_name, wc.wa_id, wc.phone_formatted,
                      wc.contact_avatar_path,
                      op.display_name as operator_name
               FROM wa_messages wm
               JOIN wa_contacts wc ON wc.id = wm.contact_id
               LEFT JOIN users op ON op.id = wm.operator_id
               WHERE wm.contact_id = ? ORDER BY wm.created_at ASC LIMIT ? OFFSET ?""",
            (contact_id, limit, offset)
        ).fetchall()
        return [dict(r) for r in rows]


def update_wa_message_status(wa_message_id, status, timestamp_wa=""):
    with db_session() as conn:
        conn.execute("UPDATE wa_messages SET status = ? WHERE wa_message_id = ?", (status, wa_message_id))
        conn.execute(
            "INSERT INTO wa_message_status (wa_message_id, status, timestamp_wa) VALUES (?, ?, ?)",
            (wa_message_id, status, timestamp_wa)
        )


def get_wa_unread_count():
    with db_session() as conn:
        rows = conn.execute(
            "SELECT contact_id, COUNT(*) as count FROM wa_messages "
            "WHERE direction = 'inbound' AND status = 'received' GROUP BY contact_id"
        ).fetchall()
        return {r["contact_id"]: r["count"] for r in rows}


def mark_wa_conversation_read(contact_id):
    with db_session() as conn:
        conn.execute(
            "UPDATE wa_messages SET status = 'read' WHERE contact_id = ? "
            "AND direction = 'inbound' AND status = 'received'",
            (contact_id,)
        )


# -- Auditoria --

def log_audit(user_id, action, detail="", ip_address=""):
    with db_session() as conn:
        conn.execute(
            "INSERT INTO audit_log (user_id, action, detail, ip_address) VALUES (?, ?, ?, ?)",
            (user_id, action, detail, ip_address)
        )


# -- Utilidades --

def format_phone_br(wa_id):
    s = str(wa_id)
    if len(s) == 13 and s.startswith("55"):
        return f"+55 ({s[2:4]}) {s[4:9]}-{s[9:]}"
    elif len(s) == 12 and s.startswith("55"):
        return f"+55 ({s[2:4]}) {s[4:8]}-{s[8:]}"
    return f"+{s}" if not s.startswith("+") else s


def normalize_br_phone(wa_id):
    s = str(wa_id)
    if len(s) == 12 and s.startswith("55"):
        ddd = s[2:4]
        local = s[4:]
        if local[0] in ("6", "7", "8", "9"):
            return f"55{ddd}9{local}"
    return s
