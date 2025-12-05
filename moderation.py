# moderation.py - Полная система модерации
import sqlite3
from datetime import datetime, timedelta
from config import DB_PATH
import logging

logger = logging.getLogger(__name__)

class ModerationSystem:
    """Централизованная система модерации"""
    
    def __init__(self):
        self._active_mutes = {}  # Кэш мутов в памяти
        self._silence_mode = {}  # Режим тишины по чатам
        self._init_tables()
        self._load_mutes_from_db()
        logger.info("✅ Система модерации инициализирована")
    
    def _init_tables(self):
        """Создает таблицы для модерации"""
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        # Таблица мутов
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
                is_active BOOLEAN DEFAULT 1,
                UNIQUE(user_id, peer_id)
            )
        ''')
        
        # Индексы для быстрого поиска
        c.execute('CREATE INDEX IF NOT EXISTS idx_mutes_active ON mutes(is_active, mute_until)')
        c.execute('CREATE INDEX IF NOT EXISTS idx_mutes_user ON mutes(user_id, peer_id)')
        
        conn.commit()
        conn.close()
    
    def _load_mutes_from_db(self):
        """Загружает активные муты из базы данных"""
        try:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            
            current_time = datetime.now().isoformat()
            c.execute('''
                SELECT user_id, peer_id, duration_minutes, moderator_id, 
                       reason, muted_at, mute_until 
                FROM mutes 
                WHERE is_active = 1 AND mute_until > ?
            ''', (current_time,))
            
            for row in c.fetchall():
                user_id, peer_id, duration, moderator_id, reason, muted_at, mute_until = row
                key = f"{user_id}_{peer_id}"
                self._active_mutes[key] = {
                    'user_id': user_id,
                    'peer_id': peer_id,
                    'until': datetime.fromisoformat(mute_until),
                    'moderator': moderator_id,
                    'reason': reason,
                    'duration': duration
                }
            
            conn.close()
            logger.info(f"✅ Загружено {len(self._active_mutes)} активных мутов из БД")
        except Exception as e:
            logger.error(f"❌ Ошибка загрузки мутов из БД: {e}")
    
    # ========== МУТЫ ==========
    
    def mute_user(self, user_id, peer_id, duration_minutes, moderator_id, reason=""):
        """Выдает мут пользователю"""
        try:
            # Удаляем старый мут если есть
            self.unmute_user(user_id, peer_id)
            
            # Рассчитываем время окончания
            mute_until = datetime.now() + timedelta(minutes=duration_minutes)
            
            # Сохраняем в БД
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute('''
                INSERT INTO mutes 
                (user_id, peer_id, duration_minutes, moderator_id, reason, mute_until) 
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (user_id, peer_id, duration_minutes, moderator_id, reason, mute_until.isoformat()))
            conn.commit()
            conn.close()
            
            # Сохраняем в кэш
            key = f"{user_id}_{peer_id}"
            self._active_mutes[key] = {
                'user_id': user_id,
                'peer_id': peer_id,
                'until': mute_until,
                'moderator': moderator_id,
                'reason': reason,
                'duration': duration_minutes
            }
            
            logger.info(f"✅ Мут установлен: user={user_id}, chat={peer_id}, until={mute_until}")
            return True, f"Мут выдан на {duration_minutes} минут"
            
        except Exception as e:
            logger.error(f"❌ Ошибка выдачи мута: {e}")
            return False, f"Ошибка: {e}"
    
    def unmute_user(self, user_id, peer_id):
        """Снимает мут с пользователя"""
        try:
            # Удаляем из БД
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute('''
                UPDATE mutes SET is_active = 0 
                WHERE user_id = ? AND peer_id = ? AND is_active = 1
            ''', (user_id, peer_id))
            conn.commit()
            conn.close()
            
            # Удаляем из кэша
            key = f"{user_id}_{peer_id}"
            if key in self._active_mutes:
                del self._active_mutes[key]
            
            logger.info(f"✅ Мут снят: user={user_id}, chat={peer_id}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Ошибка снятия мута: {e}")
            return False
    
    def check_mute(self, user_id, peer_id):
        """Проверяет, находится ли пользователь в муте"""
        key = f"{user_id}_{peer_id}"
        
        if key in self._active_mutes:
            mute_data = self._active_mutes[key]
            
            # Проверяем не истек ли мут
            if mute_data['until'] > datetime.now():
                return mute_data
            else:
                # Мут истек - удаляем
                self.unmute_user(user_id, peer_id)
                return None
        
        return None
    
    def cleanup_expired_mutes(self):
        """Очищает истекшие муты"""
        try:
            current_time = datetime.now().isoformat()
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            
            # Находим истекшие муты
            c.execute('''
                SELECT user_id, peer_id FROM mutes 
                WHERE is_active = 1 AND mute_until <= ?
            ''', (current_time,))
            
            expired = c.fetchall()
            
            # Помечаем как неактивные
            for user_id, peer_id in expired:
                c.execute('''
                    UPDATE mutes SET is_active = 0 
                    WHERE user_id = ? AND peer_id = ? AND is_active = 1
                ''', (user_id, peer_id))
                
                # Удаляем из кэша
                key = f"{user_id}_{peer_id}"
                if key in self._active_mutes:
                    del self._active_mutes[key]
            
            conn.commit()
            conn.close()
            
            if expired:
                logger.info(f"✅ Очищено {len(expired)} истекших мутов")
                
        except Exception as e:
            logger.error(f"❌ Ошибка очистки мутов: {e}")
    
    # ========== РЕЖИМ ТИШИНЫ ==========
    
    def set_silence_mode(self, peer_id, enabled):
        """Включает/выключает режим тишины"""
        if enabled:
            self._silence_mode[peer_id] = True
            logger.info(f"🔇 Режим тишины ВКЛЮЧЕН в чате {peer_id}")
        else:
            self._silence_mode[peer_id] = False
            logger.info(f"🔊 Режим тишины ВЫКЛЮЧЕН в чате {peer_id}")
    
    def get_silence_mode(self, peer_id):
        """Проверяет режим тишины"""
        return self._silence_mode.get(peer_id, False)
    
    # ========== УДАЛЕНИЕ СООБЩЕНИЙ ==========
    
    def should_delete_message(self, vk, msg, user_role_func):
        """Определяет, нужно ли удалить сообщение"""
        try:
            peer_id = msg.get('peer_id', 0)
            user_id = msg.get('from_id', 0)
            text = msg.get('text', '').strip()
            
            # Только для чатов
            if peer_id < 2000000000:
                return False
            
            # Игнорируем команды бота
            if text.startswith('/') or text.startswith('!') or text.lower() == 'кто':
                return False
            
            # Админы могут писать всегда
            if user_role_func(user_id) >= 2:  # Модератор и выше
                return False
            
            # 1. Проверяем режим тишины
            if self.get_silence_mode(peer_id):
                logger.info(f"🔇 Удаляем сообщение: режим тишины, user={user_id}")
                return True
            
            # 2. Проверяем мут
            if self.check_mute(user_id, peer_id):
                logger.info(f"🔇 Удаляем сообщение: пользователь в муте, user={user_id}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"❌ Ошибка проверки сообщения: {e}")
            return False
    
    # ========== ПОЛУЧЕНИЕ ИНФОРМАЦИИ ==========
    
    def get_active_mutes(self, peer_id=None):
        """Получает активные муты"""
        result = []
        current_time = datetime.now()
        
        for key, mute_data in self._active_mutes.items():
            if mute_data['until'] > current_time:
                if peer_id is None or mute_data['peer_id'] == peer_id:
                    result.append(mute_data)
        
        return result
    
    def get_mute_info(self, user_id, peer_id):
        """Получает информацию о муте"""
        return self.check_mute(user_id, peer_id)
    
    # Добавьте этот метод в класс ModerationSystem в moderation.py:

def delete_user_message(self, vk, peer_id, message_id, user_id):
    """Удаляет сообщение пользователя"""
    try:
        result = vk.messages.delete(
            message_ids=message_id,
            delete_for_all=True,
            peer_id=peer_id
        )
        logger.info(f"✅ Сообщение {message_id} от пользователя {user_id} удалено")
        return True
    except Exception as e:
        logger.error(f"❌ Ошибка удаления сообщения {message_id}: {e}")
        return False

def handle_message_deletion(self, vk, msg, user_role_func):
    """Обрабатывает удаление сообщений (режим тишины и муты)"""
    try:
        peer_id = msg.get('peer_id', 0)
        user_id = msg.get('from_id', 0)
        message_id = msg.get('id', 0)
        text = msg.get('text', '').strip()
        
        # Только для чатов
        if peer_id < 2000000000:
            return False
        
        # Игнорируем команды бота
        if text.startswith('/') or text.startswith('!') or text.lower() == 'кто':
            return False
        
        # Админы могут писать всегда
        if user_role_func(user_id) >= 2:  # Модератор и выше
            return False
        
        should_delete = False
        delete_reason = ""
        
        # 1. Проверяем режим тишины
        if self.get_silence_mode(peer_id):
            should_delete = True
            delete_reason = "🔇 Режим тишины включен. Писать могут только администраторы."
        
        # 2. Проверяем мут
        mute_data = self.check_mute(user_id, peer_id)
        if mute_data:
            should_delete = True
            time_left = mute_data['until'] - datetime.now()
            minutes_left = max(1, int(time_left.total_seconds() / 60))
            delete_reason = f"🔇 Вы в муте! Осталось: {minutes_left} мин.\nДо: {mute_data['until'].strftime('%H:%M:%S')}"
        
        if should_delete:
            # Удаляем сообщение
            if self.delete_user_message(vk, peer_id, message_id, user_id):
                # Отправляем уведомление о причине удаления
                if delete_reason:
                    try:
                        vk.messages.send(
                            peer_id=peer_id,
                            message=delete_reason,
                            random_id=0,  # VK API самостоятельно генерирует random_id
                            reply_to=message_id
                        )
                    except:
                        # Если не удалось отправить с reply_to, отправляем без него
                        try:
                            vk.messages.send(
                                peer_id=peer_id,
                                message=delete_reason,
                                random_id=0
                            )
                        except Exception as e:
                            logger.error(f"❌ Ошибка отправки уведомления: {e}")
                return True
            return False
        
        return False
        
    except Exception as e:
        logger.error(f"❌ Ошибка обработки удаления сообщения: {e}")
        return False

# Глобальный экземпляр
moderation_system = ModerationSystem()
