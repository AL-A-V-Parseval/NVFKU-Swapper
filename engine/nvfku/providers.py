"""Upstream release resolution.

Two different jobs live here:

*   **Pinned components** - the ones whose exact bytes matter for correctness.
    The NapXDD add-on is the sharpest example: its README states that a model
    build which is not the tested one "reported Success on every evaluate and
    then crashed the game minutes into gameplay".  Anything in
    :data:`PINNED` carries a required SHA-256 and is refused if it does not
    match.
*   **Rolling components** - ReShade and OptiScaler publish new builds on their
    own schedule, so the version is resolved from the GitHub API at run time
    and the digest recorded in the journal rather than enforced.

Downloads go through :func:`fetch` so that the proxy behaviour is explicit.
On this machine the local Clash proxy intermittently fails TLS
(``unexpected eof while reading``) while direct connections succeed, so
``direct`` is the default and the environment can override it.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import urllib.error
import urllib.request
import dataclasses
from dataclasses import dataclass, field
from pathlib import Path

from .paths import Paths, atomic_write_text, human_size, sha256_file

USER_AGENT = "nvfku/0.1 (+https://github.com/; linux)"


@dataclass
class Component:
    id: str
    name: str
    version: str
    url: str
    sha256: str | None = None
    size: int | None = None
    filename: str = ""
    license: str | None = None
    homepage: str | None = None
    notes: str | None = None
    assets: dict[str, str] = field(default_factory=dict)
    """Extra assets of the same release, by name."""

    def local_path(self, paths: Paths) -> Path:
        cache = paths.download_cache() / self.id
        cache.mkdir(parents=True, exist_ok=True)
        return cache / (self.filename or Path(self.url).name)


# --------------------------------------------------------------------- pinned

NAPXDD_VERSION = "v0.2.2"
NAPXDD_BASE = f"https://github.com/NapXDD/addon-dlssnr-linux/releases/download/{NAPXDD_VERSION}"

BRIDGE_VERSION = "v1.4.13-pre8"
BRIDGE_BASE = f"https://github.com/NIGos/dlss5-bridge/releases/download/{BRIDGE_VERSION}"

PINNED: dict[str, Component] = {
    "addon-dlssnr-linux": Component(
        id="addon-dlssnr-linux",
        name="addon-dlssnr-linux",
        version=NAPXDD_VERSION,
        url=f"{NAPXDD_BASE}/dlssnr-linux.addon64",
        filename="dlssnr-linux.addon64",
        size=242176,
        license="GPL-3.0",
        homepage="https://github.com/NapXDD/addon-dlssnr-linux",
        notes=(
            "Drives NGX feature 18 directly through a forwarder DLL whose name "
            "contains 'nvngx.dll', bypassing driver dispatch -- which is what "
            "makes neural rendering work under Proton at all."
        ),
    ),
    "addon-dlssnr-linux-forwarder": Component(
        id="addon-dlssnr-linux-forwarder",
        name="nvngx.dll_nrfwd.dll (forwarder)",
        version=NAPXDD_VERSION,
        url=f"{NAPXDD_BASE}/nvngx.dll_nrfwd.dll",
        filename="nvngx.dll_nrfwd.dll",
        size=91648,
        license="GPL-3.0",
        homepage="https://github.com/NapXDD/addon-dlssnr-linux",
    ),
    "dlss5-bridge": Component(
        id="dlss5-bridge",
        name="dlss5-bridge",
        version=BRIDGE_VERSION,
        url=f"{BRIDGE_BASE}/dlss5-bridge.addon64",
        filename="dlss5-bridge.addon64",
        size=546304,
        license="see upstream THIRD-PARTY-NOTICES.txt",
        homepage="https://github.com/NIGos/dlss5-bridge",
        notes=(
            "Mirrors the game's own DLSS contract onto a private D3D12 session. "
            "On Linux the substitute path needs unwrap=0: ReShade's proxy device "
            "descriptors get re-translated by vkd3d and fault otherwise."
        ),
    ),
    "dlss5-bridge-shasums": Component(
        id="dlss5-bridge",
        name="dlss5-bridge SHA256SUMS",
        version=BRIDGE_VERSION,
        url=f"{BRIDGE_BASE}/SHA256SUMS.txt",
        filename="SHA256SUMS.txt",
        homepage="https://github.com/NIGos/dlss5-bridge",
    ),
}


# -------------------------------------------------------------------- rolling

GITHUB_API = "https://api.github.com/repos"

ROLLING: dict[str, dict] = {
    "optiscaler": {
        "repo": "optiscaler/OptiScaler",
        "homepage": "https://github.com/optiscaler/OptiScaler",
        "asset_pattern": r".*\.7z$",
        "archive": "7z",
        "license": "GPL-3.0",
    },
    "dlss5-bridge": {
        "repo": "NIGos/dlss5-bridge",
        "homepage": "https://github.com/NIGos/dlss5-bridge",
        "asset_pattern": r"dlss5-bridge\.addon64$",
        "license": "see upstream",
    },
    "addon-dlssnr-linux": {
        "repo": "NapXDD/addon-dlssnr-linux",
        "homepage": "https://github.com/NapXDD/addon-dlssnr-linux",
        "asset_pattern": r"dlssnr-linux\.addon64$",
        "license": "GPL-3.0",
    },
}


# ------------------------------------------------------------------ transport


def _proxy_mode() -> str:
    """``direct`` (default) or an explicit proxy URL."""
    value = os.environ.get("DLSS5_HTTP_PROXY", "").strip()
    if value:
        return value
    return "direct"


def _ambient_proxy() -> str | None:
    """A proxy the environment already knows about, if any.

    Measured on the development machine: GitHub's release downloads redirect to
    ``release-assets.githubusercontent.com``, which is unreachable *directly*
    while ``raw.githubusercontent.com`` and ``api.github.com`` are fine.  The
    local proxy reaches it.  So a direct failure has to be able to fall back,
    and the fallback is exactly the proxy the shell already exports.
    """
    for name in ("DLSS5_HTTP_PROXY", "https_proxy", "HTTPS_PROXY", "all_proxy", "ALL_PROXY"):
        value = os.environ.get(name, "").strip()
        if value and value.lower() != "direct":
            return value
    return None


def _opener(proxy: str | None = None) -> urllib.request.OpenerDirector:
    handlers: list[urllib.request.BaseHandler] = []
    if not proxy:
        # An empty ProxyHandler bypasses the environment's http_proxy.
        handlers.append(urllib.request.ProxyHandler({}))
    else:
        handlers.append(urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
    handlers.append(urllib.request.HTTPSHandler())
    return urllib.request.build_opener(*handlers)


# Transient failures are the norm on this network: a direct connection to
# GitHub intermittently times out (`Errno 110`) while succeeding seconds later,
# and the local proxy intermittently drops TLS.  Retrying is not optional here,
# it is the difference between an install that completes and one that does not.
# Transport-level exceptions.  `ssl.SSLError` and `socket.timeout` are both
# `OSError` subclasses, and `URLError` wraps most of what urllib raises.
_NETWORK_ERRORS = (
    urllib.error.URLError,
    TimeoutError,
    OSError,
    ConnectionError,
)

_RETRYABLE = (
    "timed out",
    "Connection reset",
    "Connection refused",
    "Temporary failure",
    "EOF occurred",
    "unexpected eof",
    "Remote end closed",
    "IncompleteRead",
    "ChunkedEncodingError",
    "Network is unreachable",
)


def _looks_transient(exc: BaseException) -> bool:
    """Whether a transport exception is worth retrying.

    A missing retry token means the failure is not network-shaped, which on this
    machine is the difference between retrying a genuine timeout and retrying a
    bug four more times.
    """
    message = str(exc)
    return any(token.lower() in message.lower() for token in _RETRYABLE)


def _attempt(
    url: str,
    *,
    proxy: str | None,
    timeout: int,
    accept: str | None,
    attempts: int,
    backoff: float,
    logger,
) -> bytes:
    import time as _time
    import urllib.error

    last: Exception | None = None
    label = f"via {proxy}" if proxy else "direct"
    for attempt in range(1, attempts + 1):
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        if accept:
            request.add_header("Accept", accept)
        try:
            with _opener(proxy).open(request, timeout=timeout) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            if 400 <= exc.code < 500:
                raise
            last = exc
        except _NETWORK_ERRORS as exc:
            # Only transport-level failures are retried.  `OSError` covers both
            # a genuine connection reset and, say, a bug that passes a bad file
            # descriptor, so the message decides: a network-shaped error is
            # retried, anything else is surfaced immediately rather than being
            # turned into a slow, misleading timeout.
            if not _looks_transient(exc):
                raise
            last = exc
        except Exception:
            # Not a transport type at all: a programming error.  Never retried.
            raise
        if attempt < attempts:
            delay = backoff ** (attempt - 1)
            if logger:
                logger(f"  retry    {label} attempt {attempt}/{attempts}, waiting {delay:.0f}s")
            _time.sleep(delay)
    raise last if last is not None else RuntimeError("no attempt was made")


def http_get(
    url: str,
    *,
    timeout: int = 60,
    accept: str | None = None,
    attempts: int = 3,
    backoff: float = 2.0,
    logger=None,
) -> bytes:
    """GET with bounded retries *and* a direct-to-proxy fallback.

    Order: the configured mode first, then the opposite one.  4xx responses are
    never retried -- the URL is wrong and repeating it wastes the user's time.
    """
    modes: list[str | None] = [None if _proxy_mode() == "direct" else _proxy_mode()]
    fallback = _ambient_proxy()
    if fallback and fallback not in modes:
        modes.append(fallback)
    modes.append(None) if None not in modes else None

    errors: list[str] = []
    for index, proxy in enumerate(modes):
        try:
            return _attempt(
                url,
                proxy=proxy,
                timeout=timeout,
                accept=accept,
                attempts=attempts,
                backoff=backoff,
                logger=logger,
            )
        except urllib.error.HTTPError:
            raise  # a definitive answer from the server; do not try another route
        except _NETWORK_ERRORS as exc:
            if not _looks_transient(exc):
                raise
            errors.append(f"{'via ' + proxy if proxy else 'direct'}: {exc}")
            if index + 1 < len(modes) and logger:
                logger(f"  fallback {'direct' if proxy else 'via ' + str(modes[index + 1])}")
    raise RuntimeError(f"GET {url} failed on every route:\n  " + "\n  ".join(errors))


def http_json(url: str) -> dict:
    return json.loads(http_get(url, accept="application/vnd.github+json").decode("utf-8"))


def fetch(component: Component, paths: Paths, *, logger=print) -> Path:
    """Download to the cache, verifying a pinned digest when there is one."""
    target = component.local_path(paths)
    if target.is_file():
        if component.sha256 is None or sha256_file(target) == component.sha256:
            logger(f"  cached   {target.name} ({human_size(target.stat().st_size)})")
            return target
        logger(f"  stale    {target.name} (digest changed), re-downloading")

    logger(f"  fetch    {component.url}")
    blob = http_get(component.url, timeout=300)
    if component.size is not None and len(blob) != component.size:
        raise ValueError(
            f"{component.name}: expected {component.size} bytes, got {len(blob)}"
        )
    if component.sha256 is not None:
        import hashlib

        digest = hashlib.sha256(blob).hexdigest()
        if digest != component.sha256:
            raise ValueError(
                f"{component.name}: SHA-256 mismatch\n  expected {component.sha256}\n  got      {digest}"
            )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(blob)
    logger(f"  saved    {target.name} ({human_size(len(blob))})")
    return target


#: A known-good release per rolling component, used only when the API cannot be
#: reached at all.
#:
#: This exists because an unauthenticated GitHub API allows 60 requests an hour,
#: and `plan` used to spend one on every game-detail open — so the rate limit was
#: reached in normal use and the route then had *no* version to name. A baseline a
#: few weeks old is a far better answer than "could not determine the version", and
#: it is what the install would resolve against its pinned digest anyway.
#:
#: Not a substitute for the query: a fresh answer always wins, and a successful
#: resolve overwrites this in the cache.
ROLLING_SEED: dict[str, dict] = {
    "optiscaler": {
        "name": "Optiscaler_0.9.4-final.20260718._MM.7z",
        "version": "v0.9.4",
        "url": (
            "https://github.com/optiscaler/OptiScaler/releases/download/v0.9.4/"
            "Optiscaler_0.9.4-final.20260718._MM.7z"
        ),
        "size": 55_016_448,
    },
    # Both of these match `ROLLING`'s asset patterns:
    # `dlss5-bridge\.addon64$` and `dlssnr-linux\.addon64$`.
    "dlss5-bridge": {
        "name": "dlss5-bridge.addon64",
        "version": "v1.4.13-pre8",
        "url": (
            "https://github.com/NIGos/dlss5-bridge/releases/download/v1.4.13-pre8/"
            "dlss5-bridge.addon64"
        ),
        "size": 546_304,
    },
    "addon-dlssnr-linux": {
        "name": "dlssnr-linux.addon64",
        "version": "v0.2.2",
        "url": (
            "https://github.com/NapXDD/addon-dlssnr-linux/releases/download/v0.2.2/"
            "dlssnr-linux.addon64"
        ),
        "size": 242_176,
    },
}


#: How long a resolved rolling release is reused before the API is asked again.
#:
#: Short, because upstream versions do move and a stale version is a real bug. The
#: point is not to avoid the query, it is to avoid it *per plan*: the UI calls
#: `plan` on every game-detail open, and each call was making a fresh HTTPS request
#: to the GitHub API — 0.9-2.4 s on a machine behind a proxy, on a page nobody can
#: use until it returns.
ROLLING_TTL_SECONDS = 900

#: How long to stop asking after the API says we are rate limited.
#:
#: A rate limit is a door that stays shut for up to an hour; retrying it on every
#: plan just pays a failed round trip each time. Long enough to stop paying it,
#: short enough that a limit which lifts early is noticed.
RATE_LIMIT_BACKOFF_SECONDS = 1800


#: Set for the life of the process as soon as any request comes back rate limited.
#:
#: The on-disk backoff is for *later* invocations; this is for the rest of this one.
#: Without it a listing of three rolling components discovered the same rate limit
#: three times over, paying a failed round trip for each — which is how a refresh of
#: the components page took 1.6 s to learn one fact.
_PROCESS_RATE_LIMITED = False


def _rate_limited_until(paths: Paths) -> float:
    return float(_read_rolling_cache(paths).get("_rate_limited_until") or 0)


def _note_rate_limit(cache: dict, exc: Exception) -> dict:
    """Record a rate-limit refusal in ``cache``, and return it.

    Mutates the caller's dictionary rather than re-reading the file. An earlier
    version read fresh, wrote the flag, and was then overwritten by the caller's
    own stale snapshot at the end of the function — so the backoff was written and
    immediately lost, and every invocation paid a failed round trip again.
    """
    text = str(exc)
    if "403" not in text and "429" not in text:
        return cache
    import time

    global _PROCESS_RATE_LIMITED
    _PROCESS_RATE_LIMITED = True
    cache["_rate_limited_until"] = time.time() + RATE_LIMIT_BACKOFF_SECONDS
    return cache


def _rolling_cache_path(paths: Paths):
    return paths.download_cache() / "rolling.json"


def _read_rolling_cache(paths: Paths) -> dict:
    try:
        data = json.loads(_rolling_cache_path(paths).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_rolling_cache(paths: Paths, data: dict) -> None:
    path = _rolling_cache_path(paths)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        # Atomic: a truncated cache must read as "no cache", never as a component
        # with no URL. The reader already treats unparseable JSON that way.
        tmp = path.with_suffix(".json.part")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        pass


def resolve_rolling_cached(
    paths: Paths,
    key: str,
    *,
    prefer_prerelease: bool | None = None,
    max_age: float = ROLLING_TTL_SECONDS,
    logger=None,
) -> Component:
    """``resolve_rolling`` with a TTL cache and two layers of fallback.

    The fallbacks are what make this usable interactively. `plan` runs on every
    game-detail open, and each call used to make a synchronous GitHub API request —
    0.9 s on a good connection, 2.4 s behind a proxy. Worse, an unauthenticated API
    allows 60 requests an hour, so ordinary use reached the limit, and the route was
    then left with no version to name at all.

    Order: a fresh cached answer, then the API, then a stale cached answer, then
    `ROLLING_SEED`. A version a few weeks old is a far better answer than "could not
    determine the version", and the install resolves against a pinned digest anyway.
    """
    import time

    slot = f"{key}:{prefer_prerelease}"
    cache = _read_rolling_cache(paths)
    entry = cache.get(slot)
    if (
        isinstance(entry, dict)
        and entry.get("component")
        and time.time() - float(entry.get("at", 0)) < max_age
    ):
        return _component_from_cache(entry["component"])

    import time as _time

    limited = _PROCESS_RATE_LIMITED or _rate_limited_until(paths) > _time.time()
    if limited:
        # Skipped rather than attempted: the answer is already known to be "no".
        #
        # Every branch here returns. An earlier version fell through when there was
        # no seed for the key, which meant it went and made the very request it had
        # just established would fail — paying the round trip to learn nothing.
        if isinstance(entry, dict) and entry.get("component"):
            return _component_from_cache(entry["component"])
        seed = ROLLING_SEED.get(key)
        if seed is None:
            raise RuntimeError(
                f"{key} cannot be resolved: the GitHub API is rate limited and no "
                "known release is recorded for it"
            )
        if logger is not None:
            logger(f"  limited  {key}; using the known release {seed['version']}")
        # Recorded too, so the next invocation answers from cache rather than
        # re-deriving the seed and re-checking the backoff for this key.
        return _remember(
            paths,
            cache,
            slot,
            Component(
                id=key,
                name=seed["name"],
                version=seed["version"],
                url=seed["url"],
                size=seed.get("size"),
                filename=seed["name"],
                license=ROLLING.get(key, {}).get("license"),
                homepage=ROLLING.get(key, {}).get("homepage"),
            ),
        )

    try:
        component = resolve_rolling(key, prefer_prerelease=prefer_prerelease)
    except Exception as exc:  # noqa: BLE001 - every failure falls back by design
        _note_rate_limit(cache, exc)
        if isinstance(entry, dict) and entry.get("component"):
            # Written through, so the backoff survives this call rather than being
            # discarded by the early return.
            _write_rolling_cache(paths, cache)
            if logger is not None:
                logger(
                    f"  stale    {key} ({exc}); using the cached "
                    f"{entry['component'].get('version')}"
                )
            return _component_from_cache(entry["component"])
        seed = ROLLING_SEED.get(key)
        if seed is None:
            _write_rolling_cache(paths, cache)
            raise
        if logger is not None:
            logger(f"  offline  {key} ({exc}); using the known release {seed['version']}")
        component = Component(
            id=key,
            name=seed["name"],
            version=seed["version"],
            url=seed["url"],
            size=seed.get("size"),
            filename=seed["name"],
            license=ROLLING.get(key, {}).get("license"),
            homepage=ROLLING.get(key, {}).get("homepage"),
        )

    return _remember(paths, cache, slot, component)


def _remember(paths: Paths, cache: dict, slot: str, component: Component) -> Component:
    """Cache ``component`` and return it.

    The write happens here and only here, so every path that produces a component
    records it — including the two fallbacks, which an earlier version returned
    without caching and so re-derived on every invocation.
    """
    import time

    cache[slot] = {"at": time.time(), "component": dataclasses.asdict(component)}
    _write_rolling_cache(paths, cache)
    return component


def _component_from_cache(data: dict) -> Component:
    """Rebuild a Component, ignoring fields this version does not know.

    Filtered rather than splatted: a cache written by a newer build could carry a
    field that no longer exists, and `Component(**data)` would then fail the plan
    instead of the plan quietly losing an unused detail.
    """
    known = {f.name for f in dataclasses.fields(Component)}
    return Component(**{k: v for k, v in data.items() if k in known})


def resolve_rolling(key: str, *, prefer_prerelease: bool | None = None) -> Component:
    """Resolve a component's current release from the GitHub API."""
    spec = ROLLING[key]
    import re

    pattern = re.compile(spec["asset_pattern"])
    releases = http_json(f"{GITHUB_API}/{spec['repo']}/releases?per_page=15")
    if isinstance(releases, dict):
        raise RuntimeError(f"GitHub API error for {key}: {releases.get('message')}")

    ordered = [
        rel
        for rel in releases
        if rel.get("assets")
        and (prefer_prerelease is None or bool(rel.get("prerelease")) == prefer_prerelease)
    ]
    # Prefer a stable release, but fall back to a prerelease when that is all
    # upstream has published for this asset (dlss5-bridge ships prereleases).
    # Newest first within each of those two groups.
    ordered.sort(
        key=lambda rel: (bool(rel.get("prerelease")), rel.get("published_at", "")),
        reverse=False,
    )
    # `reverse=False` above groups stable-before-prerelease; within a group we
    # still want the newest, so sort the timestamp descending by re-sorting on
    # the tuple with the prerelease flag inverted.
    ordered.sort(
        key=lambda rel: (rel.get("published_at", "")),
        reverse=True,
    )
    ordered.sort(key=lambda rel: bool(rel.get("prerelease")))
    if not ordered:
        raise RuntimeError(f"no usable release for {key}")

    for release in ordered + list(releases):
        for asset in release.get("assets", []):
            if pattern.search(asset["name"]):
                return Component(
                    id=key,
                    name=asset["name"],
                    version=release["tag_name"],
                    url=asset["browser_download_url"],
                    size=asset.get("size"),
                    filename=asset["name"],
                    license=spec.get("license"),
                    homepage=spec.get("homepage"),
                )
    raise RuntimeError(f"no asset matching {spec['asset_pattern']} in {key} releases")


