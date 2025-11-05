# leadership.py
import sqlite3
from config import DB_PATH

def init_leadership_db():
    """Инициализирует таблицу руководства"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    c.execute('''
        CREATE TABLE IF NOT EXISTS leadership (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE,
            position TEXT NOT NULL,
            display_name TEXT,
            added_by INTEGER,
            added_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()
    print("✅ Таблица руководства инициализирована!")

def add_leader(user_id, position, display_name, added_by):
    """Добавляет пользователя в руководство"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT OR REPLACE INTO leadership (user_id, position, display_name, added_by)
        VALUES (?, ?, ?, ?)
    ''', (user_id, position, display_name, added_by))
    
    conn.commit()
    conn.close()
    return True

def remove_leader(user_id):
    """Удаляет пользователя из руководства"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("DELETE FROM leadership WHERE user_id = ?", (user_id,))
    
    affected = cursor.rowcount
    conn.commit()
    conn.close()
    return affected > 0

def get_all_leaders():
    """Получает всех руководителей"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT user_id, position, display_name, added_at 
        FROM leadership ORDER BY added_at DESC
    ''')
    
    results = cursor.fetchall()
    conn.close()
    return results

def get_leader(user_id):
    """Получает информацию о руководителе"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("SELECT position, display_name FROM leadership WHERE user_id = ?", (user_id,))
    
    result = cursor.fetchone()
    conn.close()
    return result

# Инициализируем базу при импорте
init_leadership_db()