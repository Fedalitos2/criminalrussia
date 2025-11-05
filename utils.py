# utils.py
from typing import Dict
from vk_api.utils import get_random_id

# Временные состояния пользователей
pending: Dict[int, dict] = {}


def start_action(user_id: int, action: str):
    """Начать новое пошаговое действие"""
    pending[user_id] = {"action": action, "step": 1, "data": {}}


def update_action(user_id: int, key: str, value):
    """Обновить данные текущего шага"""
    if user_id not in pending:
        return
    pending[user_id]["data"][key] = value
    pending[user_id]["step"] += 1


def get_action(user_id: int):
    """Получить текущее состояние пользователя"""
    return pending.get(user_id)


def finish_action(user_id: int):
    """Завершить действие и удалить состояние"""
    pending.pop(user_id, None)


async def send_message(vk, user_id, message: str, keyboard=None):
    """Асинхронная универсальная функция отправки сообщений"""
    try:
        params = {
            "user_id": user_id,
            "message": message,
            "random_id": get_random_id()
        }
        if keyboard:
            params["keyboard"] = keyboard
        vk.messages.send(**params)
    except Exception as e:
        print(f"[Ошибка отправки VK] {e}")