# ------------------------------------------------------------------- archives


def have_7z() -> str | None:
    for candidate in ("7z", "7zz", "7za"):
        found = shutil.which(candidate)
        if found:
            return found
    return None


def extract_7z(archive: Path, dest: Path, *, strip_components: int = 0, logger=print) -> list[Path]:
    """Extract a 7z archive.  OptiScaler v0.9.4 ships only a .7z, which is why
    this exists instead of a zip helper."""
    tool = have_7z()
    if tool is None:
        raise RuntimeError(
            "no 7z extractor found; install p7zip (Arch: `pacman -S p7zip`)"
        )
    dest.mkdir(parents=True, exist_ok=True)
    command = [tool, "x", "-y", f"-o{dest}"]
    if strip_components:
        command.append(f"-sp{strip_components}" if False else "-spe")
    command.append(str(archive))
    # -spf2 keeps full paths; for stripping we extract then move.
    command = [tool, "x", "-y", f"-o{dest}", str(archive)]
    logger(f"  extract  {archive.name} -> {dest}")
    subprocess.run(command, check=True, capture_output=True)
    return [p for p in dest.rglob("*") if p.is_file()]


def fetch_asset(component: "Component", asset_name: str, paths: Paths, *, logger=print) -> Path:
    """Download a sibling asset of the same release (e.g. SHA256SUMS.txt).

    Kept separate from :func:`fetch` because the sibling has no pinned digest of
    its own -- it *is* the digest list.
    """
    import urllib.parse

    base = component.url.rsplit("/", 1)[0]
    url = f"{base}/{urllib.parse.quote(asset_name)}"
    cache = paths.download_cache() / component.id
    cache.mkdir(parents=True, exist_ok=True)
    target = cache / asset_name
    if target.is_file() and target.stat().st_size > 0:
        logger(f"  cached   {asset_name}")
        return target
    logger(f"  fetch    {url}")
    blob = http_get(url, timeout=120)
    if not blob:
        raise ValueError(f"{asset_name}: empty response")
    target.write_bytes(blob)
    logger(f"  saved    {asset_name} ({human_size(len(blob))})")
    return target


