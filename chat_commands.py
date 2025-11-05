# chat_commands.py
import re
from datetime import datetime, timedelta
import sqlite3
from config import DB_PATH
from vk_api.utils import get_random_id
from leadership import add_leader, remove_leader, get_all_leaders
from database import get_user_role, has_permission

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
    
    # Команда /help - показывает справку по командам
    if cmd_type == 'help':
        show_help(vk, peer_id, user_id, reply_to=msg['id'])
        return
    
    # Команда /silence on/off - управление режимом тишины
    if cmd_type == 'silence_on':
        if has_permission(user_id, 3):  # Только админы и выше
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
        if has_permission(user_id, 3):  # Только админы и выше
            from main import silence_mode
            silence_mode[peer_id] = False
            send_chat_message(vk, peer_id, "🔊 РЕЖИМ ТИШИНЫ ВЫКЛЮЧЕН", reply_to=msg['id'])
        else:
            send_chat_message(vk, peer_id, "❌ У вас нет прав для управления режимом тишины", reply_to=msg['id'])
        return
    
    # Команда /назначить - добавляет в руководство
    if cmd_type == 'assign':
        assign_leader(vk, peer_id, target_mention, user_id, position, reply_to=msg['id'])
        return
    
    # Команда /удалить - удаляет из руководства
    if cmd_type == 'remove_leader':
        remove_leader_command(vk, peer_id, target_mention, user_id, reply_to=msg['id'])
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
    if cmd_type in ['mute', 'ban', 'kick', 'warn']:
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
    elif cmd_type == 'kick':
        kick_user(vk, peer_id, target_id, user_id, reason, reply_to=msg['id'])
    elif cmd_type == 'ban':
        ban_user(vk, peer_id, target_id, user_id, duration, reason, reply_to=msg['id'])
    elif cmd_type == 'warn':
        warn_user(vk, peer_id, target_id, user_id, reason, reply_to=msg['id'])
    elif cmd_type == 'stats':
        show_user_stats(vk, peer_id, target_id, user_id, reply_to=msg['id'])
    elif cmd_type == 'clearwarns':
        clear_warns_user(vk, peer_id, target_id, user_id, reply_to=msg['id'])

def check_user_mute(user_id, peer_id):
    """Проверяет, находится ли пользователь в муте"""
    # Импортируем общее хранилище мутов из main.py
    from main import active_mutes
    
    if user_id in active_mutes:
        mute_data = active_mutes[user_id]
        # Проверяем что мут в этом чате и время не истекло
        if mute_data['peer_id'] == peer_id and mute_data['until'] > datetime.now():
            return mute_data
    
    # Очищаем истекшие муты
    cleanup_expired_mutes()
    return None

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

def cleanup_expired_mutes():
    """Очищает истекшие муты"""
    # Импортируем общее хранилище мутов из main.py
    from main import active_mutes
    
    current_time = datetime.now()
    expired_users = []
    
    for user_id, mute_data in active_mutes.items():
        if mute_data['until'] <= current_time:
            expired_users.append(user_id)
            print(f"🕐 Мут для пользователя {user_id} истек")
    
    for user_id in expired_users:
        del active_mutes[user_id]

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

⚡ КОМАНДЫ МОДЕРАЦИИ:
• /mute @user [время] [причина] - выдать мут пользователю
  Пример: /mute @id123456 60 Спам
  Время в минутах (по умолчанию: 60)

• /unmute @user - снять мут с пользователя

• /kick @user [причина] - кикнуть пользователя из беседы
  Пример: /kick @id123456 Нарушение правил

• /ban @user [время] [причина] - забанить пользователя
  Пример: /ban @id123456 1440 Массовый спам
  Время в днях (по умолчанию: 1)

• /warn @user [причина] - выдать предупреждение
  Пример: /warn @id123456 Грубое поведение
  ⚠️ 3 предупреждения = автоматический кик!

• /clearwarns @user - очистить предупреждения пользователя

• /silence on - включить режим тишины
• /silence off - выключить режим тишины

📊 КОМАНДЫ СТАТИСТИКИ:
• /стата - показать вашу статистику
• /стата @user - показать статистику пользователя

