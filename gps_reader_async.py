"""
gps_reader_async.py  —  raspi81 ism-wifi-monitor
Async gpsd client.  Used by ism_monitor.py.
Hot-plug safe: if gpsd is unreachable or no device is present,
status returns NO_GPS / NO_FIX without raising exceptions.
"""

import asyncio
import json
import logging

GPSD_HOST = "127.0.0.1"
GPSD_PORT = 2947
RECONNECT_DELAY = 5.0
READ_TIMEOUT    = 65.0   # gpsd sends keep-alive every 60s

log = logging.getLogger("gps")


class GpsReader:
    def __init__(self) -> None:
        self.lat:      float | None = None
        self.lon:      float | None = None
        self.alt:      float | None = None
        self.speed:    float | None = None
        self.mode:     int          = 0
        self.gps_time: str | None   = None
        self.sats_visible: int      = 0
        self.sats_used:    int      = 0
        self.hdop:     float | None = None
        self._has_device: bool      = False
        self._cb = None

    def set_callback(self, coro) -> None:
        self._cb = coro

    @property
    def fix(self) -> bool:
        return self.mode >= 2 and self.lat is not None and self.lon is not None

    @property
    def status(self) -> str:
        if not self._has_device:
            return "NO_GPS"
        if not self.fix:
            return "NO_FIX"
        return "FIX"

    def position(self) -> dict:
        return {
            "lat":          self.lat,
            "lon":          self.lon,
            "alt":          self.alt,
            "speed":        self.speed,
            "fix":          self.fix,
            "status":       self.status,
            "gps_time":     self.gps_time,
            "sats_visible": self.sats_visible,
            "sats_used":    self.sats_used,
            "hdop":         self.hdop,
        }

    async def run(self) -> None:
        while True:
            try:
                await self._connect_and_read()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.debug("gpsd connection lost: %s", exc)
                self.mode = 0
                self._has_device = False
                await self._notify()
            await asyncio.sleep(RECONNECT_DELAY)

    async def _connect_and_read(self) -> None:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(GPSD_HOST, GPSD_PORT),
            timeout=3.0,
        )
        log.info("Connected to gpsd")
        try:
            writer.write(b'?WATCH={"enable":true,"json":true}\n')
            await writer.drain()
            while True:
                line = await asyncio.wait_for(reader.readline(), timeout=READ_TIMEOUT)
                if not line:
                    return
                self._parse(line.decode("utf-8", errors="replace").strip())
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

    def _parse(self, line: str) -> None:
        if not line:
            return
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            return

        cls = msg.get("class")

        if cls == "DEVICES":
            devices = msg.get("devices", [])
            self._has_device = bool(devices)
            if not self._has_device:
                self.mode = 0
                self.lat = self.lon = None
            asyncio.ensure_future(self._notify())

        elif cls == "TPV":
            self.mode = msg.get("mode", 0)
            if self.mode >= 2:
                self._has_device = True
                # Only overwrite a field when the key is present in this message.
                # gpsd can send mode=2 TPVs that omit lat/lon during fix transitions;
                # using msg.get() would silently clobber valid coordinates with None.
                if "lat"   in msg: self.lat      = msg["lat"]
                if "lon"   in msg: self.lon      = msg["lon"]
                if "alt"   in msg: self.alt      = msg["alt"]
                if "speed" in msg: self.speed    = msg["speed"]
                if "time"  in msg: self.gps_time = msg["time"]
            else:
                self.lat = self.lon = self.gps_time = None
            asyncio.ensure_future(self._notify())

        elif cls == "SKY":
            sats = msg.get("satellites", [])
            self.sats_visible = len(sats)
            self.sats_used    = sum(1 for s in sats if s.get("used"))
            self.hdop         = msg.get("hdop")
            asyncio.ensure_future(self._notify())

    async def _notify(self) -> None:
        if self._cb is not None:
            try:
                await self._cb(self.position())
            except Exception as exc:
                log.debug("GPS callback error: %s", exc)
