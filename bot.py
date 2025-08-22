from collections import defaultdict
from os import getenv

from discord import Activity, ActivityType, Intents, Message, Client, DMChannel, User, Reaction
from discord.ext import tasks
from discord.ext.voice_recv import VoiceRecvClient
from discord.ext.voice_recv.extras.speechrecognition import SpeechRecognitionSink
from dotenv import load_dotenv
from speech_recognition import Recognizer, AudioData
from speech_recognition.recognizers.whisper_local import faster_whisper
from websockets import connect

from model import get_response

load_dotenv()
TOKEN = getenv("TOKEN")
client = Client(intents=Intents.all(), proxy="http://127.0.0.1:10808")
voice_channel = None
voice_client = None
prompts = {}


def process_audio(recognizer: Recognizer, audio: AudioData, user: User):
    text = faster_whisper.recognize(recognizer, audio, "tiny.en", language="en")
    if text:
        return text
    return


def got_text(user: User, text: str):
    global prompts
    if text:
        print(f"{user.display_name}: {text}")
        if prompts:
            print(prompts)
            if len(prompts[user.display_name].split(" ")) >= 25:
                merged = defaultdict(str)
                for item in prompts:
                    merged[item["user"]] += item["prompt"]
                for username, content in prompts.items():
                    prompt = f"{username}: {content}"
                    print(prompt)
                    response = get_response(prompt)
                    print(response)
                    client.loop.create_task(user.send(response))
                prompts = {}
            else:
                if user.display_name not in prompts:
                    prompts[user.display_name] = ""
                prompts[user.display_name] += text
        else:
            prompts[user.display_name] = ""


@tasks.loop(seconds=32)  # randint(32, 64)
async def auto_prompt():
    response = get_response(auto=True)
    # tts = get_tts(response, True)
    # audio = FFmpegPCMAudio(tts)
    # voice_client.play(audio)
    print(response)


@auto_prompt.before_loop
async def before_auto_prompt():
    await client.wait_until_ready()


@client.event
async def on_ready():
    global voice_channel
    global voice_client
    activity = Activity(name="Still WIP", type=ActivityType.playing)
    await client.change_presence(activity=activity)
    # auto_prompt.start()
    voice_channel = client.get_channel(1407667060527599736)
    invite = await voice_channel.create_invite(max_age=300, max_uses=1)
    user = await client.fetch_user(997401702321881088)
    await user.send(invite.url)
    voice_client = await voice_channel.connect(cls=VoiceRecvClient)
    speech_sink = SpeechRecognitionSink(process_cb=process_audio, text_cb=got_text, default_recognizer="whisper")
    voice_client.listen(speech_sink)


@client.event
async def on_message(message: Message):
    global voice_channel
    global voice_client
    if message.author == client.user:
        return
    if not isinstance(message.channel, DMChannel):
        return
    if not message.content:
        return
    text = f"{message.author}: {message.content}"
    print(text)
    response = get_response(text)
    # response = get_response_evil(text)
    print(response)
    await message.channel.send(response)


@client.event
async def on_reaction_add(reaction: Reaction, user: User):
    if user == client.user:
        return
    if not isinstance(reaction.message.channel, DMChannel):
        return
    if not reaction.emoji:
        return
    text = f"{user.name}'s reaction is: {reaction.emoji}"
    response = ""
    print(text)
    async with connect("ws://127.0.0.1:8000/generate") as websocket:
        await websocket.send("11.4 and 11.35, which is bigger?")
        async for message in websocket:
            print(message, end="", flush=True)
            response += message
    # response = get_response(text)
    # response = get_response_evil(text)
    print(response)
    await reaction.message.channel.send(response)


if __name__ == "__main__":
    client.run(TOKEN)
