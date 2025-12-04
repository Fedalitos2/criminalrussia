# mute_system.py - Централизованная система мутов с сохранением в БД
from datetime import datetime, timedelta
import threading
import time
import sqlite3
from typing import Dict, Optional, Tuple
from config import DB_PATH

class MuteSystem:
    """Класс для управления мутами с сохранением в БД"""
    
    def __init__(self):
        self._active_mutes: Dict[int, dict] = {}
        self._lock = threading.Lock()
        self._running = True
        
        # Загружаем активные муты из БД при старте
        self._load_from_db()
        
        self._cleanup_thread = threading.Thread(target=self._cleanup_loop, daemon=True)
        self._cleanup_thread.start()
        print(f"✅ Система мутов инициализирована. Загружено {len(self._active_mutes)} активных мутов")
    
    def _load_from_db(self):
        """Загружает активные муты из базы данных"""
        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            
            # Получаем активные муты, которые еще не истекли
            current_time = datetime.now().isoformat()
            cursor.execute('''
                SELECT user_id, peer_id, duration_minutes, moderator_id, 
                       reason, muted_at, mute_until 
                FROM mutes 
                WHERE is_active = 1 AND mute_until > ?
            ''', (current_time,))
            
            for row in cursor.fetchall():
                user_id, peer_id, duration, moderator_id, reason, muted_at, mute_until = row
                self._active_mutes[user_id] = {
                    'until': datetime.fromisoformat(mute_until),
                    'peer_id': peer_id,
                    'moderator': moderator_id,
                    'reason': reason,
                    'duration': duration,
                    'muted_at': datetime.fromisoformat(muted_at)
                }
            
            conn.close()
        except Exception as e:
            print(f"❌ Ошибка загрузки мутов из БД: {e}")
    
    def mute_user(self, user_id: int, peer_id: int, duration_minutes: int, 
                  moderator_id: int, reason: str = "") -> Tuple[bool, str]:
        """Выдает мут пользователю и сохраняет в БД"""
        with self._lock:
            # Проверяем, не в муте ли уже пользователь в этом чате
            for uid, data in self._active_mutes.items():
                if uid == user_id and data['peer_id'] == peer_id:
                    if data['until'] > datetime.now():
                        return False, "Пользователь уже в муте в этом чате"
                    else:
                        # Мут истек - удаляем старый
                        self._unmute_db(user_id, peer_id)
            
            mute_until = datetime.now() + timedelta(minutes=duration_minutes)
            
            # Сохраняем в БД
            try:
                conn = sqlite3.connect(DB_PATH)
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO mutes 
                    (user_id, peer_id, duration_minutes, moderator_id, reason, mute_until) 
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (user_id, peer_id, duration_minutes, moderator_id, reason, mute_until.isoformat()))
                conn.commit()
                conn.close()
            except Exception as e:
                print(f"❌ Ошибка сохранения мута в БД: {e}")
                return False, "Ошибка сохранения мута в базу данных"
            
            # Сохраняем в памяти
            self._active_mutes[user_id] = {
                'until': mute_until,
                'peer_id': peer_id,
                'moderator': moderator_id,
                'reason': reason,
                'duration': duration_minutes,
                'muted_at': datetime.now()
            }
            
            print(f"✅ Мут установлен для {user_id} в чате {peer_id} до {mute_until}")
            return True, f"Мут выдан на {duration_minutes} минут"
    
    def _unmute_db(self, user_id: int, peer_id: int):
        """Помечает мут как неактивный в БД"""
        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE mutes SET is_active = 0 
                WHERE user_id = ? AND peer_id = ? AND is_active = 1
            ''', (user_id, peer_id))
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"❌ Ошибка обновления мута в БД: {e}")
    
    def unmute_user(self, user_id: int, peer_id: int = None) -> bool:
        """Снимает мут с пользователя"""
        with self._lock:
            if user_id in self._active_mutes:
                mute_data = self._active_mutes[user_id]
                
                # Если указан peer_id, проверяем что мут для этого чата
                if peer_id and mute_data['peer_id'] != peer_id:
                    return False
                
                # Обновляем БД
                self._unmute_db(user_id, mute_data['peer_id'])
                
                # Удаляем из памяти
                del self._active_mutes[user_id]
                print(f"✅ Мут снят с пользователя {user_id}")
                return True
            return False
    
    def check_mute(self, user_id: int, peer_id: int) -> Optional[dict]:
        """Проверяет, находится ли пользователь в муте в указанном чате"""
        with self._lock:
            if user_id in self._active_mutes:
                mute_data = self._active_mutes[user_id]
                
                # Проверяем, что мут для этого чата
                if mute_data['peer_id'] != peer_id:
                    return None
                
                # Проверяем время
                if mute_data['until'] > datetime.now():
                    return mute_data
                else:
                    # Мут истек - удаляем из БД и памяти
                    self._unmute_db(user_id, peer_id)
                    del self._active_mutes[user_id]
                    return None
            return None
    
    def get_mute_info(self, user_id: int, peer_id: int = None) -> Optional[dict]:
        """Получает информацию о муте пользователя"""
        with self._lock:
            if user_id in self._active_mutes:
                mute_data = self._active_mutes[user_id]
                if not peer_id or mute_data['peer_id'] == peer_id:
                    return mute_data
            return None
    
    def get_all_active_mutes(self) -> list:
        """Возвращает все активные муты (для админ-панели)"""
        with self._lock:
            result = []
            for user_id, mute_data in self._active_mutes.items():
                if mute_data['until'] > datetime.now():
                    result.append({
                        'user_id': user_id,
                        'peer_id': mute_data['peer_id'],
                        'until': mute_data['until'],
                        'moderator': mute_data['moderator'],
                        'reason': mute_data['reason'],
                        'time_left': (mute_data['until'] - datetime.now()).seconds // 60
                    })
            return result
    
    def _cleanup_loop(self):
        """Цикл очистки истекших мутов"""
        while self._running:
            try:
                current_time = datetime.now()
                expired = []
                
                with self._lock:
                    for user_id, mute_data in self._active_mutes.items():
                        if mute_data['until'] <= current_time:
                            expired.append((user_id, mute_data['peer_id']))
                
                for user_id, peer_id in expired:
                    self._unmute_db(user_id, peer_id)
                    with self._lock:
                        if user_id in self._active_mutes:
                            del self._active_mutes[user_id]
                    print(f"🕐 Мут для пользователя {user_id} в чате {peer_id} истек")
                
                time.sleep(30)  # Проверка каждые 30 секунд
            except Exception as e:
                print(f"❌ Ошибка в cleanup_loop: {e}")
                time.sleep(30)
    
    def get_active_mutes(self) -> Dict[int, dict]:
        """Возвращает все активные муты (для отладки)"""
        with self._lock:
            return {k: v for k, v in self._active_mutes.items() if v['until'] > datetime.now()}
    
    def stop(self):
        """Останавливает систему"""
        self._running = False
        self._cleanup_thread.join(timeout=1)

# Глобальный экземпляр системы мутов
mute_system = MuteSystem()