# Автор: @airwals (VK,tg)
# При пересливе (хз какой переслив этого говна) указывайте автора, плз.
# Код сделан из говна и палок через нейронку и мой не очень умный мозг. Но, в принципе, сделать из него конфетку можно (я могу, но нет желания, концепция говна)
# Мои контакты (full):
# tg: (ЛС закрыт для обычных юзеров: t.me/airwalsbot
# vk: vk.com/airwals
# другого вам знать и не надо

# Импортируем настройки из других файлов
from db import *
from utils import *
from config import VK_TOKEN, CONFIRMATION_TOKEN, CALLBACK_SECRET

# Импортируем основные библиотеки
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from flask import Flask, request
from vk_api.keyboard import VkKeyboard, VkKeyboardColor
from types import SimpleNamespace

# Импортируем вспомагательные библиотеки
import re
import sqlite3
import os
import feedparser
import time
import requests
import threading
import vk_api
import json
import random
import string

# Переменные для блокировки чата
muted_users = {}
mute_tracker = {}
# Проверка активных репортов
active_report_replies = {}

active_personal_chats = {}

# Метрики команды пинг
start_time = time.time()
total_requests = 0
total_commands = 0

# Инициализация базы 
init_db()

# VK API
vk_session = vk_api.VkApi(token=VK_TOKEN)
vk = vk_session.get_api()

# Flask app
app = Flask(__name__)

ANSWER_LOG_PATH = "answer_log.txt"


def send_message(peer_id, message, keyboard=None):
    vk.messages.send(
        peer_id=peer_id,
        message=message,
        random_id=random.randint(1, 10**9),
        keyboard=json.dumps(keyboard) if keyboard else None
    )

def chunk_messages(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i:i + n]

def get_stats(): #логика пинга
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

def moders_action(user_id: int, action: str, is_mod_action: bool = False):
    log_entry = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {action}\n"
    with open('moderators.log', 'a', encoding='utf-8') as f:
        f.write(log_entry)

def peer_action(user_id: int, action: str, is_mod_action: bool = False):
    log_entry = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {action}\n"
    with open('peerid.log', 'a', encoding='utf-8') as f:
        f.write(log_entry)

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

def notify_all_chats(vk, message):  #уведомление во все чаты во время cусбана
    try:
        response = vk.messages.getConversations(count=200)
        for item in response['items']:
            peer_id = item['conversation']['peer']['id']
            if peer_id > 2000000000: 
                try:
                    vk.messages.send(peer_id=peer_id, message=message, random_id=get_random_id())
                except Exception as e:
                    print(f"Не удалось отправить сообщение в чат {peer_id}: {e}")
                    continue
    except Exception as e:
        print(f"[Ошибка notify_all_chats]: {e}")

def get_sysban_info(user_id):
    try:
        result = get_sysban_from_db(user_id)
        if result:
            reason = result[0]  
            admin_id = result[1]  
            return reason, admin_id
        return None, None
    except Exception as e:
        print(f"[Ошибка get_sysban_info]: {e}")
        return None, None

def get_user_info(user_id):
    try:
        user = vk.users.get(user_ids=user_id)
        if user:
            return f"{user[0]['first_name']} {user[0]['last_name']}"
        return "Пользователь не найден"
    except Exception as e:
        print(f"[Ошибка get_user_info]: {e}")
        return "Не удалось получить информацию о пользователе"

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



BLOCK_TYPES = {
    "ЧСП": " | ЧСП",
    "ОЧС": " | ОЧС",
    "ЧС ПОСТОВ": " | ЧС(ПОСТ)",
    "ЧС АДМИНИСТРАЦИИ": " | ЧСА",
}

pending_bans = {} 
temp_bans = {} 

RSS_FILE = "rss_threads.json"

