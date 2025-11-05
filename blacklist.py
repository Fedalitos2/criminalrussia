# blacklist.py
import sqlite3
from datetime import datetime, timedelta
from typing import Optional, List, Tuple
from config import DB_PATH

# Типы ЧС: ЧСП, ЧСА, ЧСЛ, ЧСЗ

def ensure_tables():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS blacklist (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        vk_id INTEGER,
        nickname TEXT,
        type TEXT,
        reason TEXT,
        added_by INTEGER,
        expire_at TEXT
    )""")
    conn.commit()
    conn.close()

def add_blacklist(vk_id: Optional[int], nickname: Optional[str], type_: str, added_by: int, days: int, reason: str=""):
    """
    Добавляет запись в ЧС. Можно передать либо vk_id либо nickname.
    expire_at хранится в ISO формате или NULL (если бессрочно).
    """
    expire_at = (datetime.utcnow() + timedelta(days=days)).isoformat() if days and days > 0 else None
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
    INSERT INTO blacklist (vk_id, nickname, type, reason, added_by, expire_at)
    VALUES (?, ?, ?, ?, ?, ?)
    """, (vk_id, nickname, type_, reason, added_by, expire_at))
    conn.commit()
    conn.close()
    return True

def remove_blacklist_by_id(vk_id: Optional[int], type_: str) -> bool:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("DELETE FROM blacklist WHERE vk_id = ? AND type = ?", (vk_id, type_))
    changed = cur.rowcount
    conn.commit()
    conn.close()
    return changed > 0

def remove_blacklist_record(record_id: int) -> bool:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("DELETE FROM blacklist WHERE id = ?", (record_id,))
    changed = cur.rowcount
    conn.commit()
    conn.close()
    return changed > 0

def list_blacklist(type_: Optional[str]=None) -> List[Tuple]:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    if type_:
        cur.execute("SELECT id, vk_id, nickname, type, reason, added_by, expire_at FROM blacklist WHERE type = ? ORDER BY expire_at IS NULL, expire_at", (type_,))
    else:
        cur.execute("SELECT id, vk_id, nickname, type, reason, added_by, expire_at FROM blacklist ORDER BY type, expire_at IS NULL, expire_at")
    rows = cur.fetchall()
    conn.close()
    return rows

def check_blacklist_by_vk(vk_id: int) -> List[Tuple]:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT id, vk_id, nickname, type, reason, added_by, expire_at FROM blacklist WHERE vk_id = ?", (vk_id,))
    rows = cur.fetchall()
    conn.close()
    return rows

def check_blacklist_by_nick(nickname: str) -> List[Tuple]:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT id, vk_id, nickname, type, reason, added_by, expire_at FROM blacklist WHERE nickname = ?", (nickname,))
    rows = cur.fetchall()
    conn.close()
    return rows

def get_expired_entries() -> List[Tuple]:
    """Возвращает записи, у которых expire_at не NULL и time < now."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT id, vk_id, nickname, type, reason, added_by, expire_at FROM blacklist WHERE expire_at IS NOT NULL")
    rows = cur.fetchall()
    conn.close()
    expired = []
    now = datetime.utcnow()
    for r in rows:
        try:
            exp = datetime.fromisoformat(r[6])
            if exp <= now:
                expired.append(r)
        except Exception:
            continue
    return expired

def remove_blacklist_by_nickname(nickname: str, type_: str) -> bool:
    """Удаляет запись из ЧС по нику и типу"""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("DELETE FROM blacklist WHERE nickname = ? AND type = ?", (nickname, type_))
    changed = cur.rowcount
    conn.commit()
    conn.close()
    return changed > 0
