"""Network layer tests.

The retry and fallback logic matters on this machine specifically, and both were
added because of measured behaviour:

*   a direct connection to GitHub intermittently times out while succeeding
    seconds later (``Errno 110``);
*   GitHub's release downloads redirect to ``release-assets.githubusercontent.com``,
    which is unreachable directly while ``raw.githubusercontent.com`` and
    ``api.github.com`` are fine -- the local proxy reaches it.

So ``http_get`` retries with backoff and falls back from direct to proxy.  These
tests drive both paths with an injected opener and touch no network.
"""

from __future__ import annotations

import os
import unittest
import urllib.error
import warnings

from nvfku import providers


class _Response:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload

    def read(self) -> bytes:
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *exc) -> None:
        return None


class _Opener:
    """Fails a scripted list of times, then succeeds."""

    def __init__(self, failures: list[Exception], payload: bytes = b"payload") -> None:
        self.failures = list(failures)
        self.payload = payload
        self.calls = 0

    def open(self, request, timeout=None):
        self.calls += 1
        if self.failures:
            raise self.failures.pop(0)
        return _Response(self.payload)


def _http_error(code: int, reason: str) -> urllib.error.HTTPError:
    """An HTTPError with a body the retry loop never reads.

    The loop only inspects ``code``, so a real response body would be dead
    weight.  CPython then warns when it garbage-collects the half-built
    exception, so callers suppress ``ResourceWarning``: the warning is about
    this test double, not about engine code.
    """
    return urllib.error.HTTPError("https://example.invalid/x", code, reason, {}, None)


class _TransportHarness(unittest.TestCase):
    """Shared plumbing: no real sleeping, restorable opener, clean environment."""

    ENV_NAMES = ("DLSS5_HTTP_PROXY", "https_proxy", "HTTPS_PROXY", "all_proxy", "ALL_PROXY")

    def setUp(self) -> None:
        self._openers: dict[str | None, _Opener] = {}
        self._real_opener = providers._opener
        self._env_backup = {name: os.environ.get(name) for name in self.ENV_NAMES}
        for name in self.ENV_NAMES:
            os.environ.pop(name, None)

        def opener_factory(proxy=None):
            if proxy in self._openers:
                return self._openers[proxy]
            return _Opener([], payload=b"unrouted")

        providers._opener = opener_factory
        self.addCleanup(self._restore)

    def _restore(self) -> None:
        providers._opener = self._real_opener
        for name, value in self._env_backup.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value

    def route(self, opener: _Opener, *, proxy: str | None = None) -> _Opener:
        """Point one transport route at a scripted opener."""
        self._openers[proxy] = opener
        return opener

    def no_sleep(self) -> None:
        import time as real_time

        self.addCleanup(setattr, real_time, "sleep", real_time.sleep)
        real_time.sleep = lambda _seconds: None


