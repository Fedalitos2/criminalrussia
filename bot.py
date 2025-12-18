# Arion Manager - система управления ЧС для SAMP/CRMP проектов
# Владелец: [id709914900|Основатель]
# Бот принадлежит вам

from db import *
from utils import *
from config import VK_TOKEN, CONFIRMATION_TOKEN, CALLBACK_SECRET, GROUP_ID

from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from flask import Flask, request
from vk_api.keyboard import VkKeyboard, VkKeyboardColor
from types import SimpleNamespace

import re
import sqlite3
import os
import time
import requests
import threading
import vk_api
import json
import random
import string

# Константы бота
BOT_NAME = "Arion Manager"
OWNER_ID = 709914900  # Ваш VK ID

# Глобальные переменные
muted_users = {}
mute_tracker = {}
active_report_replies = {}
active_personal_chats = {}
start_time = time.time()
total_requests = 0
total_commands = 0

# Инициализация
init_db()
vk_session = vk_api.VkApi(token=VK_TOKEN)
vk = vk_session.get_api()
app = Flask(__name__)
ANSWER_LOG_PATH = "answer_log.txt"

def send_message(peer_id, message, keyboard=None):
    vk.messages.send(
        peer_id=peer_id,
        message=message,
        random_id=random.randint(1, 10**9),
        keyboard=json.dumps(keyboard) if keyboard else None
    )

def get_stats():
    current_time = time.time()
    uptime_seconds = int(current_time - start_time)
    uptime_str = time.strftime('%H:%M:%S', time.gmtime(uptime_seconds))

    minutes = max(uptime_seconds / 60, 1)
    avg_requests = total_requests / minutes
    avg_commands = total_commands / minutes

    return {
        "uptime": uptime_str,
        "avg_requests": avg_requests,
        "avg_commands": avg_commands,
    }

def log_to_file(filename, message):
    with open(filename, "a", encoding="utf-8") as f:
        f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}\n")

def log_action(user_id: int, action: str, is_mod_action: bool = False):
    log_entry = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {action}\n"
    if is_mod_action:
        with open('moderators.log', 'a', encoding='utf-8') as f:
            f.write(log_entry)
    with open('alllogs.log', 'a', encoding='utf-8') as f:
        f.write(log_entry)
    print(log_entry.strip())

def auto_unban_loop():
    while True:
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        for row in get_all_banned_users():
            if row[2] != "PERMANENT" and row[2] <= now:
                remove_from_blacklist(row[0])
                name = get_user_info(row[0])
                msg = f"{name} автоматически разблокирован"
                log_to_file("autounban.log", msg)
                log_to_file("alllogs.log", msg)
        time.sleep(3 * 60 * 60)

def resolve_username(username):
    try:
        user = vk.users.get(user_ids=username)
        if user:
            return user[0]["id"]
        return None
    except vk_api.exceptions.ApiError:
        return None

def get_user_info(user_id):
    try:
        user = vk.users.get(user_ids=user_id)
        if user:
            return f"{user[0]['first_name']} {user[0]['last_name']}"
        return "Пользователь не найден"
    except Exception as e:
        print(f"[Ошибка get_user_info]: {e}")
        return "Не удалось получить информацию"

def get_today_answer_count():
    try:
        now = datetime.now()
        count = 0
        with open(ANSWER_LOG_PATH, "r", encoding="utf-8") as f:
            for line in f:
                timestamp_str = line.split(" | ")[0]
                timestamp = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
                if now - timestamp <= timedelta(hours=24):
                    count += 1
        return count + 1 
    except FileNotFoundError:
        return 1

def auto_cleanup_banned():
    while True:
        try:
            conn = sqlite3.connect("database.db")
            cursor = conn.cursor()
            cursor.execute("SELECT peer_id FROM synced_chats")
            chats = cursor.fetchall()

            for (chat_peer_id,) in chats:
                try:
                    members = vk.messages.getConversationMembers(peer_id=chat_peer_id)
                    users = [m['member_id'] for m in members['items']]

                    for user_id in users:
                        if user_id < 0:
                            continue

                        sysban = get_sysban_from_db(user_id)
                        name = get_user_info(user_id)

                        if sysban:
                            reason, admin_id = sysban
                            try:
                                vk.messages.removeChatUser(
                                    chat_id=chat_peer_id - 2000000000,
                                    user_id=user_id
                                )
                                send_message(chat_peer_id,
                                    f"⛔ [id{user_id}|{name}] находится в системном бане!\n"
                                    f"📄 Причина: {reason}\n"
                                    f"🛡 Админ: [id{admin_id}|Сотрудник]\n"
                                    f"🚫 Авто-исключение.")
                            except Exception as e:
                                print(f"[AUTO-CLEANUP SYSBAN ERROR]: {e}")
                            continue

                        blacklist_info = get_blacklist_info(user_id)
                        if blacklist_info:
                            reason = blacklist_info[1]
                            end_date = blacklist_info[2]
                            admin_id = blacklist_info[3]
                            try:
                                vk.messages.removeChatUser(
                                    chat_id=chat_peer_id - 2000000000,
                                    user_id=user_id
                                )
                                send_message(chat_peer_id,
                                    f"🚫 [id{user_id}|{name}] находится в чёрном списке!\n"
                                    f"📄 Причина: {reason}\n"
                                    f"⏳ До: {end_date}\n"
                                    f"🛡 Забанил: [id{admin_id}|Сотрудник]\n"
                                    f"🚷 Авто-исключение.")
                            except Exception as e:
                                print(f"[AUTO-CLEANUP BLACKLIST ERROR]: {e}")
                except Exception as e:
                    print(f"[AUTO-CLEANUP CHAT ERROR]: peer_id={chat_peer_id} -> {e}")

        except Exception as e:
            print(f"[AUTO-CLEANUP ERROR]: {e}")

        time.sleep(10)

def add_user_back(peer_id, user_id):
    name = get_user_info(user_id)
    try:
        vk.messages.addChatUser(chat_id=peer_id-2000000000, user_id=user_id)
        send_message(peer_id, f"✅ [id{user_id}|{name}] возвращён в беседу.")
    except Exception as e:
        print(f"[AUTO-RETURN ERROR]: {e}")

def add_user(peer_id, user_id):
    name = get_user_info(user_id)
    try:
        vk.messages.addChatUser(chat_id=peer_id-2000000000, user_id=user_id)
        send_message(peer_id, f"✅ [id{user_id}|{name}] добавлен в беседу.")
    except Exception as e:
        send_message(peer_id, f"❌ Не удалось добавить [id{user_id}|{name}] в беседу")
        print(f"[AUTO-RETURN ERROR]: {e}")

def send_reports_page(peer_id, offset=0, edit_message_id=None):
    PAGE_SIZE = 5
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM reports")
    total = cursor.fetchone()[0]

    cursor.execute(
        "SELECT id, user_id, text FROM reports ORDER BY id DESC LIMIT ? OFFSET ?",
        (PAGE_SIZE, offset)
    )
    rows = cursor.fetchall()

    page_num = offset // PAGE_SIZE + 1
    max_page = (total - 1) // PAGE_SIZE + 1

    msg = f"📋 **Репорты (стр. {page_num}/{max_page})**\n\n"
    keyboard_buttons = []

    for rep_id, uid, rep_text in rows:
        name = get_user_info(uid)
        short_text = (rep_text[:40] + "…") if len(rep_text) > 40 else rep_text
        msg += f"#{rep_id} — [id{uid}|{name}]:\n{short_text}\n\n"
        keyboard_buttons.append([{
            "action": {
                "type": "callback",
                "label": f"Ответить ({name[:10]})",
                "payload": json.dumps({"cmd": "reply_report", "report_id": rep_id})
            },
            "color": "primary"
        }])

    nav_row = []
    if offset > 0:
        nav_row.append({
            "action": {
                "type": "callback",
                "label": "⬅ Назад",
                "payload": json.dumps({
                    "cmd": "reps_page",
                    "offset": max(0, offset - PAGE_SIZE),
                    "edit_id": edit_message_id 
                })
            },
            "color": "secondary"
        })
    if offset + PAGE_SIZE < total:
        nav_row.append({
            "action": {
                "type": "callback",
                "label": "➡ Далее",
                "payload": json.dumps({
                    "cmd": "reps_page",
                    "offset": offset + PAGE_SIZE,
                    "edit_id": edit_message_id
                })
            },
            "color": "secondary"
        })
    if nav_row:
        keyboard_buttons.append(nav_row)

    keyboard = json.dumps({"inline": True, "buttons": keyboard_buttons}, ensure_ascii=False)

    if edit_message_id:
        vk.messages.edit(
            peer_id=peer_id,
            message_id=edit_message_id,
            message=msg,
            keyboard=keyboard
        )
    else:
        sent = vk.messages.send(
            peer_id=peer_id,
            message=msg,
            random_id=get_random_id(),
            keyboard=keyboard
        )
        return sent

def clear_database(db_path: str, peer_id: int):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = [row[0] for row in cursor.fetchall()]

    if not tables:
        vk.messages.send(peer_id=peer_id, message="ℹ База данных пуста, таблиц нет.", random_id=0)
        return

    messages = ["🧹 Очищаю базу данных..."]
    for table in tables:
        if table == "sqlite_sequence":
            cursor.execute("DELETE FROM sqlite_sequence;")
        else:
            cursor.execute(f"DELETE FROM {table};")
            messages.append(f"✅ Таблица {table} очищена")

    # Восстанавливаем владельца после очистки
    cursor.execute("INSERT OR REPLACE INTO admins (user_id, level) VALUES (?, ?)", (OWNER_ID, 7))
    messages.append("👑 Владелец восстановлен")
    
    conn.commit()
    conn.close()

    messages.append("🎉 Все данные удалены, таблицы сохранены.")
    vk.messages.send(peer_id=peer_id, message="\n".join(messages), random_id=0)

# Запуск фоновых процессов
threading.Thread(target=auto_cleanup_banned, daemon=True).start()
threading.Thread(target=auto_unban_loop, daemon=True).start()

