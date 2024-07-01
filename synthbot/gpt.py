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


class GptConversation:
    model: str

    def __init__(self, model: str = None):
        self.model = model or bot_config.openai.model

    async def get_response(
        self,
        message_list: list[dict[str, str]],
        max_tokens: int = None,
        temperature: float = 1,
    ) -> str:
        """Get a GPT completion for the current message history."""
        logger.debug("Requesting response from ChatGPT with messages: %s", message_list)

        completion = await openai_client.chat.completions.create(
            model=self.model,
            max_tokens=max_tokens or bot_config.openai.reply_token_limit,
            temperature=temperature,
            messages=message_list,
        )

        logger.debug("Got response from ChatGPT: %s", completion)
        content = completion.choices[0].message.content
        return content

    def calc_tokens_for_msg(self, content: dict[str, str]):
        """Calculate the number of tokens for a message."""
        return num_tokens_from_message(content, self.model)

    @property
    def token_limit(self):
        return bot_config.openai.thread_token_limit or AVAILABLE_MODELS[self.model]


def num_tokens_from_message(message: dict[str, str], model):
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
    num_tokens = tokens_per_message
    for key, value in message.items():
        num_tokens += len(encoding.encode(value))
        if key == "name":
            num_tokens += tokens_per_name
    return num_tokens


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
