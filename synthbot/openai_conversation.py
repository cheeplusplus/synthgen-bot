from openai import AsyncOpenAI
import tiktoken
import logging

from .config import bot_config

# GPT models we want to support, values are their input token limits.
AVAILABLE_MODELS: dict[str, int] = {
    "gpt-3.5-turbo": 16385,  # currently 0125
    "gpt-3.5-turbo-0125": 16385,
    "gpt-3.5-turbo-1106": 16385,
    "gpt-4-turbo": 128000,  # currently 2024-04-09
    "gpt-4-turbo-2024-04-09": 128000,
    "gpt-4-0125-preview": 128000,
    "gpt-4-1106-preview": 128000,
}


logger = logging.getLogger(__name__)
openai_client = AsyncOpenAI(api_key=bot_config.openai.api_key)


class OpenaiConversation(object):
    """Manage a single OpenAI conversation."""

    def __init__(
        self,
        system_message: str = None,
        system_continuation_message: str = None,
    ):
        self.thread_name = None
        self.message_history: list[dict[str, str]] = []
        self.model = bot_config.openai.model
        self.token_limit = AVAILABLE_MODELS[self.model]

        if system_message:
            self.system_message = system_message
            self.add("system", system_message)
        if system_continuation_message:
            self.system_continuation_message = system_continuation_message

    def add_user_message(self, content: str):
        """Add a user message to the message history."""
        if content == "-" or content.startswith("---\n"):
            # Ignore certain things in the thread's message history
            return

        self.add("user", content)

    def add_assistant_message(self, content: str):
        """Add an assistant message to the message history."""
        if content.startswith("---\n"):
            # Ignore certain things in the thread's message history
            return

        self.add("assistant", content)

    def add(self, type: str, content: str):
        """Add a message to the message history."""
        self.message_history.append({"role": type, "content": content})

    async def get_response(self, max_tokens: int = 500, temperature: float = 1) -> str:
        """Get a GPT completion for the current message history."""
        # Pull the message object out of the message history (to drop token data)
        message_list = self.message_history.copy()

        token_limit = self.token_limit - max_tokens
        orig_token_count = token_count = self.calc_tokens_for_msg(message_list)

        while token_count > token_limit:
            # Get the system message prefix
            if self.system_continuation_message:
                sys_msg = self.system_continuation_message
                if self.thread_name and "THREAD_NAME" in sys_msg:
                    sys_msg = sys_msg.replace("THREAD_NAME", self.thread_name)
            elif self.system_message:
                sys_msg = self.system_message

            # Trim down the response (keep as much context as possible)
            trim_len = 2 if sys_msg else 1
            message_list = message_list[trim_len:]

            # Reappend the system message
            if sys_msg:
                message_list.insert(0, {"role": "system", "content": sys_msg})

            # Recalculate the new token limit
            token_count = self.calc_tokens_for_msg(message_list)

        logger.debug("Requesting response from ChatGPT with messages: %s", message_list)
        logger.debug(
            "The token count is %d down to %d (TL: %d Max: %d)",
            orig_token_count,
            token_count,
            token_limit,
            self.token_limit,
        )

        completion = await openai_client.chat.completions.create(
            model=self.model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=message_list,
        )

        logger.debug("Got response from ChatGPT: %s", completion)
        content = completion.choices[0].message.content
        self.add("assistant", content)

        return content

    def calc_tokens_for_msg(self, content: list[dict[str, str]]):
        """Calculate the number of tokens for a message."""
        return num_tokens_from_messages(content, self.model)

    def update_thread_name(self, thread_name: str):
        self.thread_name = thread_name

    def __repr__(self) -> str:
        return repr(self.message_history)


async def summarize(message: str):
    """Summarize a message into something shorter."""
    summconvo = OpenaiConversation(
        "Respond with a summary of the prompt in 8 words or less"
    )
    summconvo.add_user_message(message)
    return await summconvo.get_response(max_tokens=25, temperature=0.5)


def num_tokens_from_messages(messages: list[dict[str, str]], model):
    """Return the number of tokens used by a list of messages."""
    try:
        encoding = tiktoken.encoding_for_model(model)
    except KeyError:
        logger.error("Warning: model not found. Using cl100k_base encoding.")
        encoding = tiktoken.get_encoding("cl100k_base")
    if model in AVAILABLE_MODELS:
        tokens_per_message = 3
        tokens_per_name = 1
    else:
        raise NotImplementedError(
            f"""num_tokens_from_messages() is not implemented for model {model}. See https://github.com/openai/openai-python/blob/main/chatml.md for information on how messages are converted to tokens."""
        )
    num_tokens = 0
    for message in messages:
        num_tokens += tokens_per_message
        for key, value in message.items():
            num_tokens += len(encoding.encode(value))
            if key == "name":
                num_tokens += tokens_per_name
    num_tokens += 3  # every reply is primed with <|start|>assistant<|message|>
    return num_tokens
