import openai
import tiktoken

from .config import bot_config

openai.api_key = bot_config["openai"]["api_key"]


class OpenaiConversation(object):
    def __init__(self, system_message: str = None):
        self.message_history = []
        self.has_system_message = False
        self.model = "gpt-3.5-turbo-0613"
        self.token_limit = 4096

        if system_message:
            self.add("system", system_message)
            self.has_system_message = True

    def add_user_message(self, content: str):
        if content == "-":
            # Ignore certain things in the GPT message history
            pass

        self.add("user", content)

    def add_assistant_message(self, content: str):
        self.add("assistant", content)

    def add(self, type: str, content: str):
        message = {"role": type, "content": content}
        self.message_history.append(
            {"message": message, "tokens": num_tokens_from_messages([message])}
        )

    async def get_response(self, max_tokens: int = 500, temperature: float = 1):
        message_list = list(map(lambda x: x["message"], self.message_history))

        print("Requesting response from ChatGPT with messages", repr(message_list))

        token_count = num_tokens_from_messages(message_list)
        while token_count > self.token_limit:
            message_list = message_list[1:]
            token_count = num_tokens_from_messages(message_list)

        completion = await openai.ChatCompletion.acreate(
            model=self.model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=message_list,
        )
        content = completion.choices[0].message.content
        self.add("assistant", content)
        return content

    def calc_tokens_for_msg(self, content: str):
        return num_tokens_from_messages([content], self.model)

    def get_token_count(self):
        return sum(int(v["tokens"]) for v in self.message_history)

    def __repr__(self) -> str:
        return repr(self.message_history)


async def summarize(message: str):
    summconvo = OpenaiConversation(
        "Respond with a summary of the prompt in 8 words or less"
    )
    summconvo.add_user_message(message)
    return await summconvo.get_response(max_tokens=25, temperature=0.5)


def num_tokens_from_messages(messages, model="gpt-3.5-turbo-0613"):
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
