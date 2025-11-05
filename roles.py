# roles.py — система ролей VK-бота проекта Criminal Russia
import sqlite3
from config import DB_PATH, FOUNDER_ID

# ───────────────────────────────────────────────
# 🎯 СОЗДАНИЕ ТАБЛИЦЫ РОЛЕЙ
# ───────────────────────────────────────────────
def ensure_role_table():
    """Создаёт таблицу ролей и добавляет основателя"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Таблица ролей
    c.execute("""
        CREATE TABLE IF NOT EXISTS roles (
            user_id INTEGER PRIMARY KEY,
            role TEXT NOT NULL DEFAULT 'user',
            assigned_by INTEGER,
            assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Проверяем наличие основателя
    c.execute("SELECT user_id FROM roles WHERE user_id = ?", (FOUNDER_ID,))
    if not c.fetchone():
        c.execute("INSERT INTO roles (user_id, role) VALUES (?, 'founder')", (FOUNDER_ID,))
        print(f"👑 Добавлен Технический администратор (ID {FOUNDER_ID}) в таблицу ролей.")

    conn.commit()
    conn.close()


# ───────────────────────────────────────────────
# ⚙️ ОСНОВНЫЕ ФУНКЦИИ РОЛЕЙ
# ───────────────────────────────────────────────
def get_role(user_id: int) -> str:
    """Возвращает роль пользователя"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT role FROM roles WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else "user"


def set_role(user_id: int, role: str, assigned_by: int = None):
    """Назначает пользователю новую роль"""
    role = role.lower().strip()
    valid_roles = ["user", "leader", "admin", "founder"]
    if role not in valid_roles:
        raise ValueError(f"Недопустимая роль: {role}")

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Проверяем, есть ли запись
    c.execute("SELECT user_id FROM roles WHERE user_id = ?", (user_id,))
    if c.fetchone():
        c.execute("""
            UPDATE roles
            SET role = ?, assigned_by = ?, assigned_at = CURRENT_TIMESTAMP
            WHERE user_id = ?
        """, (role, assigned_by, user_id))
    else:
        c.execute("""
            INSERT INTO roles (user_id, role, assigned_by)
            VALUES (?, ?, ?)
        """, (user_id, role, assigned_by))

    conn.commit()
    conn.close()
    print(f"🔧 Роль пользователя {user_id} установлена: {role}")


def remove_role(user_id: int):
    """Сбрасывает роль пользователя до user"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE roles SET role = 'user' WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()
    print(f"♻️ Роль пользователя {user_id} сброшена до 'user'.")


def is_admin_or_above(user_id: int) -> bool:
    """Проверяет, является ли пользователь администратором или выше"""
    return get_role(user_id) in ("admin", "leader", "founder")


def list_roles() -> list:
    """Возвращает список всех пользователей с их ролями"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT user_id, role, assigned_by, assigned_at FROM roles ORDER BY assigned_at DESC")
    rows = c.fetchall()
    conn.close()
    return rows


# ───────────────────────────────────────────────
# 🧠 ТЕСТ (если файл запущен напрямую)
# ───────────────────────────────────────────────
if __name__ == "__main__":
    ensure_role_table()
    print("📋 Текущие роли:")
    for r in list_roles():
        print(f"👤 {r[0]} → {r[1]} (назначил {r[2]}, {r[3]})")
