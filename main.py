# main.py - профессиональная версия с системой ролей и кликабельными профилями
import vk_api
from vk_api.bot_longpoll import VkBotLongPoll, VkBotEventType
from vk_api.utils import get_random_id
from vk_api.keyboard import VkKeyboard, VkKeyboardColor
import sqlite3
import os
import json
from datetime import datetime, timedelta
from leadership import init_leadership_db
from chat_commands import handle_chat_command, handle_new_chat_commands, process_user_message

from config import VK_TOKEN, GROUP_ID, DB_PATH, FOUNDER_ID

print("🚀 Запуск VK-бота...")

# Добавляем константы которые отсутствуют в config.py
ROLES = {
    1: "Пользователь",
    2: "Модератор", 
    3: "Администратор",
    4: "Руководитель", 
    5: "Технический администратор"
}

BLACKLIST_TYPES = {
    "ЧСП": "Чёрный список проекта",
    "ЧСА": "Чёрный список администрации",
    "ЧСЛ": "Чёрный список лидеров",
    "ЧСЗ": "Чёрный список заместителей"
}

# Создаем папку data если её нет
os.makedirs("data", exist_ok=True)

# Инициализация базы данных
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Таблица пользователей с числовыми ролями
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vk_id INTEGER UNIQUE,
            first_name TEXT,
            last_name TEXT,
            role INTEGER DEFAULT 1,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Таблица черных списков
    c.execute('''
        CREATE TABLE IF NOT EXISTS blacklist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vk_id INTEGER,
            nickname TEXT,
            type TEXT,
            reason TEXT,
            added_by INTEGER,
            expire_at TEXT,
            added_date DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Добавляем основателя если нужно
    if FOUNDER_ID:
        c.execute("INSERT OR IGNORE INTO users (vk_id, role) VALUES (?, ?)", 
                 (FOUNDER_ID, 5))
    
    conn.commit()
    conn.close()
    print("✅ База данных инициализирована!")

init_db()
init_leadership_db()

# Инициализация VK API
try:
    vk_session = vk_api.VkApi(token=VK_TOKEN)
    vk = vk_session.get_api()
    longpoll = VkBotLongPoll(vk_session, GROUP_ID)
    print("✅ VK API подключено успешно!")
except Exception as e:
    print(f"❌ Ошибка подключения к VK API: {e}")
    exit()

# Временное хранилище для пошаговых действий
user_states = {}

def send_message(user_id, message, keyboard=None):
    """Отправляет сообщение пользователю"""
    try:
        params = {
            "user_id": user_id,
            "message": message,
            "random_id": get_random_id()
        }
        if keyboard:
            params["keyboard"] = keyboard
        vk.messages.send(**params)
    except Exception as e:
        print(f"❌ Ошибка отправки сообщения: {e}")

def add_user(vk_id):
    """Добавляет пользователя в базу"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO users (vk_id) VALUES (?)", (vk_id,))
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

def get_role_name(role_level):
    """Возвращает название роли по уровню"""
    return ROLES.get(role_level, "Пользователь")

def has_permission(user_id, required_level):
    """Проверяет, имеет ли пользователь достаточный уровень прав"""
    user_role = get_user_role(user_id)
    return user_role >= required_level

def create_admin_keyboard(user_id):
    """Создает клавиатуру админ-панели"""
    keyboard = VkKeyboard(one_time=False, inline=False)
    
    keyboard.add_button("📋 Чёрные списки", color=VkKeyboardColor.PRIMARY)
    keyboard.add_line()
    keyboard.add_button("➕ Добавить в ЧС", color=VkKeyboardColor.POSITIVE)
    keyboard.add_button("🗑 Удалить из ЧС", color=VkKeyboardColor.NEGATIVE)
    keyboard.add_line()
    keyboard.add_button("🔍 Проверить игрока", color=VkKeyboardColor.SECONDARY)
    keyboard.add_button("📊 Статистика", color=VkKeyboardColor.SECONDARY)
    
    # Добавляем кнопку управления ролями только для руководителей и выше
    if has_permission(user_id, 4):
        keyboard.add_line()
        keyboard.add_button("👥 Управление ролями", color=VkKeyboardColor.PRIMARY)
    
    keyboard.add_line()
    keyboard.add_button("🚪 Выйти", color=VkKeyboardColor.NEGATIVE)
    
    return keyboard.get_keyboard()

def create_blacklist_types_keyboard():
    """Создает клавиатуру выбора типа ЧС"""
    keyboard = VkKeyboard(one_time=False, inline=False)
    
    keyboard.add_button("ЧСП", color=VkKeyboardColor.PRIMARY)
    keyboard.add_button("ЧСА", color=VkKeyboardColor.PRIMARY)
    keyboard.add_line()
    keyboard.add_button("ЧСЛ", color=VkKeyboardColor.PRIMARY)
    keyboard.add_button("ЧСЗ", color=VkKeyboardColor.PRIMARY)
    keyboard.add_line()
    keyboard.add_button("🔙 Назад", color=VkKeyboardColor.NEGATIVE)
    
    return keyboard.get_keyboard()

def create_roles_management_keyboard():
    """Создает клавиатуру управления ролями"""
    keyboard = VkKeyboard(one_time=False, inline=False)
    
    keyboard.add_button("📋 Список администраторов", color=VkKeyboardColor.PRIMARY)
    keyboard.add_line()
    keyboard.add_button("👑 Назначить роль", color=VkKeyboardColor.POSITIVE)
    keyboard.add_button("❌ Снять роль", color=VkKeyboardColor.NEGATIVE)
    keyboard.add_line()
    keyboard.add_button("🔙 В панель", color=VkKeyboardColor.SECONDARY)
    
    return keyboard.get_keyboard()

def add_to_blacklist(nickname, bl_type, days, reason, added_by):
    """Добавляет запись в черный список"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    expire_at = (datetime.now() + timedelta(days=days)).isoformat() if days > 0 else None
    
    cursor.execute('''
        INSERT INTO blacklist (nickname, type, reason, added_by, expire_at)
        VALUES (?, ?, ?, ?, ?)
    ''', (nickname, bl_type, reason, added_by, expire_at))
    
    conn.commit()
    conn.close()
    return True

def get_blacklist(bl_type=None):
    """Получает записи из черного списка"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    if bl_type:
        cursor.execute('''
            SELECT nickname, type, reason, expire_at, added_date 
            FROM blacklist WHERE type = ? ORDER BY added_date DESC
        ''', (bl_type,))
    else:
        cursor.execute('''
            SELECT nickname, type, reason, expire_at, added_date 
            FROM blacklist ORDER BY added_date DESC
        ''')
    
    results = cursor.fetchall()
    conn.close()
    return results

def check_player_in_blacklist(nickname):
    """Проверяет игрока в черных списках"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT nickname, type, reason, expire_at 
        FROM blacklist WHERE nickname LIKE ?
    ''', (f"%{nickname}%",))
    
    results = cursor.fetchall()
    conn.close()
    return results