def load_rss_data():
    if os.path.exists(RSS_FILE):
        with open(RSS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_rss_data(data):
    with open(RSS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def clean_bot_mention(text: str) -> str:
    return re.sub(r"\[club\d+\|[^\]]+\]\s*", "", text).strip()

def get_new_rss_items(url, seen):
    headers = {
        "User-Agent": "Mozilla/5.0"
    }
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, "xml")

        new_items = []
        for item in soup.find_all("item"):
            title_tag = item.find("title")
            link_tag = item.find("link")

            if title_tag and link_tag:
                title = title_tag.text.strip()
                link = link_tag.text.strip()
                if link not in seen:
                    new_items.append({"title": title, "link": link})
                    seen.add(link)
        return new_items, seen
    except Exception as e:
        print(f"[RSS BEAUTIFULSOUP ERROR]: {e}")
        return [], seen

import time

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

    conn.commit()
    conn.close()

    messages.append("🎉 Все данные удалены, таблицы сохранены.")
    vk.messages.send(peer_id=peer_id, message="\n".join(messages), random_id=0)

def cmd_mute(peer_id, admin_id, args):
    if get_admin_level(admin_id) < 1:
        send_message(peer_id, "❌ Недостаточно прав.")
        return

    if len(args) < 3:
        send_message(peer_id, "Использование: /mute [id/ссылка] [минуты] [причина]")
        return

    target_raw, minutes_raw, *reason_parts = args
    reason = " ".join(reason_parts)
    
    try:
        minutes = int(minutes_raw)
    except ValueError:
        send_message(peer_id, "❌ Время мута должно быть числом (в минутах).")
        return

    target_username = parse_user_id(target_raw)
    target_id = resolve_username(target_username)

    if not target_id:
        send_message(peer_id, "❌ Не удалось найти пользователя.")
        return

    target_level = get_admin_level(target_id)
    admin_level = get_admin_level(admin_id)

    if admin_level <= target_level:
        send_message(peer_id, "❌ Нельзя замутить администратора с равным или большим уровнем.")
        return

    until = time.time() + (minutes * 60)
    muted_users[target_id] = {"peer_id": peer_id, "until": until, "time": minutes}
    name = get_user_info(target_id)
    send_message(peer_id, f"🤐 [id{target_id}|[{name}] замучен на {minutes} мин.\nПричина: {reason}")

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
        
def get_mutual_chats(user_id):
    mutual_chats = []

    try:
        data = vk.messages.getConversationMembers(peer_id=peer_id)
        members = []

        for item in data.get("items", []):
            mid = item.get("member_id")
            if mid:
                members.append(mid)

        for p in data.get("profiles", []):
            members.append(p.get("id"))

        for g in data.get("groups", []):
            members.append(-g.get("id"))

        print(f"[INFO] Всего участников чата {peer_id}: {len(members)}")

    except Exception as e:
        print(f"[WARN] Не удалось проверить чат {peer_id}: {e}")

    return mutual_chats
    
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
        
def get_first_contact_date(user_id):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT first_contact FROM user_contacts WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if row:
        return row[0]
    else:
        return "Неизвестно"

GLOBAL_DB = "global_data.db"

def get_unity_peer_ids(current_peer_id):
    conn = sqlite3.connect("database.db")
    cur = conn.cursor()

    cur.execute("SELECT code FROM unity_chats WHERE peer_id = ?", (current_peer_id,))
    row = cur.fetchone()
    if not row:
        return [current_peer_id]

    code = row[0]
    cur.execute("SELECT peer_id FROM unity_chats WHERE code = ?", (code,))
    peers = [r[0] for r in cur.fetchall()]
    conn.close()

    return peers


threading.Thread(target=auto_cleanup_banned, daemon=True).start()

threading.Thread(target=auto_unban_loop, daemon=True).start()

def process_message(message):
    global mute_tracker, mute_users
    print("ZAPROS")  
    peer_id = message.get("peer_id") or ("user_id")  # ✅
    user_id = message.get("from_id")
    text = message.get('text', '').strip()
    admin_level = get_admin_level(user_id)
    mute_info = get_mute(user_id)
    save_first_contact(user_id)

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
            
    if user_id in active_report_replies:
        rep_id = active_report_replies[user_id]

        if text.strip().lower() == "/cancel":
            del active_report_replies[user_id]
            send_message(peer_id, "❌ Ответ на репорт отменён.")
            process_message({"peer_id": peer_id, "from_id": user_id, "text": "/reps"})
            return
        conn = sqlite.connect("database.db")
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM reports WHERE id = ?", (rep_id,))
        row = cursor.fetchone()

        if row:
            target_uid = row[0]
            admin_id = user_id
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
                                        "admin_id": admin_id
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

    # Завершаем диалог
        del active_report_replies[user_id]
        return

    elif text.startswith("/checkban"):
        required_level = get_command_level("/checkban")
        if admin_level < required_level:
            send_message(peer_id, "❗ Ваш уровень администратора не соответствует минимальному для этой команды.")
            return

        args = text.split()[1:]
        if not args:
            send_message(peer_id, "❗ Укажи хотя бы одного пользователя для проверки.")
            return

        results = []
        for raw_uid in args:
            parsed = parse_user_id(raw_uid)
            uid = resolve_username(parsed)
            if not uid:
                results.append(f"🔘 {raw_uid}: ❌ Не удалось определить пользователя.")
                continue

            name = get_user_info(uid)

            # Проверка на системную блокировку
            sysban_reason, sysban_admin = get_sysban_info(uid)
            if sysban_reason:
                results.append(
                    f"🔘 [id{uid}|{name}]:\n⛔ Находится в системной блокировке.\n"
                    f"📄 Причина: {sysban_reason}\n"
                    f"🛡 Админ: [id{sysban_admin}|Сотрудник]"
                )
                continue

            bl_info = get_blacklist_info(uid)
            if bl_info:
                try:
                    formatted = format_blacklist_info(bl_info, vk, bl_info[3])
                    results.append(f"🔘 [id{uid}|{name}]:\n{formatted}")
                except Exception as e:
                    results.append(f"🔘 [id{uid}|{name}]: ⛔ В ЧС. ⚠ Ошибка при получении информации: {e}")
            else:
                results.append(f"🔘 [id{uid}|{name}]: ✅ Не заблокирован")

        message_result = "📋 Результаты проверки:\n\n" + "\n\n".join(results)
        send_message(peer_id, message_result)
        moders_action(user_id, f"{peer_id} Проверил на ЧС: {', '.join(args)}")
        log_action(peer_id, f"{peer_id} Проверил на ЧС: {', '.join(args)}")

    elif text.startswith(("/banlist", "Список блокировок")):
        send_message(peer_id, "🔃 Идет проверка данных.\nПожалуйста подождите...")

        required_level = get_command_level("/banlist")
        if admin_level < required_level:
            send_message(peer_id, "❗ Ваш уровень администратора не соответствует минимальному для этой команды.")
            return

        banlist = get_all_banned_users()
        if not banlist:
            send_message(peer_id, "❌ Нет пользователей в черном списке.")
            return

        msg = "🚫 Список заблокированных:\n"
        for uid, reason, until, admin_id in banlist:
            name = get_user_info(uid)
            msg += f"🔘 [id{uid}|{name}]\n⏳ До: {until}.\n📄 Причина: {reason}\n\n"

        send_message(peer_id, msg)
        log_action(user_id, f"{peer_id} Вывел список блокировок")

    elif text.startswith("/ban"):
        required_level = get_command_level("/ban")  # заменить команду на нужную
        if admin_level < required_level:
            send_message(peer_id, "❗ Ваш уровень администратора не соответствует минимальному для этой команды.")
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
            send_message(peer_id, "❌ ID не определен.")
            return
        name = get_user_info(uid)
        if get_blacklist_info(uid):
            send_message(peer_id, f"❗ Данный [id{uid}|{name}] уже находится в ЧС.")
            return

        try:
            days = int(parts[2])
            reason = parts[3]
            temp_bans[user_id] = {
                "target_id": uid,
                "days": days,
                "reason": reason,
                "admin_id": user_id,
                "type_stage": True,  # ожидаем тип
                "aban": False
            }
            send_message(peer_id,
                        "❔ Какой тип блокировки Вы хотите назначить пользователю?\n"
                        "Напишите в чат один из вариантов:\n👉 ЧСП, ОЧС, ЧС ПОСТОВ, ЧС АДМИНИСТРАЦИИ")
        except ValueError:
            send_message(peer_id, "❌ Неверное значение дней блокировки.")

    elif text.startswith("/aban"):
        required_level = get_command_level("/aban")  # заменить команду на нужную
        if admin_level < required_level:
            send_message(peer_id, "❗ Ваш уровень администратора не соответствует минимальному для этой команды.")
            return
        if peer_id > 2000000000:
            send_message(peer_id, "🔧 Занести в ЧС можно только в личных сообщениях.")
            return
        parts = text.split(maxsplit=2)
        if len(parts) < 3:
            send_message(peer_id, "⚠ Формат: /aban [id/ссылка] [причина]")
            return

        user_ids_raw = parts[1]
        reason = parts[2]
        target_ids = [resolve_username(parse_user_id(uid)) for uid in user_ids_raw.split(",")]

        for tid in target_ids:
            if not tid:
                send_message(peer_id, f"❌ Один из ID не распознан.")
                return

            name = get_user_info(tid)
            if get_blacklist_info(tid):
                send_message(peer_id, f"❗ [id{tid}|{name}] уже находится в черном списке.")
                return

            temp_bans[user_id] = {
                "target_id": tid,
                "reason": reason,
                "days": "PERMANENT",
                "type_stage": True
            }
            send_message(peer_id, "❓ Какой тип блокировки Вы хотите назначить пользователю?\nВведите: ЧСП, ОЧС, ЧС ПОСТОВ, ЧС АДМИНИСТРАЦИИ")
            break

    elif text.startswith("/unban"):
        required_level = get_command_level("/unban")  # заменить команду на нужную
        if admin_level < required_level:
            send_message(peer_id, "❗ Ваш уровень администратора не соответствует минимальному для этой команды.")
            return

        parts = text.split()
        if len(parts) < 2:
            send_message(peer_id, "⚠ Формат: /unban [id/ссылка]")
            return
        uid = resolve_username(parse_user_id(parts[1]))
        if not uid:
            send_message(peer_id, "❌ Пользователь не определен. Возможно, вы указали неверный ID.")
            return
        info = get_blacklist_info(uid)
        if info and info[2] == "PERMANENT" and admin_level < 3:
            send_message(peer_id, "❌ Только 4+ уровень администратора может снимать перманентный бан.")
            return
        remove_from_blacklist(uid)
        name = get_user_info(uid)
        send_message(peer_id, f"♻ [id{uid}|{name}] был разблокирован.\n"
                     "Спасибо за использование [club230228477|PROSTOBOT]")
        moders_action(user_id, f"{peer_id} Разблокировал {uid}")
        log_action(user_id, f"{peer_id} Разблокировал {uid}")

    elif text.startswith("/sysban"):
        required_level = get_command_level("/sysban")  # заменить команду на нужную
        if admin_level < required_level:
            send_message(peer_id, "❗ Ваш уровень администратора не соответствует минимальному для этой команды.")
            return
        parts = text.split(maxsplit=2)
        if len(parts) < 3:
            send_message(peer_id, "⚠ Формат: /sysban [id или ссылка] [причина]")
            return
        target = parse_user_id(parts[1])
        uid = resolve_username(target)
        if uid is None:
            send_message(peer_id, "❌ Не удалось определить пользователя по ID или shortname.")
            return

        reason = parts[2]
        add_to_sysban(uid, reason, user_id)
        name = get_user_info(user_id)
        try:
            vk.messages.send(
                peer_id=uid,
                message=(
                    f"🔒 Вы были заблокированы в системе бота.\n"
                    f"📄 Причина: {reason}\n"
                    f"🛡 Администратор: [id{user_id}|{name}]"
                ),
               random_id=get_random_id()
            )
        except Exception as e:
            print(f"Ошибка при отправке уведомления заблокированному: {e}")
        name = get_user_info(uid)
        send_message(peer_id, f"🔒 [id{uid}|{name}] был заблокирован системно. Он не сможет пользоватеься функционалом бота.")
        

        moders_action(user_id, f"{peer_id} Заблокировал системно: {uid}")
        log_action(user_id, f"{peer_id} Заблокировал системно: {uid}")

        try:
            vk.messages.removeChatUser(
                chat_id=peer_id - 2000000000,
                user_id=uid
            )
        except Exception as e:
            send_message(peer_id, f"⚠ Ошибка при исключении: {e}")
        return



    elif text.startswith("/offsysban"):
        required_level = get_command_level("/offsysban")  # заменить команду на нужную
        if admin_level < required_level:
            send_message(peer_id, "❗ Ваш уровень администратора не соответствует минимальному для этой команды.")
            return
        parts = text.split()
        uid = resolve_username(parse_user_id(parts[1]))
        remove_from_sysban(uid)
        name = get_user_info(uid)
        send_message(peer_id, f"✅ [id{uid}|{name}] был разблокирован системно. \n")
        print(f"✅ Системный бан [id{uid}|пользователю] снят. ")
        moders_action(peer_id, f"{peer_id} Разблокировал системно: {uid}")
        log_action(user_id, f"{peer_id} Разблокировал системно: {uid}")

    elif text.startswith("/setadmin"):
        required_level = get_command_level("/setadmin")  # заменить команду на нужную
        if admin_level < required_level:
            send_message(peer_id, "❗ Ваш уровень администратора не соответствует минимальному для этой команды.")
            return
        parts = text.split()
        uid = resolve_username(parse_user_id(parts[1]))
        level = int(parts[2])
        add_admin(uid, level)
        name = get_user_info(uid)
        send_message(peer_id, f"✅ [id{uid}|{name}] стал администратором уровня {level}")
        log_action(user_id, f"{peer_id} Выдал права администратора: {uid}")
        moders_action(user_id, f"{peer_id} Выдал права администратора: {uid}")

    elif text.startswith("/rr"):
        required_level = get_command_level("/rr")  # заменить команду на нужную
        if admin_level < required_level:
            send_message(peer_id, "❗ Ваш уровень администратора не соответствует минимальному для этой команды.")
            return
        parts = text.split()
        uid = resolve_username(parse_user_id(parts[1]))
        remove_admin(uid)
        name = get_user_info(uid)
        send_message(peer_id, f"✅ [id{uid}|{name}] лишён прав администратора.")
        print(f"✅[id{uid}|{name}] лишён прав администратора.")
        log_action(user_id, f"{peer_id} Снял права администратора: {uid}")
        moders_action(user_id, f"{peer_id} Снял права администратора: {uid}")

    elif text.startswith(("/help", "Список команд")):
        required_level = get_command_level("/help")  # заменить команду на нужную
        if admin_level < required_level:
            send_message(peer_id, "❗ Ваш уровень администратора не соответствует минимальному для этой команды.")
            return
        keyboard = {
            "inline": True,
            "buttons": [
                [
                    {
                        "action": {
                            "type": "callback",
                            "label": "Список блокировок",
                            "payload": '{"cmd":"bbanlist"}'
                        },
                        "color": "primary"
                    }
                ],
                [
                    {
                        "action": {
                            "type": "callback",
                            "label": "Список администрации",
                            "payload": '{"cmd":"balist"}'
                        },
                        "color": "secondary"
                    }
                ],
            ]
        }


        help_message = (
            "📋 Список команд:\n"
            "🔰/checkban [ID или ссылка] — Проверить блокировки пользователя.\n"
            "🔰/ban [ID или ссылка] [дни] [причина] — Заблокировать пользователя.\n"
            "🔰/aban [ID или ссылка] [причина] — Перманентная блокировка.\n"
            "🔰/unban [ID или ссылка] — Разблокировать пользователя.\n"
            "🔰/setadmin [ID или ссылка] [уровень (1-3)] — Назначить администратора.\n"
            "🔰/rr [ID или ссылка] — Снять права администратора с пользователя.\n"
            "🔰/admins — Список всех администраторов и их уровней.\n"
            "🔰/list — Список всех заблокированных пользователей.\n"
            " Полный список команд: https://vk.com/@prostobot_gm-spisok-komand\n"
            "❗ При злоупотреблении полномочиями, баловстве командами, Вам будет выдано наказание.\n"
        )

        vk.messages.send(
            peer_id=peer_id,
            message=help_message,
            random_id=get_random_id(),
            keyboard=json.dumps(keyboard, ensure_ascii=False)
        )
        log_action(user_id, f"{peer_id} Вывел /help")

    elif text.lower() in ("/start", "начать", "старт", "start", "приветствие"):
        keyboard = {
            "inline": True,
            "buttons": [
                [
                    {
                        "action": {
                            "type": "callback",
                            "label": "Список команд",
                            "payload": '{"cmd":"bhelp"}'
                        },
                        "color": "negative"
                    }
                ],
                [
                    {
                        "action": {
                            "type": "callback",
                            "label": "Публичная офферта",
                            "payload": '{"cmd":"boffer"}'
                        },
                        "color": "positive"
                    }
                ],
            ]
        }
        

        start_message = ("Привет! 🤙\n"
"Ты попал в PROSTOBOT — помощника для CRMP/SAMP проектов!\n"
"👮 Бот помогает управлять чёрными списками игроков.\n"
"🍱 Чтобы начать:\n"
"Попроси главного администратора добавить тебя в список админов\n"
"🕳 Или создай проект и обратись к основателю для добавления в вайт-лист\n"
"☢ Нажми кнопку ниже, чтобы увидеть список команд.\n"
"Полная инструкция как начать: https://vk.com/@prostobot_gm-nachalo-raboty-s-prostobot\n"
"🤜 С уважением, команда PROSTO-HELP 🤛\n")
        vk.messages.send(
            peer_id=peer_id,
            message=start_message,
            random_id=get_random_id(),
            keyboard=json.dumps(keyboard, ensure_ascii=False)
        )
        log_action(user_id, f"{peer_id} Вывел приветствие")

    elif text.startswith("/logs"):
        required_level = get_command_level("/logs")
        if admin_level < required_level:
            send_message(peer_id, "❗ Ваш уровень администратора не соответствует минимальному для этой команды.")
            return

    # Создаем inline-клавиатуру с callback
        keyboard = {
            "inline": True,
            "buttons": [
                [
                    {
                        "action": {
                            "type": "callback",
                            "label": "Общий лог",
                            "payload": '{"cmd":"logs_all"}'
                        },
                        "color": "negative"
                    }
                ],
                [
                    {
                        "action": {
                            "type": "callback",
                            "label": "Лог модерации",
                            "payload": '{"cmd":"logs_moders"}'
                        },
                        "color": "negative"
                    }
                ],
                [
                    {
                        "action": {
                            "type": "callback",
                            "label": "Лог авто-разбана",
                            "payload": '{"cmd":"logs_autounban"}'
                        },
                        "color": "negative"
                    }
                ],
                [
                    {
                        "action": {
                            "type": "callback",
                            "label": "Лог сессии (peer_id)",
                            "payload": '{"cmd":"logs_peer"}'
                        },
                        "color": "negative"
                    }
                ]
            ]
        }

        vk.messages.send(
            peer_id=peer_id,
            message="Выберите тип логов, который хотите вывести:",
            random_id=get_random_id(),
            keyboard=json.dumps(keyboard, ensure_ascii=False)
        )


    elif text.startswith("/clearlog"):
        required_level = get_command_level("/clearlog")  # заменить команду на нужную
        if admin_level < required_level:
            send_message(peer_id, "❗ Ваш уровень администратора не соответствует минимальному для этой команды.")
            return
        try:
            with open("alllogs.log", "w", encoding="utf-8") as f:
                f.write("")  # Очистка содержимого файла
            with open("moderators.log", "w", encoding="utf-8") as f:
                f.write("")  # Очистка содержимого файла
            with open("autounban.log", "w", encoding="utf-8") as f:
                f.write("")  # Очистка содержимого файла
            with open("peerid.log", "w", encoding="utf-8") as f:
                f.write("")  # Очистка содержимого файла
            send_message(peer_id, "🧹 Логи успешно очищены. \n Учтите, что полностью лог очистить не получиться. \n Остаеться лог очистки логов.")
            print(f"[LOG] {user_id} очистил логи")
        except Exception as e:
            send_message(peer_id, "❌ Ошибка при очистке логов.")
            print(f"[Ошибка /clearlog]: {e}")
        log_action(user_id, f"{peer_id} Очистил логи:")
        moders_action(user_id, f"{peer_id} Очистил логи:")

    elif text.startswith("/admins"):
        required_level = get_command_level("/admins")  # заменить команду на нужную
        if admin_level < required_level:
            send_message(peer_id, "❗ Ваш уровень администратора не соответствует минимальному для этой команды.")
            return
    # Получаем всех админов 1–3 уровня
        conn = sqlite3.connect("database.db")
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, level FROM admins WHERE level BETWEEN 1 AND 3 ORDER BY level DESC")
        rows = cursor.fetchall()

        if not rows:
            send_message(peer_id, "ℹ В боте пока нет администраторов уровней 1–3.")
            return

        lvl3 = []  # Старший администратор
        lvl2 = []  # Младший администратор
        lvl1 = []  # Модератор

        for uid, lvl in rows:
            name = get_user_info(uid)
            if lvl == 3:
                lvl3.append(f"[id{uid}|{name}]")
            elif lvl == 2:
                lvl2.append(f"[id{uid}|{name}]")
            elif lvl == 1:
                lvl1.append(f"[id{uid}|{name}]")

        msg = "👮 Старший администратор:\n" + ("\n".join(lvl3) if lvl3 else "—") + "\n\n"
        msg += "👮‍♂️ Младший администратор:\n" + ("\n".join(lvl2) if lvl2 else "—") + "\n\n"
        msg += "👨‍🎓 Модератор:\n" + ("\n".join(lvl1) if lvl == 1 else "—")

        send_message(peer_id, msg)
        
    elif text.startswith("/staff"):
        required_level = get_command_level("/ban")  # заменить команду на нужную
        if admin_level < required_level:
            send_message(peer_id, "❗ Ваш уровень администратора не соответствует минимальному для этой команды.")
            return
       
    # Получаем всех админов 4–7 уровня
        conn = sqlite3.connect("database.db")
        cursor = conn.cursor()
        cursor.execute("SELECT user_id, level FROM admins WHERE level BETWEEN 4 AND 7 ORDER BY level DESC")
        rows = cursor.fetchall()

        if not rows:
            send_message(peer_id, "ℹ В боте пока нет сотрудников уровней 4–7.")
            return

        lvl7 = []  # Владелец
        lvl6 = []  # Со-владелец
        lvl5 = []  # Разработчик
        lvl4 = []  # Саппорт
    
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

        msg = "🚹 Владелец:\n" + ("\n".join(lvl7) if lvl7 else "—") + "\n\n"
        msg += "👤 Со-Владелец:\n" + ("\n".join(lvl6) if lvl6 else "—") + "\n\n"
        msg += "🔧 Разработчик:\n" + ("\n".join(lvl5) if lvl5 else "—") + "\n\n"
        msg += "🔏 Саппорт:\n" + ("\n".join(lvl4) if lvl4 else "—")

        send_message(peer_id, msg)

    elif text.startswith("/syslist"):
        send_message(peer_id, " 🔃 Идет проверка данных. \nПожалуйста подождите...")
        required_level = get_command_level("/syslist")  # заменить команду на нужную
        if admin_level < required_level:
            send_message(peer_id, "❗ Ваш уровень администратора не соответствует минимальному для этой команды.")
            return
        sysbans = get_all_sysbans()
        if not sysbans:
            send_message(peer_id, "✅ Системных блокировок не найдено.")
            return

        msg = "🚫 Системные блокировки:\n"
        for user_id_banned, reason, admin_id in sysbans:
            user_name = get_user_info(user_id_banned)
            admin_name = get_user_info(admin_id)
            msg += (
                f"👤 [id{user_id_banned}|{user_name}]\n"
                f"📄 Причина: {reason}\n"
                f"🛡 Администратор: [id{admin_id}|{admin_name}]\n\n"
            )
        send_message(peer_id, msg)
        log_action(user_id, f"{peer_id} Вывел системные блокировки:")
        moders_action(user_id, f"{peer_id} Вывел системные блокировки")

    elif text.startswith("/ping"): #логика пинга
        required_level = get_command_level("/ping")  # заменить команду на нужную
        if admin_level < required_level:
            send_message(peer_id, "❗ Ваш уровень администратора не соответствует минимальному для этой команды.")
            return
        start_ping = time.time()
        stats = get_stats()
        end_ping = time.time()
        response_time = (end_ping - start_ping) * 1000  # миллисекунды

        if admin_level >= 1:
            send_message(
                peer_id,
                f"🏓 Pong!\n"
                f"⏱ Uptime: {stats['uptime']}\n"
                f"📥 Avg Requests/min: {stats['avg_requests']:.2f}\n"
                f"⚙️ Avg Commands/min: {stats['avg_commands']:.2f}\n"
                f"⚡ Response Time: {response_time:.2f} ms"
            )


    elif text.startswith(("ЧСП", "ОЧС", "ЧС ПОСТОВ", "ЧС АДМИНИСТРАЦИИ")):
        print("Выбрал тип ЧС-а...")

    elif text.startswith(("/ip")):
        required_level = get_command_level("/ip")  # заменить команду на нужную
        if admin_level < required_level:
            send_message(peer_id, "❗ Ваш уровень администратора не соответствует минимальному для этой команды.")
            return
        send_message(peer_id, "IP сервера бота: 195.133.147.174")
        return
    elif text.startswith("/offer"):
        send_message(peer_id, "(Чат-менеджер / Менеджер ЧС для SAMP/CRMP проектов)\n"
"Данная оферта является публичным договором между пользователем и администрацией бота ProstoBot, регулирующим условия его использования. Используя бота, вы подтверждаете, что ознакомлены и полностью согласны с нижеприведёнными условиями. Несогласие с ними означает запрет на дальнейшее использование бота.\n"

"1. Общие положения\n\n"

"1.1. Бот предназначен для:\n"

"• автоматической модерации чатов,\n"

"• управления черным списком игроков,\n"

"• фиксации и реализации административных действий,\n"

"• упрощения взаимодействия с администрацией проекта.\n"

"1.2. Использование бота разрешено только в рамках игрового проекта SAMP/CRMP и исключительно с разрешения его владельца.\n"

"1.3. Получить доступ к боту (покупка или аренда) возможно только через владельца бота или уполномоченного заместителя (контакты указаны в описании официального сообщества).\n"

"1.4. Выделяются три (3) режима использования бота сторонними проектами:\n"

"• Общий доступ — использование общей базы ЧС, работа осуществляется на основном сервере ProstoBot.\n"

"• Отдельный доступ — данные хранятся в индивидуальной базе; бот не содержит информации о других администраторах и черных списках. Разворачивается на общем сервере ProstoBot.\n"

"• Закрытый доступ — бот размещается на выделенном сервере с изолированной базой данных и полным административным контролем. Возможна привязка к отдельному сообществу.\n"
"Полное публичное соглашение (оферта): https://vk.com/@prostobot_gm-polzovatelskoe-soglashenie"
        )
        log_action(peer_id, f"{peer_id} Вывел офферту")

    elif text.startswith("/answer"):
        required_level = get_command_level("/answer")  # заменить команду на нужную
        if admin_level < required_level:
            send_message(peer_id, "❗ Ваш уровень администратора не соответствует минимальному для этой команды.")
            return

        parts = text.split(maxsplit=2)
        if len(parts) < 3:
            send_message(peer_id, "⚠ Формат: /answer [id или shortname] [текст]")
            return

        target_raw = parse_user_id(parts[1])
        target_id = resolve_username(target_raw)
        message_text = parts[2]

        if not target_id:
            send_message(peer_id, "❌ Не удалось определить пользователя.")
            return

        answer_number = get_today_answer_count()
        answer_message = f"✨ Получен ответ от администратора.\nНомер ответа: #{answer_number}\nТекст ответа: '{message_text}'\n❗Повторно ответить можно по команде /question."

        try:
            vk.messages.send(
                peer_id=target_id,
                message=answer_message,
                random_id=get_random_id()
            )
            # логируем ответ
            with open(ANSWER_LOG_PATH, "a", encoding="utf-8") as f:
                f.write(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | to: {target_id} | #{answer_number}\n")
            send_message(peer_id, f"✅ Ответ: '{message_text}'\nНомер: #{answer_number}\nУспешно отправлен [id{target_id}|пользователю].")
        except Exception as e:
            send_message(peer_id, "⚠ Не удалось отправить сообщение.")
            print(f"[Ошибка /answer]: {e}")
        log_action(user_id, f"{peer_id} Ответил пользователю {target_id}")
        moders_action(user_id, f"{peer_id} Ответил пользователю {target_id}")

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
            f"📨 Вопрос от: [id{user_id}|{sender_name}]\n"
            f"🕒 Дата и время: {timestamp}\n"
            f"💬 Сообщение: {message_text}"
        )

        for admin_id, level in admins:
            if level >= 3:
                try:
                    vk.messages.send(
                        peer_id=admin_id,
                        message=message,
                        random_id=get_random_id()
                    )
                except Exception as e:
                    print(f"[Ошибка отправки /question админу {admin_id}]: {e}")

        send_message(peer_id, "✅ Ваш вопрос был отправлен администрации.")
        log_action(user_id, f"{peer_id} Отправил вопрос администрации")

    # elif text.startswith("/sendall"):
    #     required_level = get_command_level("/sendall")  # заменить команду на нужную
    #     if admin_level < required_level:
    #         send_message(peer_id, "❗ Ваш уровень администратора не соответствует минимальному для этой команды.")
    #         return

    #     parts = text.split(maxsplit=1)
    #     if len(parts) < 2:
    #         send_message(peer_id, "⚠ Формат: /sendall \"текст сообщения\"")
    #         return

    #     raw_message = parts[1].strip("\"“”")
    #     sender_name = get_user_info(user_id)

    #     allsend_message = (
    #         f"⚠️ УВЕДОМЛЕНИЕ\n\n"
    #         f"{raw_message}\n\n"
    #         f"👤 Отправитель: [id{user_id}|{sender_name}]\n\n"
    #         f"😔 Простите, если побеспокоили. С уважением, PROSTOBOT."
    #     )

    #     try:
    #         response = vk.messages.getConversations(count=200)
    #         sent_count = 0
    #         failed_list = []

    #         for item in response['items']:
    #             peer = item['conversation']['peer']
    #             peer_id = peer['id']
    #             try:
    #                 vk.messages.send(
    #                     peer_id=peer_id,
    #                     message=allsend_message,
    #                     random_id=get_random_id()
    #                 )
    #                 sent_count += 1
    #             except Exception as e:
    #                 failed_list.append(peer_id)
    #                 print(f"[Ошибка отправки в peer_id {peer_id}]: {e}")

    #         send_message(peer_id, f"✅ Сообщение отправлено в {sent_count} диалогов.")
    #         if failed_list:
    #             send_message(peer_id, f"⚠ Не удалось отправить в {len(failed_list)} диалогов.")
    #     except Exception as e:
    #         send_message(peer_id, "❌ Ошибка при получении списка диалогов.")
    #         print(f"[Ошибка /sendall]: {e}")

    # elif text.startswith("/sendalarm"):
    #     required_level = get_command_level("/sendalarm")  # заменить команду на нужную
    #     if admin_level < required_level:
    #         send_message(peer_id, "❗ Ваш уровень администратора не соответствует минимальному для этой команды.")
    #         return
    #     parts = text.split(maxsplit=1)
    #     if len(parts) < 2:
    #        send_message(peer_id, "⚠ Формат: /sendalarm \"текст сообщения\"")
    #        return

    #     raw_message = parts[1].strip("\"“”")
    #     sender_name = get_user_info(user_id)

    #     alarm_message = (
    #         f"⚠️ ВАЖНОЕ УВЕДОМЛЕНИЕ\n\n"
    #         f"{raw_message}\n\n"
    #         f"👤 Отправитель: [id{user_id}|{sender_name}]\n\n"
    #         f"😔 Простите, если побеспокоили. С уважением, PROSTOBOT."
    #     )

    #     try:
    #         response = vk.messages.getConversations(count=200)
    #         sent_count = 0
    #         failed_list = []

    #         for item in response['items']:
    #             peer = item['conversation']['peer']
    #             peer_id = peer['id']
    #             try:
    #                 vk.messages.send(
    #                     peer_id=peer_id,
    #                     message=formatted_message,
    #                     random_id=get_random_id()
    #                 )
    #                 sent_count += 1
    #             except Exception as e:
    #                 failed_list.append(peer_id)
    #                 print(f"[Ошибка отправки в peer_id {peer_id}]: {e}")

    #         send_message(peer_id, f"✅ Сообщение отправлено в {sent_count} диалогов.")
    #         if failed_list:
    #             send_message(peer_id, f"⚠ Не удалось отправить в {len(failed_list)} диалогов.")
    #     except Exception as e:
    #         send_message(peer_id, "❌ Ошибка при получении списка диалогов.")
    #         print(f"[Ошибка /sendalarm]: {e}")

    # elif text.startswith("/sendupd"):
    #     required_level = get_command_level("/sendupd")  # заменить команду на нужную
    #     if admin_level < required_level:
    #         send_message(peer_id, "❗ Ваш уровень администратора не соответствует минимальному для этой команды.")
    #         return
    #     parts = text.split(maxsplit=1)
    #     if len(parts) < 2:
    #         send_message(peer_id, "⚠ Формат: /sendupd \"текст сообщения\"")
    #         return

    #     raw_message = parts[1].strip("\"“”")
    #     sender_name = get_user_info(user_id)

    #     update_message = (
    #         f"⚠️ ОБНОВЛЕНИЕ\n\n"
    #         f"{raw_message}\n\n"
    #         f"👤 Отправитель: [id{user_id}|{sender_name}]\n\n"
    #         f"😔 Простите, если побеспокоили. С уважением, PROSTOBOT."
    #     )

    #     try:
    #         response = vk.messages.getConversations(count=200)
    #         sent_count = 0
    #         failed_list = []

    #         for item in response['items']:
    #             peer = item['conversation']['peer']
    #             peer_id = peer['id']
    #             try:
    #                 vk.messages.send(
    #                     peer_id=peer_id,
    #                     message=update_message,
    #                     random_id=get_random_id()
    #                 )
    #                 sent_count += 1
    #             except Exception as e:
    #                 failed_list.append(peer_id)
    #                 print(f"[Ошибка отправки в peer_id {peer_id}]: {e}")

    #         send_message(peer_id, f"✅ Сообщение отправлено в {sent_count} диалогов.")
    #         if failed_list:
    #             send_message(peer_id, f"⚠ Не удалось отправить в {len(failed_list)} диалогов.")
    #     except Exception as e:
    #         send_message(peer_id, "❌ Ошибка при получении списка диалогов.")
    #         print(f"[Ошибка /sendupd]: {e}")

    # elif text.startswith("/sendwork"):
    #     required_level = get_command_level("/sendwork")  # заменить команду на нужную
    #     if admin_level < required_level:
    #         send_message(peer_id, "❗ Ваш уровень администратора не соответствует минимальному для этой команды.")
    #         return

    #     parts = text.split(maxsplit=1)
    #     if len(parts) < 2:
    #         send_message(peer_id, "⚠ Формат: /sendwork \"текст сообщения\"")
    #         return

    #     raw_message = parts[1].strip("\"“”")
    #     sender_name = get_user_info(user_id)

    #     work_message = (
    #         f"⚠️ ТЕХНИЧЕСКИЕ РАБОТЫ\n\n"
    #         f"{raw_message}\n\n"
    #         f"👤 Отправитель: [id{user_id}|{sender_name}]\n\n"
    #         f"😔 Простите, если побеспокоили. С уважением, PROSTOBOT."
    #     )

    #     try:
    #         response = vk.messages.getConversations(count=200)
    #         sent_count = 0
    #         failed_list = []

    #         for item in response['items']:
    #             peer = item['conversation']['peer']
    #             peer_id = peer['id']
    #             try:
    #                 vk.messages.send(
    #                     peer_id=peer_id,
    #                     message=work_message,
    #                     random_id=get_random_id()
    #                 )
    #                 sent_count += 1
    #             except Exception as e:
    #                 failed_list.append(peer_id)
    #                 print(f"[Ошибка отправки в peer_id {peer_id}]: {e}")
    #         send_message(peer_id, f"✅ Сообщение отправлено в {sent_count} диалогов.")
    #         if failed_list:
    #             send_message(peer_id, f"⚠ Не удалось отправить в {len(failed_list)} диалогов.")
    #     except Exception as e:
    #         send_message(peer_id, "❌ Ошибка при получении списка диалогов.")
    #         print(f"[Ошибка /sendwork]: {e}")

    elif text.startswith("/editcmd"):
        if admin_level < 4:
            send_message(peer_id, "❗ Только администраторы 4 уровня могут изменять доступ к командам.")
            return

        parts = text.split()
        if len(parts) != 3:
            send_message(peer_id, "⚠ Формат: /editcmd [команда] [уровень от 1 до 4]")
            return

        command_name = parts[1].strip()

        set_command_level(command_name, level)
        send_message(peer_id, f"✅ Команда {command_name} теперь доступна с уровня {level}.")

    if user_id in temp_bans and temp_bans[user_id].get("type_stage"):
        type_input = text.strip().upper()
        type_map = {
            "ЧСП": "ЧСП",
            "ОЧС": "ОЧС",
            "ЧС ПОСТОВ": "ЧС(ПОСТ)",
            "ЧС АДМИНИСТРАЦИИ": "ЧСА"
        }


        if type_input not in type_map:
            keyboard = VkKeyboard(one_time=False, inline=True)
            keyboard.add_button("ЧСП", color=VkKeyboardColor.NEGATIVE)
            keyboard.add_line()
            keyboard.add_button("ОЧС", color=VkKeyboardColor.POSITIVE)
            keyboard.add_line()
            keyboard.add_button("ЧС ПОСТОВ", color=VkKeyboardColor.PRIMARY)
            keyboard.add_line()
            keyboard.add_button("ЧС АДМИНИСТРАЦИИ", color=VkKeyboardColor.SECONDARY)
            ban_type = ("⚠ Пожалуйста, напишите один из типов: ЧСП, ОЧС, ЧС ПОСТОВ, ЧС АДМИНИСТРАЦИИ")
            vk.messages.send(
                peer_id=peer_id,
                message=ban_type,
                random_id=get_random_id(),
                keyboard=keyboard.get_keyboard()
            )
            return

        ban_data = temp_bans.pop(user_id)
        ban_type = type_map[type_input]

        final_reason = f"{ban_data['reason']} | {ban_type}"
        add_to_blacklist(
            ban_data["target_id"],
            final_reason,
            ban_data["days"],
            user_id,
            datetime.now().strftime("%Y-%m-%d %H:%M")
        )

        duration_text = "перманентно" if ban_data["days"] == "PERMANENT" else f"на {ban_data['days']} дней."
        name = get_user_info(ban_data['target_id'])
        send_message(
            peer_id,
            f"✅ [id{ban_data['target_id']}|{name}] добавлен в ЧС ({ban_type}) {duration_text}.\n"
            f"Причина: {final_reason}"
        )
        log_action(user_id, f"Заблокировал {ban_data['target_id']} {duration_text}. Причина: {final_reason}")
        return
        
    elif text.startswith("/panel"):
        required_level = get_command_level("/panel")
        if admin_level < required_level:
            snackbar("❗ Ваш уровень администратора не соответствует минимальному для этой команды.")
            return
            
        keyboard = {
            "inline": True,
            "buttons": [
                [
                    {
                        "action": {
                            "type": "callback",
                            "label": "Очистить логи",
                            "payload": '{"cmd":"clogs"}'
                        },
                        "color": "secondary"
                    }
                ],
                [
                    {
                        "action": {
                            "type": "callback",
                            "label": "Показать отклик бота",
                            "payload": '{"cmd":"ping"}'
                        },
                        "color": "secondary"
                    }
                ],
                [
                    {
                        "action": {
                            "type": "callback",
                            "label": "Очистить базу данных",
                            "payload": '{"cmd":"cdb"}'
                        },
                        "color": "secondary"
                    }
                ],
            ]
        }
        vk.messages.send(
            peer_id=peer_id,
            message="Вы вошли в панель управления ботом!\nВыберите функцию которую хотите выполнить: ",
            random_id=get_random_id(),
            keyboard=json.dumps(keyboard, ensure_ascii=False)
        )
    
    elif text.startswith("/add"):
        args = text.split()[1:]  # после команды
        if not args:
            send_message(peer_id, "❗ Укажи пользователя для добавления!")
            return
    
        target_raw = args[0]
        target_username = parse_user_id(target_raw)
        target_id = resolve_username(target_username)
    
        if not target_id:
            send_message(peer_id, "❌ Не удалось определить пользователя!")
            return
    
        add_user(peer_id, target_id)  # ✅ только 2 аргумента
        return
        
    elif text.startswith("/sysinfo"):
        required_level = get_command_level("/sysinfo")
        if admin_level < required_level:
            send_message(peer_id, "❗ Ваш уровень администратора не соответствует минимальному для этой команды.")
            return
        args = text.split()[1:]
        if not args:
            send_message(peer_id, "❗ Укажи пользователя (id/ссылка/shortname)")
            return

        target_raw = args[0]
        parsed_username = parse_user_id(target_raw)
        target_id = resolve_username(parsed_username)

        if not target_id:
            send_message(peer_id, "❌ Не удалось определить пользователя.")
            return

    # Получаем основную информацию
        user_info = vk.users.get(user_ids=target_id, fields="first_name,last_name")[0]
        name = f"{user_info['first_name']} {user_info['last_name']}"

    # 1️⃣ Дата первого контакта с ботом (допустим, у нас есть функция get_first_contact)
        first_contact = get_first_contact_date(target_id) or "Нет данных"

    # 2️⃣ Сколько чёрных списков (у тебя есть get_blacklist_info?)
        bl_info = get_blacklist_info(target_id)
        blacklist_count = len(bl_info) if bl_info else 0

    # 3️⃣ Админ-уровень
        admin_level_target = get_admin_level(target_id)

    # 4️⃣ Проверяем сотрудник/разработчик
        is_staff = "Да" if admin_level_target >= 4 else "Нет"
        position = "Саппорт" if admin_level_target == 4 else ("Разработчик" if admin_level_target == 5 else "Со-Владелец" if admin_level_target == 6 else "Владелец" if admin_level_target == 7 else "—")
    # 5️⃣ Чаты, где бот и пользователь есть вместе
        mutual_chats = get_mutual_chats(target_id)
        mutual_count = len(mutual_chats)

    # 6️⃣ Кол-во чатов, созданных пользователем, где бот состоит
        owned_chats = sum(1 for c in mutual_chats if c.get("owner_id") == target_id)

    # Формируем текст
        msg = (
            f"📌 **ОСНОВНАЯ ИНФОРМАЦИЯ**:\n"
            f"👤 Пользователь: [id{target_id}|{name}]\n"
            f"💬 Чаты пользователя: {mutual_count}\n"
            f"📅 Дата регистрации: {first_contact}\n"
            f"🚫 Черные списки: {blacklist_count}\n"
            f"🛡 Права администратора: {admin_level_target}\n"
            f"---\n"
            f"**ПРАВА И ПРИВИЛЕГИИ**\n"
            f"👨‍💻 Сотрудник бота: {is_staff}\n"
            f"🏷 Должность: {position}\n"
            f"🏠 Чаты пользователя (созданные им): {owned_chats}\n"
            f"---"
        )

        vk.messages.send(
            peer_id=peer_id,
            message=msg,
            random_id=get_random_id(),
        )
        
    elif text.startswith("/setsupport"):
    # Только старшие админы (4+) могут назначать сотрудников
        required_level = get_command_level("/setstaff")  
        if admin_level < required_level:
            send_message(peer_id, "❗ У вас недостаточно прав, чтобы назначать сотрудников бота.")
            return

        args = text.split()[1:]
        if not args:
            send_message(peer_id, "❗ Укажите пользователя (id/ссылка/shortname).")
            return

        target_raw = args[0]
        parsed = parse_user_id(target_raw)
        target_id = resolve_username(parsed)

        if not target_id:
            send_message(peer_id, f"❌ Не удалось определить пользователя {target_raw}.")
            return

    # Если уже имеет >=5, не трогаем
        current_level = get_admin_level(target_id)
        if current_level == 4:
            send_message(peer_id, f"ℹ [id{target_id}|Пользователь] уже является сотрудником бота (уровень {current_level}).")
            return

    # Записываем в БД
        conn = sqlite3.connect("database.db")
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO admins (user_id, level) VALUES (?, ?)",
            (target_id, 4)
        )
        conn.commit()

        send_message(peer_id, f"✅ [id{target_id}|Пользователь] теперь сотрудник бота (уровень 4 – Саппорт).")
        log_action(peer_id, f"{user_id} выдал сотрудника {target_id}")
        
    elif text.startswith("/setcoder"):
    # Только старшие админы (4+) могут назначать сотрудников
        required_level = get_command_level("/setstaff")  
        if admin_level < required_level:
            send_message(peer_id, "❗ У вас недостаточно прав, чтобы назначать сотрудников бота.")
            return

        args = text.split()[1:]
        if not args:
            send_message(peer_id, "❗ Укажите пользователя (id/ссылка/shortname).")
            return

        target_raw = args[0]
        parsed = parse_user_id(target_raw)
        target_id = resolve_username(parsed)

        if not target_id:
            send_message(peer_id, f"❌ Не удалось определить пользователя {target_raw}.")
            return

    # Если уже имеет >=5, не трогаем
        current_level = get_admin_level(target_id)
        if current_level == 5:
            send_message(peer_id, f"ℹ [id{target_id}|Пользователь] уже является сотрудником бота (уровень {current_level}).")
            return

    # Записываем в БД
        conn = sqlite3.connect("database.db")
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO admins (user_id, level) VALUES (?, ?)",
            (target_id, 5)
        )
        conn.commit()

        send_message(peer_id, f"✅ [id{target_id}|Пользователь] теперь сотрудник бота (уровень 5 – Разработчик).")
        log_action(peer_id, f"{user_id} выдал сотрудника {target_id}")
        
    elif text.startswith("/setdep"):
    # Только старшие админы (4+) могут назначать сотрудников
        required_level = get_command_level("/setstaff")  
        if admin_level < required_level:
            send_message(peer_id, "❗ У вас недостаточно прав, чтобы назначать сотрудников бота.")
            return

        args = text.split()[1:]
        if not args:
            send_message(peer_id, "❗ Укажите пользователя (id/ссылка/shortname).")
            return

        target_raw = args[0]
        parsed = parse_user_id(target_raw)
        target_id = resolve_username(parsed)

        if not target_id:
            send_message(peer_id, f"❌ Не удалось определить пользователя {target_raw}.")
            return

    # Если уже имеет >=5, не трогаем
        current_level = get_admin_level(target_id)
        if current_level == 6:
            send_message(peer_id, f"ℹ [id{target_id}|Пользователь] уже является сотрудником бота (уровень {current_level}).")
            return

    # Записываем в БД
        conn = sqlite3.connect("database.db")
        cursor = conn.cursor()
        cursor.execute(
            "INSERT OR REPLACE INTO admins (user_id, level) VALUES (?, ?)",
            (target_id, 6)
        )
        conn.commit()

        send_message(peer_id, f"✅ [id{target_id}|Пользователь] теперь сотрудник бота (уровень 6 – Со-владелец).")
        log_action(peer_id, f"{user_id} выдал сотрудника {target_id}")
        
    elif text.startswith("/report"):
        args = text.split(" ", 1)
        if len(args) < 2:
            send_message(peer_id, "❗ Укажите текст вашего вопроса.\nПример: /report Как кикнуть пользователя?")
            return

        report_text = args[1]
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        conn = sqlite3.connect("database.db")
        cursor = conn.cursor()
        cursor.execute("INSERT INTO reports (user_id, text, created_at) VALUES (?, ?, ?)", (user_id, report_text, now))
        conn.commit()

        send_message(peer_id, "✅ Ваш вопрос отправлен администрации. Ожидайте ответа!")
        
    elif text.startswith("/reps"):
        required_level = 4
        if admin_level < required_level:
            send_message(peer_id, "❗ Доступно только администраторам уровня 4+")
            return
        conn = sqlite3.connect("database.db")
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM reports")
        total_reports = cursor.fetchone()[0]

        if total_reports == 0:
            send_message(peer_id, "✅ Репортов пока нет.")
            return  # <=== ВЫХОД, больше ничего не делаем!

    # Если есть репорты → показываем первую страницу
        send_reports_page(peer_id, offset=0)
        
    elif text.startswith("/delrep"):
        required_level = 4  # только админы 4+ уровня
        if admin_level < required_level:
            send_message(peer_id, "❗ Доступно только администраторам уровня 4+")
            return

        args = text.split()[1:]  # получаем аргументы
        if not args:
            send_message(peer_id, "❗ Укажите номер репорта или all")
            return

        target = args[0].lower()

        if target == "all":
            conn = sqlite3.connect("database.db")
            cursor = conn.cursor()
            cursor.execute("DELETE FROM reports")
            conn.commit()
            send_message(peer_id, "🗑 Все репорты удалены!")
            return

    # иначе пытаемся удалить конкретный репорт
        if not target.isdigit():
            send_message(peer_id, "❗ Укажите корректный номер репорта!")
            return

        rep_id = int(target)
        conn = sqlite3.connect("database.db")
        cursor = conn.cursor()
        cursor.execute("DELETE FROM reports WHERE id = ?", (rep_id,))
        conn.commit()

        if cursor.rowcount > 0:
            send_message(peer_id, f"✅ Репорт #{rep_id} удалён.")
        else:
            send_message(peer_id, f"❌ Репорт #{rep_id} не найден.")
            
            
    elif text.lower() == "/sync":
        try:
            conn = sqlite3.connect("database.db")            
            cursor = conn.cursor()
            cursor.execute("INSERT OR REPLACE INTO synced_chats (peer_id) VALUES (?)", (peer_id,))
            conn.commit()
            send_message(peer_id, "✅ Этот чат теперь синхронизирован с автоочисткой.")
        except Exception as e:
            send_message(peer_id, f"❌ Ошибка при синхронизации: {e}")
            
