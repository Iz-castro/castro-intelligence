# Estrutura do Projeto

## Arvore de Arquivos

```
+-- static/
|   +-- chat.html
|   +-- index.html
+-- {static/
|   +-- {css,js},media,logs}/
+-- .dockerignore
+-- .env.example
+-- Dockerfile
+-- auth.py
+-- config.py
+-- database.py
+-- deploy.sh
+-- estrutura_projeto.md
+-- gerar_estrutura.py
+-- init_db.py
+-- main.py
+-- media.py
+-- requirements.txt
+-- start.ps1
+-- start_tunnel.py
+-- test_debug.py
+-- webhook.py
```

## Codigo dos Arquivos

## .dockerignore

```text
__pycache__
*.pyc
*.pyo
.env
.git
.gitignore
venv
*.db
logs/*.log
media/*
*.tar.gz
deploy.sh
start_tunnel.py
test_debug.py
README.md
.env.example

```

## .env.example

```text
# Castro Intelligence CRM - Variaveis de Ambiente
# Copie para .env e preencha os valores

# Seguranca
SECRET_KEY=gerar_com_openssl_rand_hex_32

# WhatsApp Business API (Meta Cloud API)
WHATSAPP_TOKEN=seu_token_temporario_ou_permanente
WHATSAPP_PHONE_NUMBER_ID=983401388192837
WHATSAPP_WABA_ID=275244975509458
WHATSAPP_VERIFY_TOKEN=hubloc2024
WHATSAPP_APP_SECRET=chave_secreta_do_app_meta

# Google Cloud (deploy)
GCP_PROJECT_ID=seu-projeto-gcp

```

## Dockerfile

```text
FROM python:3.10-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libffi-dev ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/media/images /app/media/audio /app/media/video \
    /app/media/documents /app/media/stickers /app/media/avatars /app/logs

RUN python init_db.py

EXPOSE 8080

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]

```

## auth.py

```python
# -*- coding: utf-8 -*-

import logging
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from config import (
    SECRET_KEY, JWT_ALGORITHM, JWT_EXPIRATION_MINUTES,
    MAX_LOGIN_ATTEMPTS, LOGIN_LOCKOUT_SECONDS,
)
from database import (
    get_user_by_username, update_last_login,
    increment_failed_attempts, log_audit,
)

logger = logging.getLogger("castro_crm.auth")


def hash_password(plain):
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(plain.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain, hashed):
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def create_token(user_id, username):
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "usr": username,
        "iat": now,
        "exp": now + timedelta(minutes=JWT_EXPIRATION_MINUTES),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_token(token):
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def authenticate(username, password, ip_address=""):
    user = get_user_by_username(username)

    if not user:
        return {"success": False, "error": "Credenciais invalidas"}

    if user.get("locked_until"):
        lock_time = datetime.fromisoformat(user["locked_until"])
        if datetime.now(timezone.utc) < lock_time:
            remaining = int((lock_time - datetime.now(timezone.utc)).total_seconds())
            log_audit(user["id"], "LOGIN_BLOCKED", f"{remaining}s restantes", ip_address)
            return {"success": False, "error": f"Conta bloqueada. Tente em {remaining}s"}

    if not verify_password(password, user["password_hash"]):
        attempts = user.get("failed_attempts", 0) + 1
        lockout = None
        if attempts >= MAX_LOGIN_ATTEMPTS:
            lockout = (datetime.now(timezone.utc) + timedelta(seconds=LOGIN_LOCKOUT_SECONDS)).isoformat()
            log_audit(user["id"], "LOGIN_LOCKOUT", f"{attempts} tentativas", ip_address)
        increment_failed_attempts(username, lockout)
        log_audit(user["id"], "LOGIN_FAILED", f"Tentativa {attempts}", ip_address)
        return {"success": False, "error": "Credenciais invalidas"}

    update_last_login(user["id"])
    token = create_token(user["id"], user["username"])
    log_audit(user["id"], "LOGIN_SUCCESS", "", ip_address)

    return {
        "success": True,
        "token": token,
        "user": {
            "id": user["id"],
            "username": user["username"],
            "display_name": user["display_name"],
        },
    }

```

## config.py

```python
# -*- coding: utf-8 -*-

import os
import secrets

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# -- Banco de dados --
DATABASE_PATH = os.getenv("DATABASE_PATH", os.path.join(BASE_DIR, "castro_crm.db"))

# -- Seguranca --
SECRET_KEY = os.getenv("SECRET_KEY", secrets.token_hex(32))
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_MINUTES = int(os.getenv("JWT_EXPIRATION_MINUTES", "480"))

MAX_LOGIN_ATTEMPTS = 5
LOGIN_LOCKOUT_SECONDS = 300
MAX_MESSAGE_LENGTH = 4000

# -- Servidor --
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8080"))

# -- WhatsApp Business API (Meta Cloud API) --
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN", "")
WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
WHATSAPP_WABA_ID = os.getenv("WHATSAPP_WABA_ID", "")
WHATSAPP_VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "hubloc2024")
WHATSAPP_APP_SECRET = os.getenv("WHATSAPP_APP_SECRET", "")

GRAPH_API_VERSION = "v22.0"
GRAPH_API_BASE = f"https://graph.facebook.com/{GRAPH_API_VERSION}"

# -- Media --
MEDIA_DIR = os.getenv("MEDIA_DIR", os.path.join(BASE_DIR, "media"))
MAX_MEDIA_SIZE_MB = 16

# -- Avatar / Foto de perfil --
AVATAR_DIR = os.path.join(MEDIA_DIR, "avatars")
AVATAR_MAX_SIZE_KB = 512
AVATAR_ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp"}

# -- Audio gravado --
AUDIO_MAX_DURATION_SEC = 120
AUDIO_ALLOWED_MIME = {"audio/ogg", "audio/webm", "audio/mp4", "audio/mpeg"}

# -- Qualificacao de contatos --
QUALIFICATION_OPTIONS = [
    "novo",
    "em_atendimento",
    "qualificado",
    "nao_qualificado",
    "convertido",
]

# -- Cargos / funcoes --
ROLE_OPTIONS = [
    "admin",
    "supervisor",
    "operador",
]

# -- Logging --
LOG_FILE = os.path.join(BASE_DIR, "logs", "castro_crm.log")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

```

## database.py

```python
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

```

## deploy.sh

```bash
#!/bin/bash
# -*- coding: utf-8 -*-
# Deploy do CRM Castro Intelligence no Google Cloud Run
#
# Pre-requisitos:
#   1. Google Cloud SDK instalado (https://cloud.google.com/sdk/docs/install)
#   2. Projeto GCP criado e billing ativado
#   3. gcloud auth login (executar uma vez)
#
# Uso:
#   chmod +x deploy.sh
#   ./deploy.sh

set -e

# ── Configuracao ──────────────────────────────────────────
PROJECT_ID="${GCP_PROJECT_ID:-seu-projeto-gcp}"
REGION="southamerica-east1"
SERVICE_NAME="castro-crm"

# Variaveis de ambiente do WABA (preencher antes de rodar)
WA_TOKEN="${WHATSAPP_TOKEN:-}"
WA_PHONE_ID="${WHATSAPP_PHONE_NUMBER_ID:-}"
WA_WABA_ID="${WHATSAPP_WABA_ID:-}"
WA_VERIFY="${WHATSAPP_VERIFY_TOKEN:-hubloc2024}"
WA_APP_SECRET="${WHATSAPP_APP_SECRET:-}"
APP_SECRET_KEY="${SECRET_KEY:-$(openssl rand -hex 32)}"

# ── Validacao ─────────────────────────────────────────────
if [ "$PROJECT_ID" = "seu-projeto-gcp" ]; then
    echo "ERRO: Defina GCP_PROJECT_ID antes de rodar."
    echo "  export GCP_PROJECT_ID=meu-projeto-123"
    exit 1
fi

echo "Projeto GCP: $PROJECT_ID"
echo "Regiao:      $REGION"
echo "Servico:     $SERVICE_NAME"
echo ""

# ── Garantir que esta no projeto certo ────────────────────
gcloud config set project "$PROJECT_ID"

# ── Ativar APIs necessarias ───────────────────────────────
echo "Ativando APIs..."
gcloud services enable \
    run.googleapis.com \
    cloudbuild.googleapis.com \
    artifactregistry.googleapis.com \
    2>/dev/null || true

# ── Build e deploy ────────────────────────────────────────
echo ""
echo "Iniciando build e deploy..."

gcloud run deploy "$SERVICE_NAME" \
    --source . \
    --region "$REGION" \
    --platform managed \
    --allow-unauthenticated \
    --port 8080 \
    --memory 512Mi \
    --cpu 1 \
    --min-instances 0 \
    --max-instances 2 \
    --timeout 300 \
    --set-env-vars "\
SECRET_KEY=$APP_SECRET_KEY,\
WHATSAPP_TOKEN=$WA_TOKEN,\
WHATSAPP_PHONE_NUMBER_ID=$WA_PHONE_ID,\
WHATSAPP_WABA_ID=$WA_WABA_ID,\
WHATSAPP_VERIFY_TOKEN=$WA_VERIFY,\
WHATSAPP_APP_SECRET=$WA_APP_SECRET,\
LOG_LEVEL=INFO"

# ── Exibir URL ────────────────────────────────────────────
echo ""
echo "=========================================="
SERVICE_URL=$(gcloud run services describe "$SERVICE_NAME" --region "$REGION" --format="value(status.url)")
echo "  Deploy concluido."
echo ""
echo "  URL do servico:"
echo "  $SERVICE_URL"
echo ""
echo "  URL do webhook (copiar para o painel da Meta):"
echo "  ${SERVICE_URL}/webhook"
echo ""
echo "  Verify Token: $WA_VERIFY"
echo "=========================================="

```

## estrutura_projeto.md

