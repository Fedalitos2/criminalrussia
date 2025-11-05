# scheduler.py
import threading
import time
from blacklist import get_expired_entries, remove_blacklist_record
from vk_api import VkApi
from vk_api.utils import get_random_id

CHECK_INTERVAL = 30  # секунд между проверками

class Scheduler:
    def __init__(self, vk_api: VkApi, log_fn=None):
        self.vk = vk_api.get_api()
        self.running = False
        self.thread = None
        self.log = log_fn or (lambda *a, **k: None)

    def start(self):
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()
        self.log("Scheduler started.")

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=1)

    def _loop(self):
        while self.running:
            try:
                expired = get_expired_entries()
                for rec in expired:
                    rec_id, vk_id, nickname, type_, reason, added_by, expire_at = rec
                    # Удаляем запись
                    remove_blacklist_record(rec_id)
                    # Отправляем уведомление администратору (added_by) если возможно
                    if added_by:
                        text = f"⏳ Запись из ЧС ({type_}) для {nickname or vk_id} удалена — срок истёк."
                        try:
                            self.vk.messages.send(user_id=added_by, message=text, random_id=get_random_id())
                        except Exception:
                            # если не удалось отправить, просто игнорируем
                            pass
                time.sleep(CHECK_INTERVAL)
            except Exception as e:
                # логируем и продолжаем
                try:
                    self.log("Scheduler error:", str(e))
                except Exception:
                    pass
                time.sleep(CHECK_INTERVAL)
