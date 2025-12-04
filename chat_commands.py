# chat_commands.py
import re
from datetime import datetime, timedelta
import sqlite3
from config import DB_PATH
from vk_api.utils import get_random_id
from leadership import add_leader, remove_leader, get_all_leaders
from database import get_user_role, has_permission
from mute_system import mute_system

silence_mode = {}

def handle_chat_command(vk, msg, user_id, text, peer_id):
    """Обрабатывает старые команды модерации в чатах (с !)"""
    print(f"🔧 Обрабатываю старую команду в чате: {text}")
    
    # Проверяем права пользователя
    if not has_permission(user_id, 2):  # Модератор и выше
        print(f"❌ У пользователя {user_id} нет прав для модерации")
        send_chat_message(vk, peer_id, "❌ У вас нет прав для использования команд модерации", reply_to=msg['id'])
        return
    
    command = text.lower()
    
    # Команды режима тишины
    if command == '!режим_тишины вкл' and has_permission(user_id, 3):
        from main import silence_mode
        silence_mode[peer_id] = True
        send_chat_message(vk, peer_id, 
                        "🔇 РЕЖИМ ТИШИНЫ ВКЛЮЧЕН\n"
                        "Теперь писать могут только администраторы",
                        reply_to=msg['id'])
        return
        
    elif command == '!режим_тишины выкл' and has_permission(user_id, 3):
        from main import silence_mode
        silence_mode[peer_id] = False
        send_chat_message(vk, peer_id, "🔊 РЕЖИМ ТИШИНЫ ВЫКЛЮЧЕН", reply_to=msg['id'])
        return
    
    # Парсим команды с упоминаниями
    parsed = parse_old_moderation_command(text)
    if not parsed:
        print(f"❌ Не удалось распарсить команду: {text}")
        send_chat_message(vk, peer_id, "❌ Неверный формат команды", reply_to=msg['id'])
        return
        
    cmd_type, target_mention, duration, reason = parsed
    print(f"🔧 Распарсено: {cmd_type}, {target_mention}, {duration}, {reason}")
    
    # Получаем ID целевого пользователя из упоминания
    target_id = extract_user_id_from_mention(target_mention)
    if not target_id:
        # Если не удалось извлечь ID из упоминания, пробуем ответить на сообщение
        if 'reply_message' in msg:
            target_id = msg['reply_message']['from_id']
            print(f"🔧 Используем ID из ответа: {target_id}")
        else:
            send_chat_message(vk, peer_id, "❌ Не удалось определить пользователя. Используйте упоминание @id... или ответьте на сообщение пользователя", reply_to=msg['id'])
            return
    
    print(f"🔧 Целевой ID: {target_id}")
    
    # Проверяем что цель не имеет равных или высших прав
    target_role = get_user_role(target_id)
    user_role = get_user_role(user_id)
    
    print(f"🔧 Роли: пользователь {user_role}, цель {target_role}")
    
    if target_role >= user_role:
        send_chat_message(vk, peer_id, "❌ Вы не можете применить эту команду к данному пользователю", reply_to=msg['id'])
        return
    
    # Выполняем команду
    if cmd_type == 'мут':
        mute_user(vk, peer_id, target_id, user_id, duration, reason, reply_to=msg['id'])
    elif cmd_type == 'размут':
        unmute_user(vk, peer_id, target_id, user_id, reply_to=msg['id'])
    elif cmd_type == 'кик':
        kick_user(vk, peer_id, target_id, user_id, reason, reply_to=msg['id'])
    elif cmd_type == 'бан':
        ban_user(vk, peer_id, target_id, user_id, duration, reason, reply_to=msg['id'])

