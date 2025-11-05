from database import add_log, get_role
import sqlite3
from config import DB_PATH


# Проверка, имеет ли пользователь право модерировать
def can_moderate(vk_id: int) -> bool:
    role = get_role(vk_id)
    return role in ["founder", "admin", "moderator"]


def add_warning(target_id: int, moderator_id: int, reason: str = "Нарушение правил"):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT warnings, banned FROM users WHERE vk_id = ?", (target_id,))
    result = cursor.fetchone()

    if not result:
        conn.close()
        return "❌ Пользователь не найден в базе."

    warnings, banned = result
    if banned:
        conn.close()
        return "⚠️ Пользователь уже заблокирован."

    new_warnings = warnings + 1
    cursor.execute("UPDATE users SET warnings = ? WHERE vk_id = ?", (new_warnings, target_id))
    conn.commit()

    if new_warnings >= 3:
        cursor.execute("UPDATE users SET banned = 1 WHERE vk_id = ?", (target_id,))
        conn.commit()
        add_log(moderator_id, f"Заблокировал {target_id} (3 предупреждения)")
        msg = f"⛔ Пользователь {target_id} автоматически заблокирован (3 предупреждения)."
    else:
        add_log(moderator_id, f"Выдал предупреждение {target_id}: {reason}")
        msg = f"⚠️ Пользователь {target_id} получил предупреждение ({new_warnings}/3)."

    conn.close()
    return msg


def unban_user(target_id: int, moderator_id: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET banned = 0, warnings = 0 WHERE vk_id = ?", (target_id,))
    conn.commit()
    conn.close()
    add_log(moderator_id, f"Снял бан с пользователя {target_id}")
    return f"✅ Бан с пользователя {target_id} снят."


def check_status(target_id: int):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT role, warnings, banned FROM users WHERE vk_id = ?", (target_id,))
    result = cursor.fetchone()
    conn.close()

    if not result:
        return "❌ Пользователь не найден."

    role, warnings, banned = result
    status = "🚫 Заблокирован" if banned else "✅ Активен"
    return f"👤 ID: {target_id}\nРоль: {role}\nПредупреждения: {warnings}/3\nСтатус: {status}"