# ОСНОВНАЯ ФУНКЦИЯ ОБРАБОТКИ СООБЩЕНИЙ
def process_message(message):
    global mute_tracker, muted_users, total_requests, total_commands
    
    total_requests += 1
    
    peer_id = message.get("peer_id")
    user_id = message.get("from_id")
    text = message.get('text', '').strip()
    admin_level = get_admin_level(user_id)
    
    # Сохраняем первый контакт
    save_first_contact(user_id)
    
    # Проверка мута
    if user_id in muted_users:
        mute_data = muted_users[user_id]
        if time.time() < mute_data["until"]:
            count = mute_tracker.get(user_id, 0)
            if count == 0:
                mute_tracker[user_id] = 1
                send_message(peer_id, f"🤐 [id{user_id}|Вы замучены]! Следующее сообщение → кик.")
                return
            else:
                mute_tracker[user_id] = 0
                vk.messages.removeChatUser(chat_id=peer_id-2000000000, user_id=user_id)
                send_message(peer_id, f"⛔ [id{user_id}|Пользователь] кикнут за нарушение мута! Будет возвращён через {mute_data['time']} мин.")
                threading.Timer(mute_data["time"] * 60, lambda: add_user_back(peer_id, user_id)).start()
                return
        else:
            muted_users.pop(user_id, None)
            mute_tracker.pop(user_id, None)
    
    # Обработка ответов на репорты
    if user_id in active_report_replies:
        rep_id = active_report_replies[user_id]

        if text.strip().lower() == "/cancel":
            del active_report_replies[user_id]
            send_message(peer_id, "❌ Ответ на репорт отменён.")
            process_message({"peer_id": peer_id, "from_id": user_id, "text": "/reps"})
            return
            
        conn = sqlite3.connect("database.db")
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM reports WHERE id = ?", (rep_id,))
        row = cursor.fetchone()

        if row:
            target_uid = row[0]
            admin_name = get_user_info(user_id)
            send_message(target_uid, 
                f"📨 Ответ на ваш вопрос #{rep_id}\n"
                f"Администратор: {admin_name}\n\n"
                f"{text}\n\n"
                "Если есть ещё вопросы – отправьте новый /report.",                    
                keyboard=json.dumps({
                    "inline": True,
                    "buttons": [
                        [
                            {
                                "action": {
                                    "type": "callback",
                                    "label": "💬 Ответить лично",
                                    "payload": json.dumps({
                                        "cmd": "reply_personal",
                                        "admin_id": user_id
                                    })
                                },
                            "color": "primary"
                            }
                        ]
                    ]
                }, ensure_ascii=False)
            )

            send_message(peer_id, f"✅ Ответ на репорт #{rep_id} отправлен [id{target_uid}|пользователю].")
            cursor.execute("DELETE FROM reports WHERE id = ?", (rep_id,))
            conn.commit()
        else:
            send_message(peer_id, "⚠ Репорт не найден (возможно удалён).")

        del active_report_replies[user_id]
        return
    
    # Обработка команд
    if text.startswith("/"):
        total_commands += 1
    
    # ===================== КОМАНДЫ ВЛАДЕЛЬЦА =====================
    if text.startswith("/setadmin"):
        if admin_level < 7 and user_id != OWNER_ID:
            send_message(peer_id, "❌ Только владелец может назначать администраторов.")
            return
            
        parts = text.split()
        if len(parts) != 3:
            send_message(peer_id, "⚠ Формат: /setadmin [id/ссылка] [уровень 1-6]")
            return
            
        uid = resolve_username(parse_user_id(parts[1]))
        if not uid:
            send_message(peer_id, "❌ Пользователь не найден.")
            return
            
        try:
            level = int(parts[2])
            if level < 1 or level > 6:
                send_message(peer_id, "❌ Уровень должен быть от 1 до 6.")
                return
        except:
            send_message(peer_id, "❌ Неверный уровень.")
            return
            
        add_admin(uid, level)
        name = get_user_info(uid)
        send_message(peer_id, f"✅ [id{uid}|{name}] назначен администратором уровня {level}")
        log_action(user_id, f"Назначил администратора {uid} уровня {level}", True)
        
    elif text.startswith("/rr"):
        if admin_level < 7 and user_id != OWNER_ID:
            send_message(peer_id, "❌ Только владелец может снимать права.")
            return
            
        parts = text.split()
        if len(parts) != 2:
            send_message(peer_id, "⚠ Формат: /rr [id/ссылка]")
            return
            
        uid = resolve_username(parse_user_id(parts[1]))
        if not uid:
            send_message(peer_id, "❌ Пользователь не найден.")
            return
            
        if uid == OWNER_ID:
            send_message(peer_id, "❌ Нельзя снять права у владельца.")
            return
            
        remove_admin(uid)
        name = get_user_info(uid)
        send_message(peer_id, f"✅ [id{uid}|{name}] лишён прав администратора.")
        log_action(user_id, f"Снял права у {uid}", True)
        
    elif text.startswith("/editcmd"):
        if admin_level < 7 and user_id != OWNER_ID:
            send_message(peer_id, "❌ Только владелец может изменять уровни команд.")
            return
            
        parts = text.split()
        if len(parts) != 3:
            send_message(peer_id, "⚠ Формат: /editcmd [команда] [уровень 0-7]")
            return
            
        command = parts[1]
        try:
            level = int(parts[2])
            if level < 0 or level > 7:
                send_message(peer_id, "❌ Уровень должен быть от 0 до 7.")
                return
        except:
            send_message(peer_id, "❌ Неверный уровень.")
            return
            
        set_command_level(command, level)
        send_message(peer_id, f"✅ Команда {command} теперь доступна с уровня {level}.")
        log_action(user_id, f"Изменил уровень команды {command} на {level}", True)
    
    # ===================== ОСНОВНЫЕ КОМАНДЫ =====================
    # В bot.py в раздел ОСНОВНЫЕ КОМАНДЫ добавить:

