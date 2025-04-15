import discord
import logging
from typing import Generator, Iterable

from ..config import bot_config
from ..gpt import GptConversation
from .message import ChatThreadMessage, parse_discord_message

logger = logging.getLogger(__name__)


# The idea here is to have an abstracted 'thread' that holds some state of a conversation


class ChatThread:
    messages: list[ChatThreadMessage]
    bot_user: discord.ClientUser
    thread: discord.Thread
    summary: str

    def __init__(self, bot_user: discord.ClientUser, thread: discord.Thread):
        self.messages = []
        self.bot_user = bot_user
        self.thread = thread
        self.summary = None

    @property
    def system_message(self):
        return "You are talking to a friendly user. Keep your replies under 1800 characters. Markdown is allowed."

    @property
    def system_message_continuation(self):
        return f'You are continuing a conversation in a thread called "{self.summary}". Keep your replies under 1800 characters. Markdown is allowed.'

    def add(
        self,
        message: discord.Message,
        full_text: str = None,
    ):
        parsed = parse_discord_message(message, self.bot_user, full_text=full_text)
        if parsed:
            self.messages.append(parsed)

    async def load(self):
        """Load messages from Discord to the thread."""
        async for message in self.thread.history(limit=100, oldest_first=True):
            self.add(message)

        if self.thread.name != bot_config.discord.default_thread_title:
            self.summary = self.thread.name

    async def summarize(self):
        """Summarize the thread."""
        if self.summary:
            return self.summary

        """Summarize a message into something shorter."""
        summconvo = GptConversation()
        summresp = await summconvo.get_response(
            [
                {
                    "role": "system",
                    "content": bot_config.openai.summarize_prompt,
                },
                {"role": "user", "content": self.messages[0].message_text},
            ],
            max_tokens=25,
            temperature=0.5,
        )

        self.summary = summresp
        return summresp

    def get_messages(self) -> Iterable[dict[str, str]]:
        return list(
            filter(
                lambda f: f is not None,
                map(lambda m: m.to_conversation(self.bot_user), self.messages),
            )
        )

    def get_messages_under_token_limit(
        self, gpt_convo: GptConversation, token_limit=None
    ) -> Generator[dict[str, str], None, str]:
        use_token_limit = min(token_limit, gpt_convo.token_limit) if token_limit and token_limit > 0 else gpt_convo.token_limit
        token_count = 0

        for outbound_message in reversed(self.get_messages()):
            new_tokens = gpt_convo.calc_tokens_for_msg(outbound_message)
            if token_count + new_tokens < use_token_limit:
                # We have enough tokens so add this to the conversation history
                token_count += new_tokens
                yield outbound_message
            else:
                # We don't have enough tokens to replay the entire conversation
                return "token_overflow"

    async def continue_thread(self, token_limit=None) -> str:
        await self.summarize()  # Ensure we've summarized the thread so the continuation has a value

        gpt_convo = GptConversation()
        token_overflow = False

        messages: list[ChatThreadMessage] = []
        try:
            for outbound_message in self.get_messages_under_token_limit(
                gpt_convo, token_limit
            ):
                # Insert upside-down
                messages.insert(0, outbound_message)
        except StopIteration as e:
            if e.value == "token_overflow":
                # We had a token overflow
                token_overflow = True

        if token_overflow:
            # We went over the tokens, so use the continuation system message
            messages.insert(
                0, {"role": "system", "content": self.system_message_continuation}
            )
        else:
            # We're under the token limit so use the starting system message
            messages.insert(0, {"role": "system", "content": self.system_message})

        return await gpt_convo.get_response(messages)