def handle_new_chat_commands(vk, msg, user_id, text, peer_id):
    """Обрабатывает новые команды модерации в чатах (с /)"""
    print(f"🔧 Обрабатываю новую команду в чате: {text}")
    
    # Команда "Кто" - показывает список руководства
    if text.lower() == 'кто':
        show_leadership_list(vk, peer_id)
        return
    
    # Проверяем права пользователя для модерационных команд
    if text.startswith('/') and not has_permission(user_id, 2):
        print(f"❌ У пользователя {user_id} нет прав для модерации")
        send_chat_message(vk, peer_id, "❌ У вас нет прав для использования команд модерации", reply_to=msg['id'])
        return
    
    # Парсим новые команды
    parsed = parse_new_moderation_command(text)
    if not parsed:
        print(f"❌ Не удалось распарсить команду: {text}")
        send_chat_message(vk, peer_id, "❌ Неверный формат команды", reply_to=msg['id'])
        return
        
    cmd_type, target_mention, duration, reason, position = parsed
    print(f"🔧 Распарсено: {cmd_type}, {target_mention}, {duration}, {reason}, {position}")
    
    # Обработка команд без указания пользователя
    if cmd_type == 'help':
        show_help(vk, peer_id, user_id, reply_to=msg['id'])
        return
    elif cmd_type == 'silence_on':
        if has_permission(user_id, 3):
            from main import silence_mode
            silence_mode[peer_id] = True
            send_chat_message(vk, peer_id, 
                            "🔇 РЕЖИМ ТИШИНЫ ВКЛЮЧЕН\n"
                            "Теперь писать могут только администраторы",
                            reply_to=msg['id'])
        else:
            send_chat_message(vk, peer_id, "❌ У вас нет прав для управления режимом тишины", reply_to=msg['id'])
        return
    elif cmd_type == 'silence_off':
        if has_permission(user_id, 3):
            from main import silence_mode
            silence_mode[peer_id] = False
            send_chat_message(vk, peer_id, "🔊 РЕЖИМ ТИШИНЫ ВЫКЛЮЧЕН", reply_to=msg['id'])
        else:
            send_chat_message(vk, peer_id, "❌ У вас нет прав для управления режимом тишины", reply_to=msg['id'])
        return
    elif cmd_type == 'silence_status':
        check_silence_status(vk, peer_id, user_id, reply_to=msg['id'])
        return
    elif cmd_type == 'active_mutes':
        show_active_mutes(vk, peer_id, user_id, reply_to=msg['id'])
        return
    elif cmd_type == 'commands_list':
        show_commands_list(vk, peer_id, user_id, reply_to=msg['id'])
        return
    elif cmd_type == 'chat_info':
        show_chat_info(vk, peer_id, user_id, reply_to=msg['id'])
        return
    elif cmd_type == 'chat_admins':
        show_chat_admins(vk, peer_id, user_id, reply_to=msg['id'])
        return
    elif cmd_type == 'my_status':
        show_my_status(vk, peer_id, user_id, reply_to=msg['id'])
        return
    elif cmd_type == 'my_permissions':
        show_my_permissions(vk, peer_id, user_id, reply_to=msg['id'])
        return
    
    # Получаем ID целевого пользователя из упоминания
    target_id = extract_user_id_from_mention(target_mention)
    if not target_id:
        # Если не удалось извлечь ID из упоминания, пробуем ответить на сообщение
        if 'reply_message' in msg:
            target_id = msg['reply_message']['from_id']
            print(f"🔧 Используем ID из ответа: {target_id}")
        else:
            send_chat_message(vk, peer_id, "❌ Не удалось определить пользователя. Используйте упоминание @id... или ответьте на сообщение пользователя", reply_to=msg['id'])
            return
    
    print(f"🔧 Целевой ID: {target_id}")
    
    # Проверяем что цель не имеет равных или высших прав (для модерационных команд)
    if cmd_type in ['mute', 'ban', 'kick', 'warn', 'unban', 'set_role', 'set_role_by_name']:
        target_role = get_user_role(target_id)
        user_role = get_user_role(user_id)
        
        print(f"🔧 Роли: пользователь {user_role}, цель {target_role}")
        
        if target_role >= user_role:
            send_chat_message(vk, peer_id, "❌ Вы не можете применить эту команду к данному пользователю", reply_to=msg['id'])
            return
    
    # Выполняем команду
    if cmd_type == 'mute':
        mute_user(vk, peer_id, target_id, user_id, duration, reason, reply_to=msg['id'])
    elif cmd_type == 'unmute':
        unmute_user(vk, peer_id, target_id, user_id, reply_to=msg['id'])
    elif cmd_type == 'muteinfo':
        get_mute_info_command(vk, peer_id, target_mention, user_id, reply_to=msg['id'])
    elif cmd_type == 'kick':
        kick_user(vk, peer_id, target_id, user_id, reason, reply_to=msg['id'])
    elif cmd_type == 'ban':
        ban_user(vk, peer_id, target_id, user_id, duration, reason, reply_to=msg['id'])
    elif cmd_type == 'unban':
        unban_user_command(vk, peer_id, target_mention, user_id, reply_to=msg['id'])
    elif cmd_type == 'warn':
        warn_user(vk, peer_id, target_id, user_id, reason, reply_to=msg['id'])
    elif cmd_type == 'stats':
        show_user_stats(vk, peer_id, target_id, user_id, reply_to=msg['id'])
    elif cmd_type == 'clearwarns':
        clear_warns_user(vk, peer_id, target_id, user_id, reply_to=msg['id'])
    elif cmd_type == 'warnings_list':
        show_warnings_list(vk, peer_id, target_mention, user_id, reply_to=msg['id'])
    elif cmd_type == 'assign':
        assign_leader(vk, peer_id, target_mention, user_id, position, reply_to=msg['id'])
    elif cmd_type == 'remove_leader':
        remove_leader_command(vk, peer_id, target_mention, user_id, reply_to=msg['id'])
    elif cmd_type == 'set_role':
        set_role_command(vk, peer_id, target_mention, user_id, duration, reason, reply_to=msg['id'])
    elif cmd_type == 'set_role_by_name':
        set_role_by_name_command(vk, peer_id, target_mention, user_id, reason, reply_to=msg['id'])

