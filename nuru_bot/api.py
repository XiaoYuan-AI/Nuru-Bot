from __future__ import annotations

from base64 import b64encode

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

    def _request_result(self, method: str, path: str, **kwargs: object) -> str:
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

        if not isinstance(payload, dict) or "result" not in payload:
            raise NuruApiError(f"Request to {url} did not include a result field")

        return str(payload["result"])