# ===================== /kick =====================
    elif text.startswith("/kick"):
        required_level = get_command_level("/kick")
        if admin_level < required_level:
            send_message(peer_id, "❗️ Ваш уровень администратора не соответствует минимальному для этой команды.")
            return

        args = text.split()[1:]
        if len(args) < 2:
            send_message(peer_id, "⚠ Использование: /kick <id/ссылка/shortname> <причина>")
            return

        raw_uid = args[0]
        reason = " ".join(args[1:])

        parsed = parse_user_id(raw_uid)
        uid = resolve_username(parsed)
        if not uid:
            send_message(peer_id, f"❌ Не удалось определить пользователя: {raw_uid}")
            return

        # 🛡 Проверка уровня цели
        target_level = get_admin_level(uid)
        if target_level > admin_level:
            send_message(peer_id, f"❗ [id{uid}|{get_user_info(uid)}] имеет более высокий уровень администратора. Действие запрещено.")
            return

        try:
            vk.messages.removeChatUser(
                chat_id=peer_id - 2000000000,
                user_id=uid
            )
            name = get_user_info(uid)
            send_message(peer_id, f"🚫 [id{uid}|{name}] исключён из беседы.\nПричина: {reason}")
        except Exception as e:
            send_message(peer_id, f"⚠ Ошибка при исключении: {e}")
        return