def check_user_mute(user_id, peer_id):
    """Проверяет, находится ли пользователь в муте"""
    return mute_system.check_mute(user_id, peer_id)

def process_user_message(vk, msg):
    """Обрабатывает ВСЕ сообщения пользователей - проверяет муты и режим тишины"""
    try:
        peer_id = msg.get('peer_id', 0)
        user_id = msg.get('from_id', 0)
        message_id = msg.get('id', 0)
        text = msg.get('text', '')
        
        # Проверяем что это беседа
        if peer_id < 2000000000:
            return True
            
        # Игнорируем команды бота и сообщения от админов
        if text.startswith('/') or text.startswith('!') or text.lower() == 'кто':
            return True
            
        # Проверяем права пользователя (админы игнорируют ограничения)
        if has_permission(user_id, 2):  # Модераторы и выше могут писать всегда
            return True
            
        # 1. Сначала проверяем режим тишины
        from main import silence_mode
        if peer_id in silence_mode and silence_mode[peer_id]:
            print(f"🔇 Удаляем сообщение в режиме тишины от пользователя {user_id}")
            delete_user_message(vk, peer_id, message_id, user_id)
            send_chat_message(vk, peer_id, 
                            f"🔇 Сообщение удалено. Режим тишины включен.\n"
                            f"Писать могут только администраторы.")
            return False
            
        # 2. Затем проверяем мут
        mute_data = check_user_mute(user_id, peer_id)
        if mute_data:
            print(f"🔇 Пользователь {user_id} в муте, удаляем сообщение")
            delete_user_message(vk, peer_id, message_id, user_id)
            
            # Отправляем уведомление о муте
            time_left = mute_data['until'] - datetime.now()
            minutes_left = max(1, int(time_left.total_seconds() / 60))
            
            send_chat_message(vk, peer_id,
                            f"🔇 Вы в муте! Осталось: {minutes_left} мин.\n"
                            f"До: {mute_data['until'].strftime('%H:%M:%S')}")
            return False
            
        return True
        
    except Exception as e:
        print(f"❌ Ошибка в process_user_message: {e}")
        return True

def delete_user_message(vk, peer_id, message_id, user_id):
    """Удаляет сообщение пользователя"""
    try:
        vk.messages.delete(
            message_ids=message_id,
            delete_for_all=True,
            peer_id=peer_id
        )
        print(f"✅ Сообщение {message_id} от пользователя {user_id} удалено")
        return True
    except Exception as e:
        print(f"❌ Ошибка удаления сообщения {message_id}: {e}")
        return False

def show_help(vk, peer_id, user_id, reply_to=None):
    """Показывает справку по всем командам бота"""
    print(f"🔧 Показываем справку для пользователя {user_id}")
    
    if not has_permission(user_id, 3):  # Только админы и выше
        send_chat_message(vk, peer_id, "❌ У вас нет прав для просмотра этой справки", reply_to=reply_to)
        return
    
    help_message = """
👑 СПРАВКА ПО КОМАНДАМ БОТА

📋 ОСНОВНЫЕ КОМАНДЫ:
• /help - эта справка (только для администраторов)
• Кто - показывает список руководства сервера
• /my_status - ваш статус
• /my_permissions - ваши права

⚡ КОМАНДЫ МОДЕРАЦИИ:
• /mute @user [время] [причина] - выдать мут пользователю
• /unmute @user - снять мут
• /muteinfo @user - информация о муте
• /active_mutes - активные муты (админы)
• /kick @user [причина] - кикнуть пользователя
• /ban @user [время] [причина] - забанить пользователя
• /unban @user - разбанить пользователя
• /warn @user [причина] - выдать предупреждение
• /clearwarns @user - очистить предупреждения
• /warnings @user - показать предупреждения
• /silence on - включить режим тишины
• /silence off - выключить режим тишины
• /silence status - статус режима тишины

👑 КОМАНДЫ РУКОВОДСТВА:
• /назначить @user [должность] - добавить в руководство
• /удалить @user - удалить из руководства

🎭 КОМАНДЫ РОЛЕЙ:
• /роль @user [уровень] [причина] - назначить роль (1-5)
• /роль @user [название] - назначить роль по названию

📊 КОМАНДЫ СТАТИСТИКИ:
• /стата [@user] - статистика пользователя
• /users - список пользователей
• /chat info - информация о чате
• /chat admins - администраторы чата
• /commands - список команд

💡 ПРИМЕЧАНИЯ:
• Время мута указывается в минутах (5-10080)
• Время бана указывается в днях (1-365)
• Администраторы не могут быть замьючены
• Муты работают только в том чате, где были выданы
    """
    
    send_chat_message(vk, peer_id, help_message, reply_to=reply_to)

