# handlers/admin_panel.py
import asyncio
from datetime import datetime, timedelta
from vk_api.keyboard import VkKeyboard, VkKeyboardColor
from vk_api.utils import get_random_id
from database import (
    get_user_role,
    add_blacklist_entry,
    remove_blacklist_entry,
    get_blacklist,
    clean_expired_blacklist
)
from utils import (
    send_message,
    start_action,
    update_action,
    get_action,
    finish_action
)

# Типы ЧС
BLACKLIST_TYPES = {
    "ЧСП": "Чёрный список проекта",
    "ЧСА": "Чёрный список администрации",
    "ЧСЛ": "Чёрный список лидеров",
    "ЧСЗ": "Чёрный список заместителей"
}


async def admin_panel(vk, user_id):
    """Главное меню админ-панели"""
    role = await get_user_role(user_id)
    if role not in ["admin", "owner", "founder"]:
        await send_message(vk, user_id, "⛔ У вас нет доступа к админ-панели.")
        return

    kb = VkKeyboard(one_time=False)
    kb.add_button("➕ Добавить в ЧС", VkKeyboardColor.POSITIVE)
    kb.add_button("🗑 Удалить из ЧС", VkKeyboardColor.NEGATIVE)
    kb.add_line()
    kb.add_button("📜 Посмотреть ЧС", VkKeyboardColor.PRIMARY)
    kb.add_line()
    kb.add_button("🔍 Проверить игрока", VkKeyboardColor.SECONDARY)
    kb.add_line()
    kb.add_button("🚪 Выйти", VkKeyboardColor.NEGATIVE)

    await send_message(
        vk,
        user_id,
        f"🛠 Админ-панель ({role.upper()})\n\n"
        f"Выберите нужное действие:",
        keyboard=kb
    )


async def handle_admin_command(vk, event):
    """Главный обработчик команд панели"""
    user_id = event.obj.message["from_id"]
    text = event.obj.message["text"].strip()

    # Проверка состояния
    state = get_action(user_id)

    # Очистка просроченных записей
    await clean_expired_blacklist(vk)

    # Если пользователь в процессе действия
    if state:
        await process_action(vk, user_id, text, state)
        return

    # Открытие панели
    if text.lower() in ["админ", "панель"]:
        await admin_panel(vk, user_id)
        return

    # Меню панели
    match text:
        case "➕ Добавить в ЧС":
            start_action(user_id, "add_blacklist")
            await send_message(vk, user_id, "Введите ник игрока для добавления в ЧС:")
        case "🗑 Удалить из ЧС":
            start_action(user_id, "remove_blacklist")
            await send_message(vk, user_id, "Введите ник игрока для удаления из ЧС:")
        case "📜 Посмотреть ЧС":
            await show_blacklist(vk, user_id)
        case "🔍 Проверить игрока":
            start_action(user_id, "check_player")
            await send_message(vk, user_id, "Введите ник игрока для проверки:")
        case "🚪 Выйти":
            await send_message(vk, user_id, "🚪 Вы вышли из админ-панели.")
        case _:
            pass


async def show_blacklist(vk, user_id):
    """Вывод всех ЧС"""
    bl = await get_blacklist()
    if not bl:
        await send_message(vk, user_id, "📭 Все списки пусты.")
        return

    msg = "📋 Текущие ЧС:\n\n"
    for entry in bl:
        msg += (
            f"👤 {entry['nickname']}\n"
            f"🗂 Тип: {entry['type']}\n"
            f"📅 До: {entry['until']}\n"
            f"💬 Причина: {entry['reason']}\n\n"
        )
    await send_message(vk, user_id, msg)


async def process_action(vk, user_id, text, state):
    """Обработка пошаговых действий"""
    action = state["action"]
    step = state["step"]

    # Добавление в ЧС
    if action == "add_blacklist":
        if step == 1:
            update_action(user_id, "nickname", text)
            await send_message(vk, user_id, "Введите тип ЧС (ЧСП / ЧСА / ЧСЛ / ЧСЗ):")
        elif step == 2:
            bl_type = text.upper()
            if bl_type not in BLACKLIST_TYPES:
                await send_message(vk, user_id, "❌ Неверный тип ЧС. Попробуйте снова:")
                return
            update_action(user_id, "type", bl_type)
            await send_message(vk, user_id, "Введите срок наказания (в днях):")
        elif step == 3:
            try:
                days = int(text)
                if days <= 0:
                    raise ValueError
            except ValueError:
                await send_message(vk, user_id, "❌ Неверный формат. Введите число дней:")
                return
            update_action(user_id, "days", days)
            await send_message(vk, user_id, "Введите причину добавления в ЧС:")
        elif step == 4:
            reason = text
            data = state["data"]
            until = datetime.now() + timedelta(days=data["days"])
            await add_blacklist_entry(
                data["nickname"],
                data["type"],
                until,
                reason,
                user_id
            )
            await send_message(
                vk,
                user_id,
                f"✅ {data['nickname']} добавлен в {data['type']} на {data['days']} дн.\n💬 Причина: {reason}"
            )
            finish_action(user_id)

    # Удаление из ЧС
    elif action == "remove_blacklist":
        nickname = text
        removed = await remove_blacklist_entry(nickname)
        if removed:
            await send_message(vk, user_id, f"✅ {nickname} удалён из всех ЧС.")
        else:
            await send_message(vk, user_id, f"⚠️ {nickname} не найден в ЧС.")
        finish_action(user_id)

    # Проверка игрока
    elif action == "check_player":
        bl = await get_blacklist()
        found = [b for b in bl if b["nickname"].lower() == text.lower()]
        if found:
            msg = f"🔎 Игрок {text} найден в ЧС:\n\n"
            for entry in found:
                msg += f"🗂 {entry['type']} | до {entry['until']} | 💬 {entry['reason']}\n"
        else:
            msg = f"✅ Игрок {text} не находится в ЧС."
        await send_message(vk, user_id, msg)
        finish_action(user_id)
