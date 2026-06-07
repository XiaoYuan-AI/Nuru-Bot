from __future__ import annotations

from base64 import b64encode
from collections.abc import Iterator

from requests import RequestException, Session


class NuruApiError(RuntimeError):
    """Raised when the local Nuru API cannot return a usable result."""


class NuruApi:
    def __init__(self, base_url: str, timeout_seconds: float) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.session = Session()

    def generate(self, prompt: str) -> str:
        return self._request_result("POST", "/model", json={"input": prompt})

    def describe_image(self, image_data: bytes) -> str:
        encoded_image = b64encode(image_data).decode("utf-8")
        return self._request_result("POST", "/vision", json={"input": encoded_image})

    def embed(self, text: str) -> list[float]:
        payload = self._request_json("POST", "/embeddings", json={"input": text})
        embedding = _extract_embedding(payload)
        if embedding is None:
            raise NuruApiError("Embedding response did not include an embedding")
        return embedding

    def transcribe_audio(self, audio_data: bytes) -> str:
        encoded_audio = b64encode(audio_data).decode("utf-8")
        return self._request_result(
            "POST",
            "/audio/transcribe",
            json={"input": encoded_audio},
        )

    def stream_tts(self, text: str, *, voice: str | None = None) -> Iterator[bytes]:
        payload = {"input": text}
        if voice:
            payload["voice"] = voice

        url = f"{self.base_url}/tts/stream"
        try:
            with self.session.post(
                url,
                json=payload,
                timeout=self.timeout_seconds,
                stream=True,
            ) as response:
                response.raise_for_status()
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        yield chunk
        except RequestException as exc:
            raise NuruApiError(f"Request to {url} failed") from exc

    def _request_result(self, method: str, path: str, **kwargs: object) -> str:
        payload = self._request_json(method, path, **kwargs)

        if not isinstance(payload, dict) or "result" not in payload:
            url = f"{self.base_url}/{path.lstrip('/')}"
            raise NuruApiError(f"Request to {url} did not include a result field")

        return str(payload["result"])

    def _request_json(self, method: str, path: str, **kwargs: object) -> object:
        url = f"{self.base_url}/{path.lstrip('/')}"

        try:
            response = self.session.request(
                method,
                url,
                timeout=self.timeout_seconds,
                **kwargs,
            )
            response.raise_for_status()
            payload = response.json()
        except RequestException as exc:
            raise NuruApiError(f"Request to {url} failed") from exc
        except ValueError as exc:
            raise NuruApiError(f"Request to {url} returned invalid JSON") from exc

        return payload


def _extract_embedding(payload: object) -> list[float] | None:
    if isinstance(payload, dict):
        if isinstance(payload.get("embedding"), list):
            return [float(value) for value in payload["embedding"]]
        if isinstance(payload.get("result"), list):
            return [float(value) for value in payload["result"]]

        data = payload.get("data")
        if isinstance(data, list) and data:
            first = data[0]
            if isinstance(first, dict) and isinstance(first.get("embedding"), list):
                return [float(value) for value in first["embedding"]]

    if isinstance(payload, list):
        return [float(value) for value in payload]

    return None