# ... остальные функции остаются без изменений до parse_new_moderation_command ...

def parse_new_moderation_command(text):
    """Парсит новые команды модерации (с /)"""
    print(f"🔧 Парсим новую команду: {text}")
    
    parts = text.split()
    if len(parts) < 1:
        return None
    
    cmd_type = parts[0].lower().replace('/', '')
    
    # Команды без обязательных параметров
    if cmd_type in ['help', 'active_mutes', 'commands_list', 'chat_info', 'chat_admins', 
                    'my_status', 'my_permissions', 'users_list', 'silence_status']:
        return (cmd_type, '', 0, '', '')
    
    # Команды режима тишины
    if cmd_type == 'silence':
        if len(parts) >= 2:
            if parts[1].lower() in ['вкл', 'on', 'включить', 'enable']:
                return ('silence_on', '', 0, '', '')
            elif parts[1].lower() in ['выкл', 'off', 'выключить', 'disable']:
                return ('silence_off', '', 0, '', '')
            elif parts[1].lower() in ['статус', 'status']:
                return ('silence_status', '', 0, '', '')
    
    # Команды без обязательного упоминания
    if len(parts) < 2:
        if cmd_type in ['стата', 'stats']:
            return ('stats', 'self', 0, '', '')
        elif cmd_type in ['clearwarns', 'снятьпреды']:
            return ('clearwarns', 'self', 0, '', '')
        return None
    
    target_mention = parts[1]
    
    # Команды модерации с улучшенной обработкой
    if cmd_type == 'unmute':
        return ('unmute', target_mention, 0, '', '')
    elif cmd_type == 'muteinfo' or cmd_type == 'мутинфо':
        return ('muteinfo', target_mention, 0, '', '')
    elif cmd_type == 'kick':
        reason = ' '.join(parts[2:]) if len(parts) > 2 else 'Не указана'
        return ('kick', target_mention, 0, reason, '')
    elif cmd_type == 'mute':
        if len(parts) >= 4:
            try:
                duration = int(parts[2])
                # Валидация времени (от 1 минуты до 7 дней)
                if duration < 5:
                    duration = 5  # Минимум 5 минут
                elif duration > 10080:  # 7 дней
                    duration = 10080
                reason = ' '.join(parts[3:])
                return ('mute', target_mention, duration, reason, '')
            except ValueError:
                return None
        elif len(parts) == 3:
            # Проверяем, является ли третий аргумент числом (временем)
            try:
                duration = int(parts[2])
                if duration < 5:
                    duration = 5
                elif duration > 10080:
                    duration = 10080
                return ('mute', target_mention, duration, 'Не указана', '')
            except ValueError:
                # Если не число, то это причина, время по умолчанию
                reason = parts[2]
                return ('mute', target_mention, 60, reason, '')
        else:
            # Только команда и упоминание
            return ('mute', target_mention, 60, 'Не указана', '')
    elif cmd_type == 'ban':
        if len(parts) >= 4:
            try:
                duration = int(parts[2])
                # Валидация времени бана (в днях, от 1 до 365 дней)
                if duration < 1:
                    duration = 1
                elif duration > 365:
                    duration = 365
                reason = ' '.join(parts[3:])
                # Конвертируем дни в минуты для внутреннего использования
                duration_minutes = duration * 1440
                return ('ban', target_mention, duration_minutes, reason, '')
            except ValueError:
                return None
        elif len(parts) == 3:
            try:
                duration = int(parts[2])
                if duration < 1:
                    duration = 1
                elif duration > 365:
                    duration = 365
                duration_minutes = duration * 1440
                return ('ban', target_mention, duration_minutes, 'Не указана', '')
            except ValueError:
                reason = parts[2]
                return ('ban', target_mention, 1440, reason, '')
        else:
            return ('ban', target_mention, 1440, 'Не указана', '')
    elif cmd_type in ['unban', 'разбан']:
        return ('unban', target_mention, 0, '', '')
    elif cmd_type == 'warn':
        reason = ' '.join(parts[2:]) if len(parts) > 2 else 'Не указана'
        return ('warn', target_mention, 0, reason, '')
    elif cmd_type in ['стата', 'stats']:
        return ('stats', target_mention, 0, '', '')
    elif cmd_type in ['clearwarns', 'снятьпреды']:
        return ('clearwarns', target_mention, 0, '', '')
    elif cmd_type in ['warnings', 'преды']:
        return ('warnings_list', target_mention, 0, '', '')
    elif cmd_type in ['назначить', 'assign']:
        if len(parts) >= 3:
            position = ' '.join(parts[2:])
            return ('assign', target_mention, 0, '', position)
        else:
            return None
    elif cmd_type in ['удалить', 'remove']:
        return ('remove_leader', target_mention, 0, '', '')
    elif cmd_type in ['роль', 'role']:
        if len(parts) >= 3:
            role_value = parts[2]
            # Пробуем понять, это число (уровень роли) или название
            try:
                role_level = int(role_value)
                if 1 <= role_level <= 5:
                    reason = ' '.join(parts[3:]) if len(parts) > 3 else 'Назначение роли'
                    return ('set_role', target_mention, role_level, reason, '')
            except ValueError:
                # Если не число, используем как название роли
                role_name = ' '.join(parts[2:])
                return ('set_role_by_name', target_mention, 0, role_name, '')
    elif cmd_type in ['команды', 'commands']:
        return ('commands_list', '', 0, '', '')
    elif cmd_type in ['users', 'юзеры']:
        return ('users_list', '', 0, '', '')
    elif cmd_type in ['chat', 'чат']:
        if len(parts) >= 2:
            subcmd = parts[1].lower()
            if subcmd in ['инфо', 'info']:
                return ('chat_info', '', 0, '', '')
            elif subcmd in ['админы', 'admins']:
                return ('chat_admins', '', 0, '', '')
    
    return None

