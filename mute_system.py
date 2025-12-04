# mute_system.py - Централизованная система мутов
from datetime import datetime, timedelta
import threading
import time
from typing import Dict, Optional, Tuple

class MuteSystem:
    """Класс для управления мутами"""
    
    def __init__(self):
        self._active_mutes: Dict[int, dict] = {}
        self._lock = threading.Lock()
        self._running = True
        self._cleanup_thread = threading.Thread(target=self._cleanup_loop, daemon=True)
        self._cleanup_thread.start()
        print("✅ Система мутов инициализирована")
    
    def mute_user(self, user_id: int, peer_id: int, duration_minutes: int, 
                  moderator_id: int, reason: str = "") -> Tuple[bool, str]:
        """Выдает мут пользователю"""
        with self._lock:
            if user_id in self._active_mutes:
                return False, "Пользователь уже в муте"
            
            mute_until = datetime.now() + timedelta(minutes=duration_minutes)
            self._active_mutes[user_id] = {
                'until': mute_until,
                'peer_id': peer_id,
                'moderator': moderator_id,
                'reason': reason,
                'duration': duration_minutes
            }
            
            print(f"✅ Мут установлен для {user_id} до {mute_until}")
            return True, f"Мут выдан на {duration_minutes} минут"
    
    def unmute_user(self, user_id: int) -> bool:
        """Снимает мут с пользователя"""
        with self._lock:
            if user_id in self._active_mutes:
                del self._active_mutes[user_id]
                print(f"✅ Мут снят с пользователя {user_id}")
                return True
            return False
    
    def check_mute(self, user_id: int, peer_id: int) -> Optional[dict]:
        """Проверяет, находится ли пользователь в муте"""
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
                    # Мут истек - удаляем
                    del self._active_mutes[user_id]
                    return None
            return None
    
    def get_mute_info(self, user_id: int) -> Optional[dict]:
        """Получает информацию о муте пользователя"""
        with self._lock:
            return self._active_mutes.get(user_id)
    
    def _cleanup_loop(self):
        """Цикл очистки истекших мутов"""
        while self._running:
            try:
                current_time = datetime.now()
                expired = []
                
                with self._lock:
                    for user_id, mute_data in self._active_mutes.items():
                        if mute_data['until'] <= current_time:
                            expired.append(user_id)
                
                for user_id in expired:
                    with self._lock:
                        if user_id in self._active_mutes:
                            del self._active_mutes[user_id]
                            print(f"🕐 Мут для пользователя {user_id} истек")
                
                time.sleep(60)  # Проверка каждую минуту
            except Exception as e:
                print(f"❌ Ошибка в cleanup_loop: {e}")
                time.sleep(60)
    
    def get_active_mutes(self) -> Dict[int, dict]:
        """Возвращает все активные муты (для отладки)"""
        with self._lock:
            return self._active_mutes.copy()
    
    def stop(self):
        """Останавливает систему"""
        self._running = False
        self._cleanup_thread.join(timeout=1)

# Глобальный экземпляр системы мутов
mute_system = MuteSystem()