# ===================== /unwarn =====================
    elif text.startswith("/unwarn"):
        required_level = get_command_level("/warn")  # пусть тот же уровень, что и warn
        if admin_level < required_level:
            send_message(peer_id, "❗️ Ваш уровень администратора не соответствует минимальному для этой команды.")
            return

        args = text.split()[1:]
        if not args:
            send_message(peer_id, "⚠ Использование: /unwarn <id/ссылка/shortname>")
            return

        raw_uid = args[0]
        parsed = parse_user_id(raw_uid)
        uid = resolve_username(parsed)
        if not uid:
            send_message(peer_id, f"❌ Не удалось определить пользователя: {raw_uid}")
            return

        reset_warnings(peer_id, uid)
        name = get_user_info(uid)
        send_message(peer_id, f"✅ Все предупреждения для [id{uid}|{name}] были сняты.")
        return

    # ===================== /warnlist =====================
    elif text.startswith("/warnlist"):
        required_level = get_command_level("/warn")  # пусть тот же уровень
        if admin_level < required_level:
            send_message(peer_id, "❗️ Ваш уровень администратора не соответствует минимальному для этой команды.")
            return

        data = get_all_warnings(peer_id)
        if not data:
            send_message(peer_id, "✅ В этой беседе нет пользователей с предупреждениями.")
            return

        msg_lines = ["⚠ Список предупреждённых:"]
        for uid, count in data:
            name = get_user_info(uid)
            msg_lines.append(f"• [id{uid}|{name}] – {count} предупреждений.")
        send_message(peer_id, "\n".join(msg_lines))
        return