# ... остальной код остается без изменений ...

def get_mute_info_command(vk, peer_id, target_mention, user_id, reply_to=None):
    """Показывает информацию о муте пользователя"""
    target_id = extract_user_id_from_mention(target_mention)
    if not target_id:
        send_chat_message(vk, peer_id, "❌ Не удалось определить пользователя", reply_to=reply_to)
        return
    
    mute_data = mute_system.get_mute_info(target_id)
    
    if mute_data:
        time_left = mute_data['until'] - datetime.now()
        minutes_left = max(0, int(time_left.total_seconds() / 60))
        hours_left = minutes_left // 60
        minutes_remain = minutes_left % 60
        
        target_info = get_user_info(vk, target_id)
        moderator_info = get_user_info(vk, mute_data['moderator'])
        
        message = (
            f"📊 ИНФОРМАЦИЯ О МУТЕ\n"
            f"👤 Пользователь: {target_info}\n"
            f"⏰ Выдан на: {format_duration(mute_data['duration'])}\n"
            f"🕐 Осталось: {hours_left}ч {minutes_remain}м\n"
            f"📅 Истекает: {mute_data['until'].strftime('%H:%M:%S %d.%m.%Y')}\n"
            f"📝 Причина: {mute_data.get('reason', 'Не указана')}\n"
            f"👮 Модератор: {moderator_info}"
        )
    else:
        message = "✅ Пользователь не в муте"
    
    send_chat_message(vk, peer_id, message, reply_to=reply_to)

def show_active_mutes(vk, peer_id, user_id, reply_to=None):
    """Показывает все активные муты"""
    if not has_permission(user_id, 3):  # Только админы
        send_chat_message(vk, peer_id, "❌ У вас нет прав для этой команды", reply_to=reply_to)
        return
    
    mutes = mute_system.get_active_mutes()
    
    if not mutes:
        send_chat_message(vk, peer_id, "📭 Нет активных мутов", reply_to=reply_to)
        return
    
    message = "📊 АКТИВНЫЕ МУТЫ:\n\n"
    
    for mute_user_id, data in mutes.items():
        time_left = data['until'] - datetime.now()
        minutes_left = max(0, int(time_left.total_seconds() / 60))
        hours_left = minutes_left // 60
        minutes_remain = minutes_left % 60
        
        user_info = get_user_info(vk, mute_user_id)
        moderator_info = get_user_info(vk, data['moderator'])
        
        message += (
            f"👤 {user_info}\n"
            f"  Чат: {data['peer_id']}\n"
            f"  Осталось: {hours_left}ч {minutes_remain}м\n"
            f"  Причина: {data.get('reason', 'Не указана')[:50]}\n"
            f"  Модератор: {moderator_info}\n\n"
        )
    
    send_chat_message(vk, peer_id, message, reply_to=reply_to)

