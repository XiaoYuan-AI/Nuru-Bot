import asyncio

from websockets import connect, ConnectionClosed


async def listen():
    async with connect("ws://127.0.0.1:8000/generate") as websocket:
        while True:
            await websocket.send(input("Message: "))
            try:
                message = await websocket.recv()
                print(message, end="", flush=True)
            except ConnectionClosed:
                break


asyncio.run(listen())
