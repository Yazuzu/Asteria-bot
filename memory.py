from collections import deque
import json
from pathlib import Path


class ChannelMemory:
    def __init__(self, channel_id: int):
        self.channel_id = str(channel_id)
        self.file = Path("data/memory") / f"{self.channel_id}.json"
        self.messages: deque = deque(maxlen=6)
        self.load()

    def add(self, user_msg: str, bot_msg: str):
        self.messages.append({"user": user_msg, "bot": bot_msg})
        self.save()

    def get_context(self) -> str:
        if not self.messages:
            return ""
        return "\n".join(
            f"Usuário: {m['user']}\nAstéria: {m['bot']}" for m in self.messages
        ) + "\n"

    def clear(self):
        self.messages.clear()
        if self.file.exists():
            self.file.unlink()

    def save(self):
        try:
            with open(self.file, "w", encoding="utf-8") as f:
                json.dump(list(self.messages), f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def load(self):
        if self.file.exists():
            try:
                with open(self.file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.messages.extend(data[-6:])
            except Exception:
                pass


class MemoryManager:
    def __init__(self):
        self.memories: dict[int, ChannelMemory] = {}

    def get(self, channel_id: int) -> ChannelMemory:
        if channel_id not in self.memories:
            self.memories[channel_id] = ChannelMemory(channel_id)
        return self.memories[channel_id]

    def clear(self, channel_id: int):
        mem = self.get(channel_id)
        mem.clear()
