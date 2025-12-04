# main.py - Webhook версия
from flask import Flask, request, jsonify
import vk_api
from vk_api.utils import get_random_id
import sqlite3
import os
import json
from datetime import datetime, timedelta
import threading
import time
import logging
from vk_api.keyboard import VkKeyboard, VkKeyboardColor

# Импорт модулей
from config import VK_TOKEN, GROUP_ID, DB_PATH, FOUNDER_ID, ROLES, BLACKLIST_TYPES
from leadership import init_leadership_db
from chat_commands import handle_chat_command, handle_new_chat_commands, process_user_message
from blacklist import ensure_tables, get_expired_entries, remove_blacklist_record
from mute_system import mute_system 

app = Flask(__name__)

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

print("🚀 Запуск VK-бота на Webhooks...")

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
    
    # Таблица предупреждений (НОВАЯ ТАБЛИЦА)
    c.execute('''
        CREATE TABLE IF NOT EXISTS warnings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            moderator_id INTEGER,
            reason TEXT,
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
    
    # Таблица мутов (ДОБАВЬТЕ ЭТУ ТАБЛИЦУ)
    c.execute('''
        CREATE TABLE IF NOT EXISTS mutes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            peer_id INTEGER NOT NULL,
            duration_minutes INTEGER NOT NULL,
            moderator_id INTEGER NOT NULL,
            reason TEXT,
            muted_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            mute_until DATETIME NOT NULL,
            is_active BOOLEAN DEFAULT 1
        )
    ''')
    
     # Создаем индекс для быстрого поиска
    c.execute('CREATE INDEX IF NOT EXISTS idx_mutes_user_peer ON mutes(user_id, peer_id)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_mutes_until ON mutes(mute_until)')
    
    # Добавляем основателя если нужно
    if FOUNDER_ID:
        c.execute("INSERT OR IGNORE INTO users (vk_id, role) VALUES (?, ?)", 
                 (FOUNDER_ID, 5))
    
    conn.commit()
    conn.close()
    print("✅ База данных инициализирована!")

# Инициализация VK API - С ОТЛАДКОЙ
try:
    print(f"🔧 Инициализация VK API...")
    print(f"📋 Токен (первые 30 символов): {VK_TOKEN[:30]}...")
    print(f"📋 Длина токена: {len(VK_TOKEN)}")
    
    vk_session = vk_api.VkApi(
        token=VK_TOKEN,
        api_version="5.199"
    )
    
    vk = vk_session.get_api()
    
    # Пробная отправка сообщения для проверки
    print("🔧 Проверяем токен отправкой тестового сообщения...")
    try:
        test_result = vk.messages.send(
            user_id=FOUNDER_ID,
            message="🤖 Бот запущен и готов к работе!",
            random_id=get_random_id(),
            dont_parse_links=1
        )
        print(f"✅ Тестовое сообщение отправлено! ID: {test_result}")
    except Exception as test_e:
        print(f"⚠️ Не удалось отправить тестовое сообщение: {test_e}")
        print("⚠️ Но продолжаем работу...")
    
    print("✅ VK API подключено успешно!")
    
except Exception as e:
    print(f"❌ КРИТИЧЕСКАЯ ОШИБКА подключения к VK API: {e}")
    print(f"❌ Тип ошибки: {type(e).__name__}")
    import traceback
    traceback.print_exc()
    exit(1)

# Инициализация всех компонентов
init_db()
init_leadership_db()
ensure_tables()

# Временное хранилище для пошаговых действий
user_states = {}

# Глобальные переменные для мутов и режима тишины
silence_mode = {}

class Scheduler:
    def __init__(self, vk_api, log_fn=None):
        self.vk = vk_api.get_api()
        self.running = False
        self.thread = None
        self.log = log_fn or (lambda *a, **k: None)

    def start(self):
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()
        self.log("Scheduler started.")

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=1)

    def _loop(self):
        while self.running:
            try:
                # Очистка истекших записей ЧС
                expired = get_expired_entries()
                for rec in expired:
                    rec_id, vk_id, nickname, type_, reason, added_by, expire_at = rec
                    remove_blacklist_record(rec_id)
                    if added_by:
                        text = f"⏳ Запись из ЧС ({type_}) для {nickname or vk_id} удалена — срок истёк."
                        try:
                            self.vk.messages.send(user_id=added_by, message=text, random_id=get_random_id())
                        except Exception:
                            pass
                
                # УДАЛИТЕ ЭТОТ БЛОК - очистка мутов теперь в mute_system
                # Очистка истекших мутов
                # current_time = datetime.now()
                # expired_users = []
                # for user_id, mute_data in active_mutes.items():
                #     if mute_data['until'] <= current_time:
                #         expired_users.append(user_id)
                # for user_id in expired_users:
                #     del active_mutes[user_id]
                
                time.sleep(30)  # Проверка каждые 30 секунд
            except Exception as e:
                try:
                    self.log(f"Scheduler error: {e}")
                except Exception:
                    pass
                time.sleep(30)

# Запуск планировщика
scheduler = Scheduler(vk_session)
scheduler.start()

# Вспомогательные функции
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
        logger.info(f"✅ Сообщение отправлено пользователю {user_id}")
    except Exception as e:
        logger.error(f"❌ Ошибка отправки сообщения: {e}")

def send_chat_message(peer_id, message, reply_to=None):
    """Отправляет сообщение в чат"""
    try:
        params = {
            "peer_id": peer_id,
            "message": message,
            "random_id": get_random_id()
        }
        if reply_to:
            params["reply_to"] = reply_to
        vk.messages.send(**params)
        logger.info(f"✅ Сообщение отправлено в чат {peer_id}")
    except Exception as e:
        logger.error(f"❌ Ошибка отправки в чат: {e}")

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

def get_user_info(user_id):
    """Получает информацию о пользователе для упоминания"""
    try:
        users = vk.users.get(user_ids=user_id, fields="first_name,last_name")
        if users:
            user = users[0]
            return f"[id{user_id}|{user['first_name']} {user['last_name']}]"
    except Exception as e:
        logger.error(f"❌ Ошибка получения информации о пользователе {user_id}: {e}")
    return f"[id{user_id}|Пользователь]"

# Webhook обработчики
@app.route('/')
def home():
    """Корневой маршрут для проверки работы"""
    return '✅ VK Bot is running! Send messages to /webhook'

@app.route('/webhook', methods=['POST', 'GET'])
def webhook():
    """Основной обработчик вебхуков от VK"""
    logger.info(f"📨 Получен запрос: {request.method} {request.url}")
    
    if request.method == 'GET':
        # Подтверждение сервера
        confirmation_token = request.args.get('hub.challenge')
        logger.info(f"🔧 GET запрос от VK: {dict(request.args)}")
        
        if confirmation_token:
            logger.info("✅ Подтверждение вебхука получено")
            return confirmation_token
        return 'OK'
    
    # Обработка POST запросов (события)
    try:
        data = request.get_json()
    except Exception as e:
        logger.error(f"❌ Ошибка парсинга JSON: {e}")
        return 'ok'
    
    if not data:
        logger.warning("⚠️ Пустой JSON в запросе")
        return 'ok'
    
    logger.info(f"📨 Получено событие: {data}")
    
    # Обработка типа события
    event_type = data.get('type')
    logger.info(f"🔧 Тип события: {event_type}")
    
    if event_type == 'confirmation':
        logger.info("🔧 Запрос подтверждения вебхука")
        from config import CONFIRMATION_TOKEN
        token = CONFIRMATION_TOKEN if CONFIRMATION_TOKEN else 'confirmation_token'
        logger.info(f"🔧 Возвращаем токен: {token}")
        return token
    
    elif event_type == 'message_new':
        message = data['object']['message']
        logger.info(f"📨 Новое сообщение от {message.get('from_id')}: {message.get('text')}")
        process_webhook_message(message)  # Теперь эта функция определена
    
    else:
        logger.warning(f"⚠️ Неизвестный тип события: {event_type}")
    
    return 'ok'

def process_webhook_message(msg):
    """Обрабатывает сообщение из вебхука"""
    try:
        user_id = msg['from_id']
        text = msg.get('text', '').strip()
        peer_id = msg.get('peer_id', 0)
        message_id = msg.get('id', 0)
        
        # Определяем тип чата
        is_chat = peer_id > 2000000000  # Беседа
        is_dm = peer_id == user_id      # Личное сообщение
        
        logger.info(f"📨 Сообщение от {user_id} в {'чате' if is_chat else 'ЛС'}: {text}")
        
        # Добавляем пользователя в базу
        add_user(user_id)
        
        # ОБРАБОТКА КОМАНД В ЧАТАХ
        if is_chat:
            # Сначала проверяем муты и режим тишины для ВСЕХ сообщений
            if not process_webhook_user_message(msg):
                return  # Сообщение удалено (мут или режим тишины)
            
            # Затем обрабатываем команды
            if text.startswith('/') or text.lower() == 'кто':
                logger.info(f"🔧 Обрабатываем команду в чате: {text}")
                handle_new_chat_commands(vk, msg, user_id, text, peer_id)
                return
            
            # Старые команды с ! (для обратной совместимости)
            if text.startswith('!'):
                logger.info(f"🔧 Обрабатываем старую команду в чате: {text}")
                handle_chat_command(vk, msg, user_id, text, peer_id)
                return
            
            # Если это обычное сообщение (не команда), просто выходим
            # так как проверка на мут/тишину уже выполнена выше
            return
        
        # ОБРАБОТКА ЛИЧНЫХ СООБЩЕНИЙ
        if is_dm:
            logger.info(f"🔧 Обрабатываем ЛС: {text}")
            process_dm_message(user_id, text, msg)
            
    except Exception as e:
        logger.error(f"❌ Ошибка обработки сообщения: {e}")
        import traceback
        traceback.print_exc()



def create_welcome_keyboard():
    """Создает клавиатуру приветствия"""
    from vk_api.keyboard import VkKeyboard, VkKeyboardColor
    keyboard = VkKeyboard(one_time=True, inline=False)
    
    keyboard.add_button("📋 Команды", color=VkKeyboardColor.PRIMARY)
    keyboard.add_line()
    keyboard.add_button("👑 Моя роль", color=VkKeyboardColor.SECONDARY)
    keyboard.add_button("🛠 Панель", color=VkKeyboardColor.SECONDARY)
    keyboard.add_line()
    keyboard.add_button("❓ Помощь", color=VkKeyboardColor.SECONDARY)
    
    return keyboard.get_keyboard()

def create_commands_keyboard():
    """Создает клавиатуру с командами"""
    from vk_api.keyboard import VkKeyboard, VkKeyboardColor
    keyboard = VkKeyboard(one_time=False, inline=False)
    
    keyboard.add_button("🔙 Назад", color=VkKeyboardColor.NEGATIVE)
    keyboard.add_line()
    keyboard.add_button("👑 Моя роль", color=VkKeyboardColor.SECONDARY)
    keyboard.add_button("🛠 Панель", color=VkKeyboardColor.SECONDARY)
    keyboard.add_line()
    keyboard.add_button("❓ Помощь", color=VkKeyboardColor.SECONDARY)
    
    return keyboard.get_keyboard()

def process_dm_message(user_id, text, msg):
    """Обрабатывает личные сообщения"""
    current_state = user_states.get(user_id, {})
    
    # Обработка пошаговых действий для добавления в ЧС
    if current_state.get('action') == 'adding_blacklist':
        if current_state.get('step') == 1:  # Ожидаем ник
            user_states[user_id] = {
                'action': 'adding_blacklist',
                'step': 2,
                'nickname': text
            }
            keyboard = create_blacklist_types_keyboard()
            send_message(user_id, "📂 Выберите тип черного списка:", keyboard=keyboard)
            return
            
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
            return
                
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
            return
                
        elif current_state.get('step') == 4:  # Ожидаем причину
            nickname = current_state['nickname']
            bl_type = current_state['bl_type']
            days = current_state['days']
            
            # Добавляем в ЧС
            from blacklist import add_blacklist
            add_blacklist(None, nickname, bl_type, user_id, days, text)
            
            days_text = "бессрочно" if days == 0 else f"{days} дней"
            keyboard = create_admin_keyboard(user_id)
            send_message(user_id, 
                       f"✅ Игрок {nickname} добавлен в {bl_type}\n"
                       f"⏰ Срок: {days_text}\n"
                       f"📝 Причина: {text}",
                       keyboard=keyboard)
            
            # Завершаем действие
            user_states.pop(user_id, None)
        return
    
    # Обработка пошаговых действий для удаления из ЧС
    elif current_state.get('action') == 'removing_blacklist':
        if current_state.get('step') == 1:  # Ожидаем ник
            user_states[user_id] = {
                'action': 'removing_blacklist',
                'step': 2, 
                'nickname': text
            }
            send_message(user_id, "📂 Введите тип ЧС для удаления:")
            return
            
        elif current_state.get('step') == 2:  # Ожидаем тип ЧС
            nickname = current_state['nickname']
            bl_type = text.upper()
            
            from blacklist import remove_blacklist_by_nickname
            if remove_blacklist_by_nickname(nickname, bl_type):
                keyboard = create_admin_keyboard(user_id)
                send_message(user_id, f"✅ Игрок {nickname} удален из {bl_type}", keyboard=keyboard)
            else:
                keyboard = create_admin_keyboard(user_id)
                send_message(user_id, f"❌ Игрок {nickname} не найден в {bl_type}", keyboard=keyboard)
            
            user_states.pop(user_id, None)
        return

    # Обработка пошаговых действий для назначения роли
    elif current_state.get('action') == 'assigning_role':
        if current_state.get('step') == 1:  # Ожидаем ID пользователя
            try:
                target_id = int(text)
                user_states[user_id] = {
                    'action': 'assigning_role',
                    'step': 2,
                    'target_id': target_id
                }
                send_message(user_id, "🎯 Выберите роль для назначения:\n\n1 - Пользователь\n2 - Модератор\n3 - Администратор\n4 - Руководитель\n5 - Технический администратор")
            except ValueError:
                send_message(user_id, "❌ Введите корректный ID пользователя (только цифры):")
            return
        
        elif current_state.get('step') == 2:  # Ожидаем уровень роли
            try:
                role_level = int(text)
                if 1 <= role_level <= 5:
                    target_id = current_state['target_id']
                    
                    # Проверяем права
                    user_role = get_user_role(user_id)
                    if role_level >= user_role:
                        keyboard = create_roles_management_keyboard()
                        send_message(user_id, "❌ Вы не можете назначать роли выше или равные своей", keyboard=keyboard)
                    else:
                        set_user_role(target_id, role_level, user_id)
                        role_name = get_role_name(role_level)
                        keyboard = create_roles_management_keyboard()
                        target_info = get_user_info(target_id)
                        send_message(user_id, f"✅ Пользователю {target_info} назначена роль: {role_name}", keyboard=keyboard)
                else:
                    send_message(user_id, "❌ Неверный уровень роли. Введите число от 1 до 5:")
                    return
            except ValueError:
                send_message(user_id, "❌ Введите корректный уровень роли (число от 1 до 5):")
                return
            
            user_states.pop(user_id, None)
        return

    # Обработка пошаговых действий для снятия роли
    elif current_state.get('action') == 'removing_role':
        if current_state.get('step') == 1:  # Ожидаем ID пользователя
            try:
                target_id = int(text)
                remove_user_role(target_id, user_id)
                keyboard = create_roles_management_keyboard()
                target_info = get_user_info(target_id)
                send_message(user_id, f"✅ С пользователя {target_info} снята роль", keyboard=keyboard)
                user_states.pop(user_id, None)
            except ValueError:
                send_message(user_id, "❌ Введите корректный ID пользователя (только цифры):")
        return

    # Обработка обычных команд
    text_lower = text.lower()
    
    if text_lower in ['начать', 'start', '/start']:
        keyboard = create_welcome_keyboard()
        send_message(user_id, 
                   "👋 Привет! Я профессиональный бот-модератор\n\n"
                   "📋 Основные функции:\n"
                   "• Управление черных списков\n"
                   "• Модерация чатов\n"
                   "• Режим тишины\n"
                   "• Система ролей\n\n"
                   "Используй кнопки ниже для навигации:",
                   keyboard=keyboard)
        
    elif text == '📋 Команды':
        keyboard = create_commands_keyboard()
        help_text = "📋 Доступные команды:\n\n" \
                   "📊 Основные:\n" \
                   "• начать - начать работу\n" \
                   "• помощь - справка по командам\n" \
                   "• моя роль - узнать свою роль\n" \
                   "• панель - админ-панель\n\n" \
                   "⚙️ Админ-команды:\n" \
                   "• /mute @id время причина - мут\n" \
                   "• /kick @id причина - кик\n" \
                   "• /ban @id время причина - бан\n" \
                   "• /warn @id причина - предупреждение\n\n" \
                   "📈 Для модераторов: /help в чате"
        send_message(user_id, help_text, keyboard=keyboard)
    
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
            keyboard = create_admin_keyboard(user_id)
            send_message(user_id, 
                       f"🛠 Добро пожаловать в админ-панель, {role_name}!\n\n"
                       f"📊 Ваши права:\n"
                       f"{'• Мут/Кик/Бан' if has_permission(user_id, 2) else ''}\n"
                       f"{'• Черные списки' if has_permission(user_id, 3) else ''}\n"
                       f"{'• Назначение ролей' if has_permission(user_id, 4) else ''}",
                       keyboard=keyboard)
        else:
            send_message(user_id, "❌ У вас нет доступа к админ-панели")
    
    # Обработка кнопок админ-панели
    elif text == '📋 Чёрные списки':
        if has_permission(user_id, 3):
            show_blacklist_command(user_id)
        else:
            send_message(user_id, "❌ Недостаточно прав")
    
    elif text == '➕ Добавить в ЧС':
        if has_permission(user_id, 3):
            user_states[user_id] = {'action': 'adding_blacklist', 'step': 1}
            send_message(user_id, "✏️ Введите ник игрока для добавления в ЧС:")
        else:
            send_message(user_id, "❌ Недостаточно прав")
    
    elif text == '🗑 Удалить из ЧС':
        if has_permission(user_id, 3):
            user_states[user_id] = {'action': 'removing_blacklist', 'step': 1}
            send_message(user_id, "✏️ Введите ник игрока для удаления из ЧС:")
        else:
            send_message(user_id, "❌ Недостаточно прав")
    
    elif text == '📊 Статистика':
        if has_permission(user_id, 2):
            show_stats_command(user_id)
        else:
            send_message(user_id, "❌ Недостаточно прав")
    
    elif text == '👥 Управление ролями':
        if has_permission(user_id, 4):
            keyboard = create_roles_management_keyboard()
            send_message(user_id, "👑 Управление ролями\n\nВыберите действие:", keyboard=keyboard)
        else:
            send_message(user_id, "❌ Недостаточно прав")
    
    elif text == '📋 Список администраторов':
        if has_permission(user_id, 4):
            show_admins_list(user_id)
        else:
            send_message(user_id, "❌ Недостаточно прав")
    
    elif text == '👑 Назначить роль':
        if has_permission(user_id, 4):
            user_states[user_id] = {'action': 'assigning_role', 'step': 1}
            send_message(user_id, "✏️ Введите ID пользователя для назначения роли:")
        else:
            send_message(user_id, "❌ Недостаточно прав")
    
    elif text == '❌ Снять роль':
        if has_permission(user_id, 4):
            user_states[user_id] = {'action': 'removing_role', 'step': 1}
            send_message(user_id, "✏️ Введите ID пользователя для снятия роли:")
        else:
            send_message(user_id, "❌ Недостаточно прав")
    
    elif text == '🔙 В панель':
        keyboard = create_admin_keyboard(user_id)
        send_message(user_id, "🔙 Возврат в админ-панель", keyboard=keyboard)
    
    elif text == '🚪 Выйти':
        user_states.pop(user_id, None)
        send_message(user_id, "🚪 Вы вышли из админ-панели")
    
    else:
        send_message(user_id, "🤔 Не понимаю команду. Напиши 'помощь' для списка команд.")

def process_webhook_user_message(msg):
    """Проверяет все сообщения на муты и режим тишины - УДАЛЯЕТ сообщения"""
    try:
        peer_id = msg.get('peer_id', 0)
        user_id = msg.get('from_id', 0)
        message_id = msg.get('id', 0)
        text = msg.get('text', '')
        
        # Проверяем что это беседа
        if peer_id < 2000000000:
            return True
            
        logger.info(f"🔍 Проверка сообщения от {user_id} в чате {peer_id}: {text[:50]}...")
            
        # Игнорируем команды бота и сообщения от админов
        if text.startswith('/') or text.startswith('!') or text.lower() == 'кто':
            logger.info(f"🔧 Игнорируем команду бота")
            return True
            
        # Проверяем права пользователя (админы игнорируют ограничения)
        if has_permission(user_id, 2):  # Модераторы и выше могут писать всегда
            logger.info(f"👑 Администратор {user_id} может писать всегда")
            return True
            
        # 1. Сначала проверяем режим тишины
        if peer_id in silence_mode and silence_mode[peer_id]:
            logger.info(f"🔇 Режим тишины активен, удаляем сообщение от {user_id}")
            delete_user_message(peer_id, message_id, user_id)
            send_chat_message(peer_id, 
                            f"🔇 Сообщение удалено. Режим тишины включен.\n"
                            f"Писать могут только администраторы.")
            return False
            
        # 2. Затем проверяем мут - ВАЖНО: сначала удаляем, потом уведомляем
        mute_data = check_user_mute(user_id, peer_id)
        if mute_data:
            logger.info(f"🔇 Пользователь {user_id} в муте, немедленно удаляем сообщение")
            
            # СНАЧАЛА УДАЛЯЕМ СООБЩЕНИЕ
            delete_user_message(peer_id, message_id, user_id)
            
            # ПОТОМ отправляем уведомление (один раз в 30 секунд, чтобы не спамить)
            time_left = mute_data['until'] - datetime.now()
            minutes_left = max(1, int(time_left.total_seconds() / 60))
            
            # Проверяем, когда последний раз отправляли уведомление
            last_notify_key = f"mute_notify_{user_id}_{peer_id}"
            last_notify = getattr(msg, '_last_mute_notify', None)
            
            if not last_notify or (datetime.now() - last_notify).seconds > 30:
                send_chat_message(peer_id,
                                f"🔇 Вы в муте! Осталось: {minutes_left} мин.\n"
                                f"До: {mute_data['until'].strftime('%H:%M:%S')}")
                msg._last_mute_notify = datetime.now()
            
            return False
            
        logger.info(f"✅ Пользователь {user_id} может писать")
        return True
        
    except Exception as e:
        logger.error(f"❌ Ошибка в process_webhook_user_message: {e}")
        import traceback
        traceback.print_exc()
        return True

def delete_user_message(peer_id, message_id, user_id):
    """Удаляет сообщение пользователя"""
    try:
        vk.messages.delete(
            message_ids=message_id,
            delete_for_all=True,
            peer_id=peer_id
        )
        logger.info(f"✅ Сообщение {message_id} от пользователя {user_id} удалено")
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка удаления сообщения {message_id}: {e}")
        return False

def check_user_mute(user_id, peer_id):
    """Проверяет, находится ли пользователь в муте"""
    # Используем mute_system вместо active_mutes
    return mute_system.check_mute(user_id, peer_id)

def set_user_role(target_id, role_level, moderator_id):
    """Назначает роль пользователю"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO users (vk_id, role) VALUES (?, ?)", 
                  (target_id, role_level))
    conn.commit()
    conn.close()
    
    # Логируем действие
    logger.info(f"👑 Пользователь {moderator_id} назначил роль {role_level} пользователю {target_id}")

def remove_user_role(target_id, moderator_id):
    """Снимает роль пользователя (делает обычным пользователем)"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET role = 1 WHERE vk_id = ?", (target_id,))
    conn.commit()
    conn.close()
    
    # Логируем действие
    logger.info(f"👑 Пользователь {moderator_id} снял роль с пользователя {target_id}")
        
def create_admin_keyboard(user_id):
    """Создает клавиатуру админ-панели"""
    from vk_api.keyboard import VkKeyboard, VkKeyboardColor
    keyboard = VkKeyboard(one_time=False, inline=False)
    
    keyboard.add_button("📋 Чёрные списки", color=VkKeyboardColor.PRIMARY)
    keyboard.add_line()
    keyboard.add_button("➕ Добавить в ЧС", color=VkKeyboardColor.POSITIVE)
    keyboard.add_button("🗑 Удалить из ЧС", color=VkKeyboardColor.NEGATIVE)
    keyboard.add_line()
    keyboard.add_button("📊 Статистика", color=VkKeyboardColor.SECONDARY)
    
    if has_permission(user_id, 4):
        keyboard.add_line()
        keyboard.add_button("👥 Управление ролями", color=VkKeyboardColor.PRIMARY)
    
    keyboard.add_line()
    keyboard.add_button("🚪 Выйти", color=VkKeyboardColor.NEGATIVE)
    
    return keyboard.get_keyboard()

def create_roles_management_keyboard():
    """Создает клавиатуру управления ролями"""
    from vk_api.keyboard import VkKeyboard, VkKeyboardColor
    keyboard = VkKeyboard(one_time=False, inline=False)
    
    keyboard.add_button("📋 Список администраторов", color=VkKeyboardColor.PRIMARY)
    keyboard.add_line()
    keyboard.add_button("👑 Назначить роль", color=VkKeyboardColor.POSITIVE)
    keyboard.add_button("❌ Снять роль", color=VkKeyboardColor.NEGATIVE)
    keyboard.add_line()
    keyboard.add_button("🔙 В панель", color=VkKeyboardColor.SECONDARY)
    
    return keyboard.get_keyboard()

def show_blacklist_command(user_id):
    """Показывает черные списки"""
    from blacklist import list_blacklist
    blacklists = list_blacklist()
    
    if blacklists:
        message = "📋 Все черные списки:\n\n"
        for entry in blacklists[:10]:  # Показываем первые 10 записей
            id, vk_id, nickname, type_, reason, added_by, expire_at = entry
            expire_text = f"до {datetime.fromisoformat(expire_at).strftime('%d.%m.%Y')}" if expire_at else "бессрочно"
            message += f"👤 {nickname} | 🗂 {type_} | ⏰ {expire_text} | 💬 {reason}\n"
        
        if len(blacklists) > 10:
            message += f"\n... и еще {len(blacklists) - 10} записей"
    else:
        message = "📭 Черные списки пусты"
    
    send_message(user_id, message)
    
def create_blacklist_types_keyboard():
    """Создает клавиатуру выбора типа ЧС"""
    from vk_api.keyboard import VkKeyboard, VkKeyboardColor
    keyboard = VkKeyboard(one_time=False, inline=False)
    
    keyboard.add_button("ЧСП", color=VkKeyboardColor.PRIMARY)
    keyboard.add_button("ЧСА", color=VkKeyboardColor.PRIMARY)
    keyboard.add_line()
    keyboard.add_button("ЧСЛ", color=VkKeyboardColor.PRIMARY)
    keyboard.add_button("ЧСЗ", color=VkKeyboardColor.PRIMARY)
    keyboard.add_line()
    keyboard.add_button("🔙 Назад", color=VkKeyboardColor.NEGATIVE)
    
    return keyboard.get_keyboard()

def show_stats_command(user_id):
    """Показывает статистику"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("SELECT COUNT(*) FROM blacklist")
    total_blacklist = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM users WHERE role > 1")
    total_admins = cursor.fetchone()[0]
    
    conn.close()
    
    send_message(user_id,
                f"📊 Статистика бота:\n\n"
                f"👥 Пользователей: {total_users}\n"
                f"👑 Администраторов: {total_admins}\n"
                f"📋 Записей в ЧС: {total_blacklist}")
    
def add_warning(target_id, moderator_id, reason):
    """Добавляет предупреждение пользователю"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Добавляем предупреждение
    cursor.execute(
        "INSERT INTO warnings (user_id, moderator_id, reason) VALUES (?, ?, ?)",
        (target_id, moderator_id, reason)
    )
    
    # Получаем количество предупреждений
    cursor.execute("SELECT COUNT(*) FROM warnings WHERE user_id = ?", (target_id,))
    warning_count = cursor.fetchone()[0]
    
    conn.commit()
    conn.close()
    
    logger.info(f"⚠️ Пользователь {moderator_id} выдал предупреждение {target_id}. Всего: {warning_count}/3")
    
    # Если 3+ предупреждений - кикаем из всех чатов
    if warning_count >= 3:
        result = auto_kick_for_warnings(target_id, moderator_id)
        if result == "auto_kick":
            return "auto_kick"
    
    return warning_count

def auto_kick_for_warnings(target_id, moderator_id):
    """Автоматически кикает пользователя за 3+ предупреждений"""
    try:
        logger.info(f"🚨 Автоматический кик пользователя {target_id} за 3+ предупреждений")
        
        # Получаем информацию о пользователе
        target_info = get_user_info(target_id)
        
        # Получаем все беседы, где есть бот
        conversations = vk.messages.getConversations(filter="all", count=200)
        
        kicked_from = []
        
        for conv in conversations['items']:
            if conv['conversation']['peer']['type'] == 'chat':
                peer_id = conv['conversation']['peer']['local_id'] + 2000000000
                chat_id = conv['conversation']['peer']['local_id']
                
                try:
                    # Пробуем кикнуть пользователя из беседы
                    vk.messages.removeChatUser(
                        chat_id=chat_id,
                        member_id=target_id
                    )
                    kicked_from.append(chat_id)
                    logger.info(f"✅ Пользователь {target_id} кикнут из чата {chat_id}")
                    
                except Exception as e:
                    # Игнорируем ошибки (нет прав, пользователя нет в чате и т.д.)
                    logger.debug(f"⚠️ Не удалось кикнуть из чата {chat_id}: {e}")
        
        # Очищаем предупреждения после кика
        clear_warnings(target_id)
        
        logger.info(f"✅ Пользователь {target_id} автоматически кикнут из {len(kicked_from)} чатов за 3+ предупреждений")
        
        # Отправляем уведомление администраторам
        if kicked_from:
            notify_admins_about_auto_kick(target_id, target_info, len(kicked_from))
        
        return "auto_kick"
        
    except Exception as e:
        logger.error(f"❌ Ошибка автоматического кика: {e}")
        return "error"

def notify_admins_about_auto_kick(target_id, target_info, chat_count):
    """Уведомляет администраторов об автоматическом кике"""
    try:
        # Получаем список администраторов
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT vk_id FROM users WHERE role >= 2")  # Модераторы и выше
        admins = cursor.fetchall()
        conn.close()
        
        message = (f"🚨 АВТОМАТИЧЕСКИЙ КИК\n"
                  f"👤 Пользователь: {target_info}\n"
                  f"📊 Кикнут из {chat_count} чатов\n"
                  f"💬 Причина: 3+ предупреждений\n"
                  f"⏰ Время: {datetime.now().strftime('%H:%M:%S %d.%m.%Y')}")
        
        for admin in admins:
            admin_id = admin[0]
            try:
                send_message(admin_id, message)
            except Exception as e:
                logger.error(f"❌ Не удалось уведомить администратора {admin_id}: {e}")
                
    except Exception as e:
        logger.error(f"❌ Ошибка уведомления администраторов: {e}")

def get_warning_count(user_id):
    """Получает количество предупреждений пользователя"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM warnings WHERE user_id = ?", (user_id,))
    count = cursor.fetchone()[0]
    conn.close()
    return count

def get_warnings_history(user_id):
    """Получает историю предупреждений пользователя"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        SELECT w.reason, w.created_at, u.first_name, u.last_name 
        FROM warnings w
        LEFT JOIN users u ON w.moderator_id = u.vk_id
        WHERE w.user_id = ?
        ORDER BY w.created_at DESC
    ''', (user_id,))
    warnings = cursor.fetchall()
    conn.close()
    return warnings