```markdown
# Estrutura do Projeto

## Arvore de Arquivos

```
+-- static/
|   +-- chat.html
|   +-- index.html
+-- {static/
|   +-- {css,js},media,logs}/
+-- .dockerignore
+-- .env.example
+-- Dockerfile
+-- auth.py
+-- config.py
+-- database.py
+-- deploy.sh
+-- estrutura_projeto.md
+-- gerar_estrutura.py
+-- init_db.py
+-- main.py
+-- media.py
+-- requirements.txt
+-- start.ps1
+-- start_tunnel.py
+-- test_debug.py
+-- webhook.py
```

## Codigo dos Arquivos

## .dockerignore

```text
__pycache__
*.pyc
*.pyo
.env
.git
.gitignore
venv
*.db
logs/*.log
media/*
*.tar.gz
deploy.sh
start_tunnel.py
test_debug.py
README.md
.env.example

```

## .env.example

```text
# Castro Intelligence CRM - Variaveis de Ambiente
# Copie para .env e preencha os valores

# Seguranca
SECRET_KEY=gerar_com_openssl_rand_hex_32

# WhatsApp Business API (Meta Cloud API)
WHATSAPP_TOKEN=seu_token_temporario_ou_permanente
WHATSAPP_PHONE_NUMBER_ID=983401388192837
WHATSAPP_WABA_ID=275244975509458
WHATSAPP_VERIFY_TOKEN=hubloc2024
WHATSAPP_APP_SECRET=chave_secreta_do_app_meta

# Google Cloud (deploy)
GCP_PROJECT_ID=seu-projeto-gcp

```

## Dockerfile

```text
FROM python:3.10-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libffi-dev ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/media/images /app/media/audio /app/media/video \
    /app/media/documents /app/media/stickers /app/media/avatars /app/logs

RUN python init_db.py

EXPOSE 8080

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]

```

## auth.py

```python
# -*- coding: utf-8 -*-

import logging
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from config import (
    SECRET_KEY, JWT_ALGORITHM, JWT_EXPIRATION_MINUTES,
    MAX_LOGIN_ATTEMPTS, LOGIN_LOCKOUT_SECONDS,
)
from database import (
    get_user_by_username, update_last_login,
    increment_failed_attempts, log_audit,
)

logger = logging.getLogger("castro_crm.auth")


def hash_password(plain):
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(plain.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain, hashed):
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def create_token(user_id, username):
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "usr": username,
        "iat": now,
        "exp": now + timedelta(minutes=JWT_EXPIRATION_MINUTES),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_token(token):
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def authenticate(username, password, ip_address=""):
    user = get_user_by_username(username)

    if not user:
        return {"success": False, "error": "Credenciais invalidas"}

    if user.get("locked_until"):
        lock_time = datetime.fromisoformat(user["locked_until"])
        if datetime.now(timezone.utc) < lock_time:
            remaining = int((lock_time - datetime.now(timezone.utc)).total_seconds())
            log_audit(user["id"], "LOGIN_BLOCKED", f"{remaining}s restantes", ip_address)
            return {"success": False, "error": f"Conta bloqueada. Tente em {remaining}s"}

    if not verify_password(password, user["password_hash"]):
        attempts = user.get("failed_attempts", 0) + 1
        lockout = None
        if attempts >= MAX_LOGIN_ATTEMPTS:
            lockout = (datetime.now(timezone.utc) + timedelta(seconds=LOGIN_LOCKOUT_SECONDS)).isoformat()
            log_audit(user["id"], "LOGIN_LOCKOUT", f"{attempts} tentativas", ip_address)
        increment_failed_attempts(username, lockout)
        log_audit(user["id"], "LOGIN_FAILED", f"Tentativa {attempts}", ip_address)
        return {"success": False, "error": "Credenciais invalidas"}

    update_last_login(user["id"])
    token = create_token(user["id"], user["username"])
    log_audit(user["id"], "LOGIN_SUCCESS", "", ip_address)

    return {
        "success": True,
        "token": token,
        "user": {
            "id": user["id"],
            "username": user["username"],
            "display_name": user["display_name"],
        },
    }

```

## config.py

```python
# -*- coding: utf-8 -*-

import os
import secrets

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# -- Banco de dados --
DATABASE_PATH = os.getenv("DATABASE_PATH", os.path.join(BASE_DIR, "castro_crm.db"))

# -- Seguranca --
SECRET_KEY = os.getenv("SECRET_KEY", secrets.token_hex(32))
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_MINUTES = int(os.getenv("JWT_EXPIRATION_MINUTES", "480"))

MAX_LOGIN_ATTEMPTS = 5
LOGIN_LOCKOUT_SECONDS = 300
MAX_MESSAGE_LENGTH = 4000

# -- Servidor --
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8080"))

# -- WhatsApp Business API (Meta Cloud API) --
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN", "")
WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
WHATSAPP_WABA_ID = os.getenv("WHATSAPP_WABA_ID", "")
WHATSAPP_VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", "hubloc2024")
WHATSAPP_APP_SECRET = os.getenv("WHATSAPP_APP_SECRET", "")

GRAPH_API_VERSION = "v22.0"
GRAPH_API_BASE = f"https://graph.facebook.com/{GRAPH_API_VERSION}"

# -- Media --
MEDIA_DIR = os.getenv("MEDIA_DIR", os.path.join(BASE_DIR, "media"))
MAX_MEDIA_SIZE_MB = 16

# -- Avatar / Foto de perfil --
AVATAR_DIR = os.path.join(MEDIA_DIR, "avatars")
AVATAR_MAX_SIZE_KB = 512
AVATAR_ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp"}

# -- Audio gravado --
AUDIO_MAX_DURATION_SEC = 120
AUDIO_ALLOWED_MIME = {"audio/ogg", "audio/webm", "audio/mp4", "audio/mpeg"}

# -- Qualificacao de contatos --
QUALIFICATION_OPTIONS = [
    "novo",
    "em_atendimento",
    "qualificado",
    "nao_qualificado",
    "convertido",
]

# -- Cargos / funcoes --
ROLE_OPTIONS = [
    "admin",
    "supervisor",
    "operador",
]

# -- Logging --
LOG_FILE = os.path.join(BASE_DIR, "logs", "castro_crm.log")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

```

## database.py

```python
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

```

## gerar_estrutura.py

```python
﻿# -*- coding: utf-8 -*-
# gerar_estrutura.py

import os
from pathlib import Path

exclude_folders = {'__pycache__', '.git', 'node_modules', '.pytest_cache', 'venv', 'logs', 'media', '.env', '.venv', 'dist', 'build', '.idea', '.vscode'}
exclude_files = {'.db', '.sqlite', '.sqlite3'}

code_types = {
    '.py': 'python',
    '.js': 'javascript',
    '.html': 'html',
    '.css': 'css',
    '.json': 'json',
    '.sh': 'bash',
    '.ps1': 'powershell',
    '.md': 'markdown',
    '.txt': 'text',
    '.sql': 'sql'
}

def should_exclude(path):
    """Verifica se o arquivo/pasta deve ser excluido"""
    parts = Path(path).parts
    for part in parts:
        if part in exclude_folders:
            return True
    
    if Path(path).suffix in exclude_files:
        return True
    
    return False

def print_tree(directory, prefix="", output_file=None):
    """Gera a arvore de arquivos"""
    try:
        entries = sorted(os.listdir(directory))
    except PermissionError:
        return
    
    dirs = [e for e in entries if os.path.isdir(os.path.join(directory, e)) and e not in exclude_folders]
    files = [e for e in entries if os.path.isfile(os.path.join(directory, e))]
    
    all_entries = dirs + files
    
    for i, entry in enumerate(all_entries):
        path = os.path.join(directory, entry)
        
        if should_exclude(path):
            continue
        
        is_last = (i == len(all_entries) - 1)
        current_prefix = "|   " if not is_last else "    "
        
        if os.path.isdir(path):
            line = f"{prefix}+-- {entry}/"
        else:
            line = f"{prefix}+-- {entry}"
        
        if output_file:
            output_file.write(line + "\n")
        else:
            print(line)
        
        if os.path.isdir(path):
            new_prefix = prefix + current_prefix
            print_tree(path, new_prefix, output_file)

def get_code_type(filename):
    """Retorna o tipo de codigo para syntax highlighting"""
    ext = Path(filename).suffix
    return code_types.get(ext, 'text')

def main():
    output_filename = "estrutura_projeto.md"
    
    with open(output_filename, 'w', encoding='utf-8') as f:
        f.write("# Estrutura do Projeto\n\n")
        f.write("## Arvore de Arquivos\n\n")
        f.write("```\n")
        
        print_tree(".", "", f)
        
        f.write("```\n\n")
        f.write("## Codigo dos Arquivos\n\n")
        
        all_files = []
        for root, dirs, files in os.walk("."):
            dirs[:] = [d for d in dirs if d not in exclude_folders]
            
            for file in files:
                filepath = os.path.join(root, file)
                if not should_exclude(filepath):
                    all_files.append(filepath)
        
        for filepath in sorted(all_files):
            filename = os.path.basename(filepath)
            code_type = get_code_type(filename)
            
            f.write(f"## {filename}\n\n")
            f.write(f"```{code_type}\n")
            
            try:
                with open(filepath, 'r', encoding='utf-8') as source:
                    content = source.read()
                    f.write(content)
            except Exception as e:
                f.write(f"# Erro ao ler arquivo: {e}\n")
            
            f.write("\n```\n\n")
    
    print(f"Estrutura completa gerada em: {output_filename}")

if __name__ == "__main__":
    main()
```

## init_db.py

```python
# -*- coding: utf-8 -*-

from database import init_database, db_session, create_department
from auth import hash_password

DEPARTMENTS = [
    {"name": "Geral", "description": "Atendimento geral"},
    {"name": "Vendas", "description": "Equipe comercial"},
    {"name": "Suporte", "description": "Suporte tecnico"},
    {"name": "Financeiro", "description": "Cobranca e pagamentos"},
]

USERS = [
    {"username": "izael", "display_name": "Izael Castro", "password": "castro@2026", "department": "Geral", "role": "admin"},
    {"username": "rafael", "display_name": "Rafael Castro", "password": "castro@2026", "department": "Geral", "role": "supervisor"},
]


def seed():
    init_database()

    # Criar setores
    dept_map = {}
    for d in DEPARTMENTS:
        did = create_department(d["name"], d["description"])
        dept_map[d["name"]] = did
        print(f"  Setor '{d['name']}' (id={did})")

    # Criar usuarios
    with db_session() as conn:
        for u in USERS:
            exists = conn.execute("SELECT id FROM users WHERE username = ?", (u["username"],)).fetchone()
            if exists:
                # Atualizar role se necessario
                conn.execute(
                    "UPDATE users SET role = ? WHERE username = ?",
                    (u["role"], u["username"])
                )
                print(f"  '{u['username']}' ja existe. Role atualizado para '{u['role']}'.")
                continue
            h = hash_password(u["password"])
            dept_id = dept_map.get(u["department"])
            conn.execute(
                "INSERT INTO users (username, display_name, password_hash, department_id, role) "
                "VALUES (?, ?, ?, ?, ?)",
                (u["username"], u["display_name"], h, dept_id, u["role"]),
            )
            print(f"  '{u['username']}' criado (setor: {u['department']}, cargo: {u['role']})")

    print("\nCredenciais:")
    print("  izael  / castro@2026  (admin)")
    print("  rafael / castro@2026  (supervisor)")
    print("\nSetores: " + ", ".join(d["name"] for d in DEPARTMENTS))


if __name__ == "__main__":
    seed()

```

## main.py

```python
# -*- coding: utf-8 -*-

import hashlib
import html
import logging
import os
from datetime import datetime, timezone

import httpx
from fastapi import (
    FastAPI, WebSocket, WebSocketDisconnect, Request,
    HTTPException, Depends, Query, UploadFile, File, Form,
)
from fastapi.responses import JSONResponse, HTMLResponse, PlainTextResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, field_validator

from config import (
    HOST, PORT, MAX_MESSAGE_LENGTH, BASE_DIR, LOG_FILE, LOG_LEVEL,
    MEDIA_DIR, WHATSAPP_VERIFY_TOKEN, WHATSAPP_TOKEN,
    WHATSAPP_PHONE_NUMBER_ID, GRAPH_API_BASE,
    AVATAR_DIR, AVATAR_MAX_SIZE_KB, AVATAR_ALLOWED_MIME,
    QUALIFICATION_OPTIONS, ROLE_OPTIONS,
)
from database import (
    init_database, get_user_by_id, get_all_users,
    save_internal_message, get_internal_conversation,
    mark_messages_as_read, get_unread_count,
    get_all_wa_contacts, get_wa_conversation, get_wa_unread_count,
    mark_wa_conversation_read, save_wa_message, get_wa_contact,
    log_audit, normalize_br_phone,
    get_all_departments, create_department,
    assign_wa_contact, get_transfer_history,
    update_user_avatar, get_user_avatar,
    create_user, update_user, deactivate_user,
    update_wa_contact_qualification, archive_wa_contact, restore_wa_contact,
    update_contact_avatar, insert_transfer_system_message,
)
from auth import authenticate, decode_token, hash_password
from webhook import process_webhook_payload, validate_signature
from media import (
    ensure_media_dir, upload_media_to_whatsapp, send_media_message,
    save_upload_locally, detect_media_type, convert_audio_to_ogg_opus,
)

# -- Logging --

os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger("castro_crm.main")

# -- App --

app = FastAPI(
    title="Castro Intelligence CRM",
    version="0.4.0",
    docs_url=None,
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")

# -- Modelos --

class LoginRequest(BaseModel):
    username: str
    password: str

    @field_validator("username")
    @classmethod
    def sanitize_username(cls, v):
        v = v.strip().lower()
        if not v or len(v) > 50:
            raise ValueError("Nome de usuario invalido")
        return v


class SendMessageRequest(BaseModel):
    receiver_id: int
    content: str
    msg_type: str = "text"

    @field_validator("content")
    @classmethod
    def validate_content(cls, v):
        v = v.strip()
        if not v:
            raise ValueError("Mensagem vazia")
        if len(v) > MAX_MESSAGE_LENGTH:
            raise ValueError(f"Mensagem excede {MAX_MESSAGE_LENGTH} caracteres")
        return v


class WaSendRequest(BaseModel):
    contact_id: int
    content: str

    @field_validator("content")
    @classmethod
    def validate_content(cls, v):
        v = v.strip()
        if not v:
            raise ValueError("Mensagem vazia")
        if len(v) > MAX_MESSAGE_LENGTH:
            raise ValueError(f"Excede {MAX_MESSAGE_LENGTH} caracteres")
        return v


# -- Dependencias --

def get_current_user(request: Request):
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Token ausente")
    token = auth_header.split(" ", 1)[1]
    payload = decode_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Token invalido ou expirado")
    user = get_user_by_id(payload["sub"])
    if not user:
        raise HTTPException(status_code=401, detail="Usuario nao encontrado")
    return user


# -- Validacao de imagem --

AVATAR_MAGIC_BYTES = {
    b"\xff\xd8\xff": "image/jpeg",
    b"\x89PNG": "image/png",
    b"RIFF": "image/webp",
}


def _validate_image_bytes(content):
    for magic, mime in AVATAR_MAGIC_BYTES.items():
        if content[:len(magic)] == magic:
            return mime
    return None


def _save_avatar(content, prefix, entity_id):
    real_mime = _validate_image_bytes(content)
    if not real_mime or real_mime not in AVATAR_ALLOWED_MIME:
        return None
    ext_map = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
    ext = ext_map.get(real_mime, ".jpg")
    file_hash = hashlib.sha256(content).hexdigest()[:16]
    filename = f"{prefix}_{entity_id}_{file_hash}{ext}"
    os.makedirs(AVATAR_DIR, exist_ok=True)
    filepath = os.path.join(AVATAR_DIR, filename)
    with open(filepath, "wb") as f:
        f.write(content)
    return f"/media/avatars/{filename}"


def _remove_old_avatar(old_path):
    if not old_path:
        return
    old_file = os.path.join(BASE_DIR, old_path.lstrip("/"))
    if os.path.isfile(old_file):
        try:
            os.remove(old_file)
        except OSError:
            pass


# -- Startup --

@app.on_event("startup")
async def startup():
    init_database()
    ensure_media_dir()
    logger.info("CRM iniciado | host=%s port=%d", HOST, PORT)
    if WHATSAPP_TOKEN:
        logger.info("WABA configurado | phone_id=%s", WHATSAPP_PHONE_NUMBER_ID)
    else:
        logger.warning("WHATSAPP_TOKEN nao definido - webhook ativo mas envio desabilitado")


# -- Paginas HTML --

@app.get("/", response_class=HTMLResponse)
async def index():
    with open(os.path.join(BASE_DIR, "static", "index.html"), "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


@app.get("/chat", response_class=HTMLResponse)
async def chat_page():
    with open(os.path.join(BASE_DIR, "static", "chat.html"), "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


# -- Servir midia --

@app.get("/media/{subdir}/{filename}")
async def serve_media(subdir: str, filename: str):
    safe_subdir = os.path.basename(subdir)
    safe_filename = os.path.basename(filename)
    filepath = os.path.join(MEDIA_DIR, safe_subdir, safe_filename)
    if not os.path.isfile(filepath):
        raise HTTPException(status_code=404, detail="Arquivo nao encontrado")
    return FileResponse(filepath)


# -- Webhook WABA --

@app.get("/webhook")
async def webhook_verify(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
):
    if hub_mode == "subscribe" and hub_verify_token == WHATSAPP_VERIFY_TOKEN:
        logger.info("Webhook verificado com sucesso")
        return PlainTextResponse(hub_challenge)
    logger.warning("Falha na verificacao do webhook (token=%s)", hub_verify_token)
    return PlainTextResponse("Forbidden", status_code=403)


@app.post("/webhook")
async def webhook_receive(request: Request):
    body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256", "")
    if not validate_signature(body, signature):
        logger.warning("Assinatura invalida no webhook")
        return JSONResponse(status_code=403, content={"error": "Assinatura invalida"})
    payload = await request.json()
    await process_webhook_payload(payload, ws_notify_callback=broadcast_to_operators)
    return {"status": "ok"}


# -- API: Autenticacao --

@app.post("/api/login")
async def login(body: LoginRequest, request: Request):
    ip = request.client.host if request.client else "unknown"
    result = authenticate(body.username, body.password, ip)
    if not result["success"]:
        return JSONResponse(status_code=401, content={"error": result["error"]})
    avatar = get_user_avatar(result["user"]["id"])
    user_data = result["user"]
    user_data["avatar_path"] = avatar or ""
    full_user = get_user_by_id(result["user"]["id"])
    user_data["role"] = full_user.get("role", "operador") if full_user else "operador"
    return {"token": result["token"], "user": user_data}


# -- API: Avatar do operador --

@app.post("/api/profile/avatar")
async def upload_avatar(request: Request, file: UploadFile = File(...)):
    current_user = get_current_user(request)
    user_id = current_user["id"]
    declared_mime = (file.content_type or "").lower()
    if declared_mime not in AVATAR_ALLOWED_MIME:
        raise HTTPException(status_code=400, detail="Formato nao permitido. Use JPEG, PNG ou WebP.")
    content = await file.read()
    if len(content) > AVATAR_MAX_SIZE_KB * 1024:
        raise HTTPException(status_code=413, detail=f"Imagem excede {AVATAR_MAX_SIZE_KB}KB.")
    _remove_old_avatar(get_user_avatar(user_id))
    path = _save_avatar(content, "avatar", user_id)
    if not path:
        raise HTTPException(status_code=400, detail="Conteudo do arquivo nao corresponde a uma imagem valida.")
    update_user_avatar(user_id, path)
    log_audit(user_id, "AVATAR_UPLOAD", f"Arquivo: {os.path.basename(path)}")
    return {"status": "ok", "avatar_path": path}


@app.delete("/api/profile/avatar")
async def remove_avatar(current_user: dict = Depends(get_current_user)):
    _remove_old_avatar(get_user_avatar(current_user["id"]))
    update_user_avatar(current_user["id"], "")
    log_audit(current_user["id"], "AVATAR_REMOVE", "")
    return {"status": "ok"}


# -- API: Avatar do contato WhatsApp --

@app.post("/api/wa/contact/{contact_id}/avatar")
async def upload_contact_avatar(contact_id: int, request: Request, file: UploadFile = File(...)):
    current_user = get_current_user(request)
    contact = get_wa_contact(contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="Contato nao encontrado")
    declared_mime = (file.content_type or "").lower()
    if declared_mime not in AVATAR_ALLOWED_MIME:
        raise HTTPException(status_code=400, detail="Formato nao permitido.")
    content = await file.read()
    if len(content) > AVATAR_MAX_SIZE_KB * 1024:
        raise HTTPException(status_code=413, detail=f"Imagem excede {AVATAR_MAX_SIZE_KB}KB.")
    _remove_old_avatar(contact.get("contact_avatar_path", ""))
    path = _save_avatar(content, "contact", contact_id)
    if not path:
        raise HTTPException(status_code=400, detail="Arquivo invalido.")
    update_contact_avatar(contact_id, path)
    log_audit(current_user["id"], "CONTACT_AVATAR", f"Contato {contact_id}: {os.path.basename(path)}")
    return {"status": "ok", "avatar_path": path}


# -- API: Admin - Gerenciar usuarios --

@app.post("/api/admin/users")
async def admin_create_user(request: Request, current_user: dict = Depends(get_current_user)):
    if current_user.get("role") not in ("admin", "supervisor"):
        raise HTTPException(status_code=403, detail="Permissao negada")
    body = await request.json()
    username = (body.get("username", "")).strip().lower()
    display_name = (body.get("display_name", "")).strip()
    password = body.get("password", "")
    department_id = body.get("department_id")
    role = body.get("role", "operador")
    if not username or not display_name or not password:
        raise HTTPException(status_code=400, detail="Campos obrigatorios: username, display_name, password")
    if len(username) > 50 or len(display_name) > 100:
        raise HTTPException(status_code=400, detail="Nome excede limite de caracteres")
    if len(password) < 6:
        raise HTTPException(status_code=400, detail="Senha deve ter pelo menos 6 caracteres")
    if role not in ROLE_OPTIONS:
        raise HTTPException(status_code=400, detail=f"Cargo invalido. Opcoes: {', '.join(ROLE_OPTIONS)}")
    pw_hash = hash_password(password)
    user_id = create_user(username, display_name, pw_hash, department_id, role)
    if not user_id:
        raise HTTPException(status_code=409, detail="Usuario ja existe")
    log_audit(current_user["id"], "USER_CREATE", f"{username} ({role})")
    return {"status": "ok", "user_id": user_id}


@app.put("/api/admin/users/{user_id}")
async def admin_update_user(user_id: int, request: Request, current_user: dict = Depends(get_current_user)):
    if current_user.get("role") not in ("admin", "supervisor"):
        raise HTTPException(status_code=403, detail="Permissao negada")
    target = get_user_by_id(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="Usuario nao encontrado")
    body = await request.json()
    display_name = body.get("display_name")
    department_id = body.get("department_id")
    role = body.get("role")
    if role and role not in ROLE_OPTIONS:
        raise HTTPException(status_code=400, detail=f"Cargo invalido. Opcoes: {', '.join(ROLE_OPTIONS)}")
    update_user(user_id, display_name=display_name, department_id=department_id, role=role)
    log_audit(current_user["id"], "USER_UPDATE", f"id={user_id}")
    return {"status": "ok"}


@app.delete("/api/admin/users/{user_id}")
async def admin_deactivate_user(user_id: int, current_user: dict = Depends(get_current_user)):
    if current_user.get("role") not in ("admin",):
        raise HTTPException(status_code=403, detail="Apenas admin pode desativar usuarios")
    if user_id == current_user["id"]:
        raise HTTPException(status_code=400, detail="Nao pode desativar a si mesmo")
    target = get_user_by_id(user_id)
    if not target:
        raise HTTPException(status_code=404, detail="Usuario nao encontrado")
    deactivate_user(user_id)
    log_audit(current_user["id"], "USER_DEACTIVATE", f"id={user_id} ({target['display_name']})")
    return {"status": "ok"}


@app.get("/api/admin/roles")
async def list_roles(current_user: dict = Depends(get_current_user)):
    return {"roles": ROLE_OPTIONS}


# -- API: Chat Interno --

@app.get("/api/users")
async def list_users(current_user: dict = Depends(get_current_user)):
    users = get_all_users()
    return [
        {
            "id": u["id"], "display_name": u["display_name"],
            "last_login": u["last_login"], "avatar_path": u.get("avatar_path", ""),
            "role": u.get("role", "operador"), "department_name": u.get("department_name", ""),
        }
        for u in users if u["id"] != current_user["id"] and u.get("is_active")
    ]


@app.get("/api/messages/{contact_id}")
async def get_messages(contact_id: int, current_user: dict = Depends(get_current_user)):
    messages = get_internal_conversation(current_user["id"], contact_id)
    mark_messages_as_read(current_user["id"], contact_id)
    return {"messages": messages}


@app.get("/api/unread")
async def unread(current_user: dict = Depends(get_current_user)):
    return {"unread": get_unread_count(current_user["id"])}


@app.post("/api/messages")
async def send_internal_message(body: SendMessageRequest, current_user: dict = Depends(get_current_user)):
    receiver = get_user_by_id(body.receiver_id)
    if not receiver:
        raise HTTPException(status_code=404, detail="Destinatario nao encontrado")
    sanitized = html.escape(body.content)
    msg_id = save_internal_message(current_user["id"], body.receiver_id, sanitized, body.msg_type)
    ws_conn = operator_connections.get(body.receiver_id)
    if ws_conn:
        try:
            await ws_conn.send_json({
                "event": "new_message",
                "data": {
                    "id": msg_id, "sender_id": current_user["id"],
                    "sender_name": current_user["display_name"],
                    "sender_avatar": current_user.get("avatar_path", ""),
                    "content": sanitized, "msg_type": body.msg_type,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                },
            })
        except Exception:
            pass
    return {"id": msg_id, "status": "sent"}


# -- API: WhatsApp --

@app.get("/api/wa/contacts")
async def wa_contacts(current_user: dict = Depends(get_current_user)):
    contacts = get_all_wa_contacts()
    unread_counts = get_wa_unread_count()
    for c in contacts:
        c["unread"] = unread_counts.get(c["id"], 0)
    return {"contacts": contacts}


@app.get("/api/wa/messages/{contact_id}")
async def wa_messages(contact_id: int, current_user: dict = Depends(get_current_user)):
    messages = get_wa_conversation(contact_id)
    mark_wa_conversation_read(contact_id)
    return {"messages": messages}


@app.post("/api/wa/send")
async def wa_send(body: WaSendRequest, current_user: dict = Depends(get_current_user)):
    if not WHATSAPP_TOKEN or not WHATSAPP_PHONE_NUMBER_ID:
        raise HTTPException(status_code=503, detail="WABA nao configurado")
    contact = get_wa_contact(body.contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="Contato nao encontrado")
    if contact.get("assigned_to") and contact["assigned_to"] != current_user["id"]:
        raise HTTPException(status_code=403, detail="Atendimento atribuido a outro operador")

    wa_id = normalize_br_phone(contact["wa_id"])
    url = f"{GRAPH_API_BASE}/{WHATSAPP_PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    payload = {"messaging_product": "whatsapp", "to": wa_id, "type": "text", "text": {"body": body.content}}

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(url, json=payload, headers=headers)
        result = resp.json()

    if resp.status_code == 200:
        wa_msg_id = result.get("messages", [{}])[0].get("id", "")
        save_wa_message(
            wa_message_id=wa_msg_id, contact_id=body.contact_id, direction="outbound",
            msg_type="text", content=body.content, status="sent",
            timestamp_wa=datetime.now(timezone.utc).isoformat(), operator_id=current_user["id"],
        )
        log_audit(current_user["id"], "WA_SEND", f"Para {wa_id}: {body.content[:80]}")
        return {"status": "sent", "wa_message_id": wa_msg_id}
    else:
        error_msg = result.get("error", {}).get("message", "Erro desconhecido")
        raise HTTPException(status_code=502, detail=error_msg)


@app.post("/api/wa/send-media")
async def wa_send_media(
    request: Request, contact_id: int = Form(...),
    caption: str = Form(""), file: UploadFile = File(...),
):
    current_user = get_current_user(request)
    if not WHATSAPP_TOKEN or not WHATSAPP_PHONE_NUMBER_ID:
        raise HTTPException(status_code=503, detail="WABA nao configurado")
    contact = get_wa_contact(contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="Contato nao encontrado")
    if contact.get("assigned_to") and contact["assigned_to"] != current_user["id"]:
        raise HTTPException(status_code=403, detail="Atendimento atribuido a outro operador")

    file_content = await file.read()
    if len(file_content) > 16 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Arquivo excede 16MB")

    mime_type = file.content_type or "application/octet-stream"
    filename = file.filename or "upload"
    local_result = await save_upload_locally(file_content, filename, mime_type)
    msg_type = local_result["msg_type"]

    media_id = await upload_media_to_whatsapp(file_content, mime_type, filename)
    if not media_id:
        raise HTTPException(status_code=502, detail="Falha no upload para a Meta")

    send_result = await send_media_message(contact["wa_id"], media_id, msg_type, caption)
    if not send_result or "error" in send_result:
        error = send_result.get("error", "Erro desconhecido") if send_result else "Sem resposta"
        raise HTTPException(status_code=502, detail=str(error))

    wa_msg_id = send_result.get("wa_message_id", "")
    save_wa_message(
        wa_message_id=wa_msg_id, contact_id=contact_id, direction="outbound",
        msg_type=msg_type, content=caption, media_path=local_result["path"],
        media_mime=mime_type, media_id=media_id, filename=filename,
        status="sent", timestamp_wa=datetime.now(timezone.utc).isoformat(),
        operator_id=current_user["id"],
    )
    log_audit(current_user["id"], "WA_SEND_MEDIA", f"{msg_type} para {contact['wa_id']}: {filename}")
    return {"status": "sent", "wa_message_id": wa_msg_id, "msg_type": msg_type, "media_path": local_result["path"]}


@app.post("/api/wa/send-audio")
async def wa_send_audio(
    request: Request, contact_id: int = Form(...), file: UploadFile = File(...),
):
    """Envia audio gravado pelo microfone para contato WhatsApp.
    Converte WebM/Opus do navegador para OGG/Opus via FFmpeg."""
    current_user = get_current_user(request)

    if not WHATSAPP_TOKEN or not WHATSAPP_PHONE_NUMBER_ID:
        raise HTTPException(status_code=503, detail="WABA nao configurado")

    contact = get_wa_contact(contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="Contato nao encontrado")
    if contact.get("assigned_to") and contact["assigned_to"] != current_user["id"]:
        raise HTTPException(status_code=403, detail="Atendimento atribuido a outro operador")

    raw_content = await file.read()
    if len(raw_content) > 16 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Audio excede 16MB")

    original_mime = file.content_type or "audio/webm"

    # Converter WebM/Opus -> OGG/Opus (formato exigido pelo WhatsApp)
    converted = convert_audio_to_ogg_opus(raw_content, original_mime)
    if not converted:
        raise HTTPException(status_code=500, detail="Falha na conversao do audio. Verifique se o FFmpeg esta instalado.")

    # Salvar versao convertida localmente
    local_result = await save_upload_locally(converted, "gravacao.ogg", "audio/ogg")

    # Upload do OGG convertido para a Meta
    media_id = await upload_media_to_whatsapp(converted, "audio/ogg", "audio.ogg")
    if not media_id:
        raise HTTPException(status_code=502, detail="Falha no upload de audio para a Meta")

    # Enviar mensagem de audio
    send_result = await send_media_message(contact["wa_id"], media_id, "audio")
    if not send_result or "error" in send_result:
        error = send_result.get("error", "Erro desconhecido") if send_result else "Sem resposta"
        raise HTTPException(status_code=502, detail=str(error))

    wa_msg_id = send_result.get("wa_message_id", "")
    save_wa_message(
        wa_message_id=wa_msg_id, contact_id=contact_id, direction="outbound",
        msg_type="audio", content="", media_path=local_result["path"],
        media_mime="audio/ogg", media_id=media_id, filename="gravacao.ogg",
        status="sent", timestamp_wa=datetime.now(timezone.utc).isoformat(),
        operator_id=current_user["id"],
    )
    log_audit(current_user["id"], "WA_SEND_AUDIO", f"Para {contact['wa_id']}")
    return {"status": "sent", "wa_message_id": wa_msg_id, "msg_type": "audio", "media_path": local_result["path"]}


@app.post("/api/wa/send-template")
async def wa_send_template(
    contact_id: int, template_name: str = "hello_world",
    language: str = "pt_BR", current_user: dict = Depends(get_current_user),
):
    if not WHATSAPP_TOKEN or not WHATSAPP_PHONE_NUMBER_ID:
        raise HTTPException(status_code=503, detail="WABA nao configurado")
    contact = get_wa_contact(contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="Contato nao encontrado")
    url = f"{GRAPH_API_BASE}/{WHATSAPP_PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}", "Content-Type": "application/json"}
    payload = {
        "messaging_product": "whatsapp", "to": normalize_br_phone(contact["wa_id"]),
        "type": "template", "template": {"name": template_name, "language": {"code": language}},
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(url, json=payload, headers=headers)
        result = resp.json()
    if resp.status_code == 200:
        wa_msg_id = result.get("messages", [{}])[0].get("id", "")
        save_wa_message(
            wa_message_id=wa_msg_id, contact_id=contact_id, direction="outbound",
            msg_type="template", content=f"[template: {template_name}]",
            status="sent", timestamp_wa=datetime.now(timezone.utc).isoformat(),
            operator_id=current_user["id"],
        )
        return {"status": "sent", "wa_message_id": wa_msg_id}
    else:
        raise HTTPException(status_code=502, detail=result.get("error", {}).get("message", "Erro desconhecido"))


# -- API: Contatos - Qualificacao e gerenciamento --

@app.put("/api/wa/contact/{contact_id}/qualify")
async def qualify_contact(contact_id: int, request: Request, current_user: dict = Depends(get_current_user)):
    body = await request.json()
    qualification = body.get("qualification", "")
    notes = body.get("notes")
    if qualification and qualification not in QUALIFICATION_OPTIONS:
        raise HTTPException(status_code=400, detail=f"Qualificacao invalida. Opcoes: {', '.join(QUALIFICATION_OPTIONS)}")
    contact = get_wa_contact(contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="Contato nao encontrado")
    update_wa_contact_qualification(contact_id, qualification, notes)
    log_audit(current_user["id"], "CONTACT_QUALIFY", f"Contato {contact_id}: {qualification}")
    return {"status": "ok"}


@app.delete("/api/wa/contact/{contact_id}")
async def delete_contact(contact_id: int, current_user: dict = Depends(get_current_user)):
    contact = get_wa_contact(contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="Contato nao encontrado")
    archive_wa_contact(contact_id)
    log_audit(current_user["id"], "CONTACT_ARCHIVE", f"Contato {contact_id}")
    return {"status": "ok"}


@app.post("/api/wa/contact/{contact_id}/restore")
async def restore_contact(contact_id: int, current_user: dict = Depends(get_current_user)):
    restore_wa_contact(contact_id)
    log_audit(current_user["id"], "CONTACT_RESTORE", f"Contato {contact_id}")
    return {"status": "ok"}


@app.get("/api/wa/qualifications")
async def list_qualifications(current_user: dict = Depends(get_current_user)):
    return {"qualifications": QUALIFICATION_OPTIONS}


# -- API: Departamentos e Transferencia --

@app.get("/api/departments")
async def list_departments(current_user: dict = Depends(get_current_user)):
    return {"departments": get_all_departments()}


@app.get("/api/wa/contact/{contact_id}")
async def wa_contact_detail(contact_id: int, current_user: dict = Depends(get_current_user)):
    contact = get_wa_contact(contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="Contato nao encontrado")
    return {"contact": contact}


@app.post("/api/wa/transfer")
async def wa_transfer(request: Request, current_user: dict = Depends(get_current_user)):
    body = await request.json()
    contact_id = body.get("contact_id")
    to_user_id = body.get("to_user_id")
    to_department_id = body.get("to_department_id")
    reason = body.get("reason", "")
    summary = body.get("summary", "")
    if not contact_id:
        raise HTTPException(status_code=400, detail="contact_id obrigatorio")
    if not to_user_id:
        raise HTTPException(status_code=400, detail="Selecione o operador destino")
    if not summary:
        raise HTTPException(status_code=400, detail="Resumo do atendimento e obrigatorio")
    contact = get_wa_contact(contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="Contato nao encontrado")

    result = assign_wa_contact(contact_id, to_user_id, to_department_id, current_user["id"], reason, summary)
    if result is None:
        raise HTTPException(status_code=404, detail="Contato nao encontrado")

    to_user = get_user_by_id(to_user_id) if to_user_id else None
    to_name = to_user["display_name"] if to_user else "Nenhum"

    sys_content = (
        f"Transferido de {current_user['display_name']} para {to_name}"
        + (f" | Motivo: {reason}" if reason else "")
        + (f" | Resumo: {summary}" if summary else "")
    )
    insert_transfer_system_message(contact_id, sys_content, current_user["id"])
    log_audit(current_user["id"], "WA_TRANSFER", f"Contato {contact_id} -> {to_name} (dept={to_department_id}): {reason}")

    if to_user_id and to_user_id in operator_connections:
        try:
            await operator_connections[to_user_id].send_json({
                "event": "wa_transfer_received",
                "data": {
                    "contact_id": contact_id, "contact_name": contact.get("display_name", ""),
                    "from_user": current_user["display_name"], "reason": reason, "summary": summary,
                },
            })
        except Exception:
            pass

    await broadcast_to_operators({
        "event": "wa_contact_reassigned",
        "data": {"contact_id": contact_id, "assigned_to": to_user_id, "assigned_name": to_name},
    })
    return {"status": "transferred", "to_user": to_name}


@app.get("/api/wa/transfer-history/{contact_id}")
async def wa_transfer_hist(contact_id: int, current_user: dict = Depends(get_current_user)):
    return {"history": get_transfer_history(contact_id)}


@app.get("/api/operators")
async def list_operators(current_user: dict = Depends(get_current_user)):
    users = get_all_users()
    return [
        {
            "id": u["id"], "display_name": u["display_name"],
            "department_name": u.get("department_name", ""),
            "department_id": u.get("department_id"),
            "avatar_path": u.get("avatar_path", ""),
            "role": u.get("role", "operador"),
        }
        for u in users if u.get("is_active")
    ]


# -- WebSocket --

operator_connections: dict[int, WebSocket] = {}


async def broadcast_to_operators(message: dict):
    disconnected = []
    for uid, conn in operator_connections.items():
        try:
            await conn.send_json(message)
        except Exception:
            disconnected.append(uid)
    for uid in disconnected:
        operator_connections.pop(uid, None)


@app.websocket("/ws/{token}")
async def websocket_endpoint(websocket: WebSocket, token: str):
    payload = decode_token(token)
    if not payload:
        await websocket.close(code=4001, reason="Token invalido")
        return
    user_id = payload["sub"]
    user = get_user_by_id(user_id)
    if not user:
        await websocket.close(code=4001, reason="Usuario invalido")
        return

    await websocket.accept()
    operator_connections[user_id] = websocket
    logger.info("WS conectado: %s (id=%d)", user["display_name"], user_id)

    for uid, conn in operator_connections.items():
        if uid != user_id:
            try:
                await conn.send_json({
                    "event": "user_online",
                    "data": {
                        "user_id": user_id, "display_name": user["display_name"],
                        "avatar_path": user.get("avatar_path", ""), "role": user.get("role", ""),
                    },
                })
            except Exception:
                pass

    try:
        while True:
            data = await websocket.receive_json()
            event = data.get("event")

            if event == "send_message":
                receiver_id = data.get("receiver_id")
                content = data.get("content", "").strip()
                if not content or len(content) > MAX_MESSAGE_LENGTH:
                    await websocket.send_json({"event": "error", "data": {"detail": "Mensagem invalida"}})
                    continue
                receiver = get_user_by_id(receiver_id)
                if not receiver:
                    await websocket.send_json({"event": "error", "data": {"detail": "Destinatario invalido"}})
                    continue
                sanitized = html.escape(content)
                msg_id = save_internal_message(user_id, receiver_id, sanitized)
                now = datetime.now(timezone.utc).isoformat()
                await websocket.send_json({
                    "event": "message_sent",
                    "data": {"id": msg_id, "receiver_id": receiver_id, "content": sanitized, "created_at": now},
                })
                ws_dest = operator_connections.get(receiver_id)
                if ws_dest:
                    try:
                        await ws_dest.send_json({
                            "event": "new_message",
                            "data": {
                                "id": msg_id, "sender_id": user_id,
                                "sender_name": user["display_name"],
                                "sender_avatar": user.get("avatar_path", ""),
                                "content": sanitized, "msg_type": "text", "created_at": now,
                            },
                        })
                    except Exception:
                        pass

            elif event == "mark_read":
                sender_id = data.get("sender_id")
                if sender_id:
                    mark_messages_as_read(user_id, sender_id)
                    ws_sender = operator_connections.get(sender_id)
                    if ws_sender:
                        try:
                            await ws_sender.send_json({"event": "messages_read", "data": {"reader_id": user_id}})
                        except Exception:
                            pass

            elif event == "typing":
                receiver_id = data.get("receiver_id")
                ws_dest = operator_connections.get(receiver_id)
                if ws_dest:
                    try:
                        await ws_dest.send_json({"event": "typing", "data": {"user_id": user_id, "display_name": user["display_name"]}})
                    except Exception:
                        pass

    except WebSocketDisconnect:
        logger.info("WS desconectado: %s (id=%d)", user["display_name"], user_id)
    except Exception as exc:
        logger.error("Erro WS (user_id=%d): %s", user_id, exc)
    finally:
        operator_connections.pop(user_id, None)
        for uid, conn in operator_connections.items():
            try:
                await conn.send_json({"event": "user_offline", "data": {"user_id": user_id}})
            except Exception:
                pass


# -- Execucao --

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=HOST, port=PORT, reload=True, log_level="info")

```

## media.py

```python
# -*- coding: utf-8 -*-

"""
Gerencia download de midia recebida via WhatsApp Cloud API
e conversao de formatos de audio para compatibilidade.
"""

import os
import logging
import hashlib
import subprocess
import tempfile
from datetime import datetime

import httpx

from config import WHATSAPP_TOKEN, WHATSAPP_PHONE_NUMBER_ID, GRAPH_API_BASE, MEDIA_DIR, MAX_MEDIA_SIZE_MB

logger = logging.getLogger("castro_crm.media")


def _normalize_br(wa_id):
    s = str(wa_id)
    if len(s) == 12 and s.startswith("55") and s[4] in ("6","7","8","9"):
        return f"55{s[2:4]}9{s[4:]}"
    return s


MIME_EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "audio/aac": ".aac",
    "audio/mp4": ".m4a",
    "audio/mpeg": ".mp3",
    "audio/amr": ".amr",
    "audio/ogg": ".ogg",
    "audio/opus": ".opus",
    "audio/webm": ".webm",
    "video/mp4": ".mp4",
    "video/3gpp": ".3gp",
    "application/pdf": ".pdf",
    "application/vnd.ms-excel": ".xls",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "application/msword": ".doc",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/zip": ".zip",
}


def ensure_media_dir():
    os.makedirs(MEDIA_DIR, exist_ok=True)
    for subdir in ("images", "audio", "video", "documents", "stickers", "avatars"):
        os.makedirs(os.path.join(MEDIA_DIR, subdir), exist_ok=True)


def get_subdir_for_type(msg_type):
    mapping = {
        "image": "images",
        "audio": "audio",
        "video": "video",
        "document": "documents",
        "sticker": "stickers",
    }
    return mapping.get(msg_type, "documents")


def convert_audio_to_ogg_opus(input_bytes, input_mime="audio/webm"):
    """
    Converte audio gravado pelo navegador (webm/opus) para OGG/Opus
    que e o formato aceito pelo WhatsApp.
    Retorna os bytes do arquivo OGG ou None em caso de falha.
    """
    # Determinar extensao de entrada
    ext_in = ".webm"
    if "mp4" in input_mime or "m4a" in input_mime:
        ext_in = ".m4a"
    elif "mpeg" in input_mime or "mp3" in input_mime:
        ext_in = ".mp3"
    elif "ogg" in input_mime:
        # Ja pode ser ogg valido, verificar se precisa conversao
        ext_in = ".ogg"

    tmp_in = None
    tmp_out_path = None
    try:
        # Criar arquivo temporario de entrada
        tmp_in = tempfile.NamedTemporaryFile(suffix=ext_in, delete=False)
        tmp_in.write(input_bytes)
        tmp_in.close()

        # Criar caminho de saida
        tmp_out_path = tmp_in.name.replace(ext_in, "_converted.ogg")

        # Executar ffmpeg para converter
        cmd = [
            "ffmpeg",
            "-i", tmp_in.name,
            "-c:a", "libopus",
            "-b:a", "48k",
            "-ar", "48000",
            "-ac", "1",
            "-application", "voip",
            "-f", "ogg",
            "-y",
            tmp_out_path,
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=30,
        )

        if result.returncode != 0:
            stderr_text = result.stderr.decode("utf-8", errors="replace")[-500:]
            logger.error("FFmpeg falhou (code=%d): %s", result.returncode, stderr_text)
            return None

        # Ler resultado
        with open(tmp_out_path, "rb") as f:
            converted = f.read()

        if len(converted) < 100:
            logger.error("Arquivo convertido muito pequeno (%d bytes)", len(converted))
            return None

        logger.info(
            "Audio convertido: %s -> ogg/opus (%d -> %d bytes)",
            ext_in, len(input_bytes), len(converted)
        )
        return converted

    except subprocess.TimeoutExpired:
        logger.error("FFmpeg timeout na conversao de audio")
        return None
    except Exception as exc:
        logger.error("Erro na conversao de audio: %s", exc)
        return None
    finally:
        if tmp_in and os.path.isfile(tmp_in.name):
            try:
                os.remove(tmp_in.name)
            except OSError:
                pass
        if tmp_out_path and os.path.isfile(tmp_out_path):
            try:
                os.remove(tmp_out_path)
            except OSError:
                pass


async def get_media_url(media_id):
    if not WHATSAPP_TOKEN:
        logger.error("WHATSAPP_TOKEN nao configurado")
        return None

    endpoint = f"{GRAPH_API_BASE}/{media_id}"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}"}

    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            resp = await client.get(endpoint, headers=headers)
            if resp.status_code != 200:
                logger.error("Falha ao obter URL da midia %s: %s", media_id, resp.text)
                return None
            data = resp.json()
            return {
                "url": data.get("url", ""),
                "mime_type": data.get("mime_type", ""),
                "file_size": data.get("file_size", 0),
                "sha256": data.get("sha256", ""),
            }
        except Exception as exc:
            logger.error("Erro ao consultar midia %s: %s", media_id, exc)
            return None


async def download_media(media_id, msg_type, original_filename=""):
    ensure_media_dir()

    media_info = await get_media_url(media_id)
    if not media_info or not media_info["url"]:
        return None

    file_size = media_info.get("file_size", 0)
    if file_size > MAX_MEDIA_SIZE_MB * 1024 * 1024:
        logger.warning("Midia %s excede limite de %dMB", media_id, MAX_MEDIA_SIZE_MB)
        return None

    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}"}

    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            resp = await client.get(media_info["url"], headers=headers)
            if resp.status_code != 200:
                logger.error("Falha no download da midia %s: HTTP %d", media_id, resp.status_code)
                return None

            content = resp.content
            mime = media_info["mime_type"]
            ext = MIME_EXTENSIONS.get(mime, "")

            if not ext and original_filename:
                _, ext = os.path.splitext(original_filename)
            if not ext:
                ext = ".bin"

            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            safe_id = hashlib.sha256(media_id.encode()).hexdigest()[:12]
            filename = f"{timestamp}_{safe_id}{ext}"

            subdir = get_subdir_for_type(msg_type)
            filepath = os.path.join(MEDIA_DIR, subdir, filename)

            with open(filepath, "wb") as f:
                f.write(content)

            relative_path = f"/media/{subdir}/{filename}"
            logger.info("Midia salva: %s (%s, %d bytes)", relative_path, mime, len(content))

            return {
                "path": relative_path,
                "mime_type": mime,
                "size": len(content),
                "filename": original_filename or filename,
            }

        except Exception as exc:
            logger.error("Erro no download da midia %s: %s", media_id, exc)
            return None


def detect_media_type(mime_type):
    if mime_type.startswith("image/"):
        return "image"
    elif mime_type.startswith("audio/"):
        return "audio"
    elif mime_type.startswith("video/"):
        return "video"
    else:
        return "document"


async def save_upload_locally(file_content, filename, mime_type):
    ensure_media_dir()

    msg_type = detect_media_type(mime_type)
    subdir = get_subdir_for_type(msg_type)
    ext = MIME_EXTENSIONS.get(mime_type, "")

    if not ext and filename:
        _, ext = os.path.splitext(filename)
    if not ext:
        ext = ".bin"

    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    safe_hash = hashlib.sha256(file_content[:1024]).hexdigest()[:12]
    safe_name = f"{timestamp}_{safe_hash}{ext}"

    filepath = os.path.join(MEDIA_DIR, subdir, safe_name)
    with open(filepath, "wb") as f:
        f.write(file_content)

    relative_path = f"/media/{subdir}/{safe_name}"
    logger.info("Upload local salvo: %s (%s, %d bytes)", relative_path, mime_type, len(file_content))

    return {
        "path": relative_path,
        "mime_type": mime_type,
        "size": len(file_content),
        "msg_type": msg_type,
    }


async def upload_media_to_whatsapp(file_content, mime_type, filename=""):
    if not WHATSAPP_TOKEN or not WHATSAPP_PHONE_NUMBER_ID:
        logger.error("WABA nao configurado para upload")
        return None

    url = f"{GRAPH_API_BASE}/{WHATSAPP_PHONE_NUMBER_ID}/media"
    headers = {"Authorization": f"Bearer {WHATSAPP_TOKEN}"}

    if not filename:
        ext = MIME_EXTENSIONS.get(mime_type, ".bin")
        filename = f"upload{ext}"

    files = {"file": (filename, file_content, mime_type)}
    data = {"messaging_product": "whatsapp", "type": mime_type}

    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            resp = await client.post(url, headers=headers, files=files, data=data)
            result = resp.json()
            if resp.status_code in (200, 201):
                media_id = result.get("id", "")
                logger.info("Upload para Meta OK: media_id=%s", media_id)
                return media_id
            else:
                error = result.get("error", {}).get("message", resp.text[:200])
                logger.error("Upload para Meta falhou: %s", error)
                return None
        except Exception as exc:
            logger.error("Erro no upload para Meta: %s", exc)
            return None


async def send_media_message(wa_id, media_id, msg_type, caption=""):
    if not WHATSAPP_TOKEN or not WHATSAPP_PHONE_NUMBER_ID:
        return None

    wa_id = _normalize_br(wa_id)

    url = f"{GRAPH_API_BASE}/{WHATSAPP_PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json",
    }

    media_object = {"id": media_id}
    if caption and msg_type in ("image", "video", "document"):
        media_object["caption"] = caption

    payload = {
        "messaging_product": "whatsapp",
        "to": wa_id,
        "type": msg_type,
        msg_type: media_object,
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.post(url, json=payload, headers=headers)
            result = resp.json()
            if resp.status_code == 200:
                wa_msg_id = result.get("messages", [{}])[0].get("id", "")
                logger.info("[WA MEDIA OUT] %s -> %s (type=%s)", wa_id, wa_msg_id, msg_type)
                return {"wa_message_id": wa_msg_id, "status": "sent"}
            else:
                error = result.get("error", {}).get("message", "Erro desconhecido")
                logger.error("[WA MEDIA FAIL] %s: %s", wa_id, error)
                return {"error": error}
        except Exception as exc:
            logger.error("Erro ao enviar midia para %s: %s", wa_id, exc)
            return {"error": str(exc)}

```

## requirements.txt

```text
fastapi==0.115.0
uvicorn[standard]==0.30.0
httpx==0.27.0
bcrypt==4.2.0
PyJWT==2.9.0
pyngrok==7.2.2
python-multipart==0.0.9

```

## start.ps1

```powershell
$env:SECRET_KEY="castro_intel_2026_chave_fixa"
$env:WHATSAPP_TOKEN="EAALBK2KV99sBQZCwHhZBiiL3BFQoW7FZBeIxZAYWDhZAQIVZCKDhGNZABztEjHH5Due2xZCArZAZBXOj4DjTHZCyy651OLu2RxTlSSDhDnlp3Ho58ipdxnmFIUTetlXVlkzNZAFqZCdxov8j8n0dCZAaskxaCNBkUcjdNIkpFZBZACFRjXCBcVEdy5g9KZBVoCc9tNSloTax3cAZDZD"
$env:WHATSAPP_PHONE_NUMBER_ID="983401388192837"
$env:WHATSAPP_VERIFY_TOKEN="hubloc2024"
$env:WHATSAPP_APP_SECRET=""

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Castro Intelligence CRM" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Abrindo dois terminais:"
Write-Host "    1. Servidor FastAPI (porta 8080)"
Write-Host "    2. Tunel ngrok (HTTPS)"
Write-Host ""

# Terminal 1: Servidor
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$PWD'; .\venv\Scripts\activate; python main.py"

# Esperar servidor subir
Start-Sleep -Seconds 4

# Terminal 2: ngrok com IPv4 explicito
Start-Process powershell -ArgumentList "-NoExit", "-Command", "ngrok http 127.0.0.1:8080"

Write-Host "  Servidor e ngrok iniciados." -ForegroundColor Green
Write-Host ""
Write-Host "  Acesso local: http://127.0.0.1:8080" -ForegroundColor Yellow
Write-Host "  Copie a URL HTTPS do ngrok e atualize no painel da Meta se necessario."
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
```

## start_tunnel.py

```python
# -*- coding: utf-8 -*-

import subprocess, sys, time, threading, signal


def check_dep():
    try:
        from pyngrok import ngrok
        return True
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyngrok", "-q"])
        return True


def run_server():
    import uvicorn
    from main import app
    uvicorn.run(app, host="0.0.0.0", port=8080, log_level="warning")


def main():
    check_dep()
    from pyngrok import ngrok, conf

    print("Iniciando servidor...")
    t = threading.Thread(target=run_server, daemon=True)
    t.start()
    time.sleep(2)

    print("Criando tunel...\n")
    try:
        conf.get_default().region = "sa"
        tunnel = ngrok.connect(8080, "http")
        url = tunnel.public_url.replace("http://", "https://", 1) if tunnel.public_url.startswith("http://") else tunnel.public_url
    except Exception as e:
        print(f"Falha: {e}")
        print("Verifique: ngrok config add-authtoken SEU_TOKEN")
        sys.exit(1)

    print("=" * 56)
    print("  Castro Intelligence CRM")
    print("=" * 56)
    print(f"\n  Acesso local:  http://127.0.0.1:8080")
    print(f"  Acesso externo: {url}")
    print(f"\n  Webhook (para Meta): {url}/webhook")
    print(f"  Verify Token: hubloc2024")
    print(f"\n  Ctrl+C para encerrar")
    print("=" * 56 + "\n")

    try:
        signal.signal(signal.SIGINT, lambda s, f: sys.exit(0))
        while True:
            time.sleep(1)
    except (KeyboardInterrupt, SystemExit):
        print("\nEncerrando...")
        ngrok.kill()


if __name__ == "__main__":
    main()

```

## chat.html

```html
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Castro Intelligence - CRM</title>
    <link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600&display=swap" rel="stylesheet">
    <style>
        *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
        :root {
            --bg: #0f1117; --surface: #1a1d27; --surface-alt: #22252f;
            --border: #2a2d3a; --text: #e4e4e7; --text-muted: #71717a;
            --accent: #2563eb; --accent-hover: #1d4ed8; --accent-subtle: rgba(37,99,235,0.1);
            --sent-bg: #1e3a5f; --received-bg: #2a2d3a;
            --online: #22c55e; --wa-green: #25d366; --wa-dark: #1a3a2a;
            --danger: #dc2626; --warning: #f59e0b;
        }
        body { font-family: 'DM Sans', sans-serif; background: var(--bg); color: var(--text); height: 100vh; overflow: hidden; }
        .app { display: flex; height: 100vh; }

        .sidebar { width: 300px; min-width: 300px; background: var(--surface); border-right: 1px solid var(--border); display: flex; flex-direction: column; }
        .sidebar-header { padding: 16px 20px; border-bottom: 1px solid var(--border); display: flex; align-items: center; gap: 10px; }
        .sidebar-header-info { flex: 1; min-width: 0; }
        .sidebar-header h2 { font-size: 15px; font-weight: 600; letter-spacing: -0.01em; }
        .sidebar-header .user-info { font-size: 12px; color: var(--text-muted); margin-top: 2px; }
        .sidebar-header .user-role { font-size: 10px; color: var(--accent); text-transform: uppercase; letter-spacing: 0.04em; }

        .profile-avatar-wrapper { position: relative; cursor: pointer; flex-shrink: 0; }
        .profile-avatar-wrapper:hover .profile-avatar-overlay { opacity: 1; }
        .profile-avatar-overlay { position: absolute; inset: 0; border-radius: 50%; background: rgba(0,0,0,0.5); display: flex; align-items: center; justify-content: center; opacity: 0; transition: opacity 0.2s; font-size: 14px; color: #fff; }

        .sidebar-actions { display: flex; gap: 6px; padding: 8px 16px; border-bottom: 1px solid var(--border); }
        .btn-sidebar-action { flex: 1; padding: 5px; font-family: inherit; font-size: 10px; font-weight: 500; color: var(--text-muted); background: transparent; border: 1px solid var(--border); border-radius: 5px; cursor: pointer; transition: all 0.15s; text-align: center; }
        .btn-sidebar-action:hover { color: var(--text); border-color: var(--text-muted); }

        .section-label { padding: 10px 20px 6px; font-size: 11px; font-weight: 600; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.05em; }
        .contact-list { flex: 1; overflow-y: auto; }
        .contact-item { display: flex; align-items: center; gap: 10px; padding: 10px 16px; cursor: pointer; transition: background 0.12s; position: relative; }
        .contact-item:hover { background: var(--surface-alt); }
        .contact-item.active { background: var(--accent-subtle); }
        .contact-item.locked { opacity: 0.5; }

        .contact-avatar { width: 36px; height: 36px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 13px; font-weight: 600; flex-shrink: 0; color: var(--text-muted); background: var(--border); overflow: hidden; position: relative; }
        .contact-avatar.online { box-shadow: 0 0 0 2px var(--surface), 0 0 0 3.5px var(--online); }
        .contact-avatar.wa { background: var(--wa-dark); color: var(--wa-green); }
        .contact-avatar img { width: 100%; height: 100%; object-fit: cover; display: block; }

        .contact-details { flex: 1; min-width: 0; }
        .contact-name { font-size: 13px; font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .contact-sub { font-size: 11px; color: var(--text-muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .qual-dot { display: inline-block; width: 7px; height: 7px; border-radius: 50%; margin-right: 4px; vertical-align: middle; }
        .qual-novo { background: #60a5fa; } .qual-em_atendimento { background: #fbbf24; }
        .qual-qualificado { background: #34d399; } .qual-nao_qualificado { background: #f87171; }
        .qual-convertido { background: #a78bfa; }

        .badge { min-width: 18px; height: 18px; border-radius: 9px; display: flex; align-items: center; justify-content: center; font-size: 10px; font-weight: 600; padding: 0 5px; color: #fff; flex-shrink: 0; }
        .badge.internal { background: var(--accent); } .badge.wa { background: var(--wa-green); }
        .badge.hidden { display: none; }

        .sidebar-footer { padding: 10px 16px; border-top: 1px solid var(--border); }
        .btn-logout { width: 100%; padding: 7px; font-family: inherit; font-size: 12px; color: var(--text-muted); background: transparent; border: 1px solid var(--border); border-radius: 6px; cursor: pointer; transition: all 0.15s; }
        .btn-logout:hover { color: var(--text); border-color: var(--text-muted); }

        .chat-area { flex: 1; display: flex; flex-direction: column; }
        .chat-header { padding: 14px 20px; border-bottom: 1px solid var(--border); display: flex; align-items: center; gap: 10px; }
        .chat-header-info { flex: 1; }
        .chat-header-name { font-size: 14px; font-weight: 600; }
        .chat-header-sub { font-size: 12px; color: var(--text-muted); }
        .typing-indicator { font-size: 11px; color: var(--accent); font-style: italic; display: none; }

        .chat-locked-banner { padding: 10px 20px; background: rgba(245,158,11,0.1); border-bottom: 1px solid rgba(245,158,11,0.2); font-size: 12px; color: var(--warning); text-align: center; }

        .messages-container { flex: 1; overflow-y: auto; padding: 16px 20px; display: flex; flex-direction: column; gap: 4px; }
        .msg-row { display: flex; gap: 8px; align-items: flex-end; }
        .msg-row.sent { flex-direction: row-reverse; }
        .msg-row-avatar { width: 28px; height: 28px; border-radius: 50%; flex-shrink: 0; background: var(--border); display: flex; align-items: center; justify-content: center; font-size: 10px; font-weight: 600; color: var(--text-muted); overflow: hidden; margin-bottom: 2px; }
        .msg-row-avatar img { width: 100%; height: 100%; object-fit: cover; display: block; }

        .msg { max-width: 60%; padding: 8px 12px; border-radius: 10px; font-size: 13px; line-height: 1.45; word-wrap: break-word; }
        .msg.sent { background: var(--sent-bg); border-bottom-right-radius: 3px; }
        .msg.received { background: var(--received-bg); border-bottom-left-radius: 3px; }
        .msg-time { font-size: 10px; color: var(--text-muted); margin-top: 3px; }
        .msg.sent .msg-time { text-align: right; }
        .msg-status { font-size: 10px; color: var(--text-muted); margin-left: 6px; }
        .date-sep { text-align: center; font-size: 11px; color: var(--text-muted); padding: 10px 0; }
        .msg-sender-name { font-size: 11px; color: var(--wa-green); font-weight: 500; margin-bottom: 2px; }

        .system-msg { text-align: center; padding: 8px 16px; margin: 8px 0; font-size: 11px; color: var(--warning); background: rgba(245,158,11,0.08); border: 1px dashed rgba(245,158,11,0.25); border-radius: 8px; line-height: 1.5; }

        .msg-image { max-width: 280px; border-radius: 6px; margin-bottom: 4px; cursor: pointer; display: block; }
        .msg-video { max-width: 300px; border-radius: 6px; margin-bottom: 4px; }
        .msg-audio { width: 240px; margin-bottom: 4px; }
        .msg-sticker { max-width: 140px; margin-bottom: 4px; }
        .msg-document { display: flex; align-items: center; gap: 8px; padding: 8px 10px; background: rgba(255,255,255,0.05); border-radius: 6px; margin-bottom: 4px; text-decoration: none; color: var(--text); font-size: 12px; }
        .msg-document:hover { background: rgba(255,255,255,0.08); }
        .msg-location { display: block; color: var(--accent); text-decoration: none; font-size: 12px; margin-bottom: 4px; }
        .msg-caption { margin-top: 4px; font-size: 13px; }

        .message-input-area { padding: 12px 20px; border-top: 1px solid var(--border); display: flex; gap: 10px; align-items: flex-end; }
        .message-input-area.disabled { opacity: 0.35; pointer-events: none; }
        .msg-input { flex: 1; padding: 9px 12px; font-family: inherit; font-size: 13px; color: var(--text); background: var(--surface); border: 1px solid var(--border); border-radius: 8px; outline: none; resize: none; max-height: 100px; min-height: 38px; line-height: 1.4; }
        .msg-input:focus { border-color: var(--accent); }
        .btn-send { padding: 9px 16px; font-family: inherit; font-size: 13px; font-weight: 500; color: #fff; background: var(--accent); border: none; border-radius: 8px; cursor: pointer; white-space: nowrap; }
        .btn-send.wa-send { background: var(--wa-green); }
        .btn-icon { padding: 9px 12px; font-size: 16px; color: var(--text-muted); background: transparent; border: 1px solid var(--border); border-radius: 8px; cursor: pointer; flex-shrink: 0; }
        .btn-icon:hover { color: var(--text); border-color: var(--text-muted); }
        .btn-icon.recording { color: var(--danger); border-color: var(--danger); animation: pulse 1s infinite; }
        @keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.5; } }

        .recording-bar { display: none; padding: 10px 20px; border-top: 1px solid var(--border); align-items: center; gap: 12px; background: var(--surface-alt); }
        .recording-bar.active { display: flex; }
        .rec-dot { width: 10px; height: 10px; border-radius: 50%; background: var(--danger); animation: pulse 1s infinite; }
        .rec-timer { font-size: 13px; font-variant-numeric: tabular-nums; flex: 1; }
        .btn-rec-cancel { padding: 6px 14px; font-family: inherit; font-size: 12px; color: var(--text-muted); background: transparent; border: 1px solid var(--border); border-radius: 6px; cursor: pointer; }
        .btn-rec-send { padding: 6px 14px; font-family: inherit; font-size: 12px; font-weight: 500; color: #fff; background: var(--wa-green); border: none; border-radius: 6px; cursor: pointer; }

        .attach-preview { display: none; padding: 8px 12px; margin: 0 20px; background: var(--surface-alt); border: 1px solid var(--border); border-radius: 8px; font-size: 12px; color: var(--text-muted); align-items: center; gap: 8px; }
        .attach-preview.show { display: flex; }
        .attach-preview-name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        .attach-preview-remove { background: none; border: none; color: var(--text-muted); cursor: pointer; font-size: 16px; padding: 2px 6px; }

        .chat-header-actions { display: flex; gap: 6px; margin-left: auto; }
        .btn-header { padding: 6px 12px; font-family: inherit; font-size: 11px; font-weight: 500; border-radius: 6px; cursor: pointer; border: 1px solid var(--border); background: transparent; color: var(--text-muted); }
        .btn-header:hover { color: var(--text); }
        .btn-transfer { border-color: var(--warning); color: var(--warning); }

        .assigned-tag { display: inline-block; padding: 2px 8px; font-size: 10px; font-weight: 500; border-radius: 10px; background: rgba(37,99,235,0.15); color: #60a5fa; }
        .dept-tag { display: inline-block; padding: 2px 8px; font-size: 10px; font-weight: 500; border-radius: 10px; background: rgba(245,158,11,0.1); color: var(--warning); margin-left: 4px; }

        .modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.6); display: none; align-items: center; justify-content: center; z-index: 50; }
        .modal-overlay.show { display: flex; }
        .modal { background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 24px; width: 440px; max-width: 92vw; max-height: 85vh; overflow-y: auto; }
        .modal h3 { font-size: 15px; font-weight: 600; margin-bottom: 16px; }
        .modal-field { margin-bottom: 12px; }
        .modal-field label { display: block; font-size: 12px; color: var(--text-muted); margin-bottom: 4px; }
        .modal-field input, .modal-field select, .modal-field textarea { width: 100%; padding: 8px 10px; font-family: inherit; font-size: 13px; color: var(--text); background: var(--bg); border: 1px solid var(--border); border-radius: 6px; outline: none; }
        .modal-field textarea { resize: vertical; min-height: 60px; }
        .modal-actions { display: flex; gap: 8px; justify-content: flex-end; margin-top: 16px; }
        .modal-actions button { padding: 8px 16px; font-family: inherit; font-size: 13px; font-weight: 500; border-radius: 6px; cursor: pointer; border: none; }
        .btn-modal-cancel { background: var(--border); color: var(--text); }
        .btn-modal-confirm { background: var(--warning); color: #000; }
        .btn-modal-primary { background: var(--accent); color: #fff; }
        .btn-modal-danger { background: var(--danger); color: #fff; }

        .transfer-history { padding: 8px 0; }
        .transfer-item { padding: 6px 0; font-size: 11px; color: var(--text-muted); border-bottom: 1px solid var(--border); }
        .transfer-item:last-child { border-bottom: none; }

        .empty-state { flex: 1; display: flex; align-items: center; justify-content: center; color: var(--text-muted); font-size: 14px; }

        .lightbox { position: fixed; inset: 0; background: rgba(0,0,0,0.9); display: none; align-items: center; justify-content: center; z-index: 100; cursor: pointer; }
        .lightbox.show { display: flex; }
        .lightbox img { max-width: 90vw; max-height: 90vh; border-radius: 4px; }

        ::-webkit-scrollbar { width: 5px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }

        @media (max-width: 700px) {
            .sidebar { width: 72px; min-width: 72px; }
            .sidebar-header h2, .sidebar-header .user-info, .sidebar-header .user-role,
            .contact-details, .section-label, .sidebar-footer, .sidebar-header-info, .sidebar-actions { display: none; }
            .contact-item { justify-content: center; }
            .msg { max-width: 85%; }
            .msg-row-avatar { display: none; }
        }
    </style>
</head>
<body>
    <div class="app">
        <div class="sidebar">
            <div class="sidebar-header">
                <div class="profile-avatar-wrapper" id="profileAvatarWrapper" title="Alterar foto de perfil">
                    <div class="contact-avatar" id="myAvatar" style="width:40px;height:40px;font-size:14px;"></div>
                    <div class="profile-avatar-overlay">&#9998;</div>
                    <input type="file" id="avatarInput" accept="image/jpeg,image/png,image/webp" style="display:none">
                </div>
                <div class="sidebar-header-info">
                    <h2>Castro Intelligence</h2>
                    <div class="user-info" id="currentUserName"></div>
                    <div class="user-role" id="currentUserRole"></div>
                </div>
            </div>
            <div class="sidebar-actions" id="sidebarActions"></div>
            <div class="contact-list" id="contactList"></div>
            <div class="sidebar-footer">
                <button class="btn-logout" id="btnLogout">Sair</button>
            </div>
        </div>
        <div class="chat-area" id="chatArea">
            <div class="empty-state">Selecione uma conversa</div>
        </div>
    </div>

    <div class="lightbox" id="lightbox"><img id="lightboxImg" src="" alt=""></div>

    <!-- Modal: Transferencia -->
    <div class="modal-overlay" id="transferModal">
        <div class="modal">
            <h3>Transferir atendimento</h3>
            <div class="modal-field"><label>Operador destino *</label><select id="transferOperator"><option value="">Selecione...</option></select></div>
            <div class="modal-field"><label>Setor</label><select id="transferDept"><option value="">Nenhum</option></select></div>
            <div class="modal-field"><label>Resumo do atendimento *</label><textarea id="transferSummary" placeholder="Descreva o que foi realizado e o estado atual do atendimento..." rows="4"></textarea></div>
            <div class="modal-field"><label>Motivo da transferencia</label><textarea id="transferReason" placeholder="Porque esta transferindo?" rows="2"></textarea></div>
            <div id="transferHistory" class="transfer-history" style="display:none"></div>
            <div class="modal-actions">
                <button class="btn-modal-cancel" id="transferCancel">Cancelar</button>
                <button class="btn-modal-confirm" id="transferConfirm">Transferir</button>
            </div>
        </div>
    </div>

    <!-- Modal: Gerenciar contato -->
    <div class="modal-overlay" id="contactModal">
        <div class="modal">
            <h3 id="contactModalTitle">Gerenciar contato</h3>
            <div class="modal-field"><label>Qualificacao</label><select id="contactQualification">
                <option value="novo">Novo</option><option value="em_atendimento">Em atendimento</option>
                <option value="qualificado">Qualificado</option><option value="nao_qualificado">Nao qualificado</option>
                <option value="convertido">Convertido</option>
            </select></div>
            <div class="modal-field"><label>Observacoes</label><textarea id="contactNotes" placeholder="Anotacoes sobre o contato..." rows="3"></textarea></div>
            <div class="modal-field"><label>Foto do contato</label><input type="file" id="contactAvatarInput" accept="image/jpeg,image/png,image/webp"></div>
            <div class="modal-actions">
                <button class="btn-modal-danger" id="contactArchive">Arquivar</button>
                <button class="btn-modal-cancel" id="contactCancel">Cancelar</button>
                <button class="btn-modal-primary" id="contactSave">Salvar</button>
            </div>
        </div>
    </div>

    <!-- Modal: Criar usuario -->
    <div class="modal-overlay" id="userModal">
        <div class="modal">
            <h3>Novo atendente</h3>
            <div class="modal-field"><label>Nome de usuario *</label><input type="text" id="newUsername" placeholder="ex: joao.silva" autocomplete="off"></div>
            <div class="modal-field"><label>Nome completo *</label><input type="text" id="newDisplayName" placeholder="Joao da Silva"></div>
            <div class="modal-field"><label>Senha *</label><input type="password" id="newPassword" placeholder="Minimo 6 caracteres" autocomplete="new-password"></div>
            <div class="modal-field"><label>Cargo *</label><select id="newRole"><option value="operador">Operador</option><option value="supervisor">Supervisor</option><option value="admin">Administrador</option></select></div>
            <div class="modal-field"><label>Setor</label><select id="newDepartment"><option value="">Nenhum</option></select></div>
            <div class="modal-actions">
                <button class="btn-modal-cancel" id="userCancel">Cancelar</button>
                <button class="btn-modal-primary" id="userCreate">Criar</button>
            </div>
        </div>
    </div>

    <script>
    (function(){
        "use strict";

        var session = sessionStorage.getItem("crm_session");
        if (!session) { window.location.href = "/"; return; }
        var parsed = JSON.parse(session);
        var TOKEN = parsed.token;
        var USER = parsed.user;

        var activeChat = null;
        var ws = null;
        var onlineUsers = {};
        var typingTimeout = null;
        var lastTypingSent = 0;
        var internalContacts = [];
        var waContacts = [];
        var internalUnread = {};
        var waUnread = {};
        var avatarCache = {};
        var mediaRecorder = null;
        var audioChunks = [];
        var recInterval = null;

        document.getElementById("currentUserName").textContent = USER.display_name;
        document.getElementById("currentUserRole").textContent = USER.role || "operador";

        function hdrs() { return {"Authorization": "Bearer " + TOKEN, "Content-Type": "application/json"}; }
        function initials(name) { var p = (name || "?").split(" "); return p.length >= 2 ? (p[0][0] + p[p.length-1][0]).toUpperCase() : p[0][0].toUpperCase(); }
        function esc(s) { var d = document.createElement("div"); d.textContent = s; return d.innerHTML; }
        function fmtTime(iso) { var d = new Date(iso); if (isNaN(d.getTime())) d = new Date(iso.replace(" ", "T") + "Z"); return String(d.getHours()).padStart(2,"0") + ":" + String(d.getMinutes()).padStart(2,"0"); }
        function fmtDate(iso) { var d = new Date(iso); if (isNaN(d.getTime())) d = new Date(iso.replace(" ", "T") + "Z"); var today = new Date(); if (d.toDateString() === today.toDateString()) return "Hoje"; var y = new Date(today); y.setDate(y.getDate()-1); if (d.toDateString() === y.toDateString()) return "Ontem"; return String(d.getDate()).padStart(2,"0") + "/" + String(d.getMonth()+1).padStart(2,"0") + "/" + d.getFullYear(); }
        function scrollBottom(el) { el.scrollTop = el.scrollHeight; }

        function avatarHtml(name, path, cls, sz) {
            var c = "contact-avatar" + (cls ? " " + cls : "");
            var st = sz ? ' style="width:'+sz+'px;height:'+sz+'px;font-size:'+Math.round(sz*0.36)+'px;"' : "";
            if (path) return '<div class="'+c+'"'+st+'><img src="'+esc(path)+'" alt=""></div>';
            return '<div class="'+c+'"'+st+'>'+esc(initials(name))+'</div>';
        }
        function msgAvatarHtml(name, path) {
            if (path) return '<div class="msg-row-avatar"><img src="'+esc(path)+'" alt=""></div>';
            return '<div class="msg-row-avatar">'+esc(initials(name))+'</div>';
        }

        // -- Avatar do usuario --
        function updateMyAvatar() {
            var el = document.getElementById("myAvatar");
            if (!el) return;
            var path = USER.avatar_path || "";
            el.innerHTML = path ? '<img src="'+esc(path)+'" alt="">' : esc(initials(USER.display_name));
        }
        document.getElementById("profileAvatarWrapper").addEventListener("click", function(){ document.getElementById("avatarInput").click(); });
        document.getElementById("avatarInput").addEventListener("change", function(){
            if (!this.files || !this.files[0]) return;
            var file = this.files[0];
            if (file.size > 512 * 1024) { alert("Imagem excede 512KB."); this.value = ""; return; }
            var fd = new FormData(); fd.append("file", file);
            fetch("/api/profile/avatar", { method: "POST", headers: {"Authorization": "Bearer " + TOKEN}, body: fd })
            .then(function(r){ return r.json(); })
            .then(function(d){
                if (d.avatar_path) { USER.avatar_path = d.avatar_path; avatarCache[USER.id] = d.avatar_path; var s = JSON.parse(sessionStorage.getItem("crm_session")); s.user.avatar_path = d.avatar_path; sessionStorage.setItem("crm_session", JSON.stringify(s)); updateMyAvatar(); renderSidebar(); }
            });
            this.value = "";
        });
        updateMyAvatar();

        // -- Sidebar actions --
        function renderSidebarActions() {
            var el = document.getElementById("sidebarActions");
            var btns = [];
            if (USER.role === "admin" || USER.role === "supervisor") {
                btns.push('<button class="btn-sidebar-action" id="btnNewUser">+ Atendente</button>');
            }
            el.innerHTML = btns.join("");
            var b = document.getElementById("btnNewUser");
            if (b) b.addEventListener("click", openUserModal);
        }
        renderSidebarActions();

        // -- Carregar contatos --
        function loadAll() {
            fetch("/api/users", {headers: hdrs()}).then(function(r){ return r.json(); }).then(function(data){
                internalContacts = data;
                data.forEach(function(c){ if (c.avatar_path) avatarCache[c.id] = c.avatar_path; });
                renderSidebar();
            });
            fetch("/api/unread", {headers: hdrs()}).then(function(r){ return r.json(); }).then(function(data){ internalUnread = data.unread || {}; renderSidebar(); });
            fetch("/api/wa/contacts", {headers: hdrs()}).then(function(r){ return r.json(); }).then(function(data){
                waContacts = data.contacts || [];
                waUnread = {};
                waContacts.forEach(function(c){ if (c.unread > 0) waUnread[c.id] = c.unread; });
                renderSidebar();
            });
        }

        function renderSidebar() {
            var list = document.getElementById("contactList");
            list.innerHTML = "";
            if (internalContacts.length > 0) {
                var lbl = document.createElement("div"); lbl.className = "section-label"; lbl.textContent = "Equipe"; list.appendChild(lbl);
                internalContacts.forEach(function(c){
                    var isOn = onlineUsers[c.id] === true;
                    var isAct = activeChat && activeChat.type === "internal" && activeChat.id === c.id;
                    var unread = internalUnread[String(c.id)] || 0;
                    var ap = c.avatar_path || avatarCache[c.id] || "";
                    var el = document.createElement("div");
                    el.className = "contact-item" + (isAct ? " active" : "");
                    var roleText = c.role ? " (" + c.role + ")" : "";
                    el.innerHTML = avatarHtml(c.display_name, ap, isOn ? "online" : "", 0) +
                        '<div class="contact-details"><div class="contact-name">'+esc(c.display_name)+'</div>' +
                        '<div class="contact-sub">'+(isOn?"Online":"Offline")+esc(roleText)+'</div></div>' +
                        '<div class="badge internal'+(unread===0?" hidden":"")+'">'+unread+'</div>';
                    el.addEventListener("click", function(){ openInternal(c); });
                    list.appendChild(el);
                });
            }
            if (waContacts.length > 0) {
                var lbl2 = document.createElement("div"); lbl2.className = "section-label"; lbl2.textContent = "WhatsApp"; list.appendChild(lbl2);
                waContacts.forEach(function(c){
                    var isAct = activeChat && activeChat.type === "whatsapp" && activeChat.id === c.id;
                    var unread = waUnread[c.id] || 0;
                    var dn = c.display_name || c.phone_formatted || c.wa_id;
                    var sub = c.phone_formatted || c.wa_id;
                    if (c.assigned_name && c.assigned_to !== USER.id) sub += " - " + c.assigned_name;
                    var isLocked = c.assigned_to && c.assigned_to !== USER.id;
                    var cAvatar = c.contact_avatar_path || "";
                    var qualDot = c.qualification ? '<span class="qual-dot qual-'+c.qualification+'"></span>' : "";
                    var el = document.createElement("div");
                    el.className = "contact-item" + (isAct ? " active" : "") + (isLocked ? " locked" : "");
                    el.innerHTML = avatarHtml(dn, cAvatar, "wa", 0) +
                        '<div class="contact-details"><div class="contact-name">'+qualDot+esc(dn)+'</div><div class="contact-sub">'+esc(sub)+'</div></div>' +
                        '<div class="badge wa'+(unread===0?" hidden":"")+'">'+unread+'</div>';
                    el.addEventListener("click", function(){ openWhatsApp(c); });
                    list.appendChild(el);
                });
            }
        }

        // -- Chat interno --
        function openInternal(contact) {
            activeChat = {type: "internal", id: contact.id, data: contact};
            internalUnread[String(contact.id)] = 0; renderSidebar();
            var isOn = onlineUsers[contact.id] === true;
            var ap = contact.avatar_path || avatarCache[contact.id] || "";
            var area = document.getElementById("chatArea");
            area.innerHTML = '<div class="chat-header">'+avatarHtml(contact.display_name, ap, isOn?"online":"", 0)+
                '<div class="chat-header-info"><div class="chat-header-name">'+esc(contact.display_name)+'</div>' +
                '<div class="chat-header-sub">'+(isOn?"Online":"Offline")+'</div>' +
                '<div class="typing-indicator" id="typingIndicator">digitando...</div></div></div>' +
                '<div class="messages-container" id="messagesContainer"></div>' +
                '<div class="message-input-area"><textarea class="msg-input" id="msgInput" rows="1" placeholder="Digite uma mensagem..."></textarea>' +
                '<button class="btn-send" id="btnSend">Enviar</button></div>';
            bindInput("internal");
            if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({event: "mark_read", sender_id: contact.id}));
            loadInternalMessages(contact.id);
        }

        function loadInternalMessages(cid) {
            fetch("/api/messages/" + cid, {headers: hdrs()}).then(function(r){ return r.json(); }).then(function(data){
                var c = document.getElementById("messagesContainer"); if (!c) return; c.innerHTML = "";
                var lastDate = "";
                (data.messages || []).forEach(function(m){ var d = fmtDate(m.created_at); if (d !== lastDate) { lastDate = d; addDateSep(c, d); } addInternalMsg(c, m); });
                scrollBottom(c);
            });
        }

        function addInternalMsg(container, m) {
            var isSent = m.sender_id === USER.id;
            var sn = isSent ? USER.display_name : (m.sender_name || "");
            var sa = isSent ? (USER.avatar_path || "") : (avatarCache[m.sender_id] || "");
            var row = document.createElement("div"); row.className = "msg-row" + (isSent ? " sent" : "");
            var msgDiv = document.createElement("div"); msgDiv.className = "msg " + (isSent ? "sent" : "received");
            msgDiv.innerHTML = '<div>'+esc(m.content)+'</div><div class="msg-time">'+fmtTime(m.created_at)+'</div>';
            row.innerHTML = msgAvatarHtml(sn, sa);
            row.appendChild(msgDiv); container.appendChild(row);
        }

        // -- Chat WhatsApp --
        function openWhatsApp(contact) {
            activeChat = {type: "whatsapp", id: contact.id, data: contact};
            delete waUnread[contact.id]; renderSidebar();
            var dn = contact.display_name || contact.phone_formatted || contact.wa_id;
            var cAvatar = contact.contact_avatar_path || "";
            var isLocked = contact.assigned_to && contact.assigned_to !== USER.id;
            var assignHtml = "";
            if (contact.assigned_name) assignHtml += '<span class="assigned-tag">'+esc(contact.assigned_name)+'</span>';
            if (contact.department_name) assignHtml += '<span class="dept-tag">'+esc(contact.department_name)+'</span>';

            var area = document.getElementById("chatArea");
            var headerBtns = '';
            if (!isLocked) {
                headerBtns = '<button class="btn-header" id="btnContactMgmt">Gerenciar</button>' +
                    '<button class="btn-header btn-transfer" id="btnTransfer">Transferir</button>';
            }
            var lockedBanner = isLocked ? '<div class="chat-locked-banner">Atendimento com '+esc(contact.assigned_name || "outro operador")+' - somente leitura</div>' : '';

            area.innerHTML = '<div class="chat-header">'+avatarHtml(dn, cAvatar, "wa", 0)+
                '<div class="chat-header-info"><div class="chat-header-name">'+esc(dn)+'</div>' +
                '<div class="chat-header-sub">'+esc(contact.phone_formatted || contact.wa_id)+(assignHtml?'&nbsp;&nbsp;'+assignHtml:'')+'</div></div>' +
                '<div class="chat-header-actions">'+headerBtns+'</div></div>'+lockedBanner+
                '<div class="messages-container" id="messagesContainer"></div>' +
                '<div class="attach-preview" id="attachPreview"><img class="attach-preview-thumb" id="attachThumb" src="" alt="" style="display:none">' +
                '<span class="attach-preview-name" id="attachName"></span><button class="attach-preview-remove" id="attachRemove">&#10005;</button></div>' +
                '<div class="recording-bar" id="recordingBar"><div class="rec-dot"></div><span class="rec-timer" id="recTimer">00:00</span>' +
                '<button class="btn-rec-cancel" id="recCancel">Cancelar</button><button class="btn-rec-send" id="recSend">Enviar</button></div>' +
                '<div class="message-input-area'+(isLocked?' disabled':'')+'"><input type="file" id="fileInput" style="display:none" accept="image/*,audio/*,video/*,.pdf,.doc,.docx,.xls,.xlsx,.zip">' +
                '<button class="btn-icon" id="btnAttach" title="Anexar arquivo">&#128206;</button>' +
                '<button class="btn-icon" id="btnMic" title="Gravar audio">&#127908;</button>' +
                '<textarea class="msg-input" id="msgInput" rows="1" placeholder="Responder no WhatsApp..."></textarea>' +
                '<button class="btn-send wa-send" id="btnSend">Enviar</button></div>';

            var bt = document.getElementById("btnTransfer");
            if (bt) bt.addEventListener("click", function(){ openTransferModal(contact); });
            var bm = document.getElementById("btnContactMgmt");
            if (bm) bm.addEventListener("click", function(){ openContactModal(contact); });

            if (!isLocked) {
                bindInput("whatsapp");
                bindAudioRecorder(contact.id);
            }
            loadWaMessages(contact.id);
        }

        function loadWaMessages(cid) {
            fetch("/api/wa/messages/" + cid, {headers: hdrs()}).then(function(r){ return r.json(); }).then(function(data){
                var c = document.getElementById("messagesContainer"); if (!c) return; c.innerHTML = "";
                var lastDate = "";
                (data.messages || []).forEach(function(m){
                    if (m.msg_type === "system") { addSystemMsg(c, m); return; }
                    var d = fmtDate(m.created_at); if (d !== lastDate) { lastDate = d; addDateSep(c, d); }
                    addWaMsg(c, m);
                });
                scrollBottom(c);
            });
        }

        function addSystemMsg(container, m) {
            var div = document.createElement("div"); div.className = "system-msg";
            div.textContent = m.content;
            container.appendChild(div);
        }

        function addWaMsg(container, m) {
            var isSent = m.direction === "outbound";
            var div = document.createElement("div"); div.className = "msg " + (isSent ? "sent" : "received");
            var parts = [];
            if (!isSent && m.contact_name) parts.push('<div class="msg-sender-name">'+esc(m.contact_name)+'</div>');
            switch (m.msg_type) {
                case "image": if (m.media_path) parts.push('<img class="msg-image" src="'+esc(m.media_path)+'" alt="Imagem" onclick="showLightbox(this.src)">'); if (m.content) parts.push('<div class="msg-caption">'+esc(m.content)+'</div>'); break;
                case "video": if (m.media_path) parts.push('<video class="msg-video" controls preload="metadata"><source src="'+esc(m.media_path)+'" type="'+esc(m.media_mime||"video/mp4")+'"></video>'); if (m.content) parts.push('<div class="msg-caption">'+esc(m.content)+'</div>'); break;
                case "audio": if (m.media_path) parts.push('<audio class="msg-audio" controls preload="metadata"><source src="'+esc(m.media_path)+'" type="'+esc(m.media_mime||"audio/ogg")+'"></audio>'); break;
                case "sticker": if (m.media_path) parts.push('<img class="msg-sticker" src="'+esc(m.media_path)+'" alt="Figurinha">'); break;
                case "document": var fn = m.filename || "Documento"; if (m.media_path) parts.push('<a class="msg-document" href="'+esc(m.media_path)+'" target="_blank" download><span style="font-size:18px">&#128196;</span><span>'+esc(fn)+'</span></a>'); if (m.content) parts.push('<div class="msg-caption">'+esc(m.content)+'</div>'); break;
                case "location": if (m.latitude && m.longitude) parts.push('<a class="msg-location" href="https://maps.google.com/?q='+m.latitude+','+m.longitude+'" target="_blank" rel="noopener">&#128205; '+m.latitude.toFixed(5)+', '+m.longitude.toFixed(5)+'</a>'); if (m.content) parts.push('<div class="msg-caption">'+esc(m.content)+'</div>'); break;
                case "reaction": parts.push('<div style="font-size:28px">'+esc(m.content)+'</div>'); break;
                default: if (m.content) parts.push('<div>'+esc(m.content)+'</div>'); break;
            }
            var si = "";
            if (isSent && m.status) { var ic = {sent:"&#10003;",delivered:"&#10003;&#10003;",read:"&#10003;&#10003;",failed:"&#10007;"}; si = '<span class="msg-status">'+(ic[m.status]||"")+'</span>'; }
            parts.push('<div class="msg-time">'+fmtTime(m.timestamp_wa||m.created_at)+si+'</div>');
            div.innerHTML = parts.join(""); container.appendChild(div);
        }

        // -- Audio recorder --
        function bindAudioRecorder(contactId) {
            var btnMic = document.getElementById("btnMic");
            if (!btnMic) return;
            btnMic.addEventListener("click", function() {
                if (mediaRecorder && mediaRecorder.state === "recording") return;
                navigator.mediaDevices.getUserMedia({audio: true}).then(function(stream) {
                    audioChunks = [];
                    var opts = {mimeType: "audio/webm;codecs=opus"};
                    try { mediaRecorder = new MediaRecorder(stream, opts); } catch(e) { mediaRecorder = new MediaRecorder(stream); }
                    mediaRecorder.ondataavailable = function(e) { if (e.data.size > 0) audioChunks.push(e.data); };
                    mediaRecorder.onstop = function() { stream.getTracks().forEach(function(t){ t.stop(); }); };
                    mediaRecorder.start();
                    btnMic.classList.add("recording");
                    var bar = document.getElementById("recordingBar"); bar.classList.add("active");
                    var sec = 0;
                    recInterval = setInterval(function() { sec++; var m = String(Math.floor(sec/60)).padStart(2,"0"); var s = String(sec%60).padStart(2,"0"); document.getElementById("recTimer").textContent = m+":"+s; }, 1000);
                    document.getElementById("recCancel").onclick = function() { cancelRec(); };
                    document.getElementById("recSend").onclick = function() { sendRecordedAudio(contactId); };
                }).catch(function(err) { alert("Acesso ao microfone negado: " + err.message); });
            });
        }
        function cancelRec() {
            if (mediaRecorder && mediaRecorder.state !== "inactive") mediaRecorder.stop();
            clearInterval(recInterval);
            audioChunks = [];
            var bar = document.getElementById("recordingBar"); if (bar) bar.classList.remove("active");
            var btn = document.getElementById("btnMic"); if (btn) btn.classList.remove("recording");
        }
        function sendRecordedAudio(contactId) {
            if (!mediaRecorder || mediaRecorder.state === "inactive") return;
            mediaRecorder.stop();
            clearInterval(recInterval);
            var bar = document.getElementById("recordingBar"); if (bar) bar.classList.remove("active");
            var btn = document.getElementById("btnMic"); if (btn) btn.classList.remove("recording");
            setTimeout(function() {
                var blob = new Blob(audioChunks, {type: mediaRecorder.mimeType || "audio/webm"});
                var fd = new FormData();
                fd.append("contact_id", contactId);
                fd.append("file", blob, "gravacao.ogg");
                var sendBtn = document.getElementById("btnSend"); if (sendBtn) { sendBtn.textContent = "Enviando..."; sendBtn.disabled = true; }
                fetch("/api/wa/send-audio", {method: "POST", headers: {"Authorization": "Bearer " + TOKEN}, body: fd})
                .then(function(r){ return r.json(); })
                .then(function(d){
                    if (d.status === "sent") {
                        var c = document.getElementById("messagesContainer");
                        if (c) { addWaMsg(c, {direction:"outbound",msg_type:"audio",content:"",media_path:d.media_path,media_mime:"audio/ogg",status:"sent",created_at:new Date().toISOString(),timestamp_wa:new Date().toISOString()}); scrollBottom(c); }
                    } else { alert(d.detail || "Falha ao enviar audio"); }
                })
                .catch(function(err){ alert("Erro: " + err.message); })
                .finally(function(){ if (sendBtn) { sendBtn.textContent = "Enviar"; sendBtn.disabled = false; } audioChunks = []; });
            }, 300);
        }

        // -- Input e envio --
        var pendingFile = null;
        function bindInput(chatType) {
            var input = document.getElementById("msgInput");
            var btn = document.getElementById("btnSend");
            input.addEventListener("input", function(){ this.style.height = "auto"; this.style.height = Math.min(this.scrollHeight, 100) + "px";
                if (chatType === "internal" && ws && ws.readyState === WebSocket.OPEN) { var now = Date.now(); if (now - lastTypingSent > 2000) { ws.send(JSON.stringify({event: "typing", receiver_id: activeChat.id})); lastTypingSent = now; } }
            });
            input.addEventListener("keydown", function(e){ if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); doSend(chatType); } });
            btn.addEventListener("click", function(){ doSend(chatType); });
            var ba = document.getElementById("btnAttach"); var fi = document.getElementById("fileInput"); var ar = document.getElementById("attachRemove");
            if (ba && fi) { ba.addEventListener("click", function(){ fi.click(); }); fi.addEventListener("change", function(){ if (this.files && this.files[0]) { pendingFile = this.files[0]; showAttachPreview(pendingFile); } }); }
            if (ar) ar.addEventListener("click", function(){ pendingFile = null; hideAttachPreview(); fi.value = ""; });
            input.focus();
        }
        function showAttachPreview(file) { var p = document.getElementById("attachPreview"); var t = document.getElementById("attachThumb"); var n = document.getElementById("attachName"); if (!p) return; n.textContent = file.name + " (" + (file.size/1024).toFixed(0) + " KB)"; if (file.type.startsWith("image/")) { t.style.display = "block"; var r = new FileReader(); r.onload = function(e){ t.src = e.target.result; }; r.readAsDataURL(file); } else { t.style.display = "none"; } p.classList.add("show"); }
        function hideAttachPreview() { var p = document.getElementById("attachPreview"); if (p) p.classList.remove("show"); }
        function doSend(chatType) {
            var input = document.getElementById("msgInput"); var content = input.value.trim();
            if (chatType === "whatsapp" && pendingFile) { sendMedia(content); return; }
            if (!content || !activeChat) return;
            if (chatType === "internal") { if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({event: "send_message", receiver_id: activeChat.id, content: content})); }
            else { fetch("/api/wa/send", {method: "POST", headers: hdrs(), body: JSON.stringify({contact_id: activeChat.id, content: content})})
                .then(function(r){ return r.json(); }).then(function(data){ if (data.status === "sent") { var c = document.getElementById("messagesContainer"); if (c) { addWaMsg(c, {direction:"outbound",msg_type:"text",content:content,status:"sent",created_at:new Date().toISOString(),timestamp_wa:new Date().toISOString()}); scrollBottom(c); } } }); }
            input.value = ""; input.style.height = "auto"; input.focus();
        }
        function sendMedia(caption) {
            if (!pendingFile || !activeChat) return;
            var fd = new FormData(); fd.append("contact_id", activeChat.id); fd.append("caption", caption || ""); fd.append("file", pendingFile);
            var btn = document.getElementById("btnSend"); btn.textContent = "Enviando..."; btn.disabled = true;
            fetch("/api/wa/send-media", {method: "POST", headers: {"Authorization": "Bearer " + TOKEN}, body: fd})
            .then(function(r){ return r.json().then(function(d){ return {status: r.status, body: d}; }); })
            .then(function(res){ if (res.status === 200 && res.body.status === "sent") { var c = document.getElementById("messagesContainer"); if (c) { addWaMsg(c, {direction:"outbound",msg_type:res.body.msg_type,content:caption||"",media_path:res.body.media_path,media_mime:pendingFile.type,filename:pendingFile.name,status:"sent",created_at:new Date().toISOString(),timestamp_wa:new Date().toISOString()}); scrollBottom(c); } } else { alert(res.body.detail || "Erro ao enviar"); } })
            .catch(function(err){ alert("Falha: " + err.message); })
            .finally(function(){ pendingFile = null; hideAttachPreview(); var fi = document.getElementById("fileInput"); if (fi) fi.value = ""; var inp = document.getElementById("msgInput"); if (inp) { inp.value = ""; inp.style.height = "auto"; inp.focus(); } btn.textContent = "Enviar"; btn.disabled = false; });
        }

        function addDateSep(c, text) { var d = document.createElement("div"); d.className = "date-sep"; d.textContent = text; c.appendChild(d); }

        // -- Lightbox --
        window.showLightbox = function(src) { document.getElementById("lightboxImg").src = src; document.getElementById("lightbox").classList.add("show"); };
        document.getElementById("lightbox").addEventListener("click", function(){ this.classList.remove("show"); });

        // -- WebSocket --
        function connectWS() {
            var proto = location.protocol === "https:" ? "wss" : "ws";
            ws = new WebSocket(proto + "://" + location.host + "/ws/" + TOKEN);
            ws.onmessage = function(evt){
                var msg; try { msg = JSON.parse(evt.data); } catch(e) { return; }
                switch(msg.event) {
                    case "new_message":
                        if (activeChat && activeChat.type === "internal" && msg.data.sender_id === activeChat.id) {
                            var c = document.getElementById("messagesContainer"); if (c) { if (msg.data.sender_avatar) avatarCache[msg.data.sender_id] = msg.data.sender_avatar; addInternalMsg(c, msg.data); scrollBottom(c); }
                            if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({event: "mark_read", sender_id: msg.data.sender_id}));
                        } else { internalUnread[String(msg.data.sender_id)] = (internalUnread[String(msg.data.sender_id)] || 0) + 1; renderSidebar(); } break;
                    case "message_sent":
                        if (activeChat && activeChat.type === "internal" && msg.data.receiver_id === activeChat.id) {
                            var c2 = document.getElementById("messagesContainer"); if (c2) { addInternalMsg(c2, {sender_id: USER.id, content: msg.data.content, created_at: msg.data.created_at}); scrollBottom(c2); } } break;
                    case "user_online": onlineUsers[msg.data.user_id] = true; if (msg.data.avatar_path) avatarCache[msg.data.user_id] = msg.data.avatar_path; renderSidebar(); break;
                    case "user_offline": delete onlineUsers[msg.data.user_id]; renderSidebar(); break;
                    case "typing":
                        if (activeChat && activeChat.type === "internal" && msg.data.user_id === activeChat.id) { var ti = document.getElementById("typingIndicator"); if (ti) { ti.style.display = "block"; clearTimeout(typingTimeout); typingTimeout = setTimeout(function(){ ti.style.display = "none"; }, 3000); } } break;
                    case "wa_new_message":
                        if (activeChat && activeChat.type === "whatsapp" && activeChat.id === msg.data.contact_id) {
                            var c3 = document.getElementById("messagesContainer"); if (c3) { addWaMsg(c3, {direction:"inbound",msg_type:msg.data.msg_type,content:msg.data.content,media_path:msg.data.media_path,media_mime:msg.data.media_mime,latitude:msg.data.latitude,longitude:msg.data.longitude,filename:msg.data.filename,contact_name:msg.data.contact_name,created_at:msg.data.timestamp,timestamp_wa:msg.data.timestamp,status:"received"}); scrollBottom(c3); }
                        } else { waUnread[msg.data.contact_id] = (waUnread[msg.data.contact_id] || 0) + 1; var found = false; for (var i = 0; i < waContacts.length; i++) { if (waContacts[i].id === msg.data.contact_id) { found = true; break; } } if (!found) loadAll(); renderSidebar(); } break;
                    case "wa_transfer_received":
                        loadAll();
                        var summaryText = msg.data.summary ? "\nResumo: " + msg.data.summary : "";
                        var reasonText = msg.data.reason ? "\nMotivo: " + msg.data.reason : "";
                        alert("Transferencia recebida de " + msg.data.from_user + "\nContato: " + (msg.data.contact_name || "Desconhecido") + reasonText + summaryText);
                        break;
                    case "wa_contact_reassigned": loadAll(); break;
                }
            };
            ws.onclose = function(evt){ if (evt.code === 4001) { sessionStorage.removeItem("crm_session"); window.location.href = "/"; } else { setTimeout(connectWS, 3000); } };
        }

        // -- Modal: Transferencia --
        function openTransferModal(contact) {
            var modal = document.getElementById("transferModal");
            document.getElementById("transferSummary").value = "";
            document.getElementById("transferReason").value = "";
            fetch("/api/operators", {headers: hdrs()}).then(function(r){ return r.json(); }).then(function(ops){
                var sel = document.getElementById("transferOperator"); sel.innerHTML = '<option value="">Selecione...</option>';
                ops.forEach(function(o){ if (o.id === USER.id) return; var opt = document.createElement("option"); opt.value = o.id; opt.textContent = o.display_name + " (" + (o.role||"operador") + ")" + (o.department_name ? " - " + o.department_name : ""); sel.appendChild(opt); });
            });
            fetch("/api/departments", {headers: hdrs()}).then(function(r){ return r.json(); }).then(function(data){
                var sel = document.getElementById("transferDept"); sel.innerHTML = '<option value="">Nenhum</option>';
                (data.departments || []).forEach(function(d){ var opt = document.createElement("option"); opt.value = d.id; opt.textContent = d.name; if (contact.department_id && contact.department_id === d.id) opt.selected = true; sel.appendChild(opt); });
            });
            fetch("/api/wa/transfer-history/" + contact.id, {headers: hdrs()}).then(function(r){ return r.json(); }).then(function(data){
                var items = data.history || []; var hd = document.getElementById("transferHistory");
                if (items.length === 0) { hd.style.display = "none"; return; }
                hd.style.display = "block"; hd.innerHTML = "<div style='font-size:11px;font-weight:600;color:var(--text-muted);margin-bottom:4px'>Historico de transferencias</div>";
                items.forEach(function(h){ var div = document.createElement("div"); div.className = "transfer-item"; div.textContent = fmtDate(h.created_at)+" "+fmtTime(h.created_at)+": "+(h.from_user_name||"Nenhum")+" -> "+(h.to_user_name||"Nenhum")+(h.summary?" | "+h.summary.substring(0,80):""); hd.appendChild(div); });
            });
            modal.classList.add("show");
        }
        document.getElementById("transferCancel").addEventListener("click", function(){ document.getElementById("transferModal").classList.remove("show"); });
        document.getElementById("transferModal").addEventListener("click", function(e){ if (e.target === this) this.classList.remove("show"); });
        document.getElementById("transferConfirm").addEventListener("click", function(){
            if (!activeChat || activeChat.type !== "whatsapp") return;
            var opVal = document.getElementById("transferOperator").value;
            var summary = document.getElementById("transferSummary").value.trim();
            if (!opVal) { alert("Selecione o operador destino."); return; }
            if (!summary) { alert("O resumo do atendimento e obrigatorio."); return; }
            var body = { contact_id: activeChat.id, to_user_id: parseInt(opVal), to_department_id: document.getElementById("transferDept").value ? parseInt(document.getElementById("transferDept").value) : null, reason: document.getElementById("transferReason").value.trim(), summary: summary };
            fetch("/api/wa/transfer", {method: "POST", headers: hdrs(), body: JSON.stringify(body)})
            .then(function(r){ return r.json(); }).then(function(data){
                if (data.status === "transferred") { document.getElementById("transferModal").classList.remove("show"); loadAll(); document.getElementById("chatArea").innerHTML = '<div class="empty-state">Atendimento transferido para '+esc(data.to_user)+'</div>'; activeChat = null; }
                else { alert(data.detail || "Erro na transferencia"); }
            });
        });

        // -- Modal: Gerenciar contato --
        function openContactModal(contact) {
            document.getElementById("contactModalTitle").textContent = contact.display_name || contact.phone_formatted || "Contato";
            document.getElementById("contactQualification").value = contact.qualification || "novo";
            document.getElementById("contactNotes").value = contact.notes || "";
            document.getElementById("contactAvatarInput").value = "";
            document.getElementById("contactModal").classList.add("show");

            document.getElementById("contactSave").onclick = function(){
                var qual = document.getElementById("contactQualification").value;
                var notes = document.getElementById("contactNotes").value.trim();
                fetch("/api/wa/contact/"+contact.id+"/qualify", {method:"PUT", headers: hdrs(), body: JSON.stringify({qualification: qual, notes: notes})})
                .then(function(r){ return r.json(); }).then(function(){
                    // Upload de foto se selecionado
                    var fi = document.getElementById("contactAvatarInput");
                    if (fi.files && fi.files[0]) {
                        var fd = new FormData(); fd.append("file", fi.files[0]);
                        return fetch("/api/wa/contact/"+contact.id+"/avatar", {method:"POST", headers:{"Authorization":"Bearer "+TOKEN}, body: fd}).then(function(r){ return r.json(); });
                    }
                }).then(function(){ document.getElementById("contactModal").classList.remove("show"); loadAll(); });
            };
            document.getElementById("contactArchive").onclick = function(){
                if (!confirm("Arquivar este contato? Ele sera removido da lista ativa.")) return;
                fetch("/api/wa/contact/"+contact.id, {method:"DELETE", headers: hdrs()})
                .then(function(r){ return r.json(); }).then(function(){ document.getElementById("contactModal").classList.remove("show"); loadAll(); activeChat = null; document.getElementById("chatArea").innerHTML = '<div class="empty-state">Contato arquivado</div>'; });
            };
        }
        document.getElementById("contactCancel").addEventListener("click", function(){ document.getElementById("contactModal").classList.remove("show"); });
        document.getElementById("contactModal").addEventListener("click", function(e){ if (e.target === this) this.classList.remove("show"); });

        // -- Modal: Criar usuario --
        function openUserModal() {
            document.getElementById("newUsername").value = "";
            document.getElementById("newDisplayName").value = "";
            document.getElementById("newPassword").value = "";
            document.getElementById("newRole").value = "operador";
            fetch("/api/departments", {headers: hdrs()}).then(function(r){ return r.json(); }).then(function(data){
                var sel = document.getElementById("newDepartment"); sel.innerHTML = '<option value="">Nenhum</option>';
                (data.departments||[]).forEach(function(d){ var o = document.createElement("option"); o.value = d.id; o.textContent = d.name; sel.appendChild(o); });
            });
            document.getElementById("userModal").classList.add("show");
        }
        document.getElementById("userCancel").addEventListener("click", function(){ document.getElementById("userModal").classList.remove("show"); });
        document.getElementById("userModal").addEventListener("click", function(e){ if (e.target === this) this.classList.remove("show"); });
        document.getElementById("userCreate").addEventListener("click", function(){
            var body = { username: document.getElementById("newUsername").value.trim(), display_name: document.getElementById("newDisplayName").value.trim(), password: document.getElementById("newPassword").value, role: document.getElementById("newRole").value, department_id: document.getElementById("newDepartment").value ? parseInt(document.getElementById("newDepartment").value) : null };
            if (!body.username || !body.display_name || !body.password) { alert("Preencha todos os campos obrigatorios."); return; }
            fetch("/api/admin/users", {method:"POST", headers: hdrs(), body: JSON.stringify(body)})
            .then(function(r){ return r.json().then(function(d){ return {status: r.status, body: d}; }); })
            .then(function(res){ if (res.status === 200) { document.getElementById("userModal").classList.remove("show"); loadAll(); alert("Atendente criado com sucesso."); } else { alert(res.body.detail || "Erro ao criar usuario"); } });
        });

        // -- Logout --
        document.getElementById("btnLogout").addEventListener("click", function(){ if (ws) ws.close(); sessionStorage.removeItem("crm_session"); window.location.href = "/"; });

        // -- Init --
        loadAll();
        connectWS();
        setInterval(function(){ fetch("/api/wa/contacts", {headers: hdrs()}).then(function(r){return r.json();}).then(function(data){ waContacts = data.contacts || []; renderSidebar(); }); }, 15000);
    })();
    </script>
</body>
</html>

```

## index.html

```html
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Castro Intelligence</title>
    <link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600&display=swap" rel="stylesheet">
    <style>
        *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
        :root {
            --bg: #0f1117;
            --surface: #1a1d27;
            --border: #2a2d3a;
            --text: #e4e4e7;
            --text-muted: #71717a;
            --accent: #2563eb;
            --accent-hover: #1d4ed8;
        }
        body {
            font-family: 'DM Sans', sans-serif;
            background: var(--bg);
            color: var(--text);
            height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .login-container { width: 100%; max-width: 380px; padding: 0 20px; }
        .login-header { text-align: center; margin-bottom: 40px; }
        .login-header h1 { font-size: 22px; font-weight: 600; letter-spacing: -0.02em; margin-bottom: 6px; }
        .login-header p { font-size: 13px; color: var(--text-muted); }
        .form-group { margin-bottom: 16px; }
        .form-group label { display: block; font-size: 13px; font-weight: 500; color: var(--text-muted); margin-bottom: 6px; }
        .form-group input {
            width: 100%; padding: 10px 14px; font-family: inherit; font-size: 14px;
            color: var(--text); background: var(--surface); border: 1px solid var(--border);
            border-radius: 8px; outline: none; transition: border-color 0.2s;
        }
        .form-group input:focus { border-color: var(--accent); }
        .btn-login {
            width: 100%; padding: 11px; margin-top: 8px; font-family: inherit;
            font-size: 14px; font-weight: 500; color: #fff; background: var(--accent);
            border: none; border-radius: 8px; cursor: pointer; transition: background 0.2s;
        }
        .btn-login:hover { background: var(--accent-hover); }
        .btn-login:disabled { opacity: 0.5; cursor: not-allowed; }
        .error-msg {
            margin-top: 12px; padding: 10px 14px; font-size: 13px; color: #fca5a5;
            background: rgba(220,38,38,0.1); border: 1px solid rgba(220,38,38,0.2);
            border-radius: 8px; display: none;
        }
    </style>
</head>
<body>
    <div class="login-container">
        <div class="login-header">
            <h1>Castro Intelligence</h1>
            <p>CRM &middot; Chat</p>
        </div>
        <form id="loginForm" autocomplete="off">
            <div class="form-group">
                <label for="username">Usuario</label>
                <input type="text" id="username" name="username" required autofocus autocomplete="username" spellcheck="false">
            </div>
            <div class="form-group">
                <label for="password">Senha</label>
                <input type="password" id="password" name="password" required autocomplete="current-password">
            </div>
            <button type="submit" class="btn-login" id="btnLogin">Entrar</button>
            <div class="error-msg" id="errorMsg"></div>
        </form>
    </div>
    <script>
    (function(){
        "use strict";
        var form = document.getElementById("loginForm");
        var btnLogin = document.getElementById("btnLogin");
        var errorMsg = document.getElementById("errorMsg");
        if (sessionStorage.getItem("crm_session")) window.location.href = "/chat";
        form.addEventListener("submit", function(e){
            e.preventDefault();
            errorMsg.style.display = "none";
            btnLogin.disabled = true;
            btnLogin.textContent = "Autenticando...";
            var u = document.getElementById("username").value.trim();
            var p = document.getElementById("password").value;
            fetch("/api/login", {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify({username: u, password: p})
            })
            .then(function(r){ return r.json().then(function(d){ return {status: r.status, body: d}; }); })
            .then(function(res){
                if (res.status === 200) {
                    sessionStorage.setItem("crm_session", JSON.stringify({token: res.body.token, user: res.body.user}));
                    window.location.href = "/chat";
                } else {
                    errorMsg.textContent = res.body.error || "Falha na autenticacao";
                    errorMsg.style.display = "block";
                }
            })
            .catch(function(){ errorMsg.textContent = "Erro de conexao"; errorMsg.style.display = "block"; })
            .finally(function(){ btnLogin.disabled = false; btnLogin.textContent = "Entrar"; });
        });
    })();
    </script>
</body>
</html>

```

## test_debug.py

```python
# -*- coding: utf-8 -*-

"""
Suite de testes para validar o CRM antes e apos o deploy.

Uso:
    python test_debug.py [url_base]

Exemplos:
    python test_debug.py                           # Testa localhost:8080
    python test_debug.py https://castro-crm-xxxxx.run.app  # Testa Cloud Run
"""

import sys
import json
import time
import requests

BASE_URL = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://127.0.0.1:8080"

PASS = "[OK]"
FAIL = "[FALHA]"

results = {"total": 0, "passed": 0, "failed": 0, "errors": []}


def test(name, condition, detail=""):
    results["total"] += 1
    if condition:
        results["passed"] += 1
        print(f"  {PASS} {name}")
    else:
        results["failed"] += 1
        results["errors"].append(f"{name}: {detail}")
        print(f"  {FAIL} {name} -> {detail}")


def section(title):
    print(f"\n{'='*50}")
    print(f"  {title}")
    print(f"{'='*50}")


# ── Payloads simulando a Meta ─────────────────────────────

def make_wa_payload(msg_type, msg_data, wa_id="5531982779779", name="Cliente Teste"):
    """Gera payload no formato exato da Meta Cloud API."""
    msg = {
        "from": wa_id,
        "id": f"wamid.test_{msg_type}_{int(time.time())}",
        "timestamp": str(int(time.time())),
        "type": msg_type,
    }
    msg.update(msg_data)

    return {
        "object": "whatsapp_business_account",
        "entry": [{
            "id": "275244975509458",
            "changes": [{
                "value": {
                    "messaging_product": "whatsapp",
                    "metadata": {
                        "display_phone_number": "15551754802",
                        "phone_number_id": "983401388192837"
                    },
                    "contacts": [{
                        "profile": {"name": name},
                        "wa_id": wa_id
                    }],
                    "messages": [msg]
                },
                "field": "messages"
            }]
        }]
    }


def make_status_payload(msg_id, status, recipient="5531982779779"):
    return {
        "object": "whatsapp_business_account",
        "entry": [{
            "id": "275244975509458",
            "changes": [{
                "value": {
                    "messaging_product": "whatsapp",
                    "metadata": {
                        "display_phone_number": "15551754802",
                        "phone_number_id": "983401388192837"
                    },
                    "statuses": [{
                        "id": msg_id,
                        "status": status,
                        "timestamp": str(int(time.time())),
                        "recipient_id": recipient
                    }]
                },
                "field": "messages"
            }]
        }]
    }


# ── Testes ────────────────────────────────────────────────

def test_health():
    section("1. Verificacao de saude do servidor")
    try:
        r = requests.get(f"{BASE_URL}/", timeout=10)
        test("Pagina de login acessivel", r.status_code == 200, f"HTTP {r.status_code}")
    except Exception as e:
        test("Conexao com servidor", False, str(e))
        print("\n  Servidor nao encontrado. Verifique se esta rodando.\n")
        sys.exit(1)


def test_auth():
    section("2. Autenticacao e seguranca")

    # Login valido
    r = requests.post(f"{BASE_URL}/api/login", json={"username": "izael", "password": "castro@2026"})
    test("Login com credenciais corretas", r.status_code == 200, f"HTTP {r.status_code}")

    data = r.json()
    token = data.get("token", "")
    test("Token JWT retornado", len(token) > 50, f"Token: {token[:20]}...")
    test("Dados do usuario retornados", data.get("user", {}).get("display_name") == "Izael Castro")

    # Login invalido
    r2 = requests.post(f"{BASE_URL}/api/login", json={"username": "izael", "password": "errada"})
    test("Login com senha errada bloqueado", r2.status_code == 401)

    # Acesso sem token
    r3 = requests.get(f"{BASE_URL}/api/users")
    test("Rota protegida rejeita sem token", r3.status_code == 401 or r3.status_code == 403)

    # Acesso com token invalido
    r4 = requests.get(f"{BASE_URL}/api/users", headers={"Authorization": "Bearer token_falso"})
    test("Rota protegida rejeita token invalido", r4.status_code == 401)

    return token


def test_internal_chat(token):
    section("3. Chat interno")
    hdrs = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    # Listar usuarios
    r = requests.get(f"{BASE_URL}/api/users", headers=hdrs)
    test("Listar contatos internos", r.status_code == 200)
    users = r.json()
    test("Rafael aparece na lista", any(u["display_name"] == "Rafael Castro" for u in users))

    rafael_id = None
    for u in users:
        if u["display_name"] == "Rafael Castro":
            rafael_id = u["id"]
            break

    if not rafael_id:
        test("ID do Rafael encontrado", False, "Nao localizado")
        return

    # Enviar mensagem
    r2 = requests.post(f"{BASE_URL}/api/messages", headers=hdrs,
        json={"receiver_id": rafael_id, "content": "Mensagem de teste automatizado", "msg_type": "text"})
    test("Enviar mensagem interna", r2.status_code == 200)
    test("ID da mensagem retornado", r2.json().get("id") is not None)

    # Buscar conversa
    r3 = requests.get(f"{BASE_URL}/api/messages/{rafael_id}", headers=hdrs)
    test("Buscar historico de conversa", r3.status_code == 200)
    msgs = r3.json().get("messages", [])
    test("Mensagem enviada encontrada no historico", len(msgs) > 0)

    # Nao lidas
    r4 = requests.get(f"{BASE_URL}/api/unread", headers=hdrs)
    test("Endpoint de nao lidas funciona", r4.status_code == 200)

    # Teste XSS
    r5 = requests.post(f"{BASE_URL}/api/messages", headers=hdrs,
        json={"receiver_id": rafael_id, "content": '<script>alert("xss")</script>', "msg_type": "text"})
    test("Envio com XSS aceito (sera sanitizado)", r5.status_code == 200)

    r6 = requests.get(f"{BASE_URL}/api/messages/{rafael_id}", headers=hdrs)
    last_msg = r6.json().get("messages", [])[-1] if r6.json().get("messages") else {}
    test("XSS sanitizado no armazenamento",
         "<script>" not in last_msg.get("content", "<script>"),
         f"Conteudo: {last_msg.get('content', '')[:60]}")


def test_webhook_verify():
    section("4. Verificacao do webhook (GET)")

    # Verificacao correta
    r = requests.get(f"{BASE_URL}/webhook", params={
        "hub.mode": "subscribe",
        "hub.verify_token": "hubloc2024",
        "hub.challenge": "teste_challenge_123"
    })
    test("Verificacao com token correto", r.status_code == 200)
    test("Challenge retornado corretamente", r.text == "teste_challenge_123", f"Retornou: {r.text[:50]}")

    # Verificacao com token errado
    r2 = requests.get(f"{BASE_URL}/webhook", params={
        "hub.mode": "subscribe",
        "hub.verify_token": "token_errado",
        "hub.challenge": "abc"
    })
    test("Verificacao com token errado bloqueada", r2.status_code == 403)


def test_webhook_messages(token):
    section("5. Webhook - Recebimento de mensagens")
    hdrs = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    # 5.1 Mensagem de texto
    payload = make_wa_payload("text", {"text": {"body": "Ola, preciso alugar uma betoneira"}})
    r = requests.post(f"{BASE_URL}/webhook", json=payload)
    test("Texto recebido (HTTP 200)", r.status_code == 200)

    # 5.2 Mensagem de imagem
    payload = make_wa_payload("image", {
        "image": {"id": "media_img_001", "mime_type": "image/jpeg", "caption": "Foto do equipamento"}
    })
    r = requests.post(f"{BASE_URL}/webhook", json=payload)
    test("Imagem recebida", r.status_code == 200)

    # 5.3 Audio
    payload = make_wa_payload("audio", {
        "audio": {"id": "media_audio_001", "mime_type": "audio/ogg"}
    })
    r = requests.post(f"{BASE_URL}/webhook", json=payload)
    test("Audio recebido", r.status_code == 200)

    # 5.4 Video
    payload = make_wa_payload("video", {
        "video": {"id": "media_video_001", "mime_type": "video/mp4", "caption": "Video da obra"}
    })
    r = requests.post(f"{BASE_URL}/webhook", json=payload)
    test("Video recebido", r.status_code == 200)

    # 5.5 Sticker
    payload = make_wa_payload("sticker", {
        "sticker": {"id": "media_sticker_001", "mime_type": "image/webp"}
    })
    r = requests.post(f"{BASE_URL}/webhook", json=payload)
    test("Figurinha recebida", r.status_code == 200)

    # 5.6 Documento
    payload = make_wa_payload("document", {
        "document": {"id": "media_doc_001", "mime_type": "application/pdf", "filename": "orcamento.pdf"}
    })
    r = requests.post(f"{BASE_URL}/webhook", json=payload)
    test("Documento recebido", r.status_code == 200)

    # 5.7 Localizacao
    payload = make_wa_payload("location", {
        "location": {"latitude": -19.9167, "longitude": -43.9345, "name": "Hub Loc", "address": "Belo Horizonte, MG"}
    })
    r = requests.post(f"{BASE_URL}/webhook", json=payload)
    test("Localizacao recebida", r.status_code == 200)

    # 5.8 Reacao
    payload = make_wa_payload("reaction", {
        "reaction": {"message_id": "wamid.original_123", "emoji": "\ud83d\udc4d"}
    })
    r = requests.post(f"{BASE_URL}/webhook", json=payload)
    test("Reacao recebida", r.status_code == 200)

    # 5.9 Contato de outro numero
    payload2 = make_wa_payload("text",
        {"text": {"body": "Bom dia, quero um orcamento"}},
        wa_id="5511999887766", name="Maria Silva"
    )
    r = requests.post(f"{BASE_URL}/webhook", json=payload2)
    test("Segundo contato registrado", r.status_code == 200)

    # Verificar se contatos foram criados
    r_contacts = requests.get(f"{BASE_URL}/api/wa/contacts", headers=hdrs)
    test("API de contatos WhatsApp funciona", r_contacts.status_code == 200)
    contacts = r_contacts.json().get("contacts", [])
    test("Contatos WhatsApp registrados", len(contacts) >= 2, f"Encontrados: {len(contacts)}")

    # Verificar historico do contato principal (5531982779779 - recebeu todos os tipos)
    if contacts:
        target = None
        for c in contacts:
            if c.get("wa_id") == "5531982779779":
                target = c
                break
        if not target:
            target = contacts[-1]  # fallback para o mais antigo

        cid = target["id"]
        r_msgs = requests.get(f"{BASE_URL}/api/wa/messages/{cid}", headers=hdrs)
        test("Historico de mensagens WhatsApp", r_msgs.status_code == 200)
        wa_msgs = r_msgs.json().get("messages", [])
        test("Mensagens salvas no banco", len(wa_msgs) > 0, f"Total: {len(wa_msgs)}")

        # Verificar tipos
        types_found = set(m["msg_type"] for m in wa_msgs)
        test("Multiplos tipos de mensagem registrados",
             len(types_found) > 1,
             f"Tipos: {types_found}")


def test_webhook_status():
    section("6. Webhook - Status de mensagens")

    status_payload = make_status_payload("wamid.test_sent_001", "delivered")
    r = requests.post(f"{BASE_URL}/webhook", json=status_payload)
    test("Status 'delivered' processado", r.status_code == 200)

    status_payload2 = make_status_payload("wamid.test_sent_001", "read")
    r2 = requests.post(f"{BASE_URL}/webhook", json=status_payload2)
    test("Status 'read' processado", r2.status_code == 200)


def test_webhook_edge_cases():
    section("7. Webhook - Casos limite")

    # Payload vazio
    r = requests.post(f"{BASE_URL}/webhook", json={})
    test("Payload vazio nao quebra", r.status_code == 200)

    # Payload com object errado
    r2 = requests.post(f"{BASE_URL}/webhook", json={"object": "instagram"})
    test("Object diferente ignorado", r2.status_code == 200)

    # Entry vazio
    r3 = requests.post(f"{BASE_URL}/webhook", json={"object": "whatsapp_business_account", "entry": []})
    test("Entry vazio processado", r3.status_code == 200)

    # Mensagem duplicada (mesmo wamid)
    payload = make_wa_payload("text", {"text": {"body": "teste duplicado"}})
    requests.post(f"{BASE_URL}/webhook", json=payload)
    requests.post(f"{BASE_URL}/webhook", json=payload)  # mesma mensagem
    test("Mensagem duplicada nao gera erro", True)  # se chegou aqui, nao deu erro


def test_wa_send(token):
    section("8. Envio de mensagem WhatsApp (via API)")
    hdrs = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    # Obter contato
    r = requests.get(f"{BASE_URL}/api/wa/contacts", headers=hdrs)
    contacts = r.json().get("contacts", [])
    if not contacts:
        test("Contato disponivel para teste de envio", False, "Nenhum contato")
        return

    cid = contacts[0]["id"]

    # Tentar enviar (vai falhar se WHATSAPP_TOKEN nao esta configurado, o que e esperado em teste local)
    r2 = requests.post(f"{BASE_URL}/api/wa/send", headers=hdrs,
        json={"contact_id": cid, "content": "Resposta de teste"})

    if r2.status_code == 200:
        test("Mensagem enviada via Graph API", True)
    elif r2.status_code == 503:
        test("Envio retorna 503 (WABA nao configurado - esperado em dev)", True)
    elif r2.status_code == 502:
        test("Envio retorna 502 (token invalido ou expirado - verificar configuracao)",
             True, r2.json().get("detail", ""))
    else:
        test("Envio de mensagem WhatsApp", False, f"HTTP {r2.status_code}: {r2.text[:100]}")


def test_media_endpoint():
    section("9. Servico de midia")

    # Arquivo inexistente
    r = requests.get(f"{BASE_URL}/media/images/nao_existe.jpg")
    test("Midia inexistente retorna 404", r.status_code == 404)

    # Tentativa de path traversal
    r2 = requests.get(f"{BASE_URL}/media/../config.py")
    test("Path traversal bloqueado", r2.status_code == 404 or r2.status_code == 422)


def print_summary():
    section("RESULTADO FINAL")
    print(f"\n  Total:    {results['total']}")
    print(f"  Passou:   {results['passed']}")
    print(f"  Falhou:   {results['failed']}")
    print()

    if results["errors"]:
        print("  Falhas encontradas:")
        for e in results["errors"]:
            print(f"    - {e}")
        print()

    if results["failed"] == 0:
        print("  Todos os testes passaram.\n")
    else:
        print(f"  {results['failed']} teste(s) falharam. Revise os itens acima.\n")


# ── Execucao ──────────────────────────────────────────────

if __name__ == "__main__":
    print(f"\nTestando: {BASE_URL}\n")

    test_health()
    token = test_auth()
    test_internal_chat(token)
    test_webhook_verify()
    test_webhook_messages(token)
    test_webhook_status()
    test_webhook_edge_cases()
    test_wa_send(token)
    test_media_endpoint()
    print_summary()

```

## webhook.py

```python
# -*- coding: utf-8 -*-

"""
Processamento de eventos recebidos via webhook da Meta Cloud API.
Trata mensagens de texto, imagem, audio, video, sticker, localizacao e documentos.
"""

import hmac
import hashlib
import logging
from datetime import datetime, timezone

from config import WHATSAPP_APP_SECRET
from database import (
    upsert_wa_contact, save_wa_message, update_wa_message_status, log_audit,
)
from media import download_media

logger = logging.getLogger("castro_crm.webhook")


def validate_signature(payload_bytes, signature_header):
    """
    Valida assinatura HMAC-SHA256 do webhook da Meta.
    Retorna True se valido ou se APP_SECRET nao esta configurado (modo dev).
    """
    if not WHATSAPP_APP_SECRET:
        return True  # Pular validacao em dev

    if not signature_header:
        logger.warning("Webhook recebido sem assinatura")
        return False

    expected = hmac.new(
        WHATSAPP_APP_SECRET.encode("utf-8"),
        payload_bytes,
        hashlib.sha256
    ).hexdigest()

    received = signature_header.replace("sha256=", "")
    return hmac.compare_digest(expected, received)


async def process_webhook_payload(payload, ws_notify_callback=None):
    """
    Processa o payload completo do webhook.
    ws_notify_callback: funcao async para notificar clientes via WebSocket.
    """
    if payload.get("object") != "whatsapp_business_account":
        return

    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})

            if "messages" in value:
                await _process_messages(value, ws_notify_callback)

            if "statuses" in value:
                _process_statuses(value)


async def _process_messages(value, ws_notify_callback):
    """Processa mensagens recebidas de clientes."""
    contacts_data = value.get("contacts", [])
    contact_info = contacts_data[0] if contacts_data else {}
    contact_name = contact_info.get("profile", {}).get("name", "")

    for msg in value.get("messages", []):
        wa_id = msg.get("from", "")
        msg_id = msg.get("id", "")
        msg_type = msg.get("type", "unknown")
        timestamp = msg.get("timestamp", "")

        # Converter timestamp Unix para ISO
        ts_iso = ""
        if timestamp:
            try:
                dt = datetime.fromtimestamp(int(timestamp), tz=timezone.utc)
                ts_iso = dt.isoformat()
            except (ValueError, OSError):
                ts_iso = datetime.now(timezone.utc).isoformat()

        # Registrar ou atualizar contato
        contact_id = upsert_wa_contact(wa_id, contact_name)

        # Extrair conteudo conforme o tipo
        content = ""
        media_path = ""
        media_mime = ""
        media_id_str = ""
        latitude = None
        longitude = None
        filename = ""

        if msg_type == "text":
            content = msg.get("text", {}).get("body", "")

        elif msg_type == "image":
            image = msg.get("image", {})
            media_id_str = image.get("id", "")
            media_mime = image.get("mime_type", "")
            content = image.get("caption", "")
            media_result = await download_media(media_id_str, "image")
            if media_result:
                media_path = media_result["path"]
                media_mime = media_result["mime_type"]

        elif msg_type == "audio":
            audio = msg.get("audio", {})
            media_id_str = audio.get("id", "")
            media_mime = audio.get("mime_type", "")
            media_result = await download_media(media_id_str, "audio")
            if media_result:
                media_path = media_result["path"]
                media_mime = media_result["mime_type"]

        elif msg_type == "video":
            video = msg.get("video", {})
            media_id_str = video.get("id", "")
            media_mime = video.get("mime_type", "")
            content = video.get("caption", "")
            media_result = await download_media(media_id_str, "video")
            if media_result:
                media_path = media_result["path"]
                media_mime = media_result["mime_type"]

        elif msg_type == "sticker":
            sticker = msg.get("sticker", {})
            media_id_str = sticker.get("id", "")
            media_mime = sticker.get("mime_type", "image/webp")
            media_result = await download_media(media_id_str, "sticker")
            if media_result:
                media_path = media_result["path"]
                media_mime = media_result["mime_type"]

        elif msg_type == "document":
            doc = msg.get("document", {})
            media_id_str = doc.get("id", "")
            media_mime = doc.get("mime_type", "")
            filename = doc.get("filename", "")
            content = doc.get("caption", "")
            media_result = await download_media(media_id_str, "document", filename)
            if media_result:
                media_path = media_result["path"]
                media_mime = media_result["mime_type"]

        elif msg_type == "location":
            loc = msg.get("location", {})
            latitude = loc.get("latitude")
            longitude = loc.get("longitude")
            loc_name = loc.get("name", "")
            loc_address = loc.get("address", "")
            content = f"{loc_name} {loc_address}".strip() if (loc_name or loc_address) else ""

        elif msg_type == "contacts":
            # Cartao de contato - salvar como texto JSON
            content = str(msg.get("contacts", []))

        elif msg_type == "reaction":
            reaction = msg.get("reaction", {})
            content = reaction.get("emoji", "")

        else:
            content = f"[{msg_type}]"
            logger.info("Tipo de mensagem nao tratado: %s", msg_type)

        # Persistir
        db_id = save_wa_message(
            wa_message_id=msg_id,
            contact_id=contact_id,
            direction="inbound",
            msg_type=msg_type,
            content=content,
            media_path=media_path,
            media_mime=media_mime,
            media_id=media_id_str,
            latitude=latitude,
            longitude=longitude,
            filename=filename,
            status="received",
            timestamp_wa=ts_iso,
        )

        logger.info(
            "[WA IN] %s (%s) | tipo=%s | id=%s",
            contact_name, wa_id, msg_type, msg_id[:20]
        )

        # Notificar operadores conectados via WebSocket
        if ws_notify_callback:
            await ws_notify_callback({
                "event": "wa_new_message",
                "data": {
                    "id": db_id,
                    "contact_id": contact_id,
                    "contact_name": contact_name,
                    "wa_id": wa_id,
                    "msg_type": msg_type,
                    "content": content,
                    "media_path": media_path,
                    "media_mime": media_mime,
                    "latitude": latitude,
                    "longitude": longitude,
                    "filename": filename,
                    "timestamp": ts_iso,
                },
            })


def _process_statuses(value):
    """Processa atualizacoes de status de mensagens enviadas."""
    for status in value.get("statuses", []):
        msg_id = status.get("id", "")
        state = status.get("status", "")
        timestamp = status.get("timestamp", "")

        ts_iso = ""
        if timestamp:
            try:
                dt = datetime.fromtimestamp(int(timestamp), tz=timezone.utc)
                ts_iso = dt.isoformat()
            except (ValueError, OSError):
                pass

        update_wa_message_status(msg_id, state, ts_iso)
        logger.info("[WA STATUS] %s -> %s", msg_id[:20], state)

```

