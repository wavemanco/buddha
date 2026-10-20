"""Optional SDK transport views over a host-owned asynchronous exchange.

No credentials, networking, queue implementation or SDK dependency is installed
here. The host exchange owns durable authority decisions before returning/stopping.
"""

import importlib
import re
from dataclasses import dataclass, field
from typing import Any, Protocol

from buddha.native_context import Contexts, NativeStop
from buddha.releases import ReleaseError, _digest
from buddha.wire import MAX_BODY_BYTES, MAX_HEADER_VALUE_BYTES, MAX_HEADERS, RawEnvelope

ENDPOINTS = {
    "openai": "https://api.openai.com/v1/chat/completions",
    "anthropic": "https://api.anthropic.com/v1/messages",
}
STRIPPED = frozenset({"authorization", "x-api-key", "host", "content-length"})
FORBIDDEN = frozenset(
    {
        "cookie",
        "cookie2",
        "proxy-authorization",
        "proxy-authenticate",
        "transfer-encoding",
        "te",
        "trailer",
        "upgrade",
        "keep-alive",
        "connection",
    }
)


def _provider(value: object) -> str:
    if type(value) is not str or value not in ENDPOINTS:
        raise ReleaseError("unsupported native transport provider")
    return value


def _headers(value: object) -> tuple[tuple[str, str], ...]:
    if type(value) is not tuple or len(value) > MAX_HEADERS:
        raise ReleaseError("native request requires bounded immutable header pairs")
    result = []
    seen = set()
    for pair in value:
        if type(pair) is not tuple or len(pair) != 2:
            raise ReleaseError("invalid native request header pair")
        name, text = pair
        if (
            type(name) is not str
            or len(name) > 128
            or not re.fullmatch(r"[!#$%&'*+.^_`|~0-9A-Za-z-]+", name)
        ):
            raise ReleaseError("native request header name must be an ASCII token")
        name = name.lower()
        if name in seen or name in STRIPPED | FORBIDDEN:
            raise ReleaseError("native request contains a duplicate or forbidden header")
        if (
            type(text) is not str
            or len(text) > MAX_HEADER_VALUE_BYTES
            or any(not 32 <= ord(char) <= 126 for char in text)
        ):
            raise ReleaseError("native request header value must be bounded printable ASCII")
        seen.add(name)
        result.append((name, text))
    return tuple(result)


@dataclass(frozen=True)
class NativeRequest:
    provider: str
    method: str
    url: str
    body: bytes = field(repr=False)
    headers: tuple[tuple[str, str], ...] = field(repr=False)
    logical_id: str
    attempt: int

    def __post_init__(self) -> None:
        provider = _provider(self.provider)
        if (
            type(self.method) is not str
            or type(self.url) is not str
            or self.method != "POST"
            or self.url != ENDPOINTS[provider]
        ):
            raise ReleaseError("native request differs from its fixed POST endpoint")
        if type(self.body) is not bytes or len(self.body) > MAX_BODY_BYTES:
            raise ReleaseError("native request body must be bounded immutable bytes")
        _digest(self.logical_id)
        if type(self.attempt) is not int or not 0 <= self.attempt < 2**31 - 1:
            raise ReleaseError("native physical attempt index is invalid")
        object.__setattr__(self, "headers", _headers(self.headers))


class Exchange(Protocol):
    async def __call__(self, request: NativeRequest) -> RawEnvelope: ...


def make_transport(provider: str, *, contexts: Contexts, exchange: Exchange) -> Any:
    """Load only the selected optional SDK HTTP package and return its transport view.

    SDK auth/framing values never cross Exchange; all other headers are retained
    for host profile validation. An unavailable or invalid context cannot send.
    """
    provider = _provider(provider)
    if not isinstance(contexts, Contexts) or not callable(exchange):
        raise ReleaseError("native transport requires contexts and an async exchange")
    try:
        sdk = importlib.import_module("httpx" if provider == "openai" else "httpx2")
    except ImportError:
        raise ReleaseError("the selected SDK HTTP package is unavailable") from None

    async def handle_async_request(self: object, request: Any) -> Any:
        try:
            # Allocate before the first await; async arrival is never sample identity.
            logical_id, attempt = contexts.attempt()
            raw = request.headers.raw
            if type(raw) not in {list, tuple} or len(raw) > MAX_HEADERS:
                raise ReleaseError("invalid bounded SDK header sequence")
            headers = []
            seen = set()
            for pair in raw:
                if type(pair) not in {list, tuple} or len(pair) != 2:
                    raise ReleaseError("invalid SDK header pair")
                if (
                    type(pair[0]) is not bytes
                    or type(pair[1]) is not bytes
                    or not 1 <= len(pair[0]) <= 128
                    or len(pair[1]) > MAX_HEADER_VALUE_BYTES
                ):
                    raise ReleaseError("SDK headers require bounded immutable bytes")
                name = pair[0].decode("ascii").lower()
                value = pair[1].decode("ascii")
                if name in seen:
                    raise ReleaseError("duplicate SDK header")
                seen.add(name)
                if name == "connection" and value.lower() == "keep-alive":
                    continue
                if name in FORBIDDEN:
                    raise ReleaseError(
                        "SDK hop headers or cookie/proxy credentials are unsupported"
                    )
                if name == "host" and value.lower() != ENDPOINTS[provider].split("/")[2]:
                    raise ReleaseError("SDK Host differs from the funded endpoint")
                if name == "content-length" and (
                    not re.fullmatch("[0-9]+", value) or int(value) != len(request.content)
                ):
                    raise ReleaseError("SDK content length differs from its literal body")
                if name not in STRIPPED:
                    headers.append((name, value))
            native = NativeRequest(
                provider,
                request.method,
                str(request.url),
                request.content,
                tuple(headers),
                logical_id,
                attempt,
            )
        except Exception:
            raise NativeStop("protocol") from None
        try:
            envelope = await exchange(native)
        except NativeStop:
            raise
        except Exception:
            raise NativeStop("unknown") from None
        try:
            if (
                not isinstance(envelope, RawEnvelope)
                or envelope.provider != provider
                or envelope.truncated
                or envelope.withheld
                or not envelope.headers_complete
            ):
                raise ReleaseError("host returned unavailable native response evidence")
            from buddha.wire import decoded_body

            decoded_body(envelope)  # Validate bounded decoding; SDK still receives encoded bytes.
            return sdk.Response(
                envelope.status, content=envelope.body, headers=envelope.headers, request=request
            )
        except Exception:
            raise NativeStop("protocol") from None

    # Dynamic inheritance avoids importing either optional SDK package at app import.
    return type(
        "NativeAsyncTransport",
        (sdk.AsyncBaseTransport,),
        {
            "handle_async_request": handle_async_request,
        },
    )()
