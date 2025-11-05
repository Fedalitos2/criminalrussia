import sqlite3
from datetime import datetime
from config import DB_PATH


def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Создаём таблицу blacklist, если её нет
    c.execute("""
    CREATE TABLE IF NOT EXISTS blacklist (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nickname TEXT NOT NULL,
        type TEXT NOT NULL,
        until DATETIME NOT NULL,
        reason TEXT,
        added_by INTEGER,
        added_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
    """)

    # Создаём таблицу ролей
    c.execute("""
    CREATE TABLE IF NOT EXISTS roles (
        user_id INTEGER PRIMARY KEY,
        role TEXT DEFAULT 'user'
    )
    """)

    conn.commit()
    conn.close()

    print("✅ База данных инициализирована!")


def add_user(vk_id: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO users (vk_id) VALUES (?)", (vk_id,))
    conn.commit()
    conn.close()


def get_role(vk_id: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT role FROM users WHERE vk_id = ?", (vk_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else "user"


def set_role(vk_id: int, role: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET role = ? WHERE vk_id = ?", (role, vk_id))
    conn.commit()
    conn.close()


def add_log(vk_id: int, action: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO logs (vk_id, action, date) VALUES (?, ?, ?)",
        (vk_id, action, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    )
    conn.commit()
    conn.close()
    
def get_user_role(vk_id):
    """Получает уровень роли пользователя (число)"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT role FROM users WHERE vk_id = ?", (vk_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else 1

def has_permission(user_id, required_level):
    """Проверяет, имеет ли пользователь достаточный уровень прав"""
    user_role = get_user_role(user_id)
    return user_role >= required_level
