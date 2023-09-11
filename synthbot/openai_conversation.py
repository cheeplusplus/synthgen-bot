import openai
from openai.error import InvalidRequestError
import tiktoken

from .config import bot_config

openai.api_key = bot_config["openai"]["api_key"]


class OpenaiConversation(object):
    """Manage a single OpenAI conversation."""

    def __init__(
        self,
        thread_name: str,
        system_message: str = None,
        system_continuation_message: str = None,
    ):
        self.message_history = []
        self.model = "gpt-3.5-turbo-0613"
        self.token_limit = 4096

        self.thread_name = thread_name

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

    async def get_response(self, max_tokens: int = 500, temperature: float = 1):
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

        print("Requesting response from ChatGPT with messages", repr(message_list))
        print(
            f"The token count is {orig_token_count} down to {token_count} (TL: {token_limit} Max: {self.token_limit})"
        )

        completion = await openai.ChatCompletion.acreate(
            model=self.model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=message_list,
        )

        print("Got response from ChatGPT", repr(completion))
        content = completion.choices[0].message.content
        self.add("assistant", content)

        return content

    def calc_tokens_for_msg(self, content: list[dict]):
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


def num_tokens_from_messages(messages: list[dict], model="gpt-3.5-turbo-0613"):
    """Return the number of tokens used by a list of messages."""
    try:
        encoding = tiktoken.encoding_for_model(model)
    except KeyError:
        print("Warning: model not found. Using cl100k_base encoding.")
        encoding = tiktoken.get_encoding("cl100k_base")
    if model in {
        "gpt-3.5-turbo-0613",
        "gpt-3.5-turbo-16k-0613",
        "gpt-4-0314",
        "gpt-4-32k-0314",
        "gpt-4-0613",
        "gpt-4-32k-0613",
    }:
        tokens_per_message = 3
        tokens_per_name = 1
    elif model == "gpt-3.5-turbo-0301":
        tokens_per_message = (
            4  # every message follows <|start|>{role/name}\n{content}<|end|>\n
        )
        tokens_per_name = -1  # if there's a name, the role is omitted
    elif "gpt-3.5-turbo" in model:
        print(
            "Warning: gpt-3.5-turbo may update over time. Returning num tokens assuming gpt-3.5-turbo-0613."
        )
        return num_tokens_from_messages(messages, model="gpt-3.5-turbo-0613")
    elif "gpt-4" in model:
        print(
            "Warning: gpt-4 may update over time. Returning num tokens assuming gpt-4-0613."
        )
        return num_tokens_from_messages(messages, model="gpt-4-0613")
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
