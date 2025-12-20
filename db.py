import sqlite3
from datetime import datetime, timedelta

# Подключение к базе данных
conn = sqlite3.connect('database.db')
cursor = conn.cursor()

# Создание таблиц для черного списка
def init_blacklist_tables():
    # Черный список для админов бота
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS blacklist_admins (
            user_id INTEGER PRIMARY KEY,
            reason TEXT,
            until_date TEXT,
            added_by INTEGER,
            added_at TEXT
        )
    ''')
    
    # Черный список для лидеров/владельцев бесед
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS blacklist_leaders (
            user_id INTEGER PRIMARY KEY,
            reason TEXT,
            until_date TEXT,
            added_by INTEGER,
            added_at TEXT
        )
    ''')
    
    # Черный список для обычных пользователей
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS blacklist_users (
            user_id INTEGER PRIMARY KEY,
            reason TEXT,
            until_date TEXT,
            added_by INTEGER,
            added_at TEXT
        )
    ''')
    
    conn.commit()

# Функции для работы с черным списком
def add_to_blacklist(user_id, reason, days=0, list_type='users'):
    """
    Добавить пользователя в черный список
    days = 0 - навсегда
    """
    if days > 0:
        until_date = (datetime.now() + timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
    else:
        until_date = 'permanent'
    
    added_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    table_name = f'blacklist_{list_type}'
    
    cursor.execute(f'''
        INSERT OR REPLACE INTO {table_name} 
        (user_id, reason, until_date, added_by, added_at) 
        VALUES (?, ?, ?, ?, ?)
    ''', (user_id, reason, until_date, 0, added_at))
    
    conn.commit()

def remove_from_blacklist(user_id, list_type='users'):
    table_name = f'blacklist_{list_type}'
    cursor.execute(f'DELETE FROM {table_name} WHERE user_id = ?', (user_id,))
    conn.commit()

def check_blacklist(user_id, list_type='users'):
    table_name = f'blacklist_{list_type}'
    cursor.execute(f'''
        SELECT * FROM {table_name} 
        WHERE user_id = ? 
        AND (until_date = 'permanent' OR until_date > datetime('now'))
    ''', (user_id,))
    
    result = cursor.fetchone()
    if result:
        return {
            'user_id': result[0],
            'reason': result[1],
            'until_date': result[2],
            'added_by': result[3],
            'added_at': result[4]
        }
    return None

def get_blacklist_all(list_type='users'):
    table_name = f'blacklist_{list_type}'
    cursor.execute(f'''
        SELECT * FROM {table_name} 
        WHERE until_date = 'permanent' OR until_date > datetime('now')
        ORDER BY added_at DESC
    ''')
    
    return cursor.fetchall()

# Инициализация таблиц при импорте
init_blacklist_tables()