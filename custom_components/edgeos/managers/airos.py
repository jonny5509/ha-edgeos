"""Client and coordinator for legacy Ubiquiti airOS 4 devices."""
from __future__ import annotations

from datetime import timedelta
import logging
import re
import time
from typing import Any

from aiohttp import ClientError, ClientTimeout, CookieJar, FormData

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from ..common.consts import DOMAIN

_LOGGER = logging.getLogger(__name__)

_VALUE_RE = re.compile(
    r"""\b(?P<key>[a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*(?P<value>"[^"]*"|-?\d+(?:\.\d+)?|true|false)""",
    re.IGNORECASE,
)


class AirosAuthenticationError(Exception):
    """Raised when the legacy airOS login did not return status data."""


class AirosClient:
    """Read status data from the legacy airOS CGI interface."""

    def __init__(
        self, hass: HomeAssistant, host: str, username: str, password: str
    ) -> None:
        self._hass = hass
        host = host.strip().rstrip("/")
        if host.startswith("http://"):
            self._base_url = host
        elif host.startswith("https://"):
            self._base_url = "http://" + host.removeprefix("https://")
        else:
            self._base_url = f"http://{host}"
        self._username = username
        self._password = password
        self._session = async_create_clientsession(
            hass, cookie_jar=CookieJar(unsafe=True)
        )

    async def async_get_status(self) -> dict[str, Any]:
        """Log in and return parsed status values."""
        timeout = ClientTimeout(total=12)
        login_url = f"{self._base_url}/login.cgi"
        status_url = f"{login_url}?uri=%2Fstatus.cgi"

        try:
            # airOS 4 redirects through /cookiechecker and initializes its
            # session cookie when the device root is visited first.
            async with self._session.get(self._base_url, timeout=timeout) as response:
                await response.read()
                response.raise_for_status()

            # Load the login page in the same cookie-backed session.
            async with self._session.get(login_url, timeout=timeout) as response:
                await response.read()
                response.raise_for_status()

            form = FormData(default_to_multipart=True)
            form.add_field("username", self._username)
            form.add_field("password", self._password)
            form.add_field("uri", "/status.cgi")
            form.add_field("press", "Login")

            async with self._session.post(
                status_url, data=form, allow_redirects=True, timeout=timeout
            ) as response:
                response.raise_for_status()
                html = await response.text(errors="replace")

        except (ClientError, TimeoutError) as err:
            raise UpdateFailed(f"Unable to contact legacy airOS device: {err}") from err

        if "parent.update_basic(" not in html or not re.search(r"\buptime\s*=", html):
            # A failed login normally leaves the browser on the login form.
            # Do not label arbitrary HTML (proxy pages, firmware-specific
            # errors, or unexpected responses) as bad credentials.
            login_form = re.search(
                r"<input\b[^>]*\btype\s*=\s*['\"]?password\b",
                html,
                re.IGNORECASE,
            )
            if response.url.path.lower().endswith("/login.cgi") or login_form:
                raise AirosAuthenticationError(
                    "airOS returned the login page instead of status data"
                )
            raise UpdateFailed(
                "Legacy airOS returned an unexpected response instead of status data"
            )

        raw: dict[str, str] = {}
        for match in _VALUE_RE.finditer(html):
            value = match.group("value")
            raw[match.group("key").lower()] = (
                value[1:-1] if value.startswith('"') and value.endswith('"') else value
            )

        def number(*keys: str) -> float | int | None:
            for key in keys:
                value = raw.get(key.lower())
                if value is None:
                    continue
                found = re.search(r"-?\d+(?:\.\d+)?", value)
                if found:
                    parsed = float(found.group())
                    return int(parsed) if parsed.is_integer() else parsed
            return None

        result: dict[str, Any] = {
            "uptime": number("uptime"),
            "signal": number("signal"),
            "noise_floor": number("noisef", "noise"),
            "ccq": number("ccq"),
            "ack_distance": number("ack"),
            "frequency": number("frequency", "freq"),
            "channel": number("channel"),
            "tx_link_rate": number("tx_rate"),
            "rx_link_rate": number("rx_rate"),
            "lan_received_bytes": number("lan_rxbytes"),
            "lan_received_packets": number("lan_rxpackets"),
            "lan_received_errors": number("lan_rxerrors"),
            "lan_sent_bytes": number("lan_txbytes"),
            "lan_sent_packets": number("lan_txpackets"),
            "lan_sent_errors": number("lan_txerrors"),
            "wlan_received_bytes": number("wlan_rxbytes"),
            "wlan_received_packets": number("wlan_rxpackets"),
            "wlan_received_errors": number("wlan_rxerrors"),
            "wlan_sent_bytes": number("wlan_txbytes"),
            "wlan_sent_packets": number("wlan_txpackets"),
            "wlan_sent_errors": number("wlan_txerrors"),
        }
        # airOS 4 reports CCQ in tenths of a percent (for example, 1000).
        if result["ccq"] is not None:
            result["ccq"] = min(float(result["ccq"]) / 10, 100)
        return result

    async def async_validate(self) -> bool:
        """Return whether credentials can retrieve a status response."""
        try:
            await self.async_get_status()
            return True
        except AirosAuthenticationError:
            return False

    async def async_close(self) -> None:
        """Leave the Home Assistant-managed HTTP session open."""
        # async_create_clientsession returns a session managed by Home Assistant.
        # Closing it here would disrupt other integrations using the shared session.
        return


class AirosCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Poll a legacy airOS device and derive rates from byte counters."""

    def __init__(
        self,
        hass: HomeAssistant,
        host: str,
        username: str,
        password: str,
        entry_id: str,
    ) -> None:
        super().__init__(
            hass,
            logger=_LOGGER,
            name=f"{DOMAIN} airOS",
            update_interval=timedelta(seconds=30),
        )
        self.client = AirosClient(hass, host, username, password)
        self.entry_id = entry_id
        self._previous: dict[str, tuple[float, float]] = {}
        self._last_sample: float | None = None

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch current counters and calculate byte-per-second rates."""
        try:
            data = await self.client.async_get_status()
        except AirosAuthenticationError as err:
            raise UpdateFailed(str(err)) from err

        now = time.monotonic()
        elapsed = now - self._last_sample if self._last_sample is not None else None
        for direction in ("received", "sent"):
            for interface in ("lan", "wlan"):
                key = f"{interface}_{direction}_bytes"
                counter = data.get(key)
                rate_key = f"{interface}_{direction}_rate"
                data[rate_key] = None
                previous = self._previous.get(key)
                if (
                    counter is not None
                    and previous is not None
                    and elapsed
                    and elapsed > 0
                ):
                    old_counter, old_time = previous
                    delta_time = now - old_time
                    if delta_time > 0 and counter >= old_counter:
                        data[rate_key] = (counter - old_counter) / delta_time
                if counter is not None:
                    self._previous[key] = (float(counter), now)
        self._last_sample = now
        return data

    async def async_validate(self) -> bool:
        """Validate device credentials before saving the config entry."""
        return await self.client.async_validate()

    async def terminate(self) -> None:
        """Stop scheduled refreshes and close the HTTP session."""
        await self.async_shutdown()
        await self.client.async_close()
