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

# Импорт модулей
from config import VK_TOKEN, GROUP_ID, DB_PATH, FOUNDER_ID, ROLES, BLACKLIST_TYPES
from leadership import init_leadership_db
from chat_commands import handle_chat_command, handle_new_chat_commands, process_user_message
from blacklist import ensure_tables, get_expired_entries, remove_blacklist_record

app = Flask(__name__)

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

# Инициализация VK API
try:
    vk_session = vk_api.VkApi(token=VK_TOKEN)
    vk = vk_session.get_api()
    print("✅ VK API подключено успешно!")
except Exception as e:
    print(f"❌ Ошибка подключения к VK API: {e}")
    exit()

# Инициализация всех компонентов
init_db()
init_leadership_db()
ensure_tables()

# Временное хранилище для пошаговых действий
user_states = {}

# Глобальные переменные для мутов и режима тишины
active_mutes = {}
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
                
                # Очистка истекших мутов
                current_time = datetime.now()
                expired_users = []
                for user_id, mute_data in active_mutes.items():
                    if mute_data['until'] <= current_time:
                        expired_users.append(user_id)
                for user_id in expired_users:
                    del active_mutes[user_id]
                
                time.sleep(30)  # Проверка каждые 30 секунд
            except Exception as e:
                try:
                    self.log("Scheduler error:", str(e))
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
    except Exception as e:
        print(f"❌ Ошибка отправки сообщения: {e}")

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
    except Exception as e:
        print(f"❌ Ошибка отправки в чат: {e}")

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
        print(f"❌ Ошибка получения информации о пользователе {user_id}: {e}")
    return f"[id{user_id}|Пользователь]"

# Webhook обработчики
@app.route('/webhook', methods=['POST', 'GET'])
def webhook():
    """Основной обработчик вебхуков от VK"""
    if request.method == 'GET':
        # Подтверждение сервера
        confirmation_token = request.args.get('hub.challenge')
        if confirmation_token:
            return confirmation_token
        return 'OK'
    
    # Обработка POST запросов (события)
    data = request.get_json()
    
    if not data:
        return 'ok'
    
    print(f"📨 Получено событие: {data}")
    
    # Обработка типа события
    event_type = data.get('type')
    
    if event_type == 'confirmation':
        # Возвращаем токен подтверждения из config.py
        from config import CONFIRMATION_TOKEN
        return CONFIRMATION_TOKEN if CONFIRMATION_TOKEN else 'confirmation_token'
    
    elif event_type == 'message_new':
        message = data['object']['message']
        process_webhook_message(message)
    
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
        
        print(f"📨 Сообщение от {user_id} в {'чате' if is_chat else 'ЛС'}: {text}")
        
        # Добавляем пользователя в базу
        add_user(user_id)
        
        # ОБРАБОТКА КОМАНД В ЧАТАХ
        if is_chat:
            # Сначала проверяем муты и режим тишины для ВСЕХ сообщений
            if not process_webhook_user_message(msg):
                return  # Сообщение удалено (мут или режим тишины)
            
            # Затем обрабатываем команды
            if text.startswith('/') or text.lower() == 'кто':
                handle_new_chat_commands(vk, msg, user_id, text, peer_id)
                return
            
            # Старые команды с ! (для обратной совместимости)
            if text.startswith('!'):
                handle_chat_command(vk, msg, user_id, text, peer_id)
                return
        
        # ОБРАБОТКА ЛИЧНЫХ СООБЩЕНИЙ
        if is_dm:
            process_dm_message(user_id, text, msg)
            
    except Exception as e:
        print(f"❌ Ошибка обработки сообщения: {e}")
        import traceback
        traceback.print_exc()

def process_webhook_user_message(msg):
    """Аналог process_user_message для вебхуков"""
    try:
        peer_id = msg.get('peer_id', 0)
        user_id = msg.get('from_id', 0)
        message_id = msg.get('id', 0)
        text = msg.get('text', '')
        
        # Проверяем что это беседа
        if peer_id < 2000000000:
            return True
            
        # Игнорируем команды бота и сообщения от админов
        if text.startswith('/') or text.startswith('!') or text.lower() == 'кто':
            return True
            
        # Проверяем права пользователя (админы игнорируют ограничения)
        if has_permission(user_id, 2):  # Модераторы и выше могут писать всегда
            return True
            
        # 1. Сначала проверяем режим тишины
        if peer_id in silence_mode and silence_mode[peer_id]:
            print(f"🔇 Удаляем сообщение в режиме тишины от пользователя {user_id}")
            delete_user_message(peer_id, message_id, user_id)
            send_chat_message(peer_id, 
                            f"🔇 Сообщение удалено. Режим тишины включен.\n"
                            f"Писать могут только администраторы.")
            return False
            
        # 2. Затем проверяем мут
        mute_data = check_user_mute(user_id, peer_id)
        if mute_data:
            print(f"🔇 Пользователь {user_id} в муте, удаляем сообщение")
            delete_user_message(peer_id, message_id, user_id)
            
            # Отправляем уведомление о муте
            time_left = mute_data['until'] - datetime.now()
            minutes_left = max(1, int(time_left.total_seconds() / 60))
            
            send_chat_message(peer_id,
                            f"🔇 Вы в муте! Осталось: {minutes_left} мин.\n"
                            f"До: {mute_data['until'].strftime('%H:%M:%S')}")
            return False
            
        return True
        
    except Exception as e:
        print(f"❌ Ошибка в process_webhook_user_message: {e}")
        return True

def delete_user_message(peer_id, message_id, user_id):
    """Удаляет сообщение пользователя"""
    try:
        vk.messages.delete(
            message_ids=message_id,
            delete_for_all=True,
            peer_id=peer_id
        )
        print(f"✅ Сообщение {message_id} от пользователя {user_id} удалено")
        return True
    except Exception as e:
        print(f"❌ Ошибка удаления сообщения {message_id}: {e}")
        return False

def check_user_mute(user_id, peer_id):
    """Проверяет, находится ли пользователь в муте"""
    if user_id in active_mutes:
        mute_data = active_mutes[user_id]
        # Проверяем что мут в этом чате и время не истекло
        if mute_data['peer_id'] == peer_id and mute_data['until'] > datetime.now():
            return mute_data
    
    return None

def process_dm_message(user_id, text, msg):
    """Обрабатывает личные сообщения"""
    current_state = user_states.get(user_id, {})
    
    # Обработка пошаговых действий (упрощенная версия)
    if current_state.get('action'):
        send_message(user_id, "❌ Действие отменено из-за перехода на webhooks")
        user_states.pop(user_id, None)
        return
    
    # Обработка обычных команд
    text_lower = text.lower()
    
    if text_lower in ['начать', 'start', '/start']:
        send_message(user_id, 
                   "👋 Привет! Я профессиональный бот-модератор\n\n"
                   "📋 Основные функции:\n"
                   "• Управление черных списков\n"
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
                       f"{'• Назначение ролей' if has_permission(user_id, 4) else ''}")
        else:
            send_message(user_id, "❌ У вас нет доступа к админ-панели")
    
    else:
        send_message(user_id, "🤔 Не понимаю команду. Напиши 'помощь' для списка команд.")

# Запуск Flask приложения
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
    print(f"✅ Webhook бот запущен на порту {port}")