from os import getenv

from dotenv import load_dotenv
from requests import post

load_dotenv()
API_KEY = getenv("MICROSOFT_API_KEY")


def get_tts(text: str) -> bytes:
    token_url = f"https://southeastasia.api.cognitive.microsoft.com/sts/v1.0/issueToken"
    headers = {"Ocp-Apim-Subscription-Key": API_KEY}
    token = post(token_url, headers=headers).text
    tts_url = f"https://southeastasia.tts.speech.microsoft.com/cognitiveservices/v1"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/ssml+xml",
        "X-Microsoft-OutputFormat": "audio-16khz-32kbitrate-mono-mp3",
        "User-Agent": "python"
    }
    ssml = f"<speak version='1.0' xml:lang='en-US'><voice name='en-US-AshleyNeural'><express-as style='chat'><prosody pitch='+25%'>{text}</prosody></express-as></voice></speak>"
    response = post(tts_url, headers=headers, data=ssml)
    return response.content
