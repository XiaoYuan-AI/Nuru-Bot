import pytest

from nuru_bot.api import NuruApi, NuruApiError


class FakeResponse:
    def __init__(self, payload=None, chunks=None, status_error=None):
        self.payload = payload
        self.chunks = chunks or []
        self.status_error = status_error

    def raise_for_status(self):
        if self.status_error is not None:
            raise self.status_error

    def json(self):
        return self.payload

    def iter_content(self, chunk_size):
        yield from self.chunks

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False


class FakeSession:
    def __init__(self):
        self.next_response = None
        self.requests = []

    def request(self, method, url, **kwargs):
        self.requests.append((method, url, kwargs))
        return self.next_response

    def post(self, url, **kwargs):
        self.requests.append(("POST", url, kwargs))
        return self.next_response


def test_generate_reads_result_field():
    session = FakeSession()
    session.next_response = FakeResponse({"result": "hello"})
    api = NuruApi("http://nuru.local", 3)
    api.session = session

    assert api.generate("hi") == "hello"
    assert session.requests[0][1] == "http://nuru.local/model"


@pytest.mark.parametrize("result", [None, "", "   "])
def test_generate_rejects_empty_result_field(result):
    session = FakeSession()
    session.next_response = FakeResponse({"result": result})
    api = NuruApi("http://nuru.local", 3)
    api.session = session

    with pytest.raises(NuruApiError, match="empty result"):
        api.generate("hi")


def test_describe_image_encodes_image_bytes():
    session = FakeSession()
    session.next_response = FakeResponse({"result": "small image"})
    api = NuruApi("http://nuru.local/", 3)
    api.session = session

    assert api.describe_image(b"image-bytes") == "small image"
    method, url, kwargs = session.requests[0]
    assert method == "POST"
    assert url == "http://nuru.local/vision"
    assert kwargs["json"] == {"input": "aW1hZ2UtYnl0ZXM="}


def test_embed_accepts_openai_style_payload():
    session = FakeSession()
    session.next_response = FakeResponse({"data": [{"embedding": [1, "2.5"]}]})
    api = NuruApi("http://nuru.local", 3)
    api.session = session

    assert api.embed("memory") == [1.0, 2.5]


def test_embed_rejects_missing_embedding():
    session = FakeSession()
    session.next_response = FakeResponse({"result": "not an embedding"})
    api = NuruApi("http://nuru.local", 3)
    api.session = session

    with pytest.raises(NuruApiError):
        api.embed("memory")


def test_embed_rejects_non_numeric_embedding_values():
    session = FakeSession()
    session.next_response = FakeResponse({"embedding": [1, None]})
    api = NuruApi("http://nuru.local", 3)
    api.session = session

    with pytest.raises(NuruApiError, match="non-numeric"):
        api.embed("memory")


def test_embed_rejects_non_finite_embedding_values():
    session = FakeSession()
    session.next_response = FakeResponse({"embedding": [1, float("nan")]})
    api = NuruApi("http://nuru.local", 3)
    api.session = session

    with pytest.raises(NuruApiError, match="non-finite"):
        api.embed("memory")


def test_transcribe_audio_encodes_audio_bytes():
    session = FakeSession()
    session.next_response = FakeResponse({"result": "hey nuru"})
    api = NuruApi("http://nuru.local", 3)
    api.session = session

    assert api.transcribe_audio(b"audio-bytes") == "hey nuru"
    method, url, kwargs = session.requests[0]
    assert method == "POST"
    assert url == "http://nuru.local/audio/transcribe"
    assert kwargs["json"] == {"input": "YXVkaW8tYnl0ZXM="}


def test_stream_tts_yields_non_empty_chunks():
    session = FakeSession()
    session.next_response = FakeResponse(chunks=[b"one", b"", b"two"])
    api = NuruApi("http://nuru.local", 3)
    api.session = session

    assert list(api.stream_tts("say this")) == [b"one", b"two"]
    assert session.requests[0][1] == "http://nuru.local/tts/stream"


def test_stream_tts_sends_voice_when_configured():
    session = FakeSession()
    session.next_response = FakeResponse(chunks=[b"voice"])
    api = NuruApi("http://nuru.local", 3)
    api.session = session

    assert list(api.stream_tts("say this", voice="vtuber")) == [b"voice"]
    assert session.requests[0][2]["json"] == {
        "input": "say this",
        "voice": "vtuber",
    }


def test_close_closes_session():
    class CloseTrackingSession(FakeSession):
        def __init__(self):
            super().__init__()
            self.closed = False

        def close(self):
            self.closed = True

    session = CloseTrackingSession()
    api = NuruApi("http://nuru.local", 3)
    api.session = session

    api.close()

    assert session.closed
