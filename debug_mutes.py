# debug_mutes.py - Утилита для отладки мутов
from mute_system import mute_system
from datetime import datetime

def print_active_mutes():
    """Печатает все активные муты"""
    mutes = mute_system.get_active_mutes()
    
    if not mutes:
        print("📭 Нет активных мутов")
        return
    
    print(f"📊 Активные муты ({len(mutes)}):")
    print("-" * 50)
    
    for user_id, data in mutes.items():
        time_left = data['until'] - datetime.now()
        minutes_left = max(0, int(time_left.total_seconds() / 60))
        
        print(f"👤 ID: {user_id}")
        print(f"  Чат: {data['peer_id']}")
        print(f"  До: {data['until'].strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"  Осталось: {minutes_left} минут")
        print(f"  Причина: {data.get('reason', 'Не указана')}")
        print(f"  Модератор: {data['moderator']}")
        print("-" * 30)

if __name__ == "__main__":
    print_active_mutes()