import sqlite3
from datetime import datetime, timedelta

def init_db():
    with sqlite3.connect ("database.db") as conn:
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
                admin_id INTEGER
            )
        ''')
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS command_levels (
                command TEXT PRIMARY KEY,
                level INTEGER
            )
        """)

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
    
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                text TEXT,
                created_at TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS synced_chats (
                peer_id INTEGER PRIMARY KEY
)
        """)

        conn.commit()

def get_sysban_from_db(user_id):
    # Подключение к базе данных (поменяйте на вашу БД)
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()

    # Запрос к таблице sysban (поменяйте на вашу таблицу)
    query = "SELECT reason, admin_id FROM sysban WHERE user_id = ?"
    cursor.execute(query, (user_id,))
    result = cursor.fetchone()

    conn.close()

    if result:
        return result  # (reason, admin_id)
    return None

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

def add_to_sysban(user_id, reason=None, admin_id=None):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO sysban (user_id) VALUES (?)", (user_id,))
    conn.commit()

def remove_from_sysban(user_id):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM sysban WHERE user_id = ?", (user_id,))
    conn.commit()

def is_sysbanned(user_id):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM sysban WHERE user_id = ?", (user_id,))
    return cursor.fetchone() is not None

def auto_unban_expired_users():
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, end_date FROM blacklist")
    expired = [row[0] for row in cursor.fetchall() if row[1] != "PERMANENT" and row[1] <= now]
    for uid in expired:
        remove_from_blacklist(uid)

def is_admin(user_id):
    conn = sqlite3.connect("database.db")
    c = conn.cursor()
    c.execute("SELECT role FROM admins WHERE user_id = ?", (user_id,))
    result = c.fetchone()
    conn.close()
    return result is not None

def add_to_sysban(user_id, reason, admin_id):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute(
        "INSERT OR REPLACE INTO sysban (user_id, reason, admin_id) VALUES (?, ?, ?)",
        (user_id, reason, admin_id)
    )
    conn.commit()

def get_all_sysbans():
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, reason, admin_id FROM sysban")
    return cursor.fetchall()
    
# ---------- Управление доступом к командам ----------
DEFAULT_COMMAND_LEVELS = {
    "/ban": 2,
    "/aban": 2,
    "/unban": 2,
    "/checkban": 1,
    "/sendall": 5,
    "/sendalarm": 5,
    "/sendupd": 5,
    "/sendwork": 5,
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
    return cursor.fetchall()  # список [(user_id, count), ...]

from datetime import datetime, timedelta

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
    # если мут истёк – убираем
    if datetime.now() > end_time:
        remove_mute(user_id)
        return None
    return row  # (end_time, reason, admin_id)
    

def save_first_contact(user_id):
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("SELECT first_contact FROM user_contacts WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if not row:
        cursor.execute("INSERT INTO user_contacts (user_id, first_contact) VALUES (?, ?)", (user_id, now))
        conn.commit()

init_db()