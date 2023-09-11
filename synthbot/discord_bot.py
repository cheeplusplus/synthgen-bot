import discord
from .openai_conversation import InvalidRequestError, OpenaiConversation, summarize


intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)


# Cache thread IDs to an OpenAI conversation
THREAD_CONVO_CACHE: dict[int, OpenaiConversation] = {}


@client.event
async def on_ready():
    print("Logged in as", client.user)
    await client.change_presence(
        status=discord.Status.online,
        activity=discord.Activity(
            type=discord.ActivityType.listening, name="a stream of tokens"
        ),
    )


@client.event
async def on_message(message: discord.Message):
    if message.author == client.user or message.author.bot:
        # It's either from ourselves or another bot, ignore it
        return

    if not message.content:
        # Don't have permission to see it, or some other issue
        return

    new_thread = False
    response_thread = None
    if isinstance(message.channel, discord.TextChannel) and client.user.mentioned_in(
        message
    ):
        # User mentioned us, create a thread with our reply
        new_thread = True
        response_thread = await message.create_thread(
            name="Synthbot reply",
            auto_archive_duration=1440,
            reason="ChatGPT conversation",
        )
    elif (
        isinstance(message.channel, discord.Thread)
        and message.channel.owner == client.user
    ):
        # User replied to a thread we created
        response_thread = message.channel
    else:
        # Channel type not supported
        return

    async with response_thread.typing():
        # Build the OpenAI conversation
        convo = None

        # Clean up the incoming content
        content = message.content.replace(client.user.mention, "").strip()

        # Keep track of the thread name
        thread_name = response_thread.name

        if new_thread:
            # Summarize the first post to use as a thread title
            summary = await summarize(content)
            await response_thread.edit(name=summary)
            thread_name = summary

        if response_thread.id in THREAD_CONVO_CACHE:
            convo = THREAD_CONVO_CACHE[response_thread.id]
            convo.update_thread_name(thread_name)
            convo.add_user_message(content)
        else:
            convo = OpenaiConversation(
                thread_name,
                "You are talking to a friendly user. Keep your replies under 1800 characters. Markdown is allowed.",
                'You are continuing a conversation in a thread called "THREAD_NAME". Keep your replies under 1800 characters. Markdown is allowed.',
            )
            if new_thread:
                convo.add_user_message(content)
            else:
                await load_thread_conversation(convo, response_thread)
            THREAD_CONVO_CACHE[response_thread.id] = convo

        # Fetch the OpenAI response
        try:
            resp = await convo.get_response()
        except InvalidRequestError as e:
            print("Got an error while trying to get a conversation response:", repr(e))

            try:
                await response_thread.send(
                    f"---\nError while getting a conversation response:\n```{repr(e)}```"
                )
            except Exception as ie:
                print(
                    "Got an error trying to talk to Discord when complaining about a conversation response!",
                    repr(ie),
                )

            return

        # Trim response to fit in Discord's 2000 character limit. The convo still contains the whole message.
        # short_resp = textwrap.shorten(resp, width=2000, placeholder="...") # this removes whitespace
        short_resp = (resp[:1996] + "...") if len(resp) > 1999 else resp

        await response_thread.send(
            short_resp, allowed_mentions=discord.AllowedMentions.none()
        )


async def load_thread_conversation(convo: OpenaiConversation, thread: discord.Thread):
    """Load a thread conversation into a conversation's message history."""
    # This really needs to be some dynamic thing where we walk backwards to the max token limit
    async for message in thread.history(limit=100, oldest_first=True):
        if not message.content:
            # Ignore empty messages
            pass
        elif message.author == client.user:
            convo.add_assistant_message(message.clean_content)
        elif message.author.bot:
            # Ignore other bot's messages
            pass
        else:
            convo.add_user_message(message.clean_content)