def check_silence_status(vk, peer_id, user_id, reply_to=None):
    """Показывает статус режима тишины"""
    if not has_permission(user_id, 3):
        send_chat_message(vk, peer_id, "❌ У вас нет прав для проверки режима тишины", reply_to=reply_to)
        return
    
    from main import silence_mode
    status = "ВКЛЮЧЕН 🔇" if silence_mode.get(peer_id, False) else "ВЫКЛЮЧЕН 🔊"
    send_chat_message(vk, peer_id, f"📢 Статус режима тишины: {status}", reply_to=reply_to)

def unban_user_command(vk, peer_id, target_mention, moderator_id, reply_to=None):
    """Разбанивает пользователя"""
    if not has_permission(moderator_id, 3):
        send_chat_message(vk, peer_id, "❌ У вас нет прав для разбана", reply_to=reply_to)
        return
    
    target_id = extract_user_id_from_mention(target_mention)
    if not target_id:
        send_chat_message(vk, peer_id, "❌ Не удалось определить пользователя", reply_to=reply_to)
        return
    
    # Удаляем из черного списка
    from blacklist import remove_blacklist_by_id
    removed = remove_blacklist_by_id(target_id, "ЧСП")
    
    if removed:
        target_info = get_user_info(vk, target_id)
        moderator_info = get_user_info(vk, moderator_id)
        send_chat_message(vk, peer_id,
                         f"✅ РАЗБАН ВЫПОЛНЕН\n"
                         f"👤 Пользователь: {target_info}\n"
                         f"👮 Модератор: {moderator_info}",
                         reply_to=reply_to)
    else:
        send_chat_message(vk, peer_id, "❌ Пользователь не найден в ЧС", reply_to=reply_to)

def show_warnings_list(vk, peer_id, target_mention, user_id, reply_to=None):
    """Показывает список предупреждений"""
    if not has_permission(user_id, 2):
        send_chat_message(vk, peer_id, "❌ У вас нет прав для просмотра предупреждений", reply_to=reply_to)
        return
    
    target_id = extract_user_id_from_mention(target_mention)
    if target_id == 'self':
        target_id = user_id
    
    if not target_id:
        send_chat_message(vk, peer_id, "❌ Не удалось определить пользователя", reply_to=reply_to)
        return
    
    from main import get_warning_count, get_warnings_history
    warning_count = get_warning_count(target_id)
    warnings_history = get_warnings_history(target_id)
    
    target_info = get_user_info(vk, target_id)
    
    message = f"⚠️ ПРЕДУПРЕЖДЕНИЯ ПОЛЬЗОВАТЕЛЯ\n"
    message += f"👤 {target_info}\n"
    message += f"📊 Всего: {warning_count}/3\n\n"
    
    if warnings_history:
        message += "📝 История:\n"
        for i, (reason, date, mod_first, mod_last) in enumerate(warnings_history, 1):
            mod_name = f"{mod_first} {mod_last}" if mod_first and mod_last else "Система"
            date_str = datetime.strptime(date, '%Y-%m-%d %H:%M:%S').strftime('%d.%m.%Y %H:%M')
            message += f"{i}. {reason} ({date_str}, {mod_name})\n"
    else:
        message += "📭 Нет предупреждений"
    
    send_chat_message(vk, peer_id, message, reply_to=reply_to)

def set_role_command(vk, peer_id, target_mention, user_id, role_level, reason, reply_to=None):
    """Назначает роль пользователю по уровню"""
    if not has_permission(user_id, 4):
        send_chat_message(vk, peer_id, "❌ У вас нет прав для назначения ролей", reply_to=reply_to)
        return
    
    target_id = extract_user_id_from_mention(target_mention)
    if not target_id:
        send_chat_message(vk, peer_id, "❌ Не удалось определить пользователя", reply_to=reply_to)
        return
    
    from main import set_user_role
    set_user_role(target_id, role_level, user_id)
    
    from main import get_role_name
    role_name = get_role_name(role_level)
    target_info = get_user_info(vk, target_id)
    moderator_info = get_user_info(vk, user_id)
    
    send_chat_message(vk, peer_id,
                     f"🎭 РОЛЬ НАЗНАЧЕНА\n"
                     f"👤 Пользователь: {target_info}\n"
                     f"📊 Уровень: {role_level} ({role_name})\n"
                     f"📝 Причина: {reason}\n"
                     f"👮 Модератор: {moderator_info}",
                     reply_to=reply_to)

