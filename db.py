import sqlite3
from datetime import datetime, timedelta

def init_db():
    with sqlite3.connect("database.db") as conn:
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS blacklist (
                user_id INTEGER PRIMARY KEY,
                reason TEXT,
                end_date TEXT,
                admin_id INTEGER,
                date_added TEXT
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS admins (
                user_id INTEGER PRIMARY KEY,
                level INTEGER
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sysban (
                user_id INTEGER PRIMARY KEY,
                reason TEXT,
                admin_id INTEGER,
                timestamp TEXT
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS command_levels (
                command TEXT PRIMARY KEY,
                level INTEGER
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS warnings (
                peer_id INTEGER,
                user_id INTEGER,
                count INTEGER,
                PRIMARY KEY(peer_id, user_id)
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS mutes (
                user_id INTEGER PRIMARY KEY,
                end_time TEXT,
                reason TEXT,
                admin_id INTEGER
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_contacts (
                user_id INTEGER PRIMARY KEY,
                first_contact TEXT
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                text TEXT,
                created_at TEXT
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_stats (
                user_id INTEGER PRIMARY KEY,
                play_time_hours INTEGER DEFAULT 0,
                events_participated INTEGER DEFAULT 0,
                rp_interactions INTEGER DEFAULT 0,
                characters_created INTEGER DEFAULT 0,
                orgs_joined INTEGER DEFAULT 0,
                warnings_received INTEGER DEFAULT 0,
                last_active TEXT,
                achievements TEXT DEFAULT '',
                created_at TEXT
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS synced_chats (
                peer_id INTEGER PRIMARY KEY
            )
        ''')
        
        # Автоматически добавляем владельца (вас) при создании БД
        cursor.execute("INSERT OR IGNORE INTO admins (user_id, level) VALUES (709914900, 7)")
        
        # Настраиваем уровни команд для владельца
        owner_commands = [
            ("/setadmin", 7),
            ("/rr", 7),
            ("/editcmd", 7),
            ("/sysban", 1),
            ("/offsysban", 1),
            ("/panel", 1),
            ("/setstaff", 1),
            ("/setcoder", 1),
            ("/setdep", 1),
            ("/ban", 1),
            ("/aban", 1),
            ("/unban", 1),
            ("/checkban", 1),
            ("/kick", 1),
            ("/warn", 1),
            ("/unwarn", 1),
            ("/warnlist", 1),
            ("/sysinfo", 1),
            ("/syslist", 1),
            ("/logs", 1),
            ("/clearlog", 1),
            ("/answer", 1),
            ("/question", 1),
            ("/report", 0),
            ("/reps", 1),
            ("/delrep", 1),
            ("/sync", 1),
            ("/add", 1),
            ("/mute", 1),
            ("/help", 0),
            ("/start", 0),
            ("/offer", 0),
            ("/admins", 0),
            ("/staff", 0),
            ("/ping", 1),
            ("/ip", 1),
        ]
        
        for cmd, level in owner_commands:
            cursor.execute("INSERT OR REPLACE INTO command_levels (command, level) VALUES (?, ?)", (cmd, level))

        conn.commit()

def get_sysban_from_db(user_id):
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT reason, admin_id FROM sysban WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result

def get_admin_level(user_id):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT level FROM admins WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    return row[0] if row else 0

def add_admin(user_id, level):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO admins (user_id, level) VALUES (?, ?)", (user_id, level))
    conn.commit()

def remove_admin(user_id):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM admins WHERE user_id = ?", (user_id,))
    conn.commit()

def get_all_admins():
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, level FROM admins")
    return cursor.fetchall()

def get_blacklist_info(user_id):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM blacklist WHERE user_id = ?", (user_id,))
    return cursor.fetchone()

def add_to_blacklist(user_id, reason, days, admin_id, date_added):
    if isinstance(days, str) and days.upper() == "PERMANENT":
        end_date = "PERMANENT"
    else:
        end_date = (datetime.now() + timedelta(days=int(days))).strftime("%Y-%m-%d %H:%M")
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO blacklist (user_id, reason, end_date, admin_id, date_added)
        VALUES (?, ?, ?, ?, ?)
    ''', (user_id, reason, end_date, admin_id, date_added))
    conn.commit()

def remove_from_blacklist(user_id):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM blacklist WHERE user_id = ?", (user_id,))
    conn.commit()

def get_all_banned_users():
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, reason, end_date, admin_id FROM blacklist")
    return cursor.fetchall()

def add_to_sysban(user_id, reason, admin_id):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR REPLACE INTO sysban (user_id, reason, admin_id) VALUES (?, ?, ?)",
        (user_id, reason, admin_id)
    )
    conn.commit()

def remove_from_sysban(user_id):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM sysban WHERE user_id = ?", (user_id,))
    conn.commit()

def get_all_sysbans():
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, reason, admin_id FROM sysban")
    return cursor.fetchall()

DEFAULT_COMMAND_LEVELS = {
    "/ban": 2,
    "/aban": 2,
    "/unban": 2,
    "/checkban": 1,
    "/answer": 2,
    "/editcmd": 7,
    "/logs": 4,
    "/clearlog": 4,
    "/help": 1,
    "/banlist": 1,
    "/syslist": 1,
    "/sysban": 5,
    "/offsysban": 5,
    "/setadmin": 7,
    "/rr": 7,
    "/ping": 1,
    "/ip": 5,
    "/admins": 1,
    "/kick": 1,
    "/warn": 1,
    "/unwarn": 2,
    "/panel": 6,
    "/mute": 2,
    "/offer": 1,
    "/setstaff": 6,
    "/sysinfo": 4,
}

def get_command_level(command):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT level FROM command_levels WHERE command = ?", (command,))
    row = cursor.fetchone()
    if row:
        return row[0]
    return DEFAULT_COMMAND_LEVELS.get(command, 1)

def set_command_level(command, level):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO command_levels (command, level) VALUES (?, ?)", (command, level))
    conn.commit()

def get_warnings(peer_id, user_id):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT count FROM warnings WHERE peer_id=? AND user_id=?", (peer_id, user_id))
    row = cursor.fetchone()
    return row[0] if row else 0

def add_warning(peer_id, user_id):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    current = get_warnings(peer_id, user_id)
    if current == 0:
        cursor.execute("INSERT INTO warnings (peer_id, user_id, count) VALUES (?, ?, 1)", (peer_id, user_id))
    else:
        cursor.execute("UPDATE warnings SET count=count+1 WHERE peer_id=? AND user_id=?", (peer_id, user_id))
    conn.commit()
    return current + 1

def reset_warnings(peer_id, user_id):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM warnings WHERE peer_id=? AND user_id=?", (peer_id, user_id))
    conn.commit()

def get_all_warnings(peer_id):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, count FROM warnings WHERE peer_id=?", (peer_id,))
    return cursor.fetchall()

def add_mute(user_id, minutes, reason, admin_id):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    end_time = datetime.now() + timedelta(minutes=minutes)
    cursor.execute("REPLACE INTO mutes (user_id, end_time, reason, admin_id) VALUES (?, ?, ?, ?)",
                   (user_id, end_time.strftime("%Y-%m-%d %H:%M:%S"), reason, admin_id))
    conn.commit()

def remove_mute(user_id):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM mutes WHERE user_id = ?", (user_id,))
    conn.commit()

def get_mute(user_id):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT end_time, reason, admin_id FROM mutes WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if not row:
        return None
    end_time = datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S")
    if datetime.now() > end_time:
        remove_mute(user_id)
        return None
    return row

def save_first_contact(user_id):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("SELECT first_contact FROM user_contacts WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if not row:
        cursor.execute("INSERT INTO user_contacts (user_id, first_contact) VALUES (?, ?)", (user_id, now))
        conn.commit()

def get_first_contact_date(user_id):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT first_contact FROM user_contacts WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if row:
        return row[0]
    else:
        return "Неизвестно"
    
def get_user_stats(user_id):
    """Получить статистику пользователя"""
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM user_stats WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    
    if row:
        # Возвращаем в виде словаря для удобства
        return {
            "user_id": row[0],
            "play_time_hours": row[1] or 0,
            "events_participated": row[2] or 0,
            "rp_interactions": row[3] or 0,
            "characters_created": row[4] or 0,
            "orgs_joined": row[5] or 0,
            "warnings_received": row[6] or 0,
            "last_active": row[7] or "Никогда",
            "achievements": row[8] or "",
            "created_at": row[9] or "Неизвестно"
        }
    else:
        # Создаём запись, если её нет
        create_user_stats(user_id)
        return get_user_stats(user_id)

def create_user_stats(user_id):
    """Создать запись статистики для нового пользователя"""
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    cursor.execute('''
        INSERT OR IGNORE INTO user_stats 
        (user_id, created_at, last_active) 
        VALUES (?, ?, ?)
    ''', (user_id, now, now))
    
    conn.commit()
    conn.close()

def update_user_stat(user_id, stat_name, value=1, operation="increment"):
    """Обновить конкретную статистику пользователя"""
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    
    # Сначала убедимся, что запись существует
    create_user_stats(user_id)
    
    # Обновляем статистику
    if operation == "increment":
        cursor.execute(f'''
            UPDATE user_stats 
            SET {stat_name} = {stat_name} + ?, last_active = ?
            WHERE user_id = ?
        ''', (value, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), user_id))
    elif operation == "set":
        cursor.execute(f'''
            UPDATE user_stats 
            SET {stat_name} = ?, last_active = ?
            WHERE user_id = ?
        ''', (value, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), user_id))
    
    conn.commit()
    conn.close()

def get_top_players(stat_name="play_time_hours", limit=10):
    """Получить топ игроков по определённой статистике"""
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    
    cursor.execute(f'''
        SELECT user_id, {stat_name} 
        FROM user_stats 
        ORDER BY {stat_name} DESC 
        LIMIT ?
    ''', (limit,))
    
    rows = cursor.fetchall()
    conn.close()
    
    return rows  # [(user_id, value), ...]

init_db()