👑 КОМАНДЫ РУКОВОДСТВА:
• /назначить @user [должность] - добавить в список руководства
  Пример: /назначить @id123456 Главный администратор

• /удалить @user - удалить из списка руководства

🎯 СТАРЫЕ КОМАНДЫ (для обратной совместимости):
• !мут @user [время] [причина]
• !размут @user
• !кик @user [причина]
• !бан @user [время] [причина]
• !режим_тишины вкл/выкл

💡 ПРИМЕЧАНИЯ:
• Все команды работают через упоминания (@id...) или ответы на сообщения
• Время указывается в минутах для мута, в днях для бана
• Причины можно не указывать, но рекомендуется
• Команды доступны в зависимости от вашей роли

🛠 ДОПОЛНИТЕЛЬНО:
В личных сообщениях бота доступна админ-панель с расширенными функциями:
• Управление черными списками
• Просмотр статистики бота
• Управление ролями пользователей

Для доступа к админ-панели напишите боту в ЛС: "панель"
    """
    
    send_chat_message(vk, peer_id, help_message, reply_to=reply_to)

def assign_leader(vk, peer_id, target_mention, moderator_id, position, reply_to=None):
    """Добавляет пользователя в список руководства"""
    print(f"🔧 Добавляем пользователя в руководство: {target_mention} как {position}")
    
    if not has_permission(moderator_id, 3):  # Только админы и выше могут добавлять
        send_chat_message(vk, peer_id, "❌ У вас нет прав для добавления в руководство", reply_to=reply_to)
        return
    
    # Получаем ID пользователя из упоминания
    target_id = extract_user_id_from_mention(target_mention)
    if not target_id:
        send_chat_message(vk, peer_id, "❌ Не удалось определить пользователя. Используйте упоминание @id...", reply_to=reply_to)
        return
    
    try:
        # Получаем информацию о пользователе для отображения
        user_info = get_user_info(vk, target_id)
        display_name = user_info.replace(f"[id{target_id}|", "").replace("]", "")
        
        add_leader(target_id, position, display_name, moderator_id)
        
        moderator_info = get_user_info(vk, moderator_id)
        
        send_chat_message(vk, peer_id,
                        f"✅ ДОБАВЛЕНИЕ В РУКОВОДСТВО\n"
                        f"👤 Пользователь: {user_info}\n"
                        f"💼 Должность: {position}\n"
                        f"👮 Добавил: {moderator_info}",
                        reply_to=reply_to)
                        
    except Exception as e:
        print(f"❌ Ошибка добавления: {e}")
        send_chat_message(vk, peer_id, "❌ Не удалось добавить пользователя в руководство", reply_to=reply_to)

def remove_leader_command(vk, peer_id, target_mention, moderator_id, reply_to=None):
    """Удаляет пользователя из списка руководства"""
    print(f"🔧 Удаляем пользователя из руководства: {target_mention}")
    
    if not has_permission(moderator_id, 3):  # Только админы и выше могут удалять
        send_chat_message(vk, peer_id, "❌ У вас нет прав для удаления из руководства", reply_to=reply_to)
        return
    
    # Получаем ID пользователя из упоминания
    target_id = extract_user_id_from_mention(target_mention)
    if not target_id:
        send_chat_message(vk, peer_id, "❌ Не удалось определить пользователя. Используйте упоминание @id...", reply_to=reply_to)
        return
    
    try:
        if remove_leader(target_id):
            user_info = get_user_info(vk, target_id)
            moderator_info = get_user_info(vk, moderator_id)
            
            send_chat_message(vk, peer_id,
                            f"✅ УДАЛЕНИЕ ИЗ РУКОВОДСТВА\n"
                            f"👤 Пользователь: {user_info}\n"
                            f"👮 Удалил: {moderator_info}",
                            reply_to=reply_to)
        else:
            send_chat_message(vk, peer_id, "❌ Пользователь не найден в списке руководства", reply_to=reply_to)
                        
    except Exception as e:
        print(f"❌ Ошибка удаления: {e}")
        send_chat_message(vk, peer_id, "❌ Не удалось удалить пользователя из руководства", reply_to=reply_to)

def show_leadership_list(vk, peer_id):
    """Показывает красивый список руководства"""
    print(f"🔧 Показываем список руководства")
    
    leaders = get_all_leaders()
    
    if not leaders:
        send_chat_message(vk, peer_id, 
                        "📋 УВАЖАЕМЫЕ ИГРОКИ!\n\n"
                        "В настоящее время руководство сервера не назначено.\n"
                        "Для добавления используйте команду /назначить")
        return
    
    message = "👑 УВАЖАЕМЫЕ ИГРОКИ!\n\n"
    message += "📋 Это список руководства сервера:\n\n"
    
    for leader in leaders:
        user_id, position, display_name, assigned_at = leader
        user_info = get_user_info(vk, user_id)
        
        message += f"• {user_info} - {position}\n"
    
    message += f"\n💫 С уважением, команда проекта!"
    
    send_chat_message(vk, peer_id, message)

def get_user_role(vk_id):
    """Получает уровень роли пользователя (число)"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT role FROM users WHERE vk_id = ?", (vk_id,))
    result = cursor.fetchone()
    conn.close()
    return result[0] if result else 1

