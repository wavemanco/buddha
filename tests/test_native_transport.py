"""Stdlib boundary checks; real pinned SDK composition is a separate oracle."""

import asyncio
import unittest
from dataclasses import FrozenInstanceError
from types import SimpleNamespace
from unittest.mock import patch

from buddha.native_context import Contexts, NativeStop
from buddha.native_transport import NativeRequest, make_transport
from buddha.releases import ReleaseError
from buddha.wire import MAX_HEADER_VALUE_BYTES, RawEnvelope


class SDKBase:
    async def aclose(self):
        pass


class SDKResponse:
    def __init__(self, status_code, *, content, headers, request):
        self.status_code, self.content = status_code, content
        self.headers, self.request = headers, request


SDK = SimpleNamespace(AsyncBaseTransport=SDKBase, Response=SDKResponse)
URL = "https://api.openai.com/v1/chat/completions"


class NativeTransportTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.contexts = Contexts()
        self.observed = []

    async def exchange(self, request):
        self.observed.append(request)
        return RawEnvelope(request.provider, 200, b"raw response", (("x-request-id", "rid"),))

    def transport(self, provider="openai", exchange=None):
        with patch("buddha.native_transport.importlib.import_module", return_value=SDK) as loader:
            transport = make_transport(
                provider, contexts=self.contexts, exchange=exchange or self.exchange
            )
        loader.assert_called_once_with("httpx" if provider == "openai" else "httpx2")
        self.assertIsInstance(transport, SDKBase)
        return transport

    def request(self, **changes):
        values = {
            "method": "POST",
            "url": URL,
            "content": b'{"literal":"body"}',
            "headers": SimpleNamespace(
                raw=[
                    (b"Authorization", b"Bearer synthetic-worker-token"),
                    (b"X-API-Key", b"synthetic-worker-token"),
                    (b"Host", b"api.openai.com"),
                    (b"Content-Length", b"18"),
                    (b"Content-Type", b"application/json"),
                    (b"OpenAI-Project", b"offline-project"),
                    (b"User-Agent", b"sdk-fixture"),
                ]
            ),
        } | changes
        return SimpleNamespace(**values)

    async def send(self, transport, request=None):
        async def call():
            return await transport.handle_async_request(request or self.request())

        wrapped = self.contexts.wrap(call, "native-sdk-call")
        with self.contexts.row("fixture-row"):
            return await wrapped()

    async def test_exact_body_semantic_header_values_and_original_response_are_preserved(self):
        request = self.request()
        response = await self.send(self.transport(), request)
        captured = self.observed[0]
        self.assertEqual(captured.body, request.content)
        self.assertEqual(
            captured.headers,
            (
                ("content-type", "application/json"),
                ("openai-project", "offline-project"),
                ("user-agent", "sdk-fixture"),
            ),
        )
        self.assertEqual((captured.method, captured.url), ("POST", URL))
        self.assertEqual((response.content, response.status_code), (b"raw response", 200))
        self.assertEqual(response.headers, (("x-request-id", "rid"),))
        self.assertIs(response.request, request)
        with self.assertRaises(FrozenInstanceError):
            captured.body = b"changed"
        self.assertNotIn("body", repr(captured))
        self.assertNotIn("offline-project", repr(captured))

    async def test_identity_is_allocated_before_exchange_await_and_retries_increment(self):
        entered = asyncio.Event()
        release = asyncio.Event()

        async def exchange(request):
            self.observed.append(request)
            entered.set()
            await release.wait()
            return RawEnvelope("openai", 200, b"{}")

        transport = self.transport(exchange=exchange)

        async def calls():
            await transport.handle_async_request(self.request())
            await transport.handle_async_request(self.request())

        wrapped = self.contexts.wrap(calls, "native-sdk-call")
        with self.contexts.row("fixture-row"):
            task = asyncio.create_task(wrapped())
        await entered.wait()
        self.assertEqual(self.observed[0].attempt, 0)
        release.set()
        await task
        self.assertEqual([request.attempt for request in self.observed], [0, 1])
        self.assertEqual(len({request.logical_id for request in self.observed}), 1)

    async def test_missing_context_and_wrong_endpoint_stop_before_exchange(self):
        transport = self.transport()
        with self.assertRaises(NativeStop) as stopped:
            await transport.handle_async_request(self.request())
        self.assertEqual(stopped.exception.reason, "protocol")
        for changes in (
            {"method": "GET"},
            {"url": URL + "?redirect=bad"},
            {"url": "https://other.example/v1/chat/completions"},
            {"content": "mutable text"},
        ):
            with self.subTest(changes=changes), self.assertRaises(NativeStop) as stopped:
                await self.send(transport, self.request(**changes))
            self.assertEqual(stopped.exception.reason, "protocol")
        self.assertEqual(self.observed, [])

    async def test_cookie_proxy_auth_duplicate_and_control_headers_are_rejected(self):
        for pairs in (
            [(b"Cookie", b"private")],
            [(b"Proxy-Authorization", b"private")],
            [(b"Accept", b"a"), (b"accept", b"b")],
            [(b"Content-Type", b"x\r\nInjected: yes")],
        ):
            with self.subTest(pairs=pairs), self.assertRaises(NativeStop) as stopped:
                await self.send(self.transport(), self.request(headers=SimpleNamespace(raw=pairs)))
            self.assertEqual(stopped.exception.reason, "protocol")
        self.assertEqual(self.observed, [])

    async def test_framing_is_checked_and_only_plain_keep_alive_is_omitted(self):
        for pairs in (
            [(b"Host", b"other.example")],
            [(b"Content-Length", b"1")],
            [(b"Content-Length", b"not-a-number")],
            [(b"Connection", b"upgrade")],
            [(b"Connection", b"keep-alive, upgrade")],
            [(b"Transfer-Encoding", b"chunked")],
            [(b"TE", b"trailers")],
            [(b"Trailer", b"x-signature")],
            [(b"Upgrade", b"websocket")],
        ):
            with self.subTest(pairs=pairs), self.assertRaises(NativeStop) as stopped:
                await self.send(self.transport(), self.request(headers=SimpleNamespace(raw=pairs)))
            self.assertEqual(stopped.exception.reason, "protocol")
        self.assertEqual(self.observed, [])
        headers = SimpleNamespace(raw=[(b"Connection", b"Keep-Alive"), (b"Accept", b"*/*")])
        await self.send(self.transport(), self.request(headers=headers))
        self.assertEqual(self.observed[0].headers, (("accept", "*/*"),))

    async def test_raw_headers_are_exact_bounded_bytes_before_decoding(self):
        decoded = []

        class UnexpectedBytes(bytes):
            def decode(self, *args, **kwargs):
                decoded.append(True)
                return "accept"

        for name, value in (
            (bytearray(b"Accept"), b"application/json"),
            (b"Accept", bytearray(b"application/json")),
            (b"x" * 129, b"application/json"),
            (b"Accept", b"x" * (MAX_HEADER_VALUE_BYTES + 1)),
            (UnexpectedBytes(b"x" * 129), b"application/json"),
        ):
            with self.subTest(name_type=type(name), value_type=type(value)):
                with self.assertRaises(NativeStop) as stopped:
                    await self.send(
                        self.transport(),
                        self.request(headers=SimpleNamespace(raw=[(name, value)])),
                    )
                self.assertEqual(stopped.exception.reason, "protocol")
        self.assertEqual(decoded, [])
        self.assertEqual(self.observed, [])

    async def test_known_host_stop_is_preserved_and_unknown_exception_is_sanitized(self):
        for reason in ("authority", "unknown", "protocol"):

            async def exchange(request, reason=reason):
                raise NativeStop(reason)

            with self.subTest(reason=reason), self.assertRaises(NativeStop) as stopped:
                await self.send(self.transport(exchange=exchange))
            self.assertEqual(stopped.exception.reason, reason)

        async def broken(request):
            raise RuntimeError("synthetic-secret-must-not-escape")

        with self.assertRaises(NativeStop) as stopped:
            await self.send(self.transport(exchange=broken))
        self.assertEqual(stopped.exception.reason, "unknown")
        self.assertNotIn("synthetic-secret", str(stopped.exception))
        self.assertTrue(stopped.exception.__suppress_context__)

    async def test_cancelled_exchange_is_not_recast_as_a_provider_failure(self):
        async def exchange(request):
            raise asyncio.CancelledError

        with self.assertRaises(asyncio.CancelledError):
            await self.send(self.transport(exchange=exchange))

    async def test_unusable_raw_evidence_stops_protocol_without_native_parse(self):
        for envelope in (
            None,
            RawEnvelope("anthropic", 200, b"{}"),
            RawEnvelope("openai", 200, b"{}", truncated=True),
            RawEnvelope("openai", 200, b"{}", headers_complete=False),
            RawEnvelope("openai", 200, b"", withheld=True, received_sha256="a" * 64),
        ):

            async def exchange(request, envelope=envelope):
                return envelope

            with self.subTest(envelope=envelope), self.assertRaises(NativeStop) as stopped:
                await self.send(self.transport(exchange=exchange))
            self.assertEqual(stopped.exception.reason, "protocol")

    async def test_anthropic_uses_its_own_sdk_type_and_endpoint(self):
        transport = self.transport("anthropic")
        request = self.request(
            url="https://api.anthropic.com/v1/messages",
            headers=SimpleNamespace(raw=[(b"Host", b"api.anthropic.com")]),
        )
        await self.send(transport, request)
        self.assertEqual(self.observed[0].provider, "anthropic")

    def test_bad_factory_and_native_request_shapes_fail_without_loading_sdk(self):
        with patch("buddha.native_transport.importlib.import_module") as loader:
            for provider in (None, [], "other"):
                with self.subTest(provider=provider), self.assertRaises(ReleaseError):
                    make_transport(provider, contexts=self.contexts, exchange=self.exchange)
            loader.assert_not_called()
        valid = {
            "provider": "openai",
            "method": "POST",
            "url": URL,
            "body": b"{}",
            "headers": (),
            "logical_id": "a" * 64,
            "attempt": 0,
        }
        for change in (
            {"attempt": True},
            {"attempt": -1},
            {"logical_id": "bad"},
            {"body": bytearray(b"mutable")},
            {"headers": [["a", "b"]]},
        ):
            with self.subTest(change=change), self.assertRaises(ReleaseError):
                NativeRequest(**(valid | change))


if __name__ == "__main__":
    unittest.main()