def set_role_by_name_command(vk, peer_id, target_mention, user_id, role_name, reply_to=None):
    """Назначает роль пользователю по названию"""
    if not has_permission(user_id, 4):
        send_chat_message(vk, peer_id, "❌ У вас нет прав для назначения ролей", reply_to=reply_to)
        return
    
    target_id = extract_user_id_from_mention(target_mention)
    if not target_id:
        send_chat_message(vk, peer_id, "❌ Не удалось определить пользователя", reply_to=reply_to)
        return
    
    # Преобразуем название роли в уровень
    role_mapping = {
        'пользователь': 1, 'user': 1,
        'модератор': 2, 'moderator': 2, 'модер': 2,
        'администратор': 3, 'admin': 3, 'админ': 3,
        'руководитель': 4, 'leader': 4,
        'технический': 5, 'тех': 5, 'founder': 5
    }
    
    role_level = role_mapping.get(role_name.lower(), 1)
    
    from main import set_user_role
    set_user_role(target_id, role_level, user_id)
    
    from main import get_role_name
    role_display_name = get_role_name(role_level)
    target_info = get_user_info(vk, target_id)
    moderator_info = get_user_info(vk, user_id)
    
    send_chat_message(vk, peer_id,
                     f"🎭 РОЛЬ НАЗНАЧЕНА\n"
                     f"👤 Пользователь: {target_info}\n"
                     f"📊 Роль: {role_display_name} (уровень {role_level})\n"
                     f"👮 Модератор: {moderator_info}",
                     reply_to=reply_to)

def show_commands_list(vk, peer_id, user_id, reply_to=None):
    """Показывает список доступных команд"""
    role_level = get_user_role(user_id)
    
    message = "📋 ДОСТУПНЫЕ КОМАНДЫ:\n\n"
    
    # Общие команды для всех
    message += "👤 ДЛЯ ВСЕХ:\n"
    message += "• Кто - список руководства\n"
    message += "• /стата - ваша статистика\n"
    message += "• /my_status - ваш статус\n"
    message += "• /my_permissions - ваши права\n\n"
    
    # Для модераторов и выше
    if role_level >= 2:
        message += "👮 ДЛЯ МОДЕРАТОРОВ:\n"
        message += "• /mute @user [время] [причина]\n"
        message += "• /unmute @user\n"
        message += "• /kick @user [причина]\n"
        message += "• /warn @user [причина]\n"
        message += "• /clearwarns @user\n"
        message += "• /muteinfo @user\n\n"
    
    # Для администраторов и выше
    if role_level >= 3:
        message += "👑 ДЛЯ АДМИНИСТРАТОРОВ:\n"
        message += "• /ban @user [время] [причина]\n"
        message += "• /unban @user\n"
        message += "• /silence on/off/status\n"
        message += "• /active_mutes\n"
        message += "• /warnings @user\n\n"
    
    # Для руководителей и выше
    if role_level >= 4:
        message += "🌟 ДЛЯ РУКОВОДИТЕЛЕЙ:\n"
        message += "• /роль @user [уровень] [причина]\n"
        message += "• /назначить @user [должность]\n"
        message += "• /удалить @user\n\n"
    
    message += "💡 Напишите /help для подробной справки"
    
    send_chat_message(vk, peer_id, message, reply_to=reply_to)

def show_users_list(vk, peer_id, user_id, reply_to=None):
    """Показывает список пользователей"""
    if not has_permission(user_id, 3):
        send_chat_message(vk, peer_id, "❌ У вас нет прав для просмотра списка пользователей", reply_to=reply_to)
        return
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]
    
    cursor.execute("SELECT vk_id, role FROM users ORDER BY role DESC LIMIT 20")
    users = cursor.fetchall()
    conn.close()
    
    from main import get_role_name
    
    message = f"👥 ПОЛЬЗОВАТЕЛИ БОТА\n"
    message += f"📊 Всего: {total_users} пользователей\n\n"
    message += "📋 Последние 20 пользователей:\n\n"
    
    for vk_id, role_level in users:
        try:
            user_info = get_user_info(vk, vk_id)
            role_name = get_role_name(role_level)
            message += f"• {user_info} - {role_name}\n"
        except:
            message += f"• [id{vk_id}|Пользователь] - {get_role_name(role_level)}\n"
    
    send_chat_message(vk, peer_id, message, reply_to=reply_to)