def remove_from_blacklist(nickname, bl_type):
    """Удаляет запись из черного списка"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        DELETE FROM blacklist WHERE nickname = ? AND type = ?
    ''', (nickname, bl_type))
    
    affected = cursor.rowcount
    conn.commit()
    conn.close()
    return affected > 0

def format_blacklist_entry(entry):
    """Форматирует запись черного списка для отображения"""
    nickname, bl_type, reason, expire_at, added_date = entry
    expire_text = f"до {datetime.fromisoformat(expire_at).strftime('%d.%m.%Y')}" if expire_at else "бессрочно"
    return f"👤 {nickname} | 🗂 {bl_type} | ⏰ {expire_text} | 💬 {reason}"

def set_user_role(target_id, role_level, moderator_id):
    """Назначает роль пользователю"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO users (vk_id, role) VALUES (?, ?)", 
                  (target_id, role_level))
    conn.commit()
    conn.close()
    
    # Логируем действие
    print(f"👑 Пользователь {moderator_id} назначил роль {role_level} пользователю {target_id}")

def remove_user_role(target_id, moderator_id):
    """Снимает роль пользователя (делает обычным пользователем)"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET role = 1 WHERE vk_id = ?", (target_id,))
    conn.commit()
    conn.close()
    
    # Логируем действие
    print(f"👑 Пользователь {moderator_id} снял роль с пользователя {target_id}")

def get_all_admins_with_names(vk_api):
    """Получает список всех администраторов с именами"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT vk_id, role FROM users WHERE role > 1 ORDER BY role DESC")
    admins = cursor.fetchall()
    conn.close()
    
    # Получаем информацию о пользователях из VK API
    if admins:
        user_ids = [str(admin[0]) for admin in admins]
        try:
            users_info = vk_api.users.get(user_ids=user_ids, fields="first_name,last_name")
            admins_with_names = []
            for admin in admins:
                admin_id, role_level = admin
                user_info = next((u for u in users_info if u['id'] == admin_id), None)
                if user_info:
                    first_name = user_info['first_name']
                    last_name = user_info['last_name']
                    admins_with_names.append((admin_id, role_level, first_name, last_name))
                else:
                    admins_with_names.append((admin_id, role_level, "Неизвестно", "Неизвестно"))
            return admins_with_names
        except Exception as e:
            print(f"❌ Ошибка получения информации о пользователях: {e}")
            # Возвращаем без имен если API не доступно
            return [(admin[0], admin[1], "", "") for admin in admins]
    return []

