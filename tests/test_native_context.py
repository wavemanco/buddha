"""Stable native logical context uses coroutine creation, never HTTP arrival."""

import asyncio
import re
import unittest
from threading import Barrier

from buddha.native_context import ContextError, Contexts, NativeStop


class NativeContextTests(unittest.IsolatedAsyncioTestCase):
    async def test_bootstrap_factory_is_legal_but_invocation_needs_a_row(self):
        contexts = Contexts()

        async def operation():
            return contexts.attempt()

        wrapped = contexts.wrap(operation, "judge")
        with self.assertRaises(ContextError):
            wrapped()
        with self.assertRaises(ContextError):
            contexts.attempt()
        with contexts.row("row-a"):
            with self.assertRaises(ContextError):
                contexts.attempt()
            identity, attempt = await wrapped()
        self.assertRegex(identity, r"^[0-9a-f]{64}$")
        self.assertEqual(attempt, 0)
        with self.assertRaises(ContextError):
            contexts.attempt()

    async def test_identical_calls_keep_creation_order_when_awaited_in_reverse(self):
        async def run(reverse):
            contexts = Contexts()

            async def operation():
                return contexts.attempt()

            wrapped = contexts.wrap(operation, "same-request")
            with contexts.row("row-a"):
                first, second = wrapped(), wrapped()
                if reverse:
                    second_result, first_result = await second, await first
                else:
                    first_result, second_result = await first, await second
            return first_result, second_result

        forward = await run(False)
        backward = await run(True)
        self.assertEqual(forward, backward)
        self.assertNotEqual(forward[0][0], forward[1][0])
        self.assertEqual([item[1] for item in forward], [0, 0])

    async def test_row_snapshot_survives_await_outside_its_creation_scope(self):
        contexts = Contexts()

        async def operation():
            await asyncio.sleep(0)
            return contexts.attempt()

        wrapped = contexts.wrap(operation, "judge")
        with contexts.row("row-a"):
            pending = wrapped()
        outside_result = await pending
        with contexts.row("row-a"):
            repeated_result = await wrapped()
        self.assertEqual(outside_result, repeated_result)
        with self.assertRaises(ContextError):
            contexts.attempt()

    async def test_delayed_rows_and_heads_keep_their_own_identity_and_attempts(self):
        contexts = Contexts()
        release = asyncio.Event()
        started = asyncio.Event()

        async def operation(delayed=False):
            first = contexts.attempt()
            if delayed:
                started.set()
                await release.wait()
            await asyncio.sleep(0)
            second = contexts.attempt()
            return first, second

        wrapped = contexts.wrap(operation, "head")
        with contexts.row("row-a"):
            slow = asyncio.create_task(wrapped(True))
            await started.wait()
        with contexts.row("row-b"):
            fast = await wrapped()
        release.set()
        late = await slow
        self.assertNotEqual(fast[0][0], late[0][0])
        for first, second in (fast, late):
            self.assertEqual(first[0], second[0])
            self.assertEqual((first[1], second[1]), (0, 1))
        with contexts.row("row-a"):
            self.assertEqual(await wrapped(), late)
        with contexts.row("row-b"):
            self.assertEqual(await wrapped(), fast)

    async def test_nested_primary_fallback_and_heads_have_hierarchical_identity(self):
        async def run(reverse):
            contexts = Contexts()

            async def model_leg():
                return contexts.attempt(), contexts.attempt()

            leg = contexts.wrap(model_leg, "model-leg")

            async def logical_call():
                first, second = leg(), leg()
                if reverse:
                    second_result, first_result = await second, await first
                else:
                    first_result, second_result = await first, await second
                return first_result, second_result

            logical = contexts.wrap(logical_call, "logical-call")
            with contexts.row("row-a"):
                first, second = logical(), logical()
                if reverse:
                    second_result, first_result = await second, await first
                else:
                    first_result, second_result = await first, await second
            return first_result, second_result

        forward = await run(False)
        self.assertEqual(forward, await run(True))
        identities = [leg[0][0] for call in forward for leg in call]
        self.assertEqual(len(set(identities)), 4)
        for call in forward:
            for first_attempt, second_attempt in call:
                self.assertEqual(first_attempt[0], second_attempt[0])
                self.assertEqual((first_attempt[1], second_attempt[1]), (0, 1))

    async def test_copied_thread_context_allocates_unique_attempts_for_one_logical_call(self):
        contexts = Contexts()
        rendezvous = Barrier(2)

        def physical_attempt():
            # Pair active workers so this also exercises concurrent copied contexts.
            rendezvous.wait(timeout=10)
            return contexts.attempt()

        async def logical_call():
            return await asyncio.gather(*(asyncio.to_thread(physical_attempt) for _ in range(32)))

        with contexts.row("one-row"):
            results = await contexts.wrap(logical_call, "one-logical-call")()
        self.assertEqual(len({identity for identity, _ in results}), 1)
        self.assertEqual(sorted(attempt for _, attempt in results), list(range(32)))
        with self.assertRaises(ContextError):
            contexts.attempt()

    async def test_context_resets_after_exception_and_cancellation(self):
        contexts = Contexts()
        started = asyncio.Event()

        async def operation(failure):
            contexts.attempt()
            if failure:
                raise ValueError("native semantic failure")
            started.set()
            await asyncio.Event().wait()

        wrapped = contexts.wrap(operation, "judge")
        with contexts.row("row-a"):
            with self.assertRaisesRegex(ValueError, "native semantic failure"):
                await wrapped(True)
            with self.assertRaises(ContextError):
                contexts.attempt()
            task = asyncio.create_task(wrapped(False))
            await started.wait()
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
            with self.assertRaises(ContextError):
                contexts.attempt()
        with self.assertRaises(ContextError):
            wrapped(True)

    async def test_distinct_labels_and_rows_do_not_alias_and_unicode_is_stable(self):
        async def run(identity, label):
            contexts = Contexts()

            async def operation():
                return contexts.attempt()

            with contexts.row(identity):
                return await contexts.wrap(operation, label)()

        unicode_result = await run("row-🧪", "judge-λ")
        self.assertEqual(unicode_result, await run("row-🧪", "judge-λ"))
        self.assertNotEqual(unicode_result[0], (await run("row-other", "judge-λ"))[0])
        self.assertNotEqual(unicode_result[0], (await run("row-🧪", "other-label"))[0])
        self.assertTrue(re.fullmatch(r"[0-9a-f]{64}", unicode_result[0]))

    async def test_nested_rows_restore_outer_counter_and_context_instances_are_separate(self):
        contexts, other = Contexts(), Contexts()

        async def operation():
            with self.assertRaises(ContextError):
                other.attempt()
            return contexts.attempt()

        wrapped = contexts.wrap(operation, "judge")
        with contexts.row("outer"):
            first = await wrapped()
            with contexts.row("inner"):
                inner = await wrapped()
            second = await wrapped()
        with contexts.row("outer"):
            self.assertEqual(await wrapped(), first)
            self.assertEqual(await wrapped(), second)
        self.assertEqual(len({first[0], inner[0], second[0]}), 3)

    async def test_identity_and_label_validation_is_bounded_and_does_not_echo_input(self):
        contexts = Contexts()

        async def operation():
            return None

        invalid = (None, True, 1, b"bytes", "", " ", "nul\x00text", "\ud800", "x" * 1_000_000)
        for value in invalid:
            with self.subTest(value_type=type(value).__name__):
                with self.assertRaises(ContextError), contexts.row(value):
                    pass
                with self.assertRaises(ContextError):
                    contexts.wrap(operation, value)
        for value in (None, 1, lambda: None):
            with self.subTest(function_type=type(value).__name__), self.assertRaises(ContextError):
                contexts.wrap(value, "judge")

    async def test_native_stop_escapes_exception_retry_handlers_and_rejects_secret_reason(self):
        self.assertTrue(issubclass(NativeStop, BaseException))
        self.assertFalse(issubclass(NativeStop, Exception))
        for reason in ("authority", "unknown", "protocol", "cancelled"):
            with self.subTest(reason=reason), self.assertRaises(NativeStop):
                try:
                    raise NativeStop(reason)
                except Exception:
                    self.fail("native retry handler swallowed a bridge authority stop")
        secret = "credential-sentinel-not-a-permitted-stop-reason"
        with self.assertRaises(ContextError) as rejected:
            NativeStop(secret)
        self.assertNotIn(secret, str(rejected.exception))
        for reason in (None, 1, True, "", "Authority"):
            with self.subTest(reason_type=type(reason).__name__), self.assertRaises(ContextError):
                NativeStop(reason)


if __name__ == "__main__":
    unittest.main()