def show_chat_info(vk, peer_id, user_id, reply_to=None):
    """Показывает информацию о чате"""
    if not has_permission(user_id, 2):
        send_chat_message(vk, peer_id, "❌ У вас нет прав для просмотра информации о чате", reply_to=reply_to)
        return
    
    try:
        chat_id = peer_id - 2000000000
        chat_info = vk.messages.getConversationsById(peer_ids=peer_id)
        
        if chat_info and 'items' in chat_info and chat_info['items']:
            chat = chat_info['items'][0]
            title = chat.get('chat_settings', {}).get('title', 'Без названия')
            members_count = chat.get('chat_settings', {}).get('members_count', 0)
            
            from main import silence_mode
            silence_status = "ВКЛЮЧЕН 🔇" if silence_mode.get(peer_id, False) else "ВЫКЛЮЧЕН 🔊"
            
            message = (
                f"💬 ИНФОРМАЦИЯ О ЧАТЕ\n"
                f"📛 Название: {title}\n"
                f"👥 Участников: {members_count}\n"
                f"🆔 ID чата: {chat_id}\n"
                f"🔇 Режим тишины: {silence_status}\n"
                f"🤖 Бот: {'✅ Активен' if has_permission(user_id, 2) else '❌ Нет прав'}"
            )
        else:
            message = "❌ Не удалось получить информацию о чате"
    except Exception as e:
        print(f"❌ Ошибка получения информации о чате: {e}")
        message = "❌ Ошибка получения информации о чате"
    
    send_chat_message(vk, peer_id, message, reply_to=reply_to)

def show_chat_admins(vk, peer_id, user_id, reply_to=None):
    """Показывает администраторов чата"""
    if not has_permission(user_id, 2):
        send_chat_message(vk, peer_id, "❌ У вас нет прав для просмотра администраторов чата", reply_to=reply_to)
        return
    
    try:
        chat_id = peer_id - 2000000000
        # Получаем информацию о чате
        chat_info = vk.messages.getConversationMembers(peer_id=peer_id)
        
        if chat_info and 'items' in chat_info:
            admins = []
            for member in chat_info['items']:
                if 'is_admin' in member and member['is_admin']:
                    member_id = member.get('member_id', 0)
                    if member_id > 0:  # Исключаем группы
                        admins.append(member_id)
            
            message = f"👑 АДМИНИСТРАТОРЫ ЧАТА\n"
            message += f"📊 Всего: {len(admins)} администраторов\n\n"
            
            if admins:
                for admin_id in admins[:10]:  # Показываем первые 10
                    admin_info = get_user_info(vk, admin_id)
                    message += f"• {admin_info}\n"
                
                if len(admins) > 10:
                    message += f"\n... и еще {len(admins) - 10} администраторов"
            else:
                message += "📭 Нет назначенных администраторов"
        else:
            message = "❌ Не удалось получить список администраторов"
    except Exception as e:
        print(f"❌ Ошибка получения администраторов чата: {e}")
        message = "❌ Ошибка получения администраторов чата"
    
    send_chat_message(vk, peer_id, message, reply_to=reply_to)

def show_my_status(vk, peer_id, user_id, reply_to=None):
    """Показывает статус пользователя"""
    role_level = get_user_role(user_id)
    from main import get_role_name, get_warning_count
    role_name = get_role_name(role_level)
    warning_count = get_warning_count(user_id)
    
    user_info = get_user_info(vk, user_id)
    
    message = (
        f"📊 ВАШ СТАТУС\n"
        f"👤 {user_info}\n"
        f"🎭 Роль: {role_name} (уровень {role_level})\n"
        f"⚠️ Предупреждений: {warning_count}/3\n"
        f"💬 Чат: ID {peer_id}"
    )
    
    # Проверяем мут
    mute_data = mute_system.check_mute(user_id, peer_id)
    if mute_data:
        time_left = mute_data['until'] - datetime.now()
        minutes_left = max(0, int(time_left.total_seconds() / 60))
        message += f"\n🔇 ВЫ В МУТЕ! Осталось: {minutes_left} минут"
    
    send_chat_message(vk, peer_id, message, reply_to=reply_to)

def show_my_permissions(vk, peer_id, user_id, reply_to=None):
    """Показывает права пользователя"""
    role_level = get_user_role(user_id)
    from main import get_role_name
    role_name = get_role_name(role_level)
    
    message = f"🔐 ВАШИ ПРАВА\n"
    message += f"🎭 Роль: {role_name} (уровень {role_level})\n\n"
    
    message += "✅ Разрешено:\n"
    
    if role_level >= 2:
        message += "• Выдавать муты\n"
        message += "• Кикать пользователей\n"
        message += "• Выдавать предупреждения\n"
    
    if role_level >= 3:
        message += "• Банить пользователей\n"
        message += "• Управлять режимом тишины\n"
        message += "• Просматривать ЧС\n"
    
    if role_level >= 4:
        message += "• Назначать роли\n"
        message += "• Управлять руководством\n"
    
    if role_level >= 5:
        message += "• Полный доступ ко всем функциям\n"
    
    send_chat_message(vk, peer_id, message, reply_to=reply_to)