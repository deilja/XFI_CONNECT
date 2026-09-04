import sqlite3
from contextlib import contextmanager
from app.core.config import settings

@contextmanager
def connect_native():
    conn = sqlite3.connect(settings.xfi_connect_db_path, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA busy_timeout=10000')
    conn.execute('PRAGMA foreign_keys=ON')
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
