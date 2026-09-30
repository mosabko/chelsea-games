import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

BASE_DIR   = Path(__file__).parent.parent.parent
DATA_DIR   = BASE_DIR / "data"
DB_FILE    = DATA_DIR / "chelsea_games.db"
SCHEMA_SQL = Path(__file__).parent / "schema.sql"

_local = threading.local()

def _get_connection():
    if not hasattr(_local, "conn") or _local.conn is None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(DB_FILE), check_same_thread=False, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        _local.conn = conn
    return _local.conn

@contextmanager
def get_db():
    conn = _get_connection()
    try:
        yield conn
    except Exception:
        conn.rollback()
        raise

@contextmanager
def transaction():
    conn = _get_connection()
    in_tx = conn.in_transaction
    if not in_tx:
        conn.execute("BEGIN")
    try:
        yield conn
        if not in_tx:
            conn.execute("COMMIT")
    except Exception:
        if not in_tx:
            conn.execute("ROLLBACK")
        raise

def initialize_db():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    schema = SCHEMA_SQL.read_text(encoding="utf-8")
    conn = _get_connection()
    conn.executescript(schema)
    print(f"✅ Database ready: {DB_FILE}")

def fetchone(sql, params=()):
    with get_db() as conn:
        row = conn.execute(sql, params).fetchone()
        return dict(row) if row else None

def fetchall(sql, params=()):
    with get_db() as conn:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]

def execute(sql, params=()):
    with get_db() as conn:
        return conn.execute(sql, params)