# ===================== КОМАНДЫ НИКОВ И ЗАКРЕПЛЕНИЯ =====================
    elif text.startswith("/pin"):
        required_level = get_command_level("/pin")
        if admin_level < required_level:
            send_message(peer_id, "❌ Недостаточно прав.")
            return
            
        # Проверяем, есть ли сообщение в ответ на которое отправлена команда
        if 'reply_message' in message:
            message_id = message['reply_message']['id']
            try:
                vk.messages.pin(peer_id=peer_id, message_id=message_id)
                send_message(peer_id, "📌 Сообщение закреплено.")
                log_action(user_id, f"Закрепил сообщение в чате {peer_id}", True)
            except Exception as e:
                send_message(peer_id, f"❌ Ошибка закрепления: {e}")
        else:
            send_message(peer_id, "❌ Используйте команду в ответ на сообщение, которое нужно закрепить.")
    
    elif text.startswith("/unpin"):
        required_level = get_command_level("/unpin")
        if admin_level < required_level:
            send_message(peer_id, "❌ Недостаточно прав.")
            return
            
        try:
            vk.messages.unpin(peer_id=peer_id)
            send_message(peer_id, "📌 Сообщение откреплено.")
            log_action(user_id, f"Открепил сообщение в чате {peer_id}", True)
        except Exception as e:
            send_message(peer_id, f"❌ Ошибка открепления: {e}")
    
    elif text.startswith("/snick"):
        required_level = get_command_level("/snick")
        if admin_level < required_level:
            send_message(peer_id, "❌ Недостаточно прав.")
            return
            
        parts = text.split(maxsplit=1)
        if len(parts) < 2:
            send_message(peer_id, "⚠ Формат: /snick [ник] в ответ на сообщение пользователя")
            return
            
        if 'reply_message' not in message:
            send_message(peer_id, "❌ Используйте команду в ответ на сообщение пользователя.")
            return
            
        target_id = message['reply_message']['from_id']
        nickname = parts[1]
        
        # Сохраняем ник в базу данных
        conn = sqlite3.connect("database.db")
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS nicknames (
                user_id INTEGER PRIMARY KEY,
                nickname TEXT,
                set_by INTEGER,
                set_at TEXT
            )
        ''')
        
        # Проверяем существующий ник
        cursor.execute("SELECT nickname FROM nicknames WHERE user_id = ?", (target_id,))
        existing = cursor.fetchone()
        
        cursor.execute("INSERT OR REPLACE INTO nicknames (user_id, nickname, set_by, set_at) VALUES (?, ?, ?, ?)",
                      (target_id, nickname, user_id, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
        conn.close()
        
        target_name = get_user_info(target_id)
        admin_name = get_user_info(user_id)
        
        if existing:
            send_message(peer_id, f"📝 Ник пользователя [id{target_id}|{target_name}] изменён на: {nickname}")
        else:
            send_message(peer_id, f"✅ Пользователю [id{target_id}|{target_name}] установлен ник: {nickname}")
        
        log_action(user_id, f"Установил ник {nickname} для {target_id}", True)
    
    elif text.startswith("/rnick"):
        required_level = get_command_level("/rnick")
        if admin_level < required_level:
            send_message(peer_id, "❌ Недостаточно прав.")
            return
            
        if 'reply_message' not in message:
            send_message(peer_id, "❌ Используйте команду в ответ на сообщение пользователя.")
            return
            
        target_id = message['reply_message']['from_id']
        
        conn = sqlite3.connect("database.db")
        cursor = conn.cursor()
        cursor.execute("SELECT nickname FROM nicknames WHERE user_id = ?", (target_id,))
        existing = cursor.fetchone()
        
        if existing:
            cursor.execute("DELETE FROM nicknames WHERE user_id = ?", (target_id,))
            conn.commit()
            target_name = get_user_info(target_id)
            send_message(peer_id, f"🗑 Ник пользователя [id{target_id}|{target_name}] удалён.")
            log_action(user_id, f"Удалил ник у {target_id}", True)
        else:
            send_message(peer_id, f"ℹ️ У пользователя нет установленного ника.")
        
        conn.close()
    
    elif text.startswith("/nlist"):
        conn = sqlite3.connect("database.db")
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE IF NOT EXISTS nicknames (user_id INTEGER PRIMARY KEY, nickname TEXT)")
        
        cursor.execute("SELECT user_id, nickname FROM nicknames")
        rows = cursor.fetchall()
        conn.close()
        
        if not rows:
            send_message(peer_id, "📋 Список ников пуст.")
            return
        
        message_lines = ["📋 **Список ников пользователей:**\n"]
        
        for user_id, nickname in rows:
            user_name = get_user_info(user_id)
            message_lines.append(f"• [id{user_id}|{user_name}] → {nickname}")
        
        send_message(peer_id, "\n".join(message_lines))
    
    elif text.startswith("/gnick"):
        if 'reply_message' not in message:
            send_message(peer_id, "❌ Используйте команду в ответ на сообщение пользователя.")
            return
            
        target_id = message['reply_message']['from_id']
        
        conn = sqlite3.connect("database.db")
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE IF NOT EXISTS nicknames (user_id INTEGER PRIMARY KEY, nickname TEXT)")
        
        cursor.execute("SELECT nickname FROM nicknames WHERE user_id = ?", (target_id,))
        row = cursor.fetchone()
        conn.close()
        
        target_name = get_user_info(target_id)
        
        if row:
            nickname = row[0]
            send_message(peer_id, f"🏷 Ник пользователя [id{target_id}|{target_name}]: {nickname}")
        else:
            send_message(peer_id, f"ℹ️ У пользователя [id{target_id}|{target_name}] нет установленного ника.")
    
    elif text.lower() in ("/start", "начать", "старт", "start", "приветствие"):
        keyboard = {
            "inline": True,
            "buttons": [
                [
                    {
                        "action": {
                            "type": "callback",
                            "label": "📋 Список команд",
                            "payload": '{"cmd":"bhelp"}'
                        },
                        "color": "negative"
                    }
                ],
                [
                    {
                        "action": {
                            "type": "callback",
                            "label": "📜 Публичная оферта",
                            "payload": '{"cmd":"boffer"}'
                        },
                        "color": "positive"
                    }
                ],
                [
                    {
                        "action": {
                            "type": "callback",
                            "label": "👥 Наш проект",
                            "payload": '{"cmd":"project_info"}'
                        },
                        "color": "primary"
                    }
                ]
            ]
        }
        
        start_message = (
            "👋 **Добро пожаловать в ARION RP!**\n\n"
            
            "🏙️ **О НАС:**\n"
            "Arion — это атмосферный русскоязычный RP-проект с глубокой проработкой игрового мира.\n"
            "Мы создаем уникальную среду для ролевых взаимодействий, где каждый может найти своего персонажа.\n\n"
        )
        
        vk.messages.send(
            peer_id=peer_id,
            message=start_message,
            random_id=get_random_id(),
            keyboard=json.dumps(keyboard, ensure_ascii=False)
        )
        log_action(user_id, f"{peer_id} Вывел приветствие")
        
    elif text.startswith("/stats"):
        # Получаем статистику пользователя
        stats = get_user_stats(user_id)
        user_name = get_user_info(user_id)
        
        # Рассчитываем уровень на основе времени игры
        play_time = stats["play_time_hours"]
        level = min(play_time // 10 + 1, 100)  # Каждые 10 часов = 1 уровень, макс 100
        
        # Определяем ранг на основе времени игры
        if play_time >= 200:
            rank = "🎖️ ВЕТЕРАН"
            rank_color = "🟣"
        elif play_time >= 100:
            rank = "🏆 ЭКСПЕРТ"
            rank_color = "🔵"
        elif play_time >= 50:
            rank = "⭐ ОПЫТНЫЙ"
            rank_color = "🟢"
        elif play_time >= 20:
            rank = "📈 АКТИВНЫЙ"
            rank_color = "🟡"
        elif play_time >= 5:
            rank = "🌱 НОВИЧОК"
            rank_color = "⚪"
        else:
            rank = "🌱 НОВИЧОК"
            rank_color = "⚪"
        
        # Рассчитываем прогресс до следующего уровня
        progress_current = play_time % 10
        progress_percent = min((progress_current / 10) * 100, 100)
        
        # Создаём прогресс-бар
        progress_bar_length = 10
        filled = int(progress_percent / 100 * progress_bar_length)
        progress_bar = "█" * filled + "░" * (progress_bar_length - filled)
        
        # Форматируем достижения
        achievements = stats["achievements"]
        if achievements:
            achievements_list = achievements.split(",")
            achievements_display = "\n".join([f"• {ach}" for ach in achievements_list[:5]])  # Показываем первые 5
            if len(achievements_list) > 5:
                achievements_display += f"\n• ... и ещё {len(achievements_list) - 5}"
        else:
            achievements_display = "🎯 Достижений пока нет"
        
        # Формируем сообщение
        stats_message = (
            f"📊 **СТАТИСТИКА ИГРОКА**\n\n"
            
            f"👤 **{user_name}**\n"
            f"🆔 ID: {user_id}\n"
            f"{rank_color} **{rank}** | Уровень {level}\n\n"
            
            f"⏱️ **ИГРОВОЕ ВРЕМЯ:** {play_time} часов\n"
            f"📈 Прогресс: {progress_bar} {progress_percent:.0f}%\n"
            f"⏳ До след. уровня: {10 - progress_current} часов\n\n"
            
            f"🎭 **АКТИВНОСТЬ:**\n"
            f"• Участие в ивентах: {stats['events_participated']}\n"
            f"• RP-взаимодействия: {stats['rp_interactions']}\n"
            f"• Создано персонажей: {stats['characters_created']}\n"
            f"• Вступил в организаций: {stats['orgs_joined']}\n\n"
            
            f"⚠ **ДИСЦИПЛИНА:**\n"
            f"• Получено предупреждений: {stats['warnings_received']}\n"
            f"• Активные предупреждения: {get_warnings(peer_id, user_id)}\n\n"
            
            f"🏆 **ДОСТИЖЕНИЯ:**\n"
            f"{achievements_display}\n\n"
            
            f"📅 **ПОСЛЕДНЯЯ АКТИВНОСТЬ:**\n"
            f"{stats['last_active']}\n\n"
            
        )
        
        # Клавиатура с дополнительными действиями
        keyboard = {
            "inline": True,
            "buttons": [
                [
                    {
                        "action": {
                            "type": "callback",
                            "label": "📈 Сравнить с другими",
                            "payload": json.dumps({"cmd": "compare_stats"})
                        },
                        "color": "primary"
                    }
                ],
                [
                    {
                        "action": {
                            "type": "callback",
                            "label": "🏆 Топ игроков",
                            "payload": json.dumps({"cmd": "top_players"})
                        },
                        "color": "secondary"
                    },
                    {
                        "action": {
                            "type": "callback",
                            "label": "🎯 Мои цели",
                            "payload": json.dumps({"cmd": "my_goals"})
                        },
                        "color": "positive"
                    }
                ]
            ]
        }
        
        send_message(peer_id, stats_message, keyboard=keyboard)
        
    elif text.startswith("/help"):
        help_message = (
            "📋 **ARION RP — ДОСТУПНЫЕ КОМАНДЫ**\n\n"
            
            "👋 **ОСНОВНЫЕ:**\n"
            "• /start — Информация о проекте\n"
            "• /help — Этот список команд\n"
            
            "📞 **СВЯЗЬ С АДМИНИСТРАЦИЕЙ:**\n"
            "• /report [текст] — Отправить жалобу или вопрос\n"
            "• /question [текст] — Задать вопрос по RP\n\n"
            
            "🎭 **ARION RP — Глубина ролевой игры важнее всего!**\n"
            "📞 Поддержка: @id709914900 (Основатель)\n"
            "🕒 Ответ в течение 24 часов"
        )
        
        send_message(peer_id, help_message)
        
    elif text.startswith("/ban"):
        required_level = get_command_level("/ban")
        if admin_level < required_level:
            send_message(peer_id, "❌ Недостаточно прав.")
            return
            
        if peer_id > 2000000000:
            send_message(peer_id, "🔧 Занести в ЧС можно только в личных сообщениях.")
            return
            
        parts = text.split(maxsplit=3)
        if len(parts) < 4:
            send_message(peer_id, "⚠ Формат: /ban [id/ссылка] [дни] [причина]")
            return

        uid = resolve_username(parse_user_id(parts[1]))
        if not uid:
            send_message(peer_id, "❌ Пользователь не найден.")
            return
            
        name = get_user_info(uid)
        if get_blacklist_info(uid):
            send_message(peer_id, f"❗ [id{uid}|{name}] уже в ЧС.")
            return

        try:
            days = int(parts[2])
            reason = parts[3]
            
            # Спрашиваем тип блокировки
            temp_data = {
                "target_id": uid,
                "days": days,
                "reason": reason,
                "admin_id": user_id,
                "type_stage": True
            }
            
            if user_id not in globals().get('temp_bans', {}):
                globals()['temp_bans'] = {}
            globals()['temp_bans'][user_id] = temp_data
            
            keyboard = VkKeyboard(one_time=False, inline=True)
            keyboard.add_button("ЧСП", color=VkKeyboardColor.NEGATIVE)
            keyboard.add_line()
            keyboard.add_button("ОЧС", color=VkKeyboardColor.POSITIVE)
            keyboard.add_line()
            keyboard.add_button("ЧС ПОСТОВ", color=VkKeyboardColor.PRIMARY)
            keyboard.add_line()
            keyboard.add_button("ЧС АДМИНИСТРАЦИИ", color=VkKeyboardColor.SECONDARY)
            
            send_message(peer_id,
                "❔ Выберите тип блокировки:\n"
                "• ЧСП - Чёрный список проекта\n"
                "• ОЧС - Общий чёрный список\n"
                "• ЧС ПОСТОВ - Запрет на посты\n"
                "• ЧС АДМИНИСТРАЦИИ - Блокировка администрации",
                keyboard.get_keyboard()
            )
            
        except ValueError:
            send_message(peer_id, "❌ Неверное количество дней.")
            
    elif text.startswith("/aban"):
        required_level = get_command_level("/aban")
        if admin_level < required_level:
            send_message(peer_id, "❌ Недостаточно прав.")
            return
            
        if peer_id > 2000000000:
            send_message(peer_id, "🔧 Занести в ЧС можно только в личных сообщениях.")
            return
            
        parts = text.split(maxsplit=2)
        if len(parts) < 3:
            send_message(peer_id, "⚠ Формат: /aban [id/ссылка] [причина]")
            return

        uid = resolve_username(parse_user_id(parts[1]))
        if not uid:
            send_message(peer_id, "❌ Пользователь не найден.")
            return
            
        name = get_user_info(uid)
        if get_blacklist_info(uid):
            send_message(peer_id, f"❗ [id{uid}|{name}] уже в ЧС.")
            return

        reason = parts[2]
        
        # Спрашиваем тип блокировки
        temp_data = {
            "target_id": uid,
            "days": "PERMANENT",
            "reason": reason,
            "admin_id": user_id,
            "type_stage": True
        }
        
        if user_id not in globals().get('temp_bans', {}):
            globals()['temp_bans'] = {}
        globals()['temp_bans'][user_id] = temp_data
        
        keyboard = VkKeyboard(one_time=False, inline=True)
        keyboard.add_button("ЧСП", color=VkKeyboardColor.NEGATIVE)
        keyboard.add_line()
        keyboard.add_button("ОЧС", color=VkKeyboardColor.POSITIVE)
        keyboard.add_line()
        keyboard.add_button("ЧС ПОСТОВ", color=VkKeyboardColor.PRIMARY)
        keyboard.add_line()
        keyboard.add_button("ЧС АДМИНИСТРАЦИИ", color=VkKeyboardColor.SECONDARY)
        
        send_message(peer_id,
            "❔ Выберите тип блокировки:\n"
            "• ЧСП - Чёрный список проекта\n"
            "• ОЧС - Общий чёрный список\n"
            "• ЧС ПОСТОВ - Запрет на посты\n"
            "• ЧС АДМИНИСТРАЦИИ - Блокировка администрации",
            keyboard.get_keyboard()
        )
        
    elif text.startswith("/unban"):
        required_level = get_command_level("/unban")
        if admin_level < required_level:
            send_message(peer_id, "❌ Недостаточно прав.")
            return

        parts = text.split()
        if len(parts) < 2:
            send_message(peer_id, "⚠ Формат: /unban [id/ссылка]")
            return
            
        uid = resolve_username(parse_user_id(parts[1]))
        if not uid:
            send_message(peer_id, "❌ Пользователь не найден.")
            return
            
        info = get_blacklist_info(uid)
        if not info:
            send_message(peer_id, "✅ Пользователь не заблокирован.")
            return
            
        # Проверка на перманентный бан
        if info[2] == "PERMANENT" and admin_level < 4 and user_id != OWNER_ID:
            send_message(peer_id, "❌ Только администраторы 4+ уровня могут снимать перманентный бан.")
            return
            
        remove_from_blacklist(uid)
        name = get_user_info(uid)
        send_message(peer_id, f"✅ [id{uid}|{name}] разблокирован.")
        log_action(user_id, f"Разблокировал {uid}", True)
        
    elif text.startswith("/checkban"):
        required_level = get_command_level("/checkban")
        if admin_level < required_level:
            send_message(peer_id, "❌ Недостаточно прав.")
            return

        args = text.split()[1:]
        if not args:
            send_message(peer_id, "❗ Укажите пользователя для проверки.")
            return

        results = []
        for raw_uid in args:
            parsed = parse_user_id(raw_uid)
            uid = resolve_username(parsed)
            if not uid:
                results.append(f"🔘 {raw_uid}: ❌ Не найден")
                continue

            name = get_user_info(uid)

            # Проверка системного бана
            sysban = get_sysban_from_db(uid)
            if sysban:
                reason, admin_id = sysban
                admin_name = get_user_info(admin_id)
                results.append(
                    f"🔘 [id{uid}|{name}]:\n⛔ **СИСТЕМНЫЙ БАН**\n"
                    f"📄 Причина: {reason}\n"
                    f"🛡 Админ: [id{admin_id}|{admin_name}]"
                )
                continue

            # Проверка обычного бана
            bl_info = get_blacklist_info(uid)
            if bl_info:
                reason = bl_info[1]
                end_date = bl_info[2]
                admin_id = bl_info[3]
                admin_name = get_user_info(admin_id)
                
                ban_type = "ЧС"
                if "ЧСП" in reason:
                    ban_type = "ЧСП"
                elif "ОЧС" in reason:
                    ban_type = "ОЧС"
                elif "ЧС(ПОСТ)" in reason:
                    ban_type = "ЧС ПОСТОВ"
                elif "ЧСА" in reason:
                    ban_type = "ЧС АДМИНИСТРАЦИИ"
                    
                duration = "Навсегда" if end_date == "PERMANENT" else f"до {end_date}"
                results.append(
                    f"🔘 [id{uid}|{name}]:\n🚫 **{ban_type}**\n"
                    f"📄 Причина: {reason.replace(' | ' + ban_type, '')}\n"
                    f"⏳ {duration}\n"
                    f"🛡 Админ: [id{admin_id}|{admin_name}]"
                )
            else:
                results.append(f"🔘 [id{uid}|{name}]: ✅ Не заблокирован")

        message_result = "📋 **Результаты проверки:**\n\n" + "\n\n".join(results)
        send_message(peer_id, message_result)
        log_action(user_id, f"Проверил бан: {', '.join(args)}", True)
        
    elif text.startswith("/banlist"):
        required_level = get_command_level("/banlist")
        if admin_level < required_level:
            send_message(peer_id, "❌ Недостаточно прав.")
            return

        # Получаем список забаненных
        banned_users = get_all_banned_users()
        
        if not banned_users:
            send_message(peer_id, "✅ Нет пользователей в черном списке.")
            return

        # Формируем сообщение
        message_lines = ["🚫 **Список заблокированных:**\n"]
        
        for user_data in banned_users:
            user_id = user_data[0]
            reason = user_data[1]
            end_date = user_data[2]
            admin_id = user_data[3]
            
            user_name = get_user_info(user_id)
            admin_name = get_user_info(admin_id)
            
            # Определяем тип бана
            ban_type = "ЧС"
            if " | ЧСП" in reason:
                ban_type = "ЧСП"
                reason_clean = reason.replace(" | ЧСП", "")
            elif " | ОЧС" in reason:
                ban_type = "ОЧС"
                reason_clean = reason.replace(" | ОЧС", "")
            elif " | ЧС(ПОСТ)" in reason:
                ban_type = "ЧС ПОСТОВ"
                reason_clean = reason.replace(" | ЧС(ПОСТ)", "")
            elif " | ЧСА" in reason:
                ban_type = "ЧС АДМИНИСТРАЦИИ"
                reason_clean = reason.replace(" | ЧСА", "")
            else:
                reason_clean = reason
            
            # Форматируем дату окончания
            if end_date == "PERMANENT":
                duration = "🔒 Навсегда"
            else:
                duration = f"⏳ До: {end_date}"
            
            message_lines.append(f"👤 [id{user_id}|{user_name}]")
            message_lines.append(f"📛 Тип: {ban_type}")
            message_lines.append(f"📄 Причина: {reason_clean}")
            message_lines.append(f"{duration}")
            message_lines.append(f"👮 Забанил: [id{admin_id}|{admin_name}]")
            message_lines.append("─" * 30)
        
        # Отправляем сообщение
        full_message = "\n".join(message_lines)
        
        # Если сообщение слишком длинное, разбиваем на части
        if len(full_message) > 4000:
            parts = [full_message[i:i+4000] for i in range(0, len(full_message), 4000)]
            for part in parts:
                send_message(peer_id, part)
                time.sleep(0.5)  # Задержка между сообщениями
        else:
            send_message(peer_id, full_message)
        
        log_action(user_id, "Вывел список банов", True)
        
    elif text.startswith("/sysban"):
        required_level = get_command_level("/sysban")
        if admin_level < required_level:
            send_message(peer_id, "❌ Недостаточно прав.")
            return
            
        parts = text.split(maxsplit=2)
        if len(parts) < 3:
            send_message(peer_id, "⚠ Формат: /sysban [id/ссылка] [причина]")
            return
            
        uid = resolve_username(parse_user_id(parts[1]))
        if not uid:
            send_message(peer_id, "❌ Пользователь не найден.")
            return
            
        if uid == OWNER_ID:
            send_message(peer_id, "❌ Нельзя забанить владельца.")
            return
            
        reason = parts[2]
        add_to_sysban(uid, reason, user_id)
        name = get_user_info(uid)
        admin_name = get_user_info(user_id)
        
        try:
            vk.messages.send(
                peer_id=uid,
                message=f"🔒 **ВЫ ЗАБЛОКИРОВАНЫ В СИСТЕМЕ**\n\n📄 Причина: {reason}\n🛡 Администратор: [id{user_id}|{admin_name}]\n\nℹ Вы не можете пользоваться функциями бота.",
                random_id=get_random_id()
            )
        except:
            pass
            
        send_message(peer_id, f"✅ [id{uid}|{name}] заблокирован в системе.")
        log_action(user_id, f"Системный бан: {uid}", True)
        
    elif text.startswith("/offsysban"):
        required_level = get_command_level("/offsysban")
        if admin_level < required_level:
            send_message(peer_id, "❌ Недостаточно прав.")
            return
            
        parts = text.split()
        if len(parts) < 2:
            send_message(peer_id, "⚠ Формат: /offsysban [id/ссылка]")
            return
            
        uid = resolve_username(parse_user_id(parts[1]))
        if not uid:
            send_message(peer_id, "❌ Пользователь не найден.")
            return
            
        remove_from_sysban(uid)
        name = get_user_info(uid)
        send_message(peer_id, f"✅ [id{uid}|{name}] разблокирован в системе.")
        log_action(user_id, f"Снял системный бан: {uid}", True)
        
    elif text.startswith("/syslist"):
        required_level = get_command_level("/syslist")
        if admin_level < required_level:
            send_message(peer_id, "❌ Недостаточно прав.")
            return

        sysbans = get_all_sysbans()
        if not sysbans:
            send_message(peer_id, "✅ Нет системных блокировок.")
            return

        msg = "🚫 **Системные блокировки:**\n\n"
        for uid, reason, admin_id in sysbans:
            name = get_user_info(uid)
            admin_name = get_user_info(admin_id)
            msg += f"🔘 [id{uid}|{name}]\n📄 {reason}\n🛡 [id{admin_id}|{admin_name}]\n\n"

        send_message(peer_id, msg)
        log_action(user_id, "Вывел syslist", True)
        
    elif text.startswith("/admins"):
        required_level = get_command_level("/admins")
        if admin_level < required_level:
            send_message(peer_id, "❌ Недостаточно прав.")
            return
            
        conn = sqlite3.connect("database.db")
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, level FROM admins WHERE level BETWEEN 1 AND 3 ORDER BY level DESC")
        rows = cursor.fetchall()

        if not rows:
            send_message(peer_id, "ℹ Нет администраторов 1-3 уровня.")
            return

        lvl3, lvl2, lvl1 = [], [], []
        for uid, lvl in rows:
            name = get_user_info(uid)
            if lvl == 3:
                lvl3.append(f"[id{uid}|{name}]")
            elif lvl == 2:
                lvl2.append(f"[id{uid}|{name}]")
            elif lvl == 1:
                lvl1.append(f"[id{uid}|{name}]")

        msg = "👮 **Старший администратор (3):**\n" + ("\n".join(lvl3) if lvl3 else "—") + "\n\n"
        msg += "👮‍♂️ **Младший администратор (2):**\n" + ("\n".join(lvl2) if lvl2 else "—") + "\n\n"
        msg += "👨‍🎓 **Модератор (1):**\n" + ("\n".join(lvl1) if lvl1 else "—")

        send_message(peer_id, msg)
        
    elif text.startswith("/staff"):
        required_level = get_command_level("/staff")
        if admin_level < required_level:
            send_message(peer_id, "❌ Недостаточно прав.")
            return
            
        conn = sqlite3.connect("database.db")
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, level FROM admins WHERE level BETWEEN 4 AND 7 ORDER BY level DESC")
        rows = cursor.fetchall()

        if not rows:
            send_message(peer_id, "ℹ Нет сотрудников 4-7 уровня.")
            return

        lvl7, lvl6, lvl5, lvl4 = [], [], [], []
        for uid, lvl in rows:
            name = get_user_info(uid)
            if lvl == 7:
                lvl7.append(f"[id{uid}|{name}]")
            elif lvl == 6:
                lvl6.append(f"[id{uid}|{name}]")
            elif lvl == 5:
                lvl5.append(f"[id{uid}|{name}]")
            elif lvl == 4:
                lvl4.append(f"[id{uid}|{name}]")

        msg = "👑 **Владелец (7):**\n" + ("\n".join(lvl7) if lvl7 else f"[id{OWNER_ID}|Основатель]") + "\n\n"
        msg += "👤 **Со-Владелец (6):**\n" + ("\n".join(lvl6) if lvl6 else "—") + "\n\n"
        msg += "🔧 **Разработчик (5):**\n" + ("\n".join(lvl5) if lvl5 else "—") + "\n\n"
        msg += "🔏 **Саппорт (4):**\n" + ("\n".join(lvl4) if lvl4 else "—")

        send_message(peer_id, msg)
        
    elif text.startswith("/ping"):
        required_level = get_command_level("/ping")
        if admin_level < required_level:
            send_message(peer_id, "❌ Недостаточно прав.")
            return
            
        start_ping = time.time()
        stats = get_stats()
        end_ping = time.time()
        response_time = (end_ping - start_ping) * 1000

        ping_msg = (
            f"🏓 **{BOT_NAME} - Статистика**\n\n"
            f"⏱ **Аптайм:** {stats['uptime']}\n"
            f"📥 **Запросов/мин:** {stats['avg_requests']:.2f}\n"
            f"⚙️ **Команд/мин:** {stats['avg_commands']:.2f}\n"
            f"⚡ **Пинг:** {response_time:.2f} мс\n\n"
            f"👑 **Владелец:** [id{OWNER_ID}|Основатель]"
        )
        
        send_message(peer_id, ping_msg)
        
    elif text.startswith("/ip"):
        send_message(peer_id, f"🌐 **{BOT_NAME} - Информация о сервере**\n\n"
                         "Сервер: Arion Manager Hosting\n"
                         "Статус: ✅ Онлайн\n"
                         "Для техподдержки: /report")
                         
    elif text.startswith("/offer"):
        offer_msg = (
            f"📜 **{BOT_NAME} - Публичная оферта**\n\n"
            "1. **Общие положения:**\n"
            "Бот предназначен для управления чёрными списками игроков в SAMP/CRMP проектах.\n\n"
            "2. **Использование:**\n"
            "Разрешено только с разрешения владельца проекта.\n\n"
            "3. **Права доступа:**\n"
            "Владелец бота имеет полный контроль над всеми функциями.\n\n"
            "4. **Ответственность:**\n"
            "Администраторы несут ответственность за свои действия.\n\n"
            "5. **Конфиденциальность:**\n"
            "Данные пользователей защищены.\n\n"
            f"👑 **Владелец:** [id{OWNER_ID}|Основатель]\n"
            "📞 **Поддержка:** /report"
        )
        send_message(peer_id, offer_msg)
        
    elif text.startswith("/logs"):
        required_level = get_command_level("/logs")
        if admin_level < required_level:
            send_message(peer_id, "❌ Недостаточно прав.")
            return
            
        keyboard = {
            "inline": True,
            "buttons": [
                [{"action": {"type": "callback", "label": "Общий лог", "payload": '{"cmd":"logs_all"}'}, "color": "negative"}],
                [{"action": {"type": "callback", "label": "Лог модерации", "payload": '{"cmd":"logs_moders"}'}, "color": "negative"}],
                [{"action": {"type": "callback", "label": "Лог авто-разбана", "payload": '{"cmd":"logs_autounban"}'}, "color": "negative"}],
                [{"action": {"type": "callback", "label": "Лог сессии", "payload": '{"cmd":"logs_peer"}'}, "color": "negative"}],
            ]
        }

        send_message(peer_id, "📊 **Выберите тип логов:**", keyboard=keyboard)
        
    elif text.startswith("/clearlog"):
        required_level = get_command_level("/clearlog")
        if admin_level < required_level:
            send_message(peer_id, "❌ Недостаточно прав.")
            return
            
        try:
            for filename in ["alllogs.log", "moderators.log", "autounban.log", "peerid.log"]:
                with open(filename, "w", encoding="utf-8") as f:
                    f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Логи очищены пользователем [id{user_id}]\n")
                    
            send_message(peer_id, "✅ Логи очищены.")
            log_action(user_id, "Очистил логи", True)
        except Exception as e:
            send_message(peer_id, f"❌ Ошибка: {e}")
            
    elif text.startswith("/panel"):
        required_level = get_command_level("/panel")
        if admin_level < required_level:
            send_message(peer_id, "❌ Недостаточно прав.")
            return
            
        keyboard = {
            "inline": True,
            "buttons": [
                [{"action": {"type": "callback", "label": "📊 Статистика", "payload": '{"cmd":"ping"}'}, "color": "primary"}],
                [{"action": {"type": "callback", "label": "🧹 Очистить логи", "payload": '{"cmd":"clogs"}'}, "color": "secondary"}],
                [{"action": {"type": "callback", "label": "🗑️ Очистить БД", "payload": '{"cmd":"cdb"}'}, "color": "negative"}],
            ]
        }
        
        panel_msg = (
            f"⚙️ **{BOT_NAME} - Панель управления**\n\n"
            f"👤 **Пользователь:** [id{user_id}]\n"
            f"🛡 **Уровень:** {admin_level}\n"
            f"👑 **Владелец:** [id{OWNER_ID}|Основатель]\n\n"
            "Выберите действие:"
        )
        
        send_message(peer_id, panel_msg, keyboard=keyboard)
        
    elif text.startswith("/kick"):
        required_level = get_command_level("/kick")
        if admin_level < required_level:
            send_message(peer_id, "❌ Недостаточно прав.")
            return

        args = text.split()[1:]
        if len(args) < 2:
            send_message(peer_id, "⚠ Формат: /kick [id/ссылка] [причина]")
            return

        raw_uid = args[0]
        reason = " ".join(args[1:])

        uid = resolve_username(parse_user_id(raw_uid))
        if not uid:
            send_message(peer_id, f"❌ Пользователь не найден: {raw_uid}")
            return

        target_level = get_admin_level(uid)
        if target_level > admin_level and user_id != OWNER_ID:
            send_message(peer_id, f"❌ Нельзя кикнуть администратора с более высоким уровнем.")
            return

        try:
            vk.messages.removeChatUser(
                chat_id=peer_id - 2000000000,
                user_id=uid
            )
            name = get_user_info(uid)
            send_message(peer_id, f"✅ [id{uid}|{name}] кикнут.\n📄 Причина: {reason}")
            log_action(user_id, f"Кикнул {uid}: {reason}", True)
        except Exception as e:
            send_message(peer_id, f"❌ Ошибка: {e}")
            
    elif text.startswith("/warn"):
        required_level = get_command_level("/warn")
        if admin_level < required_level:
            send_message(peer_id, "❌ Недостаточно прав.")
            return

        args = text.split()[1:]
        if len(args) < 2:
            send_message(peer_id, "⚠ Формат: /warn [id/ссылка] [причина]")
            return

        raw_uid = args[0]
        reason = " ".join(args[1:])

        uid = resolve_username(parse_user_id(raw_uid))
        if not uid:
            send_message(peer_id, f"❌ Пользователь не найден: {raw_uid}")
            return

        target_level = get_admin_level(uid)
        if target_level > admin_level and user_id != OWNER_ID:
            send_message(peer_id, f"❌ Нельзя выдать варн администратору с более высоким уровнем.")
            return

        count = add_warning(peer_id, uid)
        name = get_user_info(uid)
        send_message(peer_id, f"⚠ [id{uid}|{name}] получил варн #{count}.\n📄 Причина: {reason}")
        log_action(user_id, f"Варн {uid} (#{count}): {reason}", True)

        if count >= 3:
            try:
                vk.messages.removeChatUser(
                    chat_id=peer_id - 2000000000,
                    user_id=uid
                )
                reset_warnings(peer_id, uid)
                send_message(peer_id, f"🚫 [id{uid}|{name}] получил 3 варна и кикнут!")
            except Exception as e:
                send_message(peer_id, f"⚠ Не удалось кикнуть: {e}")
                
    elif text.startswith("/unwarn"):
        required_level = get_command_level("/unwarn")
        if admin_level < required_level:
            send_message(peer_id, "❌ Недостаточно прав.")
            return

        args = text.split()[1:]
        if not args:
            send_message(peer_id, "⚠ Формат: /unwarn [id/ссылка]")
            return

        uid = resolve_username(parse_user_id(args[0]))
        if not uid:
            send_message(peer_id, f"❌ Пользователь не найден.")
            return

        reset_warnings(peer_id, uid)
        name = get_user_info(uid)
        send_message(peer_id, f"✅ Варны сняты с [id{uid}|{name}].")
        log_action(user_id, f"Снял варны с {uid}", True)
        
    elif text.startswith("/warnlist"):
        required_level = get_command_level("/warnlist")
        if admin_level < required_level:
            send_message(peer_id, "❌ Недостаточно прав.")
            return

        # Получаем варны для этого чата
        warnings_data = get_all_warnings(peer_id)
        
        if not warnings_data:
            send_message(peer_id, "✅ В этом чате нет пользователей с варнами.")
            return

        # Формируем сообщение
        message_lines = ["⚠ **Список предупреждений в этом чате:**\n"]
        
        for warning in warnings_data:
            user_id = warning[0]
            count = warning[1]
            user_name = get_user_info(user_id)
            
            message_lines.append(f"• [id{user_id}|{user_name}] — {count} варн(а)")
        
        # Добавляем информацию о системе варнов
        message_lines.append("\n📝 **Система варнов:**")
        message_lines.append("1 варн — предупреждение")
        message_lines.append("2 варна — последнее предупреждение")
        message_lines.append("3 варна — автоматический кик")
        
        full_message = "\n".join(message_lines)
        send_message(peer_id, full_message)
        
    elif text.startswith("/mute"):
        if admin_level < 1:
            send_message(peer_id, "❌ Недостаточно прав.")
            return

        args = text.split()[1:]
        if len(args) < 3:
            send_message(peer_id, "⚠ Формат: /mute [id/ссылка] [минуты] [причина]")
            return

        target_raw, minutes_raw, *reason_parts = args
        reason = " ".join(reason_parts)
        
        try:
            minutes = int(minutes_raw)
        except ValueError:
            send_message(peer_id, "❌ Неверное время.")
            return

        uid = resolve_username(parse_user_id(target_raw))
        if not uid:
            send_message(peer_id, "❌ Пользователь не найден.")
            return

        target_level = get_admin_level(uid)
        if target_level > admin_level and user_id != OWNER_ID:
            send_message(peer_id, "❌ Нельзя замутить администратора с более высоким уровнем.")
            return

        until = time.time() + (minutes * 60)
        muted_users[uid] = {"peer_id": peer_id, "until": until, "time": minutes}
        name = get_user_info(uid)
        send_message(peer_id, f"🤐 [id{uid}|{name}] замучен на {minutes} мин.\n📄 Причина: {reason}")
        log_action(user_id, f"Мут {uid} на {minutes} мин: {reason}", True)
        
    elif text.startswith("/unmute"):
        required_level = get_command_level("/unmute")
        if admin_level < required_level:
            send_message(peer_id, "❌ Недостаточно прав.")
            return

        args = text.split()[1:]
        if not args:
            # Показываем список активных мутов в этом чате
            active_mutes = get_all_active_mutes()
            if not active_mutes:
                send_message(peer_id, "✅ Нет активных мутов.")
                return
            
            # Фильтруем муты для этого чата
            chat_mutes = []
            for mute_info in active_mutes:
                mute_user_id = mute_info["user_id"]
                # Проверяем, есть ли пользователь в этом чате
                try:
                    members = vk.messages.getConversationMembers(peer_id=peer_id)
                    member_ids = [m['member_id'] for m in members['items']]
                    if mute_user_id in member_ids:
                        chat_mutes.append(mute_info)
                except:
                    continue
            
            if not chat_mutes:
                send_message(peer_id, "✅ В этом чате нет активных мутов.")
                return
            
            # Формируем список
            message = "🔇 **Активные муты в этом чате:**\n\n"
            for mute in chat_mutes:
                user_name = get_user_info(mute["user_id"])
                admin_name = get_user_info(mute["admin_id"])
                
                # Рассчитываем оставшееся время
                end_time = datetime.strptime(mute["end_time"], "%Y-%m-%d %H:%M:%S")
                time_left = end_time - datetime.now()
                minutes_left = max(0, int(time_left.total_seconds() / 60))
                
                message += f"👤 [id{mute['user_id']}|{user_name}]\n"
                message += f"📄 Причина: {mute['reason']}\n"
                message += f"⏳ Осталось: {minutes_left} мин\n"
                message += f"👮 Замутил: [id{mute['admin_id']}|{admin_name}]\n\n"
            
            message += "👉 Для снятия мута: /unmute [id]"
            send_message(peer_id, message)
            return
        
        # Снимаем мут с указанного пользователя
        target_raw = args[0]
        uid = resolve_username(parse_user_id(target_raw))
        
        if not uid:
            send_message(peer_id, "❌ Пользователь не найден.")
            return
        
        # Проверяем уровень цели
        target_level = get_admin_level(uid)
        if target_level > admin_level and user_id != OWNER_ID:
            send_message(peer_id, "❌ Нельзя снять мут у администратора с более высоким уровнем.")
            return
        
        # Проверяем, есть ли активный мут
        mute_info = get_mute(uid)
        if not mute_info:
            send_message(peer_id, f"✅ У [id{uid}|пользователя] нет активного мута.")
            return
        
        # Удаляем из базы данных
        remove_mute(uid)
        
        # Удаляем из временных переменных (если используются)
        if uid in muted_users:
            del muted_users[uid]
        if uid in mute_tracker:
            del mute_tracker[uid]
        
        name = get_user_info(uid)
        admin_name = get_user_info(user_id)
        
        # Отправляем уведомление пользователю
        try:
            vk.messages.send(
                peer_id=uid,
                message=f"✅ **ВАШ МУТ СНЯТ**\n\n👮 Администратор: [id{user_id}|{admin_name}]\n💬 Причина снятия: досрочное снятие наказания",
                random_id=get_random_id()
            )
        except:
            pass  # Если не удалось отправить уведомление
        
        send_message(peer_id, f"✅ Мут снят с [id{uid}|{name}].")
        log_action(user_id, f"Снял мут с {uid}", True)
        
    elif text.startswith("/add"):
        args = text.split()[1:]
        if not args:
            send_message(peer_id, "⚠ Формат: /add [id/ссылка]")
            return

        uid = resolve_username(parse_user_id(args[0]))
        if not uid:
            send_message(peer_id, "❌ Пользователь не найден.")
            return

        add_user(peer_id, uid)
        
    elif text.startswith("/sync"):
        try:
            conn = sqlite3.connect("database.db")            
            cursor = conn.cursor()
            cursor.execute("INSERT OR REPLACE INTO synced_chats (peer_id) VALUES (?)", (peer_id,))
            conn.commit()
            send_message(peer_id, "✅ Чат синхронизирован с автоочисткой.")
            log_action(user_id, f"Синхронизировал чат {peer_id}", True)
        except Exception as e:
            send_message(peer_id, f"❌ Ошибка: {e}")
            
    elif text.startswith("/report"):
        args = text.split(" ", 1)
        if len(args) < 2:
            send_message(peer_id, "⚠ Формат: /report [текст вопроса]")
            return

        report_text = args[1]
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        conn = sqlite3.connect("database.db")
        cursor = conn.cursor()
        cursor.execute("INSERT INTO reports (user_id, text, created_at) VALUES (?, ?, ?)", (user_id, report_text, now))
        conn.commit()

        send_message(peer_id, "✅ Ваш вопрос отправлен. Ожидайте ответа!")
        
    elif text.startswith("/question"):
        parts = text.split(maxsplit=1)
        if len(parts) < 2:
            send_message(peer_id, "⚠ Формат: /question [сообщение]")
            return

        message_text = parts[1]
        sender_name = get_user_info(user_id)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        admins = get_all_admins()
        message = (
            f"📨 **Вопрос от пользователя**\n\n"
            f"👤 [id{user_id}|{sender_name}]\n"
            f"🕒 {timestamp}\n"
            f"💬 {message_text}"
        )

        for admin_id, level in admins:
            if level >= 3:
                try:
                    vk.messages.send(
                        peer_id=admin_id,
                        message=message,
                        random_id=get_random_id()
                    )
                except:
                    pass

        send_message(peer_id, "✅ Вопрос отправлен администрации.")
        
    elif text.startswith("/answer"):
        required_level = get_command_level("/answer")
        if admin_level < required_level:
            send_message(peer_id, "❌ Недостаточно прав.")
            return

        parts = text.split(maxsplit=2)
        if len(parts) < 3:
            send_message(peer_id, "⚠ Формат: /answer [id/ссылка] [текст]")
            return

        uid = resolve_username(parse_user_id(parts[1]))
        if not uid:
            send_message(peer_id, "❌ Пользователь не найден.")
            return

        message_text = parts[2]
        answer_number = get_today_answer_count()

        try:
            vk.messages.send(
                peer_id=uid,
                message=f"📨 **Ответ от администратора**\n\nНомер: #{answer_number}\nТекст: {message_text}\n\n❓ Новый вопрос: /question",
                random_id=get_random_id()
            )
            
            with open(ANSWER_LOG_PATH, "a", encoding="utf-8") as f:
                f.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | to: {uid} | #{answer_number}\n")
                
            send_message(peer_id, f"✅ Ответ #{answer_number} отправлен [id{uid}|пользователю].")
            log_action(user_id, f"Ответил {uid} (#{answer_number})", True)
        except Exception as e:
            send_message(peer_id, f"❌ Ошибка: {e}")
            
    elif text.startswith("/reps"):
        if admin_level < 4 and user_id != OWNER_ID:
            send_message(peer_id, "❌ Только администраторы 4+ уровня.")
            return
            
        send_reports_page(peer_id)
        
    elif text.startswith("/delrep"):
        if admin_level < 4 and user_id != OWNER_ID:
            send_message(peer_id, "❌ Только администраторы 4+ уровня.")
            return

        args = text.split()[1:]
        if not args:
            send_message(peer_id, "⚠ Формат: /delrep [номер/all]")
            return

        target = args[0].lower()
        conn = sqlite3.connect("database.db")
        cursor = conn.cursor()

        if target == "all":
            cursor.execute("DELETE FROM reports")
            send_message(peer_id, "✅ Все репорты удалены.")
        else:
            if not target.isdigit():
                send_message(peer_id, "❌ Неверный номер.")
                return
                
            cursor.execute("DELETE FROM reports WHERE id = ?", (int(target),))
            if cursor.rowcount > 0:
                send_message(peer_id, f"✅ Репорт #{target} удалён.")
            else:
                send_message(peer_id, f"❌ Репорт #{target} не найден.")
                
        conn.commit()
        conn.close()
        log_action(user_id, f"Удалил репорт {target}", True)
        
    elif text.startswith("/sysinfo"):
        required_level = get_command_level("/sysinfo")
        if admin_level < required_level:
            send_message(peer_id, "❌ Недостаточно прав.")
            return
            
        args = text.split()[1:]
        if not args:
            send_message(peer_id, "⚠ Формат: /sysinfo [id/ссылка]")
            return

        uid = resolve_username(parse_user_id(args[0]))
        if not uid:
            send_message(peer_id, "❌ Пользователь не найден.")
            return

        user_info = vk.users.get(user_ids=uid, fields="first_name,last_name")[0]
        name = f"{user_info['first_name']} {user_info['last_name']}"
        first_contact = get_first_contact_date(uid) or "Нет данных"
        bl_info = get_blacklist_info(uid)
        blacklist_count = 1 if bl_info else 0
        admin_level_target = get_admin_level(uid)
        is_staff = "Да" if admin_level_target >= 4 else "Нет"
        
        position = "—"
        if admin_level_target == 7:
            position = "Владелец"
        elif admin_level_target == 6:
            position = "Со-Владелец"
        elif admin_level_target == 5:
            position = "Разработчик"
        elif admin_level_target == 4:
            position = "Саппорт"
        elif admin_level_target == 3:
            position = "Старший администратор"
        elif admin_level_target == 2:
            position = "Младший администратор"
        elif admin_level_target == 1:
            position = "Модератор"

        msg = (
            f"📊 **Информация о пользователе**\n\n"
            f"👤 [id{uid}|{name}]\n"
            f"🆔 ID: {uid}\n"
            f"📅 Первый контакт: {first_contact}\n"
            f"🛡 Уровень админа: {admin_level_target} ({position})\n"
            f"🚫 В ЧС: {'Да' if blacklist_count else 'Нет'}\n"
            f"👨‍💼 Сотрудник: {is_staff}\n\n"
            f"🔍 **Проверить:**\n"
            f"• /checkban [id{uid}|{name.split()[0]}]\n"
            f"• /syslist\n"
            f"• /banlist"
        )

        send_message(peer_id, msg)
        log_action(user_id, f"Запросил инфо о {uid}", True)
        
    elif text.startswith("/setsupport") or text.startswith("/setcoder") or text.startswith("/setdep"):
        if user_id != OWNER_ID:
            send_message(peer_id, "❌ Только владелец может назначать сотрудников.")
            return
            
        args = text.split()[1:]
        if not args:
            send_message(peer_id, "⚠ Формат: /setsupport [id/ссылка]")
            return

        uid = resolve_username(parse_user_id(args[0]))
        if not uid:
            send_message(peer_id, "❌ Пользователь не найден.")
            return
            
        level = 4  # Саппорт по умолчанию
        if text.startswith("/setcoder"):
            level = 5  # Разработчик
        elif text.startswith("/setdep"):
            level = 6  # Со-владелец
            
        add_admin(uid, level)
        name = get_user_info(uid)
        
        position = "Саппорт"
        if level == 5:
            position = "Разработчик"
        elif level == 6:
            position = "Со-Владелец"
            
        send_message(peer_id, f"✅ [id{uid}|{name}] теперь {position} (уровень {level}).")
        log_action(user_id, f"Назначил {uid} как {position}", True)
    
    # ===================== ОБРАБОТКА ТИПОВ БЛОКИРОВОК =====================
    elif text.upper() in ["ЧСП", "ОЧС", "ЧС ПОСТОВ", "ЧС АДМИНИСТРАЦИИ"]:
        if user_id in globals().get('temp_bans', {}):
            temp_data = globals()['temp_bans'][user_id]
            
            type_map = {
                "ЧСП": "ЧСП",
                "ОЧС": "ОЧС",
                "ЧС ПОСТОВ": "ЧС(ПОСТ)",
                "ЧС АДМИНИСТРАЦИИ": "ЧСА"
            }
            
            ban_type = type_map.get(text.upper())
            if not ban_type:
                send_message(peer_id, "❌ Неверный тип блокировки.")
                return
                
            final_reason = f"{temp_data['reason']} | {ban_type}"
            add_to_blacklist(
                temp_data["target_id"],
                final_reason,
                temp_data["days"],
                user_id,
                datetime.now().strftime("%Y-%m-%d %H:%M")
            )

            duration_text = "навсегда" if temp_data["days"] == "PERMANENT" else f"на {temp_data['days']} дней"
            name = get_user_info(temp_data['target_id'])
            send_message(
                peer_id,
                f"✅ [id{temp_data['target_id']}|{name}] добавлен в {ban_type} {duration_text}.\n"
                f"📄 Причина: {final_reason}"
            )
            log_action(user_id, f"Забанил {temp_data['target_id']} ({ban_type}) {duration_text}", True)
            
            # Отправляем уведомление пользователю
            try:
                admin_name = get_user_info(user_id)
                ban_message = (
                    f"🚫 **ВЫ ЗАБЛОКИРОВАНЫ**\n\n"
                    f"📄 Причина: {final_reason}\n"
                    f"⏳ Срок: {duration_text}\n"
                    f"🛡 Администратор: [id{user_id}|{admin_name}]\n\n"
                    f"ℹ Для обжалования обратитесь к администрации."
                )
                vk.messages.send(
                    peer_id=temp_data['target_id'],
                    message=ban_message,
                    random_id=get_random_id()
                )
            except:
                pass
                
            # Удаляем временные данные
            del globals()['temp_bans'][user_id]

# ===================== ОБРАБОТКА CALLBACK КНОПОК =====================
def handle_event(obj):
    peer_id = obj['peer_id']
    event_id = obj['event_id']
    user_id = obj['user_id']
    
    payload_raw = obj['payload']
    if isinstance(payload_raw, dict):
        payload = payload_raw
    else:
        payload = json.loads(payload_raw)

    cmd = payload.get("cmd")
    admin_level = get_admin_level(user_id)

    def snackbar(text):
        vk.messages.sendMessageEventAnswer(
            event_id=event_id,
            user_id=user_id,
            peer_id=peer_id,
            event_data=json.dumps({
                "type": "show_snackbar",
                "text": text
            })
        )

    if cmd == "logs_all":
        required_level = get_command_level("/logs")
        if admin_level < required_level and user_id != OWNER_ID:
            snackbar("❌ Недостаточно прав.")
            return
            
        try:
            with open("alllogs.log", encoding="utf-8") as f:
                lines = f.readlines()
            msg = "".join(lines[-20:])
            name = get_user_info(user_id)
            if len(msg) > 4000:
                msg = msg[-4000:]
            send_message(peer_id, f"📜 **Последние 20 записей:**\n\n{msg}\n\n👤 [id{user_id}|{name}]")
            snackbar("✅ Логи отправлены")
        except Exception as e:
            send_message(peer_id, "❌ Ошибка чтения логов")
            snackbar("❌ Ошибка")

    elif cmd == "logs_moders":
        required_level = get_command_level("/logs")
        if admin_level < required_level and user_id != OWNER_ID:
            snackbar("❌ Недостаточно прав.")
            return
            
        try:
            with open("moderators.log", encoding="utf-8") as f:
                lines = f.readlines()
            msg = "".join(lines[-20:])
            name = get_user_info(user_id)
            if len(msg) > 4000:
                msg = msg[-4000:]
            send_message(peer_id, f"📜 **Логи модерации:**\n\n{msg}\n\n👤 [id{user_id}|{name}]")
            snackbar("✅ Логи отправлены")
        except:
            send_message(peer_id, "❌ Нет логов модерации")
            snackbar("❌ Нет логов")

    elif cmd == "logs_autounban":
        required_level = get_command_level("/logs")
        if admin_level < required_level and user_id != OWNER_ID:
            snackbar("❌ Недостаточно прав.")
            return
            
        try:
            with open("autounban.log", encoding="utf-8") as f:
                lines = f.readlines()
            msg = "".join(lines[-20:])
            name = get_user_info(user_id)
            if len(msg) > 4000:
                msg = msg[-4000:]
            send_message(peer_id, f"📜 **Логи авторазбана:**\n\n{msg}\n\n👤 [id{user_id}|{name}]")
            snackbar("✅ Логи отправлены")
        except:
            send_message(peer_id, "❌ Нет логов авторазбана")
            snackbar("❌ Нет логов")

    elif cmd == "logs_peer":
        required_level = get_command_level("/logs")
        if admin_level < required_level and user_id != OWNER_ID:
            snackbar("❌ Недостаточно прав.")
            return
            
        try:
            with open("peerid.log", encoding="utf-8") as f:
                lines = f.readlines()
            msg = "".join(lines[-20:])
            name = get_user_info(user_id)
            if len(msg) > 4000:
                msg = msg[-4000:]
            send_message(peer_id, f"📜 **Логи сессий:**\n\n{msg}\n\n👤 [id{user_id}|{name}]")
            snackbar("✅ Логи отправлены")
        except:
            send_message(peer_id, "❌ Нет логов сессий")
            snackbar("❌ Нет логов")

    elif cmd == "bbanlist":
        required_level = get_command_level("/banlist")
        if admin_level < required_level and user_id != OWNER_ID:
            snackbar("❌ Недостаточно прав.")
            return
            
        banlist = get_all_banned_users()
        if not banlist:
            send_message(peer_id, "✅ Нет пользователей в ЧС.")
            snackbar("✅ Чисто")
            return

        msg = "🚫 **Список заблокированных:**\n\n"
        for uid, reason, until, admin_id in banlist:
            name = get_user_info(uid)
            admin_name = get_user_info(admin_id)
            duration = "Навсегда" if until == "PERMANENT" else f"до {until}"
            msg += f"🔘 [id{uid}|{name}]\n📄 {reason}\n⏳ {duration}\n🛡 [id{admin_id}|{admin_name}]\n\n"

        send_message(peer_id, msg)
        snackbar("✅ Список отправлен")

    elif cmd == "balist":
        required_level = get_command_level("/admins")
        if admin_level < required_level and user_id != OWNER_ID:
            snackbar("❌ Недостаточно прав.")
            return
            
        conn = sqlite3.connect("database.db")
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, level FROM admins WHERE level BETWEEN 1 AND 3 ORDER BY level DESC")
        rows = cursor.fetchall()

        if not rows:
            send_message(peer_id, "ℹ Нет администраторов 1-3 уровня.")
            snackbar("✅ Список отправлен")
            return

        lvl3, lvl2, lvl1 = [], [], []
        for uid, lvl in rows:
            name = get_user_info(uid)
            if lvl == 3:
                lvl3.append(f"[id{uid}|{name}]")
            elif lvl == 2:
                lvl2.append(f"[id{uid}|{name}]")
            elif lvl == 1:
                lvl1.append(f"[id{uid}|{name}]")

        msg = "👮 **Старший администратор (3):**\n" + ("\n".join(lvl3) if lvl3 else "—") + "\n\n"
        msg += "👮‍♂️ **Младший администратор (2):**\n" + ("\n".join(lvl2) if lvl2 else "—") + "\n\n"
        msg += "👨‍🎓 **Модератор (1):**\n" + ("\n".join(lvl1) if lvl1 else "—")

        send_message(peer_id, msg)
        snackbar("✅ Список отправлен")

    elif cmd == "bhelp":
        help_msg = (
            f"📋 **{BOT_NAME} - Основные команды**\n\n"
            f"🔰 **ЧС:** /ban, /aban, /unban, /checkban, /banlist\n"
            f"🔰 **Система:** /sysban, /offsysban, /syslist\n"
            f"🔰 **Админы:** /admins, /staff, /setadmin, /rr\n"
            f"🔰 **Модерация:** /kick, /warn, /unwarn, /warnlist, /mute\n"
            f"🔰 **Инфо:** /start, /help, /offer, /ping, /ip\n"
            f"🔰 **Связь:** /report, /question, /answer\n"
            f"🔰 **Система:** /logs, /panel, /sysinfo\n\n"
            f"👑 **Владелец:** [id{OWNER_ID}|Основатель]"
        )
        send_message(peer_id, help_msg)
        snackbar("✅ Справка отправлена")

    elif cmd == "boffer":
        offer_msg = (
            f"📜 **{BOT_NAME} - Публичная оферта**\n\n"
            "Бот предназначен для управления проектами SAMP/CRMP.\n"
            "Владелец имеет полный контроль над системой.\n"
            "Использование бота означает согласие с условиями.\n\n"
            f"👑 **Владелец:** [id{OWNER_ID}|Основатель]\n"
            "📞 **Поддержка:** /report"
        )
        send_message(peer_id, offer_msg)
        snackbar("✅ Оферта отправлена")

    elif cmd == "clogs":
        required_level = get_command_level("/clearlog")
        if admin_level < required_level and user_id != OWNER_ID:
            snackbar("❌ Недостаточно прав.")
            return
            
        try:
            for filename in ["alllogs.log", "moderators.log", "autounban.log", "peerid.log"]:
                with open(filename, "w", encoding="utf-8") as f:
                    f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Логи очищены [id{user_id}]\n")
                    
            send_message(peer_id, "✅ Логи очищены.")
            snackbar("✅ Логи очищены")
            log_action(user_id, "Очистил логи через панель", True)
        except:
            send_message(peer_id, "❌ Ошибка")
            snackbar("❌ Ошибка")

    elif cmd == "ping":
        required_level = get_command_level("/ping")
        if admin_level < required_level and user_id != OWNER_ID:
            snackbar("❌ Недостаточно прав.")
            return
            
        start_ping = time.time()
        stats = get_stats()
        end_ping = time.time()
        response_time = (end_ping - start_ping) * 1000

        ping_msg = (
            f"🏓 **{BOT_NAME} - Статистика**\n\n"
            f"⏱ Аптайм: {stats['uptime']}\n"
            f"📥 Запросов/мин: {stats['avg_requests']:.2f}\n"
            f"⚙️ Команд/мин: {stats['avg_commands']:.2f}\n"
            f"⚡ Пинг: {response_time:.2f} мс\n\n"
            f"👤 Запросил: [id{user_id}]"
        )
        
        send_message(peer_id, ping_msg)
        snackbar("✅ Статистика отправлена")

    elif cmd == "cdb":
        required_level = get_command_level("/panel")
        if admin_level < required_level and user_id != OWNER_ID:
            snackbar("❌ Недостаточно прав.")
            return
            
        keyboard = {
            "inline": True,
            "buttons": [
                [{"action": {"type": "callback", "label": "✅ Да, очистить", "payload": '{"cmd":"cdb_yes"}'}, "color": "negative"}],
                [{"action": {"type": "callback", "label": "❌ Отмена", "payload": '{"cmd":"cdb_no"}'}, "color": "secondary"}],
            ]
        }
        
        send_message(peer_id, 
            f"⚠ **ВНИМАНИЕ!**\n\n"
            f"Все данные будут удалены.\n"
            f"Таблицы сохранятся.\n"
            f"Владелец будет восстановлен.\n\n"
            f"👤 [id{user_id}]",
            keyboard=keyboard
        )
        snackbar("⚠ Подтвердите действие")

    elif cmd == "cdb_yes":
        if user_id != OWNER_ID:
            snackbar("❌ Только владелец может очищать БД.")
            return
            
        clear_database("database.db", peer_id)
        snackbar("✅ БД очищена")

    elif cmd == "cdb_no":
        send_message(peer_id, "❌ Отменено.")
        snackbar("❌ Отменено")

    elif cmd == "reply_report":
        if admin_level < 4 and user_id != OWNER_ID:
            snackbar("❌ Только админы 4+ уровня.")
            return
            
        rep_id = payload.get("report_id")
        active_report_replies[user_id] = rep_id
        snackbar(f"✏️ Напишите ответ для #{rep_id} или /cancel")

    elif cmd == "reps_page":
        if admin_level < 4 and user_id != OWNER_ID:
            snackbar("❌ Только админы 4+ уровня.")
            return
            
        new_offset = payload.get("offset", 0)
        edit_id = payload.get("edit_id")
        send_reports_page(peer_id, new_offset, edit_id)
        snackbar("✅ Страница обновлена")
        
    elif cmd == "compare_stats":
        user_stats = get_user_stats(user_id)
        play_time = user_stats["play_time_hours"]
        
        # Получаем среднее время игры
        conn = sqlite3.connect("database.db")
        cursor = conn.cursor()
        cursor.execute("SELECT AVG(play_time_hours) FROM user_stats WHERE play_time_hours > 0")
        avg_time = cursor.fetchone()[0] or 0
        conn.close()
        
        # Определяем позицию
        top_players = get_top_players("play_time_hours", 100)
        position = None
        for i, (uid, time_val) in enumerate(top_players, 1):
            if uid == user_id:
                position = i
                break
        
        comparison_message = (
            f"📈 **ВАША ПОЗИЦИЯ СРЕДИ ИГРОКОВ**\n\n"
            
            f"⏱️ Ваше время: {play_time} часов\n"
            f"📊 Среднее время: {avg_time:.1f} часов\n"
            f"🥇 Позиция в топе: {position if position else '>100'}\n\n"
            
            f"📊 **СТАТИСТИКА ПРОЕКТА:**\n"
            f"• Всего активных игроков: {len(top_players)}\n"
            f"• Макс. время игры: {top_players[0][1] if top_players else 0} часов\n"
            f"• Мин. время в топ-100: {top_players[-1][1] if len(top_players) >= 100 else 0} часов\n\n"
        )
        
        send_message(peer_id, comparison_message)
        snackbar("✅ Сравнение статистики")
        
    elif cmd == "top_players":
        top_players = get_top_players("play_time_hours", 10)
        
        if not top_players:
            send_message(peer_id, "🏆 **Топ игроков пуст**\nПока никто не набрал статистику!")
            snackbar("❌ Топ пуст")
            return
        
        message_lines = ["🏆 **ТОП-10 ИГРОКОВ ПО ВРЕМЕНИ ИГРЫ**\n"]
        
        for i, (uid, play_time) in enumerate(top_players, 1):
            user_name = get_user_info(uid)
            medal = ""
            
            if i == 1:
                medal = "🥇 "
            elif i == 2:
                medal = "🥈 "
            elif i == 3:
                medal = "🥉 "
            else:
                medal = f"{i}. "
            
            message_lines.append(f"{medal}[id{uid}|{user_name}] — {play_time} часов")
        
        message_lines.append(f"\n📊 Ваша позиция: ... (используйте 'Сравнить с другими')")
        message_lines.append(f"⏱️ Обновляется ежедневно")
        
        send_message(peer_id, "\n".join(message_lines))
        snackbar("✅ Топ игроков")
        
    elif cmd == "my_goals":
        user_stats = get_user_stats(user_id)
        play_time = user_stats["play_time_hours"]
        
        goals_message = (
            f"🎯 **ВАШИ БЛИЖАЙШИЕ ЦЕЛИ**\n\n"
            
            f"🎮 **ИГРАЙТЕ С УДОВОЛЬСТВИЕМ!**"
        )
        
        send_message(peer_id, goals_message)
        snackbar("✅ Ваши цели")

# ===================== CALLBACK API =====================
@app.route("/callback", methods=["POST"])
def callback():
    data = request.get_json(force=True)
    
    if data.get('type') == 'confirmation':
        return CONFIRMATION_TOKEN

    if CALLBACK_SECRET and data.get('secret') != CALLBACK_SECRET:
        return 'access denied'

    elif data["type"] == "message_new":
        try:
            message = data["object"]["message"]
            process_message(message)
        except Exception as e:
            print(f"❌ Ошибка: {e}")

        return "ok"

    elif data.get('type') == 'message_event':
        try:
            handle_event(data['object'])
        except Exception as e:
            print(f"❌ Ошибка callback: {e}")
        return 'ok'

    return 'ok'

# ===================== HEALTH CHECK =====================
@app.route('/health', methods=['GET'])
def health_check():
    return 'OK', 200

@app.route('/ping', methods=['GET'])
def ping():
    return 'pong', 200

if __name__ == '__main__':
    print(f"🚀 {BOT_NAME} запущен!")
    print(f"👑 Владелец: {OWNER_ID}")
    print(f"🔧 ID группы: {GROUP_ID}")
    
    import os
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)