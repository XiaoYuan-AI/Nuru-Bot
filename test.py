from fastapi import FastAPI, WebSocket
from torch import cat
from transformers import AutoTokenizer, AutoModelForCausalLM
from uvicorn import run

from search import bing_search

tokenizer = AutoTokenizer.from_pretrained("./model/checkpoint-11000")
special_tokens = {
    "bos_token": "<BOS>",
    "eos_token": "<EOS>",
    "pad_token": "<PAD>",
    "additional_special_tokens": ["<SEARCH>", "<ANSWER>"]
}
tokenizer.add_special_tokens(special_tokens)
model = AutoModelForCausalLM.from_pretrained("./model/checkpoint-11000")
model.resize_token_embeddings(len(tokenizer))

app = FastAPI()


@app.websocket("/generate")
async def websocket_generate(websocket: WebSocket):
    await websocket.accept()
    data = await websocket.receive_text()
    prompt = data.strip()
    input = tokenizer.encode("<BOS> " + prompt, return_tensors="pt")
    generated = input
    stop = tokenizer.encode("<EOS>")[0]
    for _ in range(100):
        outputs = model(generated)
        next = outputs.logits[:, -1, :].argmax(-1)
        token = tokenizer.decode(next)
        print(token, end="", flush=True)
        if token == "<SEARCH>":
            query = tokenizer.decode(generated[0])
            result = bing_search(query)
            search = tokenizer.encode(result, return_tensors="pt")
            generated = cat([generated, search], dim=1)
            continue
        if token == "<ANSWER>":
            generated = cat([generated, next.unsqueeze(0)], dim=1)
            continue
        if next.item() == stop:
            break
        generated = cat([generated, next.unsqueeze(0)], dim=1)
        await websocket.send_text(token)


if __name__ == "__main__":
    run(app)