def has_permission(user_id, required_level):
    """Проверяет, имеет ли пользователь достаточный уровень прав"""
    user_role = get_user_role(user_id)
    return user_role >= required_level

def parse_old_moderation_command(text):
    """Парсит старые команды модерации (с !)"""
    print(f"🔧 Парсим старую команду: {text}")
    
    # Упрощенный парсинг для отладки
    parts = text.split()
    if len(parts) < 2:
        return None
    
    cmd_type = parts[0].lower().replace('!', '')
    target_mention = parts[1]
    
    if cmd_type == 'размут':
        return ('размут', target_mention, 0, '')
    elif cmd_type == 'кик':
        reason = ' '.join(parts[2:]) if len(parts) > 2 else 'Не указана'
        return ('кик', target_mention, 0, reason)
    elif cmd_type == 'мут':
        if len(parts) >= 4:
            try:
                duration = int(parts[2])
                reason = ' '.join(parts[3:])
                return ('мут', target_mention, duration, reason)
            except ValueError:
                return None
        else:
            # Если время не указано, используем 60 минут по умолчанию
            reason = ' '.join(parts[2:]) if len(parts) > 2 else 'Не указана'
            return ('мут', target_mention, 60, reason)
    elif cmd_type == 'бан':
        if len(parts) >= 4:
            try:
                duration = int(parts[2])
                reason = ' '.join(parts[3:])
                return ('бан', target_mention, duration, reason)
            except ValueError:
                return None
        else:
            # Если время не указано, используем 1 день по умолчанию
            reason = ' '.join(parts[2:]) if len(parts) > 2 else 'Не указана'
            return ('бан', target_mention, 1440, reason)
    
    return None

