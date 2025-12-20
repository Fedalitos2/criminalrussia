import random
import re
from datetime import datetime

def get_random_id():
    return random.randint(0, 2**31)

def parse_user_id(raw_input):
    if not raw_input:
        return None

    raw_input = raw_input.strip()

    if raw_input.startswith("@"):
        raw_input = raw_input[1:]

    match = re.search(r"(?:https?://)?(?:vk\.com/)?(?P<username>id\d+|club\d+|public\d+|[a-zA-Z0-9_.]+)", raw_input)
    if match:
        return match.group("username")

    return raw_input

def format_blacklist_info(info, vk, admin_id):
    user = vk.users.get(user_ids=info[0])[0]
    admin = vk.users.get(user_ids=admin_id)[0]
    return (f"🚫 Пользователь: [id{user['id']}|{user['first_name']} {user['last_name']}]\n"
            f"📄 Причина: {info[1]}\n"
            f"⏳ До: {info[2]}\n"
            f"🛡 Заблокировал: [id{admin_id}|{admin['first_name']} {admin['last_name']}]")

# Добавляем функцию для проверки главного администратора
def is_super_admin(user_id):
    # Вставьте сюда ваш VK ID
    SUPER_ADMIN_IDS = [709914900]  # Замените на ваш реальный VK ID
    return user_id in SUPER_ADMIN_IDS