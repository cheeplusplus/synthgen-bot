import discord
import logging

logger = logging.getLogger(__name__)


# The idea here is to have an abstracted 'thread' that holds some state of a conversation


class ChatThreadMessage:
    def __init__(self, message: discord.Message, bot_user: discord.ClientUser):
        self.message = message
        self.bot_user = bot_user

    def to_conversation(self):
        if self.message.content.startswith("---\n"):
            return None

        role = "assistant" if self.message.author is self.bot_user else "user"
        return {"role": role, "content": self.message.clean_content}


class ChatThread:
    messages: list[ChatThreadMessage]
    thread: discord.Thread

    def __init__(self, thread: discord.Thread):
        self.messages = []
        self.thread = thread

    async def load(self, client: discord.Client):
        async for message in self.thread.history(limit=100, oldest_first=True):
            self.messages.append(ChatThreadMessage(message, client))

            ### Cleanup

            if message.type not in [
                discord.MessageType.thread_starter_message,
                discord.MessageType.default,
                discord.MessageType.reply,
            ]:
                # Ignore other message types (thread renames, etc)
                logger.debug(
                    "Ignored thread event [name: %s, type: %s, author: %s]: %s",
                    self.thread.name,
                    message.type,
                    message.author,
                    message.system_content,
                )
                pass
            elif (
                message.type == discord.MessageType.thread_starter_message
                and message.reference
                and isinstance(message.reference.resolved, discord.Message)
            ):
                # Initial thread message - this looks like a bot message but it refers to the original
                # discordpy just doesn't handle this correctly apparently
                logger.debug(
                    "Thread loaded initial user message [name: %s, type: %s, author: %s]: %s",
                    self.thread.name,
                    message.type,
                    message.author,
                    message.system_content,
                )
                cleaned_msg = message.reference.resolved.content.replace(
                    client.user.mention, ""
                ).strip()
                convo.add_user_message(cleaned_msg)
            elif not message.content:
                # Ignore empty messages after this point
                logger.debug(
                    "Ignored thread load [name: %s, type: %s, author: %s]: %s",
                    self.thread.name,
                    message.type,
                    message.author,
                    message.content,
                )
                pass
            elif message.author == client.user:
                # Reply from us (bot)
                logger.debug(
                    "Thread loaded bot message [name: %s, type: %s, author: %s]: %s",
                    self.thread.name,
                    message.type,
                    message.author,
                    message.content,
                )
                convo.add_assistant_message(message.clean_content)
            elif message.author.bot:
                # Reply from other bot
                logger.debug(
                    "Thread ignored bot message [name: %s, type: %s, author: %s]: %s",
                    self.thread.name,
                    message.type,
                    message.author,
                    message.content,
                )
                # Ignore other bot's messages
                pass
            else:
                # Reply from user
                logger.debug(
                    "Thread loaded user message [name: %s, type: %s, author: %s]: %s",
                    self.thread.name,
                    message.type,
                    message.author,
                    message.content,
                )
                convo.add_user_message(message.clean_content)