def parse_new_moderation_command(text):
    """Парсит новые команды модерации (с /)"""
    print(f"🔧 Парсим новую команду: {text}")
    
    parts = text.split()
    if len(parts) < 1:
        return None
    
    cmd_type = parts[0].lower().replace('/', '')
    
    # Команда /help не требует дополнительных параметров
    if cmd_type == 'help':
        return ('help', '', 0, '', '')
    
    # Команды режима тишины
    if cmd_type == 'silence':
        if len(parts) >= 2:
            if parts[1].lower() == 'on':
                return ('silence_on', '', 0, '', '')
            elif parts[1].lower() == 'off':
                return ('silence_off', '', 0, '', '')
    
    if len(parts) < 2:
        # Команда /стата может быть без упоминания (показывает статистику отправителя)
        if cmd_type == 'стата':
            return ('stats', 'self', 0, '', '')
        # Команда /clearwarns может быть без упоминания (очищает свои предупреждения)
        if cmd_type == 'clearwarns':
            return ('clearwarns', 'self', 0, '', '')
        return None
    
    target_mention = parts[1]
    
    # Команды модерации
    if cmd_type == 'unmute':
        return ('unmute', target_mention, 0, '', '')
    elif cmd_type == 'kick':
        reason = ' '.join(parts[2:]) if len(parts) > 2 else 'Не указана'
        return ('kick', target_mention, 0, reason, '')
    elif cmd_type == 'mute':
        if len(parts) >= 4:
            try:
                duration = int(parts[2])
                reason = ' '.join(parts[3:])
                return ('mute', target_mention, duration, reason, '')
            except ValueError:
                return None
        else:
            # Если время не указано, используем 60 минут по умолчанию
            reason = ' '.join(parts[2:]) if len(parts) > 2 else 'Не указана'
            return ('mute', target_mention, 60, reason, '')
    elif cmd_type == 'ban':
        if len(parts) >= 4:
            try:
                duration = int(parts[2])
                reason = ' '.join(parts[3:])
                return ('ban', target_mention, duration, reason, '')
            except ValueError:
                return None
        else:
            # Если время не указано, используем 1 день по умолчанию
            reason = ' '.join(parts[2:]) if len(parts) > 2 else 'Не указана'
            return ('ban', target_mention, 1440, reason, '')
    elif cmd_type == 'warn':
        reason = ' '.join(parts[2:]) if len(parts) > 2 else 'Не указана'
        return ('warn', target_mention, 0, reason, '')
    elif cmd_type == 'стата':
        return ('stats', target_mention, 0, '', '')
    elif cmd_type == 'clearwarns':
        return ('clearwarns', target_mention, 0, '', '')
    elif cmd_type == 'назначить':
        if len(parts) >= 3:
            position = ' '.join(parts[2:])
            return ('assign', target_mention, 0, '', position)
    elif cmd_type == 'удалить':
        return ('remove_leader', target_mention, 0, '', '')
    
    return None

def extract_user_id_from_mention(mention):
    """Извлекает ID пользователя из упоминания"""
    print(f"🔧 Извлекаем ID из: {mention}")
    
    # Форматы: @id123456, [id123456|Name], id123456
    if mention.startswith('@id'):
        try:
            return int(mention[3:])
        except:
            return None
    elif mention.startswith('[') and 'id' in mention:
        # Формат [id123456|Name]
        match = re.search(r'\[id(\d+)\|', mention)
        if match:
            return int(match.group(1))
    elif mention.startswith('@'):
        # Для ников нужно API чтобы получить ID - пока возвращаем None
        return None
    
    # Пробуем извлечь число напрямую
    try:
        # Если упоминание это просто число
        return int(mention.replace('@', '').replace('[', '').replace(']', ''))
    except:
        return None

def send_chat_message(vk, peer_id, message, reply_to=None):
    """Отправляет сообщение в чат"""
    try:
        print(f"🔧 Отправляем сообщение в чат {peer_id}: {message}")
        params = {
            "peer_id": peer_id,
            "message": message,
            "random_id": get_random_id()
        }
        if reply_to:
            params["reply_to"] = reply_to
            print(f"🔧 Ответ на сообщение {reply_to}")
        
        vk.messages.send(**params)
        print("✅ Сообщение отправлено")
    except Exception as e:
        print(f"❌ Ошибка отправки в чат: {e}")

def mute_user(vk, peer_id, target_id, moderator_id, duration_minutes, reason, reply_to=None):
    """Выдает мут пользователю"""
    print(f"🔧 Выдаем мут пользователю {target_id} на {duration_minutes} минут")
    
    # Импортируем общее хранилище мутов из main.py
    from main import active_mutes
    
    mute_until = datetime.now() + timedelta(minutes=duration_minutes)
    active_mutes[target_id] = {
        'until': mute_until,
        'peer_id': peer_id,
        'moderator': moderator_id,
        'reason': reason
    }
    
    duration_text = format_duration(duration_minutes)
    moderator_info = get_user_info(vk, moderator_id)
    target_info = get_user_info(vk, target_id)
    
    send_chat_message(vk, peer_id,
                    f"🔇 МУТ ВЫДАН\n"
                    f"👤 Пользователь: {target_info}\n"
                    f"⏰ Срок: {duration_text}\n"
                    f"📝 Причина: {reason}\n"
                    f"👮 Модератор: {moderator_info}",
                    reply_to=reply_to)
    
    print(f"✅ Мут установлен для {target_id} до {mute_until}")

