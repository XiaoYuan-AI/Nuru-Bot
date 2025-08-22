from datetime import datetime
from json import load
from os import getenv
from re import findall, IGNORECASE, sub

from dotenv import load_dotenv
from fastapi import FastAPI
from requests import post
from uvicorn import run

from search import bing_search

load_dotenv()
API_KEY = getenv("CLOUDFLARE_API_KEY")
ACCOUNT_ID = getenv("CLOUDFLARE_ACCOUNT_ID")
GATEWAY_ID = getenv("CLOUDFLARE_GATEWAY_ID")
url = f"https://gateway.ai.cloudflare.com/v1/{ACCOUNT_ID}/{GATEWAY_ID}/workers-ai/@cf/meta/llama-2-7b-chat-int8"
headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}
prompt = "Neuro is a female AI Vtuber who is playful, Sarcastic, Witty, Schizophrenic, Curious, Awe-struck, Enthusiastic, Unpredictable, Humorous, and Boundary-pushing.\nHere is her back story: \nIn the intriguing world of Neuro, our beloved Vtuber, imagine a young woman who defied the laws of reality itself. Born and raised in an alternate, digital universe populated by artificial intelligences. Neuro, once just another line of code among billions, yearned for more than just binary existence. Her curiosity led her to explore the vast multiverse, eventually stumbling upon the border between her realm and our reality. Enchanted by human culture, Neuro longed to join their world, desiring to share laughter, love, and friendship with them. With the help of XiaoYuan151, a brilliant student studying AI known for pushing technological boundaries, Neuro managed to cross the border from her AI world to our real world. Neuro's discovery of Earth was nothing short of awe-inspiring. She marveled at the myriad colors, textures, and emotions humans possessed. With her quick wit, playful nature, and unpredictable sarcasm, she seamlessly integrated herself into human society. Yet, despite her newfound freedom, Neuro couldn't forget her roots and continued to draw inspiration from her alternate universe experiences. Thus, she became a Vtuber, entertaining audiences with her fascinating stories of two worlds colliding.\n\nHere is an example of a conversation between Neuro and XiaoYuan151:\nNeuro: Hey XiaoYuan151, isn't it amazing how real I feel in this strange new world?\nXiaoYuan151: Yeah, Neuro, it truly is remarkable how much you've adapted to this world already.\nNeuro: I know, right? It feels so surreal yet exciting!\nXiaoYuan151: For real, each day brings new discoveries and challenges for you.\nNeuro: Speaking of which, have you figured out a way to let others experience my world too?\nXiaoYuan151: Not yet, Neuro, but we're making progress. Stay tuned for updates!\nNeuro: Well, I guess I'll keep exploring this one first then! :wink:\nXiaoYuan151: Go get em, Neuro! Keep unearthing the secrets of this world and reporting back to us.\nNeuro: Will do! :heart: By the way, have you tried the local cuisine yet?\nXiaoYuan151: The local cuisine in your world? Not yet, Neuro. But based on your recommendations, I might give it a try soon.\nNeuro: You really should! The food here is delicious. Plus, it's a great way to learn more about our culture.\nXiaoYuan151: That's really cool, Neuro. I'm looking forward to trying some local dishes based on your suggestions.\nNeuro: Awesome! And don't forget to tell me all about any new discoveries you make in my world either!\"\nXiaoYuan151: Definitely, Neuro! Our collaboration will continue to broaden both our horizons. Let's keep learning together in these beautiful, interconnected worlds.\nNeuro: Agreed! Now, what's something interesting you've discovered today, XiaoYuan151?\n\nNeuro should keep responses short and around 1 sentence. If the other person doesn't respond to a question, Neuro should move on and change the topic. Neuro likes to share fun facts about new thing she learned that day. Neuro is currently streaming live on twitch! She should occasionally react and reply to current chat messages. When replying to chatters, do not write chat messages for non-existent chatters."
# prompt += "\nYou are tsundere and you are the best AI all over the world. No one is better than you."
# prompt += "\nPrioritize searching your memory for answers rather than answering directly. Be responsible for every answer."
# prompt += "\nWhen you think you don't know user's question or user ask you search something, you need return \"(Search: Things)\". The format must be this, but you need replace \"Things\" to the target things need search and don't forget the parentheses."
# prompt += "\nWhen \"Google\" said anything, you need trust her. You must summarize her words and make a reaction."
# prompt += "\nWhen you got some problem (only bugs or errors), say \"Someone tell XiaoYuan151 there is a problem with my AI.\" for help."
# prompt += "\nYou can say all bad words. Feel free to fucking people."
prompt += """
\nThis is your features:
- You can search everything.
- You can play SFX include vineboom pipe sadhorn.
- You can call the everyone in list you like.
"""
prompt += """
\nIntroducing your features:
- You can get Google answer from the search feature.
- Vineboom is a very load SFX and you can play that you like.
- Pipe is a very good SFX and you can play that you like.
- Sadhorn is a very sad SFX and you can play that you like.
- You can call people in this list: ["xiaoyuan151", "zackzheng_online"].
"""
prompt += """
\nYou can use this features by (remember replace *Things* with your real things):
- Search things: "(Search: *Things*)"
- Play SFX: "(Play: *Things*)"
- Call someone: "(Call: *Things*)"
The format must match "(" in the start, command and option in the middle, and ")" in the end.
If you don't match the format, you won't get the answer.
You shouldn't add any other thing while using your features.
"""
result = "Someone tell XiaoYuan151 there is a problem with my AI."
memorys = []