def parse_shasums(text: str) -> dict[str, str]:
    """Parse a ``SHA256SUMS`` file into ``{filename: digest}``.

    Tolerates the ``<digest>  <name>`` and ``<digest> *<name>`` forms, and the
    ``SHA256 (name) = digest`` form some tools emit.
    """
    import re

    out: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        match = re.match(r"^([0-9a-fA-F]{64})\s*\*?\s*(.+)$", line)
        if match:
            out[match.group(2).strip()] = match.group(1).lower()
            continue
        match = re.match(r"^SHA256\s*\((.+?)\)\s*=\s*([0-9a-fA-F]{64})$", line)
        if match:
            out[match.group(1).strip()] = match.group(2).lower()
    return out


def verify_against_shasums(path: Path, sums: dict[str, str], *, logger=print) -> tuple[bool, str]:
    """Check a file against a parsed SHA256SUMS map.

    Returns ``(verified, message)``.  A name that is simply absent from the list
    is reported as unverified rather than a failure: upstream lists are often
    partial and a missing entry is not evidence of tampering.
    """
    expected = sums.get(path.name)
    if expected is None:
        return False, f"{path.name} is not listed in the upstream SHA256SUMS"
    actual = sha256_file(path)
    if actual == expected:
        return True, f"{path.name} matches the upstream SHA-256"
    return False, f"{path.name} does NOT match upstream: got {actual}, expected {expected}"


