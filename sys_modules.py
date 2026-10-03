"""Fake versions of the device-only modules a badgeware app might import
(`network`, `wifi`, `ntptime`, `badgeware`, `urequests`), installed into
sys.modules before the app source is exec'd - the same trick
badgeware.launch() does on the real device, just with stand-ins instead of
firmware.

`urequests.get()` uses the real `requests` library, so an app that fetches
from a real HTTP endpoint can exercise that actual path (not just a mock) -
the dev machine's network is typically far more reliable than the badge's.

A shared `online` flag (toggled from the web UI) controls whether
network/wifi report connected and whether urequests actually attempts a
request at all, so both the "online" and "offline" code paths in an app
can be exercised on demand.
"""

import json
import os

import requests as _real_requests

# Defaults to a directory next to the emulator tool itself, but server.py
# points this at a directory alongside whichever app's __init__.py is being
# run (via set_state_dir()) - state should travel with the app being
# emulated, not get shared/collide across different projects using this
# same emulator checkout.
STATE_DIR = os.path.join(os.path.dirname(__file__), "state")


def set_state_dir(path):
    global STATE_DIR
    STATE_DIR = path


class _SharedConnectivity:
    online = True  # start connected; toggle via the web UI


connectivity = _SharedConnectivity()


# ---------------------------------------------------------------------------
# network
# ---------------------------------------------------------------------------

class _FakeWLAN:
    def __init__(self, interface):
        self.interface = interface

    def isconnected(self):
        return connectivity.online

    def active(self):
        return True


class _NetworkModule:
    STA_IF = 0
    WLAN = _FakeWLAN


network_module = _NetworkModule()


# ---------------------------------------------------------------------------
# wifi
# ---------------------------------------------------------------------------

class _WifiModule:
    def __init__(self):
        self.wlan = None

    def is_connected(self):
        if connectivity.online:
            self.wlan = _FakeWLAN(0)
        return connectivity.online

    def connect(self):
        self.wlan = _FakeWLAN(0)

    def tick(self):
        pass


wifi_module = _WifiModule()


# ---------------------------------------------------------------------------
# ntptime - desktop system clock is already correct, so settime() is a
# no-op that just "succeeds", letting the app's own NTP-sync-tracking
# logic (_time_synced) behave as if a real sync happened.
# ---------------------------------------------------------------------------

class _NtptimeModule:
    def settime(self):
        if not connectivity.online:
            raise OSError("emulated: offline")


ntptime_module = _NtptimeModule()


# ---------------------------------------------------------------------------
# badgeware.State - persists to emulator/state/<name>.json so toggles
# (e.g. BUTTON_A's animations_enabled) survive an emulator restart, same
# as the real device persisting to /state/<name>.json.
# ---------------------------------------------------------------------------

class _State:
    @staticmethod
    def _path(name):
        os.makedirs(STATE_DIR, exist_ok=True)
        return os.path.join(STATE_DIR, name + ".json")

    @staticmethod
    def load(name, default_dict):
        try:
            with open(_State._path(name)) as f:
                saved = json.load(f)
            default_dict.update(saved)
        except (OSError, ValueError):
            pass

    @staticmethod
    def modify(name, partial_dict):
        current = {}
        try:
            with open(_State._path(name)) as f:
                current = json.load(f)
        except (OSError, ValueError):
            pass
        current.update(partial_dict)
        with open(_State._path(name), "w") as f:
            json.dump(current, f)


class _BadgewareModule:
    State = _State


badgeware_module = _BadgewareModule()


# ---------------------------------------------------------------------------
# urequests - real HTTP via `requests`, gated on the same online flag so
# toggling offline in the UI actually simulates no connectivity rather than
# just an app-level flag mismatch.
# ---------------------------------------------------------------------------

class _Response:
    def __init__(self, real_resp):
        self._real_resp = real_resp
        self.status_code = real_resp.status_code

    def json(self):
        return self._real_resp.json()

    def close(self):
        self._real_resp.close()


class _UrequestsModule:
    @staticmethod
    def get(url, timeout=10, **kwargs):
        if not connectivity.online:
            raise OSError("emulated: offline, no route to host")
        return _Response(_real_requests.get(url, timeout=timeout))


urequests_module = _UrequestsModule()


def install():
    """Registers the fakes into sys.modules so `import network` etc. in
    the app source resolve to these instead of erroring (desktop Python
    has no such modules for real)."""
    import sys

    sys.modules["network"] = network_module
    sys.modules["wifi"] = wifi_module
    sys.modules["ntptime"] = ntptime_module
    sys.modules["badgeware"] = badgeware_module
    sys.modules["urequests"] = urequests_module