# ===================== /warn =====================
    elif text.startswith("/warn"):
        required_level = get_command_level("/warn")
        if admin_level < required_level:
            send_message(peer_id, "❗️ Ваш уровень администратора не соответствует минимальному для этой команды.")
            return

        args = text.split()[1:]
        if len(args) < 2:
            send_message(peer_id, "⚠ Использование: /warn <id/ссылка/shortname> <причина>")
            return

        raw_uid = args[0]
        reason = " ".join(args[1:])

        parsed = parse_user_id(raw_uid)
        uid = resolve_username(parsed)
        if not uid:
            send_message(peer_id, f"❌ Не удалось определить пользователя: {raw_uid}")
            return

        # 🛡 Проверка уровня цели
        target_level = get_admin_level(uid)
        if target_level > admin_level:
            send_message(peer_id, f"❗ [id{uid}|{get_user_info(uid)}] имеет более высокий уровень администратора. Действие запрещено.")
            return

        count = add_warning(peer_id, uid)
        name = get_user_info(uid)
        send_message(peer_id, f"⚠ [id{uid}|{name}] получил предупреждение №{count}.\nПричина: {reason}")

        # если это 3-е предупреждение → кик
        if count >= 3:
            try:
                vk.messages.removeChatUser(
                    chat_id=peer_id - 2000000000,
                    user_id=uid
                )
                reset_warnings(peer_id, uid)
                send_message(peer_id, f"🚫 [id{uid}|{name}] получил 3 предупреждения и был исключён из беседы!")
            except Exception as e:
                send_message(peer_id, f"⚠ Не удалось исключить: {e}")
        return