class HttpGetRetryTest(_TransportHarness):
    def test_success_on_first_attempt(self) -> None:
        opener = self.route(_Opener([]))
        self.assertEqual(providers.http_get("https://example.invalid/x"), b"payload")
        self.assertEqual(opener.calls, 1)

    def test_retries_a_timeout_then_succeeds(self) -> None:
        self.no_sleep()
        opener = self.route(_Opener([TimeoutError("Connection timed out"), OSError("Connection reset")]))
        self.assertEqual(providers.http_get("https://example.invalid/x"), b"payload")
        self.assertEqual(opener.calls, 3)

    def test_does_not_retry_a_4xx(self) -> None:
        opener = self.route(_Opener([_http_error(404, "Not Found")] * 5))
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", ResourceWarning)
            with self.assertRaises(urllib.error.HTTPError):
                providers.http_get("https://example.invalid/x")
        self.assertEqual(opener.calls, 1, "a 404 must not be retried")

    def test_retries_a_5xx(self) -> None:
        self.no_sleep()
        opener = self.route(_Opener([_http_error(503, "Unavailable")], payload=b"recovered"))
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", ResourceWarning)
            self.assertEqual(providers.http_get("https://example.invalid/x"), b"recovered")
        self.assertEqual(opener.calls, 2)

    def test_a_programming_error_is_not_retried_or_swallowed(self) -> None:
        """A bug in the transport must surface, not become a slow timeout.

        Catching bare ``Exception`` in the retry loop turned a ``ValueError``
        from the opener into a retried connection failure, which would hide real
        bugs behind the retry budget.
        """
        opener = self.route(_Opener([ValueError("something structural")]))
        with self.assertRaises(ValueError):
            providers.http_get("https://example.invalid/x")
        self.assertEqual(opener.calls, 1)

    def test_an_unrecognised_transport_error_is_not_retried(self) -> None:
        opener = self.route(_Opener([OSError("disk on fire")]))
        with self.assertRaises(OSError):
            providers.http_get("https://example.invalid/x")
        self.assertEqual(opener.calls, 1)

    def test_falls_back_to_the_ambient_proxy(self) -> None:
        """A direct connection that only times out must still succeed via proxy.

        This is the measured GitHub release-asset case: direct fails, the
        environment's proxy works.
        """
        self.no_sleep()
        os.environ["https_proxy"] = "http://127.0.0.1:7897"
        direct = self.route(_Opener([TimeoutError("Connection timed out")] * 5), proxy=None)
        proxied = self.route(_Opener([]), proxy="http://127.0.0.1:7897")

        self.assertEqual(providers.http_get("https://example.invalid/x"), b"payload")
        self.assertGreater(direct.calls, 0, "direct should have been tried")
        self.assertGreater(proxied.calls, 0, "the proxy should have been used as a fallback")

    def test_explicit_proxy_mode_is_tried_first(self) -> None:
        self.no_sleep()
        os.environ["DLSS5_HTTP_PROXY"] = "http://127.0.0.1:7897"
        proxied = self.route(_Opener([]), proxy="http://127.0.0.1:7897")
        direct = self.route(_Opener([TimeoutError("timed out")]), proxy=None)

        self.assertEqual(providers.http_get("https://example.invalid/x"), b"payload")
        self.assertEqual(direct.calls, 0, "direct must not be tried before the configured proxy")
        self.assertGreater(proxied.calls, 0)

    def test_reports_every_route_when_all_fail(self) -> None:
        self.no_sleep()
        os.environ["https_proxy"] = "http://127.0.0.1:7897"
        self.route(_Opener([TimeoutError("timed out")] * 10), proxy=None)
        self.route(_Opener([TimeoutError("timed out")] * 10), proxy="http://127.0.0.1:7897")

        with self.assertRaises(RuntimeError) as ctx:
            providers.http_get("https://example.invalid/x", attempts=2)
        message = str(ctx.exception)
        self.assertIn("failed on every route", message)
        self.assertIn("direct:", message)
        self.assertIn("127.0.0.1:7897:", message)


class ProxyModeTest(unittest.TestCase):
    def setUp(self) -> None:
        self._backup = {
            name: os.environ.get(name)
            for name in ("DLSS5_HTTP_PROXY", "https_proxy", "HTTPS_PROXY", "all_proxy", "ALL_PROXY")
        }
        for name in self._backup:
            os.environ.pop(name, None)
        self.addCleanup(self._restore)

    def _restore(self) -> None:
        for name, value in self._backup.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value

    def test_direct_is_the_default(self) -> None:
        self.assertEqual(providers._proxy_mode(), "direct")
        self.assertIsNone(providers._ambient_proxy())

    def test_explicit_mode_is_honoured(self) -> None:
        os.environ["DLSS5_HTTP_PROXY"] = "http://127.0.0.1:7897"
        self.assertEqual(providers._proxy_mode(), "http://127.0.0.1:7897")

    def test_ambient_proxy_uses_the_shell_variable(self) -> None:
        os.environ["https_proxy"] = "http://127.0.0.1:7897"
        self.assertEqual(providers._ambient_proxy(), "http://127.0.0.1:7897")

    def test_direct_sentinel_is_not_a_proxy(self) -> None:
        os.environ["DLSS5_HTTP_PROXY"] = "direct"
        self.assertIsNone(providers._ambient_proxy())


if __name__ == "__main__":
    unittest.main()
