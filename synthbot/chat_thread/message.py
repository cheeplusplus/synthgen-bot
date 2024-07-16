from abc import ABC
import discord
import logging

logger = logging.getLogger(__name__)


class ChatThreadMessage(ABC):
    author_id: int
    thread_id: int
    message_id: int
    message_text: str

    def __init__(
        self, message: discord.Message, full_text: str = None, strip_mention: str = None
    ):
        self.author_id = message.author.id
        self.thread_id = message.channel
        self.message_id = message.id

        if full_text:
            self.message_text = full_text
        elif strip_mention:
            self.message_text = message.content.replace(strip_mention, "").strip()
        else:
            self.message_text = message.clean_content

    def to_conversation(self, bot_user: discord.ClientUser) -> dict[str, str] | None:
        """Get the conversation component of this message."""
        return None


class ChatThreadConversationMessage(ChatThreadMessage):
    def to_conversation(self, bot_user: discord.ClientUser):
        if self.message_text.startswith("---\n"):
            return None

        role = "assistant" if self.author_id is bot_user.id else "user"
        return {"role": role, "content": self.message_text}


def parse_discord_message(
    message: discord.Message, bot_user: discord.ClientUser, full_text: str = None
):
    """Parse a Discord message into the approperate ChatThreadMessage type."""
    thread_name = message.channel.name

    if message.type not in [
        discord.MessageType.thread_starter_message,
        discord.MessageType.default,
        discord.MessageType.reply,
    ]:
        # Ignore other message types (thread renames, etc)
        logger.debug(
            "Ignored thread event [name: %s, type: %s, author: %s]: %s",
            message.type,
            message.author,
            message.system_content,
        )
        return None
    elif (
        message.type == discord.MessageType.thread_starter_message
        and message.reference
        and isinstance(message.reference.resolved, discord.Message)
    ):
        # Initial thread message - this looks like a bot message but it refers to the original
        # discordpy just doesn't handle this correctly apparently
        logger.debug(
            "Thread loaded initial user message [name: %s, type: %s, author: %s]: %s",
            thread_name,
            message.type,
            message.author,
            message.system_content,
        )
        return ChatThreadConversationMessage(
            message.reference.resolved,
            full_text=full_text,
            strip_mention=bot_user.mention,
        )
    elif not message.content:
        # Ignore empty messages after this point
        logger.debug(
            "Ignored thread load [name: %s, type: %s, author: %s]: %s",
            thread_name,
            message.type,
            message.author,
            message.content,
        )
        return None
    elif message.author == bot_user:
        # Reply from us (bot)
        logger.debug(
            "Thread loaded bot message [name: %s, type: %s, author: %s]: %s",
            thread_name,
            message.type,
            message.author,
            message.content,
        )
        return ChatThreadConversationMessage(message, full_text=full_text)
    elif message.author.bot:
        # Reply from other bot
        logger.debug(
            "Thread ignored bot message [name: %s, type: %s, author: %s]: %s",
            thread_name,
            message.type,
            message.author,
            message.content,
        )
        # Ignore other bot's messages
        return None
    else:
        # Reply from user
        logger.debug(
            "Thread loaded user message [name: %s, type: %s, author: %s]: %s",
            thread_name,
            message.type,
            message.author,
            message.content,
        )
        return ChatThreadConversationMessage(message, full_text=full_text)
