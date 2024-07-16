import discord
import logging

from .thread import ChatThread

logger = logging.getLogger(__name__)


class ChatThreadManager:
    threads: dict[int, ChatThread]

    def __init__(self):
        self.threads = {}

    async def get_thread(self, bot_user: discord.ClientUser, thread: discord.Thread):
        thread_id = thread.id
        if thread_id in self.threads:
            return self.threads[thread_id]

        ct = ChatThread(bot_user, thread)
        await ct.load()
        self.threads[thread_id] = ct
        return ct