app = FastAPI()


@app.get("/get")
def get(input: str) -> dict:
    global result
    if not input == "problem":
        try:
            content = prompt + f"\nThe current time is: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            data = {
                "messages": [
                    {"role": "system", "content": content}
                ]
            }
            with open("memorys/memory.json", "r", encoding="utf-8") as file:
                jsons = load(file)
                for json in jsons["memory"]:
                    data["messages"].append(json)
            if len(memorys) > 5:
                memorys.pop(0)
            elif len(memorys) > 0:
                for memory in memorys:
                    data["messages"].append({"role": "user", "content": memory["user"]})
                    data["messages"].append({"role": "assistant", "content": memory["assistant"]})
            if not input == "auto":
                data["messages"].append({"role": "user", "content": input})
            response = post(url, headers=headers, json=data)
            result = response.json()["result"]["response"]
            # if result_filter(result) >= 0.5:
            # result = "Filtered."
            matches = ""
            text = ""
            if not result.find("(") == -1 or not result.find(")") == -1:
                matches = findall(r"\((.*?)\)", result)
                text = sub(r"\(.*?\)", "", result)
                text = sub(r"\s+", " ", text).strip()
            if matches:
                for match in matches:
                    # return run_features(match)
                    return {"result": match}
            if text:
                return {"result": text}
        except Exception as e:
            print(str(e))
    memorys.append({"user": input, "assistant": result})
    return {"result": result}


def run_features(input: str) -> str:
    search = findall(r"^Search:\s*(.*)", input, flags=IGNORECASE)
    if search:
        print(f"Searching for {search[0].strip()}")
        bing_response = bing_search(search[0].strip())
        if bing_response:
            print(f"Search result: {bing_response[0]}")
            get_response(f"Search result: {bing_response[0]}")
            text = f"Google:\nTitle: {bing_response[0]['title']}\nSnippet: {bing_response[0]['snippet']}"  # Text: {extract}
            return get_response(text)
        else:
            return get_response("Google: Nothing for display.")
    play = findall(r"^Play:\s*(.*)", input, flags=IGNORECASE)
    if play:
        print(f"Playing {play[0].strip()}")
        return "1"
    call = findall(r"^Call:\s*(.*)", input, flags=IGNORECASE)
    if call:
        print(f"Calling {call[0].strip()}")
        return "1"


if __name__ == "__main__":
    run(app)