def unmute_user(vk, peer_id, target_id, moderator_id, reply_to=None):
    """Снимает мут"""
    print(f"🔧 Снимаем мут с пользователя {target_id}")
    
    # Импортируем общее хранилище мутов из main.py
    from main import active_mutes
    
    if target_id in active_mutes:
        del active_mutes[target_id]
        target_info = get_user_info(vk, target_id)
        moderator_info = get_user_info(vk, moderator_id)
        
        send_chat_message(vk, peer_id,
                        f"🔊 МУТ СНЯТ\n"
                        f"👤 Пользователь: {target_info}\n"
                        f"👮 Модератор: {moderator_info}",
                        reply_to=reply_to)
    else:
        send_chat_message(vk, peer_id, "❌ Пользователь не в муте", reply_to=reply_to)

def kick_user(vk, peer_id, target_id, moderator_id, reason, reply_to=None):
    """Кикает пользователя из беседы"""
    print(f"🔧 Кикаем пользователя {target_id}")
    
    try:
        chat_id = peer_id - 2000000000
        print(f"🔧 ID чата: {chat_id}, ID пользователя: {target_id}")
        
        # Пробуем кикнуть пользователя
        result = vk.messages.removeChatUser(
            chat_id=chat_id,
            member_id=target_id
        )
        
        print(f"🔧 Результат кика: {result}")
        
        target_info = get_user_info(vk, target_id)
        moderator_info = get_user_info(vk, moderator_id)
        
        send_chat_message(vk, peer_id,
                        f"👢 КИК ВЫПОЛНЕН\n"
                        f"👤 Пользователь: {target_info}\n"
                        f"📝 Причина: {reason}\n"
                        f"👮 Модератор: {moderator_info}",
                        reply_to=reply_to)
                        
    except Exception as e:
        print(f"❌ Ошибка кика: {e}")
        error_msg = "❌ Не удалось кикнуть пользователя. Проверьте:\n"
        error_msg += "• Права бота (должен быть администратором)\n"
        error_msg += "• Права пользователя (нельзя кикнуть администратора)\n"
        error_msg += "• Пользователь находится в чате"
        send_chat_message(vk, peer_id, error_msg, reply_to=reply_to)

def ban_user(vk, peer_id, target_id, moderator_id, duration_days, reason, reply_to=None):
    """Банит пользователя (кик + добавление в ЧС)"""
    print(f"🔧 Баним пользователя {target_id} на {duration_days} дней")
    
    try:
        # Сначала кикаем пользователя
        chat_id = peer_id - 2000000000
        print(f"🔧 ID чата: {chat_id}, ID пользователя: {target_id}")
        
        vk.messages.removeChatUser(
            chat_id=chat_id,
            member_id=target_id
        )
        
        print("✅ Пользователь кикнут")
        
        # Затем добавляем в черный список
        from blacklist import add_blacklist
        nickname = f"id{target_id}"
        add_blacklist(None, nickname, "ЧСП", moderator_id, duration_days, reason)
        print("✅ Пользователь добавлен в ЧС")
        
        target_info = get_user_info(vk, target_id)
        moderator_info = get_user_info(vk, moderator_id)
        
        send_chat_message(vk, peer_id,
                        f"⛔ БАН ВЫПОЛНЕН\n"
                        f"👤 Пользователь: {target_info}\n"
                        f"⏰ Срок: {duration_days} дней\n"
                        f"📝 Причина: {reason}\n"
                        f"👮 Модератор: {moderator_info}\n"
                        f"💾 Добавлен в Чёрный список",
                        reply_to=reply_to)
                        
    except Exception as e:
        print(f"❌ Ошибка бана: {e}")
        error_msg = "❌ Не удалось забанить пользователя. Проверьте:\n"
        error_msg += "• Права бота (должен быть администратором)\n"
        error_msg += "• Права пользователя (нельзя кикнуть администратора)\n"
        error_msg += "• Пользователь находится в чате"
        send_chat_message(vk, peer_id, error_msg, reply_to=reply_to)