def handle_event(obj):
    print("[DEBUG] пришел message_event:", obj)
    peer_id = obj['peer_id']
    event_id = obj['event_id']
    user_id = obj['user_id']

    # payload может быть строкой или dict
    payload_raw = obj['payload']
    if isinstance(payload_raw, dict):
        payload = payload_raw
    else:
        payload = json.loads(payload_raw)

    cmd = payload.get("cmd")

 

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

    admin_level = get_admin_level(user_id)

    # === Общий лог ===
    if cmd == "logs_all":
        required_level = get_command_level("/logs")
        if admin_level < required_level:
            snackbar("❗ Ваш уровень администратора не соответствует минимальному для этой команды.")
            return
        try:
            with open("alllogs.log", encoding="utf-8") as f:
                lines = f.readlines()
            msg = "".join(lines[-20:])
            name = get_user_info(user_id)
            if len(msg) > 4000:
                msg = msg[-4000:]
            vk.messages.send(peer_id=peer_id, message=f"🧾 Последние 20 общих логов:\n{msg}\n\n👤 Команду выполнил: [id{user_id}|{name}]", random_id=0)
            snackbar("✅ Общий лог отправлен")
        except Exception as e:
            vk.messages.send(peer_id=peer_id, message="⚠ Ошибка чтения логов", random_id=0)
            snackbar("⚠ Ошибка")
            print(f"[Ошибка logs_all]: {e}")

    # === Лог модерации ===
    elif cmd == "logs_moders":
        required_level = get_command_level("/logs")
        if admin_level < required_level:
            snackbar("❗ Ваш уровень администратора не соответствует минимальному для этой команды.")
            return
        try:
            with open("moderators.log", encoding="utf-8") as f:
                lines = f.readlines()
            msg = "".join(lines[-20:])
            name = get_user_info(user_id)
            if len(msg) > 4000:
                msg = msg[-4000:]
            vk.messages.send(peer_id=peer_id, message=f"🧾 Последние 20 логов модерации:\n{msg}\n\n👤 Команду выполнил: [id{user_id}|{name}]", random_id=0)
            snackbar("✅ Лог модерации отправлен")
        except Exception as e:
            vk.messages.send(peer_id=peer_id, message="⚠ Ошибка чтения логов", random_id=0)
            snackbar("⚠ Ошибка")
            print(f"[Ошибка logs_moders]: {e}")

    # === Авто-разбан ===
    elif cmd == "logs_autounban":
        required_level = get_command_level("/logs")
        if admin_level < required_level:
            snackbar("❗ Ваш уровень администратора не соответствует минимальному для этой команды.")
            return
        try:
            with open("autounban.log", encoding="utf-8") as f:
                lines = f.readlines()
            msg = "".join(lines[-20:])
            name = get_user_info(user_id)
            if len(msg) > 4000:
                msg = msg[-4000:]
            vk.messages.send(peer_id=peer_id, message=f"🧾 Последние 20 логов авто-разбана:\n{msg}\n\n👤 Команду выполнил: [id{user_id}|{name}]", random_id=0)
            snackbar("✅ Лог авто-разбана отправлен")
        except Exception as e:
            vk.messages.send(peer_id=peer_id, message="⚠ Нет логов авто-разбана", random_id=0)
            snackbar("⚠ Нет логов")
            print(f"[Ошибка logs_autounban]: {e}")

    # === peer-логи ===
    elif cmd == "logs_peer":
        required_level = get_command_level("/logs")
        if admin_level < required_level:
            snackbar("❗ Ваш уровень администратора не соответствует минимальному для этой команды.")
            return
        try:
            with open("peerid.log", encoding="utf-8") as f:
                lines = f.readlines()
            msg = "".join(lines[-20:])
            name = get_user_info(user_id)
            if len(msg) > 4000:
                msg = msg[-4000:]
            vk.messages.send(peer_id=peer_id, message=f"🧾 Последние 20 peer-логов:\n{msg}\n\n👤 Команду выполнил: [id{user_id}|{name}]", random_id=0)
            snackbar("✅ Peer-лог отправлен")
        except Exception as e:
            vk.messages.send(peer_id=peer_id, message="⚠ Ошибка чтения peer-логов", random_id=0)
            snackbar("⚠ Ошибка")
            print(f"[Ошибка logs_peer]: {e}")

    elif cmd == "bbanlist":
        send_message(peer_id, "🔃 Идет проверка данных.\nПожалуйста подождите...")

        required_level = get_command_level("/banlist")
        if admin_level < required_level:
            snackbar("❗ Ваш уровень администратора не соответствует минимальному для этой команды.")
            return

        banlist = get_all_banned_users()
        if not banlist:
            snackbar("❌ Нет пользователей в черном списке.")
            return

        msg = "🚫 Список заблокированных:\n"
        for uid, reason, until, admin_id in banlist:
            name = get_user_info(uid)
            msg += f"🔘 [id{uid}|{name}]\n⏳ До: {until}.\n📄 Причина: {reason}\n\n"
            
        name = get_user_info(user_id)
        snackbar("✅ Вывел список блокировок")
        send_message(peer_id, msg, "\n\n👤 Команду выполнил: [id{user_id}|{name}]")
        log_action(user_id, f"{peer_id} Вывел список блокировок")
    elif cmd == "balist":
        required_level = get_command_level("/admins")  # заменить команду на нужную
        if admin_level < required_level:
            send_message(peer_id, "❗ Ваш уровень администратора не соответствует минимальному для этой команды.")
            return
    # Получаем всех админов 1–3 уровня
        cursor.execute("SELECT user_id, level FROM admins WHERE level BETWEEN 1 AND 3 ORDER BY level DESC")
        rows = cursor.fetchall()

        if not rows:
            send_message(peer_id, "ℹ В боте пока нет администраторов уровней 1–3.")
            return

        lvl3 = []  # Старший администратор
        lvl2 = []  # Младший администратор
        lvl1 = []  # Модератор

        for uid, lvl in rows:
            name = get_user_info(uid)
            if lvl == 3:
                lvl3.append(f"[id{uid}|{name}]")
            elif lvl == 2:
                lvl2.append(f"[id{uid}|{name}]")
            elif lvl == 1:
                lvl1.append(f"[id{uid}|{name}]")

        msg = "👮 Старший администратор:\n" + ("\n".join(lvl3) if lvl3 else "—") + "\n\n"
        msg += "👮‍♂️ Младший администратор:\n" + ("\n".join(lvl2) if lvl2 else "—") + "\n\n"
        msg += "👨‍🎓 Модератор:\n" + ("\n".join(lvl1) if lvl1 else "—")

       
        name = get_user_info(user_id) 
        snackbar("✅ Вывел список администраторов")
        send_message(peer_id, msg, "\n\n👤 Команду выполнил: [id{user_id}|{name}")
        log_action(user_id, f"{peer_id} Вывел список администрации:")
        moders_action(user_id, f"{peer_id} Вывел список администрации:")

    elif cmd == "bhelp":
        required_level = get_command_level("/help")
        if admin_level < required_level:
            snackbar("❗ Ваш уровень администратора не соответствует минимальному для этой команды.")
            return
        name = get_user_info(user_id)
        send_message(peer_id, 
            "📋 Список команд:\n"
            "🔰/checkban [ID или ссылка] — Проверить блокировки пользователя.\n"
            "🔰/ban [ID или ссылка] [дни] [причина] — Заблокировать пользователя.\n"
            "🔰/aban [ID или ссылка] [причина] — Перманентная блокировка.\n"
            "🔰/unban [ID или ссылка] — Разблокировать пользователя.\n"
            "🔰/setadmin [ID или ссылка] [уровень (1-3)] — Назначить администратора.\n"
            "🔰/rr [ID или ссылка] — Снять права администратора с пользователя.\n"
            "🔰/admins — Список всех администраторов и их уровней.\n"
            "🔰/list — Список всех заблокированных пользователей.\n"
            "Полный список команд: https://vk.com/@prostobot_gm-spisok-komand\n"
            "❗ При злоупотреблении полномочиями, баловстве командами, Вам будет выдано наказание.\n"
            f"\n👤 Команду выполнил: [id{user_id}|{name}]"
        )
        snackbar("✅ Вывел список команд")
        log_action(user_id, f"{peer_id} Вывел /help")

    elif cmd == "boffer":
        required_level = get_command_level("/offer")
        if admin_level < required_level:
            snackbar("❗ Ваш уровень администратора не соответствует минимальному для этой команды.")
            return
        name = get_user_info(user_id)
        send_message(peer_id, "(Чат-менеджер / Менеджер ЧС для SAMP/CRMP проектов)\n"
"Данная оферта является публичным договором между пользователем и администрацией бота ProstoBot, регулирующим условия его использования. Используя бота, вы подтверждаете, что ознакомлены и полностью согласны с нижеприведёнными условиями. Несогласие с ними означает запрет на дальнейшее использование бота.\n"

"1. Общие положения\n\n"

"1.1. Бот предназначен для:\n"

"• автоматической модерации чатов,\n"

"• управления черным списком игроков,\n"

"• фиксации и реализации административных действий,\n"

"• упрощения взаимодействия с администрацией проекта.\n"

"1.2. Использование бота разрешено только в рамках игрового проекта SAMP/CRMP и исключительно с разрешения его владельца.\n"

"1.3. Получить доступ к боту (покупка или аренда) возможно только через владельца бота или уполномоченного заместителя (контакты указаны в описании официального сообщества).\n"

"1.4. Выделяются три (3) режима использования бота сторонними проектами:\n"

"• Общий доступ — использование общей базы ЧС, работа осуществляется на основном сервере ProstoBot.\n"

"• Отдельный доступ — данные хранятся в индивидуальной базе; бот не содержит информации о других администраторах и черных списках. Разворачивается на общем сервере ProstoBot.\n"

"• Закрытый доступ — бот размещается на выделенном сервере с изолированной базой данных и полным административным контролем. Возможна привязка к отдельному сообществу.\n"
"Полное публичное соглашение (оферта): https://vk.com/@prostobot_gm-polzovatelskoe-soglashenie"
f"\n\n👤 Команду выполнил: [id{user_id}|{name}]"
        )
        log_action(peer_id, f"{peer_id} Вывел офферту") 
        snackbar("✅ Вывел публичное соглашение") 
        
    elif cmd == ("clogs"):
        required_level = get_command_level("/clearlog")  # заменить команду на нужную
        if admin_level < required_level:
            snackbar("❗ Ваш уровень администратора не соответствует минимальному для этой команды.")
            return
        try:
            with open("alllogs.log", "w", encoding="utf-8") as f:
                f.write("")  # Очистка содержимого файла
            with open("moderators.log", "w", encoding="utf-8") as f:
                f.write("")  # Очистка содержимого файла
            with open("autounban.log", "w", encoding="utf-8") as f:
                f.write("")  # Очистка содержимого файла
            with open("peerid.log", "w", encoding="utf-8") as f:
                f.write("")  # Очистка содержимого файла
            snackbar("✅ Логи успешно очищены")
            name = get_user_info(user_id)
            send_message(peer_id, f"🧹 Логи успешно очищены. \n Учтите, что полностью лог очистить не получиться. \n Остаеться лог очистки логов.\n\n👤 Команду выполнил: [id{user_id}|{name}]")
            print(f"[LOG] {user_id} очистил логи")
        except Exception as e:
            snackbar("❌ Ошибка при очистке логов.")
            print(f"[Ошибка /clearlog]: {e}")
        log_action(user_id, f"{peer_id} Очистил логи:")
        moders_action(user_id, f"{peer_id} Очистил логи:")

    elif cmd == ("ping"):
        required_level = get_command_level("/ping")  # заменить команду на нужную
        if admin_level < required_level:
            snackbar("❗ Ваш уровень администратора не соответствует минимальному для этой команды.")
            return
        start_ping = time.time()
        stats = get_stats()
        end_ping = time.time()
        response_time = (end_ping - start_ping)  * 1000  # миллисекунды
        name = get_user_info(user_id)
        
        if admin_level >= 1:
            send_message(
                peer_id,
                f"🏓 Pong!\n"
                f"⏱ Uptime: {stats['uptime']}\n"
                f"📥 Avg Requests/min: {stats['avg_requests']:.2f}\n"
                f"⚙️ Avg Commands/min: {stats['avg_commands']:.2f}\n"
                f"⚡ Response Time: {response_time:.2f} ms"
                f"\n\n👤 Команду выполнил: [id{user_id}|{name}]"
            )
            snackbar("✅ Вывел отклил API")
            
    elif cmd == ("cdb"):
        required_level = get_command_level("/panel")
        if admin_level < required_level:
            snackbar("❗ Ваш уровень администратора не соответствует минимальному для этой команды.")
            return
            return
        keyboard = {
            "inline": True,
            "buttons": [
                [
                    {
                        "action": {
                            "type": "callback",
                            "label": "✅ Да, очистить",
                            "payload": json.dumps({"cmd": "cdb_yes"})
                        },
                        "color": "negative"
                    },
                    {
                        "action": {
                            "type": "callback",
                            "label": "❌ Отмена",
                            "payload": json.dumps({"cmd": "cdb_no"})
                        },
                        "color": "secondary"
                    }
                ]
            ]
        }
        
        name = get_user_info(user_id)
        vk.messages.send(
            peer_id=peer_id,
            message=f"⚠ ВНИМАНИЕ! Все данные в базе будут удалены, таблицы сохранятся.\nПодтвердите действие:\n\n👤 Команду выполнил: [id{user_id}|{name}]",
            random_id=0,
            keyboard=json.dumps(keyboard, ensure_ascii=False)
        )
        snackbar("✅ Ожидаю подтверждения")
        
    elif cmd == ("cdb_yes"):
        required_level = get_command_level("/panel")
        if admin_level < required_level:
            snackbar("❗ Ваш уровень администратора не соответствует минимальному для этой команды.")
            return
        clear_database("database.db", peer_id)
        snackbar("✅ База данных очищена")
        
    elif cmd == ("cdb_no"):
        required_level = get_command_level("/panel")
        if admin_level < required_level:
            snackbar("❗ Ваш уровень администратора не соответствует минимальному для этой команды.")
            return
        snackbar("❌ Отмена очистки базы данных")
       
    elif cmd == "reply_report":
        rep_id = payload.get("report_id")
    # Сохраняем, что этот админ отвечает
        active_report_replies[user_id] = rep_id

        snackbar(f"✏️ Напишите ответ для репорта #{rep_id} или /cancel для отмены.")

    elif cmd == "reps_page":
        new_offset = payload.get("offset", 0)
        edit_id = payload.get("edit_id")  # id редактируемого сообщения
        snackbar("✅ Перешел к другой странице")
        send_reports_page(peer_id, new_offset, edit_message_id=edit_id)
        
    elif cmd == "user_chats":
        uid = payload.get("uid")
        chats = get_mutual_chats(uid)

        if not chats:
            snackbar("❌ Нет общих чатов с этим пользователем.")
            return

        # Формируем список
        chat_list = []  

        for c in chats:  
            raw_owner_id = c.get("owner_id", 0)  
            title = c.get("title", "Без названия")  

