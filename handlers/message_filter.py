# handlers/message_filter.py
# ---------------------------
# Фильтр сообщений в чатах — проверяет муты, режим тишины, удаляет запрещённые сообщения

from datetime import datetime
from database import get_role
from utils import send_message

# Активные муты и состояния "режима тишины"
ACTIVE_MUTES = {}
ACTIVE_SILENCE = {}


def message_filter(vk, event):
    """
    Фильтрует сообщения в чатах:
    - удаляет сообщения замученных пользователей
    - удаляет все сообщения во время "режима тишины"
    """
    try:
        msg = event.obj.message
        peer_id = msg.get("peer_id")
        user_id = msg.get("from_id")
        text = msg.get("text", "")

        # Проверяем: если это не беседа (peer_id < 2e9), выходим
        if peer_id < 2000000000:
            return

        # --- Проверка режима тишины в беседе ---
        if ACTIVE_SILENCE.get(peer_id, False):
            user_role = get_role(user_id)
            if user_role not in ("admin", "leader", "founder"):
                _delete_message_safe(vk, msg)
                return

        # --- Проверка персонального мута ---
        mute_info = ACTIVE_MUTES.get(user_id)
        if mute_info:
            if datetime.now() < mute_info["until"]:
                _delete_message_safe(vk, msg)
                return
            else:
                # мут закончился — убираем
                del ACTIVE_MUTES[user_id]
                send_message(vk, peer_id, f"🔊 [id{user_id}|Пользователь] автоматически размучен.")
    except Exception as e:
        print(f"[message_filter] Ошибка: {e}")


def _delete_message_safe(vk, msg):
    """Удаляет сообщение безопасно (без падений при ошибках VK API)"""
    try:
        vk.messages.delete(
            message_ids=msg["id"],
            peer_id=msg["peer_id"],
            delete_for_all=True
        )
    except Exception:
        pass