def warn_user(vk, peer_id, target_id, moderator_id, reason, reply_to=None):
    """Выдает предупреждение пользователю"""
    print(f"🔧 Выдаем предупреждение пользователю {target_id}")
    
    try:
        # Импортируем функцию из main.py
        from main import add_warning
        
        warning_count = add_warning(target_id, moderator_id, reason)
        
        target_info = get_user_info(vk, target_id)
        moderator_info = get_user_info(vk, moderator_id)
        
        if warning_count == "auto_kick":
            send_chat_message(vk, peer_id,
                            f"🚨 АВТОМАТИЧЕСКИЙ КИК\n"
                            f"👤 Пользователь: {target_info}\n"
                            f"📝 Причина: 3+ предупреждений\n"
                            f"👮 Система: Автоматически",
                            reply_to=reply_to)
        else:
            send_chat_message(vk, peer_id,
                            f"⚠️ ПРЕДУПРЕЖДЕНИЕ ВЫДАНО\n"
                            f"👤 Пользователь: {target_info}\n"
                            f"📝 Причина: {reason}\n"
                            f"👮 Модератор: {moderator_info}\n"
                            f"🔢 Всего предупреждений: {warning_count}/3",
                            reply_to=reply_to)
                            
    except Exception as e:
        print(f"❌ Ошибка выдачи предупреждения: {e}")
        send_chat_message(vk, peer_id, "❌ Ошибка выдачи предупреждения", reply_to=reply_to)

def clear_warns_user(vk, peer_id, target_id, moderator_id, reply_to=None):
    """Очищает предупреждения пользователя"""
    print(f"🔧 Очищаем предупреждения пользователя {target_id}")
    
    from main import clear_warnings
    clear_warnings(target_id)
    
    target_info = get_user_info(vk, target_id)
    moderator_info = get_user_info(vk, moderator_id)
    
    send_chat_message(vk, peer_id,
                    f"🔄 ПРЕДУПРЕЖДЕНИЯ ОЧИЩЕНЫ\n"
                    f"👤 Пользователь: {target_info}\n"
                    f"👮 Модератор: {moderator_info}",
                    reply_to=reply_to)

def show_user_stats(vk, peer_id, target_id, moderator_id, reply_to=None):
    """Показывает статистику пользователя с предупреждениями"""
    print(f"🔧 Показываем статистику пользователя {target_id}")
    
    # Если target_id = 'self', показываем статистику отправителя
    if target_id == 'self':
        target_id = moderator_id
    
    target_info = get_user_info(vk, target_id)
    
    # Получаем количество предупреждений
    from main import get_warning_count, get_warnings_history
    warning_count = get_warning_count(target_id)
    warnings_history = get_warnings_history(target_id)
    
    message = f"📊 СТАТИСТИКА ПОЛЬЗОВАТЕЛЯ\n"
    message += f"👤 Пользователь: {target_info}\n"
    message += f"📈 Сообщений: 0\n"
    message += f"⚠️ Предупреждений: {warning_count}/3\n"
    
    # Показываем последние 3 предупреждения
    if warnings_history:
        message += f"\n📝 Последние предупреждения:\n"
        for i, (reason, date, mod_first, mod_last) in enumerate(warnings_history[:3], 1):
            mod_name = f"{mod_first} {mod_last}" if mod_first and mod_last else "Система"
            message += f"{i}. {reason} ({date.split()[0]}, {mod_name})\n"
    
    send_chat_message(vk, peer_id, message, reply_to=reply_to)

def format_duration(minutes):
    """Форматирует длительность в читаемый вид"""
    if minutes < 60:
        return f"{minutes} минут"
    elif minutes < 1440:
        hours = minutes // 60
        return f"{hours} час"
    else:
        days = minutes // 1440
        return f"{days} дней"

def get_user_info(vk, user_id):
    """Получает информацию о пользователе для упоминания"""
    try:
        users = vk.users.get(user_ids=user_id, fields="first_name,last_name")
        if users:
            user = users[0]
            return f"[id{user_id}|{user['first_name']} {user['last_name']}]"
    except Exception as e:
        print(f"❌ Ошибка получения информации о пользователе {user_id}: {e}")
    
    return f"[id{user_id}|Пользователь]"
