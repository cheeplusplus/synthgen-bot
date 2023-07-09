import discord
from .openai_conversation import OpenaiConversation, summarize


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
            type=discord.ActivityType.listening,
            name="a stream of tokens"
        )
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
    if isinstance(message.channel, discord.TextChannel) and client.user.mentioned_in(message):
        # User mentioned us, create a thread with our reply
        new_thread = True
        response_thread = await message.create_thread(name="Synthbot reply", auto_archive_duration=1440, reason="ChatGPT conversation")
    elif isinstance(message.channel, discord.Thread) and message.channel.owner == client.user:
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

        if response_thread.id in THREAD_CONVO_CACHE:
            convo = THREAD_CONVO_CACHE[response_thread.id]
            convo.add_user_message(content)
        else:
            convo = OpenaiConversation("Keep answers under 2000 characters. Markdown is allowed.")
            if new_thread:
                convo.add_user_message(content)
            else:
                await load_thread_conversation(convo, response_thread)
            THREAD_CONVO_CACHE[response_thread.id] = convo

        if new_thread:
            # Summarize the first post to use as a thread title
            summary = await summarize(content)
            await response_thread.edit(name=summary)

        # Fetch the OpenAI response
        resp = await convo.get_response()

        # Trim response to fit in Discord's 2000 character limit. The convo still contains the whole message.
        # short_resp = textwrap.shorten(resp, width=2000, placeholder="...") # this removes whitespace
        short_resp = (resp[:1996] + "...") if len(resp) > 1999 else resp

        await response_thread.send(short_resp, allowed_mentions=discord.AllowedMentions.none())
    

async def load_thread_conversation(convo: OpenaiConversation, thread: discord.Thread):
    # This really needs to be some dynamic thing where we walk backwards to the max token limit
    async for message in thread.history(limit=100, oldest_first=True):
        if message.author == client.user:
            convo.add_assistant_message(message.clean_content)
        else:
            convo.add_user_message(message.clean_content)