def clear_warnings(user_id):
    """Очищает все предупреждения пользователя"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM warnings WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()
    logger.info(f"🔄 Очищены предупреждения пользователя {user_id}")

def auto_kick_for_warnings(target_id, moderator_id):
    """Автоматически кикает пользователя за 3+ предупреждений"""
    try:
        # Получаем все чаты где есть пользователь (нужно API для этого)
        # Пока просто логируем - в реальности нужно получить список чатов
        logger.info(f"🚨 Пользователь {target_id} имеет 3+ предупреждений - требуется кик")
        
        # Очищаем предупреждения после кика
        clear_warnings(target_id)
        
        return "auto_kick"
        
    except Exception as e:
        logger.error(f"❌ Ошибка автоматического кика: {e}")
        return "error"

def show_admins_list(user_id):
    """Показывает список администраторов с именами"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT vk_id, role FROM users WHERE role > 1 ORDER BY role DESC")
    admins = cursor.fetchall()
    conn.close()
    
    if admins:
        message = "👥 Текущая команда администраторов:\n\n"
        for admin in admins:
            admin_id, role_level = admin
            role_name = get_role_name(role_level)
            
            # Получаем информацию о пользователе с именем
            try:
                users = vk.users.get(user_ids=admin_id, fields="first_name,last_name")
                if users:
                    user = users[0]
                    user_info = f"[id{admin_id}|{user['first_name']} {user['last_name']}]"
                else:
                    user_info = f"[id{admin_id}|Пользователь]"
            except:
                user_info = f"[id{admin_id}|Пользователь]"
            
            message += f"• {user_info} - {role_name} (уровень {role_level})\n"
    else:
        message = "📭 Нет назначенных администраторов"
    
    send_message(user_id, message)
    
    
        
# Запуск Flask приложения
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    logger.info(f"🚀 Запуск Flask приложения на порту {port}")
    app.run(host='0.0.0.0', port=port, debug=False)