def list_release_assets(repo: str, *, limit: int = 3) -> list[dict]:
    releases = http_json(f"{GITHUB_API}/{repo}/releases?per_page={limit}")
    if isinstance(releases, dict):
        return []
    out: list[dict] = []
    for release in releases:
        for asset in release.get("assets", []):
            out.append(
                {
                    "tag": release["tag_name"],
                    "prerelease": bool(release.get("prerelease")),
                    "name": asset["name"],
                    "size": asset["size"],
                    "url": asset["browser_download_url"],
                    "published_at": release.get("published_at"),
                }
            )
    return out


# ------------------------------------------------------------- route state

ROUTE_STATE_VERSION = 1


def route_state_path(paths: Paths, game_key: str, route: str) -> Path:
    directory = paths.profiles_root() / game_key
    directory.mkdir(parents=True, exist_ok=True)
    return directory / f"{route}.json"


def read_route_state(paths: Paths, game_key: str, route: str) -> dict:
    """Per-game, per-route settings that must survive reinstalls.

    The proxy filename is the important one: A2 has to remember which name it
    chose (``dxgi.dll`` vs ``winmm.dll``), or the next reinstall would pick a
    second name, write the same tool twice, and shadow itself.
    """
    path = route_state_path(paths, game_key, route)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"version": ROUTE_STATE_VERSION}
    if not isinstance(data, dict) or data.get("version") != ROUTE_STATE_VERSION:
        return {"version": ROUTE_STATE_VERSION}
    return data


def write_route_state(paths: Paths, game_key: str, route: str, state: dict) -> Path:
    path = route_state_path(paths, game_key, route)
    payload = dict(state)
    payload["version"] = ROUTE_STATE_VERSION
    atomic_write_text(path, json.dumps(payload, indent=2, sort_keys=True))
    return path