def get_user_stats(vk_api, user_id):
    """Получает статистику пользователя"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Основная информация
    cursor.execute("SELECT role, created_at FROM users WHERE vk_id = ?", (user_id,))
    user_data = cursor.fetchone()
    
    if not user_data:
        return None
    
    role_level, created_at = user_data
    role_name = get_role_name(role_level)
    
    # Статистика по ЧС
    cursor.execute("SELECT COUNT(*) FROM blacklist WHERE added_by = ?", (user_id,))
    blacklist_added = cursor.fetchone()[0]
    
    # Статистика по руководству
    cursor.execute("SELECT COUNT(*) FROM chat_leadership WHERE assigned_by = ?", (user_id,))
    leadership_assigned = cursor.fetchone()[0]
    
    conn.close()
    
    # Получаем информацию о пользователе
    try:
        user_info = vk_api.users.get(user_ids=[user_id], fields="first_name,last_name")[0]
        full_name = f"{user_info['first_name']} {user_info['last_name']}"
    except:
        full_name = "Неизвестно"
    
    return {
        'full_name': full_name,
        'role_name': role_name,
        'role_level': role_level,
        'created_at': created_at,
        'blacklist_added': blacklist_added,
        'leadership_assigned': leadership_assigned
    }

print("✅ Бот запущен и слушает события...")

# Главный цикл бота
for event in longpoll.listen():
    try:
        if event.type == VkBotEventType.MESSAGE_NEW:
            msg = event.object.message
            user_id = msg['from_id']
            text = msg.get('text', '').strip()
            peer_id = msg.get('peer_id', 0)
            
            # Определяем тип чата
            is_chat = peer_id > 2000000000  # Беседа
            is_dm = peer_id == user_id      # Личное сообщение
            
            print(f"📨 Сообщение от {user_id} в {'чате' if is_chat else 'ЛС'}: {text}")
            
            # Добавляем пользователя в базу
            add_user(user_id)
            
            # ОБРАБОТКА КОМАНД В ЧАТАХ
            if is_chat:
                # Сначала проверяем муты и режим тишины для ВСЕХ сообщений
                if not process_user_message(vk, msg):
                    continue  # Сообщение удалено (мут или режим тишины)
                
                # Затем обрабатываем команды
                if text.startswith('/') or text.lower() == 'кто':
                    handle_new_chat_commands(vk, msg, user_id, text, peer_id)
                    continue
                
                # Старые команды с ! (для обратной совместимости)
                if text.startswith('!'):
                    handle_chat_command(vk, msg, user_id, text, peer_id)
                    continue
            
            # ОБРАБОТКА ЛИЧНЫХ СООБЩЕНИЙ
            if is_dm:
                # Проверяем состояние пользователя (пошаговые действия)
                current_state = user_states.get(user_id, {})
                
                # Обработка пошаговых действий
                if current_state.get('action'):
                    action = current_state['action']
                    
                    # Добавление в ЧС
                    if action == 'adding_blacklist':
                        if current_state.get('step') == 1:  # Ожидаем ник
                            user_states[user_id] = {
                                'action': 'adding_blacklist',
                                'step': 2,
                                'nickname': text
                            }
                            send_message(user_id, "📂 Выберите тип черного списка:", 
                                       create_blacklist_types_keyboard())
                            
                        elif current_state.get('step') == 2:  # Ожидаем тип ЧС
                            if text.upper() in BLACKLIST_TYPES:
                                user_states[user_id] = {
                                    'action': 'adding_blacklist', 
                                    'step': 3,
                                    'nickname': current_state['nickname'],
                                    'bl_type': text.upper()
                                }
                                send_message(user_id, "⏳ Введите срок в днях (0 для бессрочно):")
                            else:
                                send_message(user_id, "❌ Неверный тип ЧС. Выберите из предложенных:")
                                
                        elif current_state.get('step') == 3:  # Ожидаем срок
                            try:
                                days = int(text)
                                if days < 0:
                                    raise ValueError
                                
                                user_states[user_id] = {
                                    'action': 'adding_blacklist',
                                    'step': 4, 
                                    'nickname': current_state['nickname'],
                                    'bl_type': current_state['bl_type'],
                                    'days': days
                                }
                                send_message(user_id, "📝 Введите причину:")
                            except ValueError:
                                send_message(user_id, "❌ Введите корректное число дней:")
                                
                        elif current_state.get('step') == 4:  # Ожидаем причину
                            nickname = current_state['nickname']
                            bl_type = current_state['bl_type']
                            days = current_state['days']
                            
                            add_to_blacklist(nickname, bl_type, days, text, user_id)
                            
                            days_text = "бессрочно" if days == 0 else f"{days} дней"
                            send_message(user_id, 
                                       f"✅ Игрок {nickname} добавлен в {bl_type}\n"
                                       f"⏰ Срок: {days_text}\n"
                                       f"📝 Причина: {text}",
                                       create_admin_keyboard(user_id))
                            
                            # Завершаем действие
                            user_states.pop(user_id, None)
                        continue
                    
                    # Удаление из ЧС
                    elif action == 'removing_blacklist':
                        if current_state.get('step') == 1:  # Ожидаем ник
                            user_states[user_id] = {
                                'action': 'removing_blacklist',
                                'step': 2, 
                                'nickname': text
                            }
                            send_message(user_id, "📂 Введите тип ЧС для удаления:")
                            
                        elif current_state.get('step') == 2:  # Ожидаем тип ЧС
                            nickname = current_state['nickname']
                            bl_type = text.upper()
                            
                            if remove_from_blacklist(nickname, bl_type):
                                send_message(user_id, f"✅ Игрок {nickname} удален из {bl_type}",
                                           create_admin_keyboard(user_id))
                            else:
                                send_message(user_id, f"❌ Игрок {nickname} не найден в {bl_type}",
                                           create_admin_keyboard(user_id))
                            
                            user_states.pop(user_id, None)
                        continue
                    
                    # Проверка игрока
                    elif action == 'checking_player':
                        nickname = text
                        results = check_player_in_blacklist(nickname)
                        
                        if results:
                            message = f"🔍 Результаты проверки {nickname}:\n\n"
                            for entry in results:
                                nickname, bl_type, reason, expire_at = entry
                                expire_text = f"до {datetime.fromisoformat(expire_at).strftime('%d.%m.%Y')}" if expire_at else "бессрочно"
                                message += f"🗂 {bl_type} | ⏰ {expire_text} | 💬 {reason}\n"
                        else:
                            message = f"✅ Игрок {nickname} не найден в черных списках"
                            
                        send_message(user_id, message, create_admin_keyboard(user_id))
                        user_states.pop(user_id, None)
                        continue
                    
                    # Назначение роли
                    elif action == 'assigning_role':
                        if current_state.get('step') == 1:  # Ожидаем ID пользователя
                            try:
                                target_id = int(text)
                                user_states[user_id] = {
                                    'action': 'assigning_role',
                                    'step': 2,
                                    'target_id': target_id
                                }
                                send_message(user_id, "🎯 Выберите роль для назначения:\n\n1 - Пользователь\n2 - Модератор\n3 - Администратор\n4 - Руководитель\n5 - Основатель")
                            except ValueError:
                                send_message(user_id, "❌ Введите корректный ID пользователя (только цифры):")
                        
                        elif current_state.get('step') == 2:  # Ожидаем уровень роли
                            try:
                                role_level = int(text)
                                if 1 <= role_level <= 5:
                                    target_id = current_state['target_id']
                                    
                                    # Проверяем права
                                    user_role = get_user_role(user_id)
                                    if role_level >= user_role:
                                        send_message(user_id, "❌ Вы не можете назначать роли выше или равные своей", create_roles_management_keyboard())
                                    else:
                                        set_user_role(target_id, role_level, user_id)
                                        role_name = get_role_name(role_level)
                                        send_message(user_id, f"✅ Пользователю [id{target_id}|пользователю] назначена роль: {role_name}", create_roles_management_keyboard())
                                else:
                                    send_message(user_id, "❌ Неверный уровень роли. Введите число от 1 до 5:")
                                    continue
                            except ValueError:
                                send_message(user_id, "❌ Введите корректный уровень роли (число от 1 до 5):")
                                continue
                            
                            user_states.pop(user_id, None)
                        continue
                    
                    # Снятие роли
                    elif action == 'removing_role':
                        if current_state.get('step') == 1:  # Ожидаем ID пользователя
                            try:
                                target_id = int(text)
                                remove_user_role(target_id, user_id)
                                send_message(user_id, f"✅ С пользователя [id{target_id}|пользователя] снята роль", create_roles_management_keyboard())
                                user_states.pop(user_id, None)
                            except ValueError:
                                send_message(user_id, "❌ Введите корректный ID пользователя (только цифры):")
                        continue
                
                # Обработка обычных команд в ЛС
                text_lower = text.lower()
                
                if text_lower in ['начать', 'start', '/start']:
                    send_message(user_id, 
                               "👋 Привет! Я профессиональный бот-модератор\n\n"
                               "📋 Основные функции:\n"
                               "• Управление черными списками\n"
                               "• Модерация чатов\n"
                               "• Режим тишины\n"
                               "• Система ролей\n\n"
                               "Напиши 'помощь' для списка команд.")
                
                elif text_lower == 'помощь':
                    help_text = "📋 Доступные команды:\n" \
                               "• начать - начать работу\n" \
                               "• помощь - это сообщение\n" \
                               "• моя роль - узнать свою роль\n" \
                               "• панель - админ-панель (если есть права)\n"
                    
                    if has_permission(user_id, 4):
                        help_text += "• роль <id> <уровень> - назначить роль\n" \
                                   "• роли - список администраторов\n"
                    
                    send_message(user_id, help_text)
                
                elif text_lower == 'моя роль':
                    role_level = get_user_role(user_id)
                    role_name = get_role_name(role_level)
                    send_message(user_id, f"🎭 Ваша роль: {role_name} (уровень {role_level})")
                
                elif text_lower == 'панель':
                    if has_permission(user_id, 2):  # Модератор и выше
                        role_name = get_role_name(get_user_role(user_id))
                        send_message(user_id, 
                                   f"🛠 Добро пожаловать в админ-панель, {role_name}!\n\n"
                                   f"📊 Ваши права:\n"
                                   f"{'• Мут/Кик/Бан' if has_permission(user_id, 2) else ''}\n"
                                   f"{'• Черные списки' if has_permission(user_id, 3) else ''}\n"
                                   f"{'• Назначение ролей' if has_permission(user_id, 4) else ''}",
                                   create_admin_keyboard(user_id))
                    else:
                        send_message(user_id, "❌ У вас нет доступа к админ-панели")
                
                # Команды управления ролями через текст
                elif text_lower.startswith('роль ') and has_permission(user_id, 4):
                    parts = text.split()
                    if len(parts) == 3:
                        try:
                            target_id = int(parts[1])
                            role_level = int(parts[2])
                            
                            if 1 <= role_level <= 5:
                                user_role = get_user_role(user_id)
                                if role_level >= user_role:
                                    send_message(user_id, "❌ Вы не можете назначать роли выше или равные своей")
                                else:
                                    set_user_role(target_id, role_level, user_id)
                                    role_name = get_role_name(role_level)
                                    send_message(user_id, f"✅ Пользователю [id{target_id}|пользователю] назначена роль: {role_name}")
                            else:
                                send_message(user_id, "❌ Неверный уровень роли. Используйте число от 1 до 5")
                                
                        except ValueError:
                            send_message(user_id, "❌ Неверный формат. Используйте: роль <user_id> <уровень_роли>")
                    else:
                        send_message(user_id, "❌ Формат команды: роль <user_id> <уровень_роли>")
                
                elif text_lower == 'роли' and has_permission(user_id, 4):
                    admins = get_all_admins_with_names(vk)
                    if admins:
                        message = "👥 Текущая команда администраторов:\n\n"
                        for admin in admins:
                            admin_id, role_level, first_name, last_name = admin
                            role_name = get_role_name(role_level)
                            
                            # Создаем кликабельную ссылку на профиль
                            profile_link = f"[id{admin_id}|{first_name} {last_name}]"
                            message += f"• {profile_link} - {role_name} (уровень {role_level})\n"
                    else:
                        message = "📭 Нет назначенных администраторов"
                    
                    send_message(user_id, message)
                
                # Обработка кнопок админ-панели
                elif text == '📋 Чёрные списки':
                    if has_permission(user_id, 3):  # Администратор и выше
                        blacklists = get_blacklist()
                        if blacklists:
                            message = "📋 Все черные списки:\n\n"
                            for entry in blacklists[:10]:  # Показываем первые 10 записей
                                message += format_blacklist_entry(entry) + "\n"
                            if len(blacklists) > 10:
                                message += f"\n... и еще {len(blacklists) - 10} записей"
                        else:
                            message = "📭 Черные списки пусты"
                        send_message(user_id, message)
                    else:
                        send_message(user_id, "❌ Недостаточно прав для просмотра ЧС")
                
                elif text == '➕ Добавить в ЧС':
                    if has_permission(user_id, 3):  # Администратор и выше
                        user_states[user_id] = {'action': 'adding_blacklist', 'step': 1}
                        send_message(user_id, "✏️ Введите ник игрока для добавления в ЧС:")
                    else:
                        send_message(user_id, "❌ Недостаточно прав для добавления в ЧС")
                
                elif text == '🗑 Удалить из ЧС':
                    if has_permission(user_id, 3):  # Администратор и выше
                        user_states[user_id] = {'action': 'removing_blacklist', 'step': 1}
                        send_message(user_id, "✏️ Введите ник игрока для удаления из ЧС:")
                    else:
                        send_message(user_id, "❌ Недостаточно прав для удаления из ЧС")
                
                elif text == '🔍 Проверить игрока':
                    if has_permission(user_id, 3):  # Администратор и выше
                        user_states[user_id] = {'action': 'checking_player', 'step': 1}
                        send_message(user_id, "🔍 Введите ник игрока для проверки:")
                    else:
                        send_message(user_id, "❌ Недостаточно прав для проверки игроков")
                
                elif text == '📊 Статистика':
                    if has_permission(user_id, 2):  # Модератор и выше
                        conn = sqlite3.connect(DB_PATH)
                        cursor = conn.cursor()
                        
                        # Статистика по ЧС
                        cursor.execute("SELECT COUNT(*) FROM blacklist")
                        total_blacklist = cursor.fetchone()[0]
                        
                        cursor.execute("SELECT COUNT(*) FROM blacklist WHERE expire_at IS NULL")
                        permanent_blacklist = cursor.fetchone()[0]
                        
                        cursor.execute("SELECT COUNT(*) FROM users")
                        total_users = cursor.fetchone()[0]
                        
                        # Статистика по ролям
                        cursor.execute("SELECT COUNT(*) FROM users WHERE role > 1")
                        total_admins = cursor.fetchone()[0]
                        
                        conn.close()
                        
                        send_message(user_id,
                                   f"📊 Статистика бота:\n\n"
                                   f"👥 Пользователей: {total_users}\n"
                                   f"👑 Администраторов: {total_admins}\n"
                                   f"📋 Записей в ЧС: {total_blacklist}\n"
                                   f"⏰ Бессрочных: {permanent_blacklist}")
                    else:
                        send_message(user_id, "❌ Недостаточно прав для просмотра статистики")
                
                elif text == '👥 Управление ролями':
                    if has_permission(user_id, 4):  # Руководитель и выше
                        send_message(user_id, 
                                   "👑 Управление ролями\n\n"
                                   "Выберите действие:",
                                   create_roles_management_keyboard())
                    else:
                        send_message(user_id, "❌ Недостаточно прав для управления ролями")
                
                # Обработка кнопок управления ролями
                elif text == '📋 Список администраторов':
                    if has_permission(user_id, 4):
                        admins = get_all_admins_with_names(vk)
                        if admins:
                            message = "👥 Текущая команда администраторов:\n\n"
                            for admin in admins:
                                admin_id, role_level, first_name, last_name = admin
                                role_name = get_role_name(role_level)
                                
                                # Создаем кликабельную ссылку на профиль
                                profile_link = f"[id{admin_id}|{first_name} {last_name}]"
                                message += f"• {profile_link} - {role_name} (уровень {role_level})\n"
                        else:
                            message = "📭 Нет назначенных администраторов"
                        
                        send_message(user_id, message, create_roles_management_keyboard())
                
                elif text == '👑 Назначить роль':
                    if has_permission(user_id, 4):
                        user_states[user_id] = {'action': 'assigning_role', 'step': 1}
                        send_message(user_id, "✏️ Введите ID пользователя для назначения роли:")
                
                elif text == '❌ Снять роль':
                    if has_permission(user_id, 4):
                        user_states[user_id] = {'action': 'removing_role', 'step': 1}
                        send_message(user_id, "✏️ Введите ID пользователя для снятия роли:")
                
                elif text == '🔙 В панель':
                    send_message(user_id, "🔙 Возврат в админ-панель", create_admin_keyboard(user_id))
                
                elif text == '🚪 Выйти':
                    user_states.pop(user_id, None)
                    send_message(user_id, "🚪 Вы вышли из админ-панели")
                
                # Обработка кнопок типов ЧС
                elif text.upper() in BLACKLIST_TYPES and current_state.get('action') == 'adding_blacklist':
                    # Эта логика уже обрабатывается в пошаговых действиях
                    pass
                
                elif text == '🔙 Назад':
                    if user_id in user_states:
                        user_states.pop(user_id)
                    send_message(user_id, "🔙 Возврат в главное меню", create_admin_keyboard(user_id))
                
                else:
                    if user_id in user_states:  # Если есть активное состояние, но команда не распознана
                        user_states.pop(user_id)
                        send_message(user_id, "❌ Действие отменено")
                    else:
                        send_message(user_id, "🤔 Не понимаю команду. Напиши 'помощь' для списка команд.")
                    
    except Exception as e:
        print(f"❌ Ошибка в главном цикле: {e}")
        import traceback
        traceback.print_exc()