# Проверяем тип владельца  
            if raw_owner_id < 0:  
    # Это сообщество  
                peer_owner = abs(raw_owner_id)  
                creator_link = f"[club{peer_owner}|Сообщество]"  
            else:  
    # Это пользователь  
                peer_owner = raw_owner_id  
                user_name = get_user_info(peer_owner)  # например, "Иван Иванов"  
                creator_link = f"[id{peer_owner}|{user_name}]"  

            chat_list.append(f"💬 Чат: {title} • Создатель: {creator_link}")  
            full_msg = "📜 Чаты пользователя:\n" + "\n".join(chat_list)

        # Если длинное сообщение, обрежем
        if len(full_msg) > 4000:
            full_msg = full_msg[:3900] + "\n... (обрезано)"

        send_message(peer_id, full_msg)
        snackbar("✅ Вывел общие чаты")
        return
    
# === CALLBACK API ===
@app.route("/callback", methods=["POST"])
def callback():
    data = request.get_json(force=True)
    event = json.loads(request.data, object_hook=lambda d: SimpleNamespace(**d))
    print("📥 Получен запрос VK:")
    print(json.dumps(data, indent=2, ensure_ascii=False))
    # Подтверждение сервера
    if data.get('type') == 'confirmation':
        return CONFIRMATION_TOKEN

    # Проверка секрета
    if CALLBACK_SECRET and data.get('secret') != CALLBACK_SECRET:
        return 'access denied'

    # Обработка нового сообщения
    elif data["type"] == "message_new":
        try:
            print("📩 Обработка message_new...")

            message = data["object"]["message"]  # <-- КОРРЕКТНО!
            print("🔔 Вызов process_message()")
            process_message(message)

        except Exception as e:
            print("❌ Ошибка в обработке message_new:", e)

        return "ok"

    # pinaem her
    elif data.get('type') == 'message_event':
        try:
            handle_event(data['object'])
        except Exception as e:
            print(f"[ERROR] Ошибка в message_event: {e}")
        return 'ok'

    return 'ok'

if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
