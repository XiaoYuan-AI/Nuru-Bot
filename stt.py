from platform import system
from queue import Queue

from faster_whisper import WhisperModel
from numpy import zeros, float32, concatenate, linalg
from sounddevice import query_devices, query_hostapis, InputStream, WasapiSettings


def get_loopback():
    devices = query_devices()
    platform = system()
    if platform == "Windows":
        for loopback, device in enumerate(devices):
            name = device["name"].lower()
            hostapi = query_hostapis()[device["hostapi"]]["name"].lower()
            if "loopback" in name or "wasapi" in hostapi:
                return loopback, device
    elif platform == "Darwin":  # macOS
        for loopback, device in enumerate(devices):
            name = device["name"].lower()
            if "blackhole" in name or "soundflower" in name:
                return loopback, device
    elif platform == "Linux":
        for loopback, device in enumerate(devices):
            name = device["name"].lower()
            if "monitor" in name:
                return loopback, device
    return None, None


def audio_callback(indata, frames, time, status):
    if status:
        print(status)
    audio.put(indata.copy())


if __name__ == "__main__":
    model = WhisperModel("base", device="cuda", compute_type="float16")
    audio = Queue()
    loopback, device = get_loopback()
    print(device)
    stream = InputStream(16000, 1600, loopback, device['max_output_channels'], dtype='float32',
                         extra_settings=WasapiSettings(), callback=audio_callback)
    buffer = zeros((0, loopback), dtype=float32)
    counter = 0
    sentence = ""
    with stream:
        try:
            while True:
                block = audio.get()
                buffer = concatenate((buffer, block), axis=0)
                energy = linalg.norm(block)
                if energy < 20:
                    counter += 1
                else:
                    counter = 0
                if len(buffer) / 16000 > 2:
                    data = buffer.flatten()
                    segments, _ = model.transcribe(data, beam_size=5)
                    text = ""
                    for segment in segments:
                        text += segment.text
                    # print(text, end=" ", flush=True)
                    sentence += " " + text.strip()
                    if (counter > 10) or text.endswith((".", "?", "!", "。")):
                        print(sentence.strip())
                        sentence = ""
                        buffer = zeros((0, loopback), dtype=float32)
                    else:
                        buffer = zeros((0, loopback), dtype=float32)

        except KeyboardInterrupt:
            pass
