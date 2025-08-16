from collections import defaultdict
from os import getenv
from random import randint

from discord import Activity, ActivityType, Intents, Message, Client, DMChannel, User
from discord.ext import tasks
from dotenv import load_dotenv
from speech_recognition import Recognizer, AudioData
from speech_recognition.recognizers.whisper_local import faster_whisper

from model import get_response

load_dotenv()
TOKEN = getenv("TOKEN")
client = Client(intents=Intents.all(), proxy="http://127.0.0.1:10808")
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


@tasks.loop(seconds=randint(60, 180))
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
    global voice_client
    activity = Activity(name="WIP", type=ActivityType.playing)
    await client.change_presence(activity=activity)
    voice_channel = client.get_channel(1398314576059043994)
    # voice_client = await voice_channel.connect(cls=voice_recv.VoiceRecvClient)
    # speech_sink = SpeechRecognitionSink(process_cb=process_audio, text_cb=got_text, default_recognizer="whisper")
    # voice_client.listen(speech_sink)


@client.event
async def on_message(message: Message):
    if message.author == client.user:
        return
    if not isinstance(message.channel, DMChannel):
        return
    # if not detect(message.content)["lang"] == "en":
    # await message.channel.send("Someone tell XiaoYuan151 that there is a problem with my AI.")
    # return
    text = f"{message.author}: {message.content}"
    print(text)
    response = get_response(text)
    # response = get_response_evil(text)
    print(response)
    await message.channel.send(response)


client.run(TOKEN)
