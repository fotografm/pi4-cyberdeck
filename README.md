# pi4-cyberdeck

> **Legal and ethical notice**
>
> This project was built for personal research — specifically to monitor and
> understand the radio behaviour of my own fixed and mobile devices, learn how
> 802.11 and ISM radio protocols work in practice, and identify what information
> my own equipment broadcasts passively.
>
> I do not advocate using this software to monitor devices you do not own or
> for which you do not have explicit permission from the owner. Passive radio
> monitoring laws vary significantly by country and jurisdiction. In many places
> capturing and storing radio transmissions from third-party devices — even
> passively — may be restricted or prohibited without consent.
>
> **Check the laws in your jurisdiction before deploying this software.**
>
> The author accepts no responsibility for the actions of anyone who uses this
> software. By using it you accept full responsibility for ensuring your use is
> lawful and ethical.

---

A passive radio monitoring platform for Raspberry Pi 4B. Captures and analyses
802.11 WiFi frames, ISM band radio signals (433/868/315 MHz), wideband SDR
signals via a waterfall receiver, and GPS data. Runs completely headless — the
Pi serves its own browser-based UI over a WiFi hotspot. No cloud, no external
services, no display required.

---

## What it does

### WiFi monitoring
The system places a USB WiFi adapter (MT7612U AC1300) in monitor mode and
captures all 802.11 frames in range across all channels. It passively
collects:

- **Access points** — every AP detected, with SSID, BSSID, encryption type,
  channel, signal strength, GPS coordinates, first/last seen timestamps
- **Client associations** — which devices are connecting to which APs, using
  DS bit analysis of data frames to determine direction
- **Probe requests** — directed probes reveal which networks a device has
  previously joined, even when the device uses MAC address randomisation
- **Device fingerprints** — a SHA-256 hash of the 802.11 Information Elements
  in each probe request (IE IDs, HT/VHT capability bytes, vendor OUIs) creates
  a stable fingerprint that identifies the same physical device across MAC
  rotation

### ISM radio monitoring
An RTL-SDR dongle feeds raw IQ samples into rtl_433, which decodes hundreds of
device types broadcasting on 433 MHz, 868 MHz and 315 MHz. This includes
weather stations, TPMS tyre pressure sensors, remote controls, smart meters,
door bells and many other devices. Decoded signals are displayed in a live feed
with GPS tagging and plotted on a map.

### SDR waterfall receiver (FerroSDR)
A wideband software-defined radio receiver with a browser-based waterfall
display. Tune to any frequency, adjust bandwidth and gain, and watch signals
appear in real time. Frequency presets can be saved and recalled. FerroSDR and
the ISM monitor share the RTL-SDR dongle and cannot run simultaneously — use
the Services page to switch between them.

### GPS
A u-blox USB GPS receiver provides real-time position for geotagging all WiFi
sightings and ISM signals. A 3D satellite skymap shows satellite positions and
signal strengths. All sightings stored with GPS coordinates are displayed on
interactive Leaflet maps with tile caching for offline use.

When a GPS fix is acquired the ISM monitor also uses the GPS UTC timestamp to
synchronise the OS clock (via `sudo date -s`). This keeps the system clock
accurate without NTP — the device is designed for offline use in the field.
The sync runs at most every 5 minutes and only when the observed drift exceeds
5 seconds. All timestamps stored in the databases and displayed in the UI are
in UTC.

### WiFi history
A separate passive sniffer records probe requests into a history database with
device fingerprinting. The history section shows directed SSIDs (networks
devices are searching for), device fingerprint profiles, association frames,
and per-device probe history — all useful for understanding which devices have
been in range and which networks they have previously connected to.

---

## Hardware

| Component | Value |
|---|---|
| Host | Raspberry Pi 4B 4GB |
| Hotspot | Onboard BCM43455 (wlan0) |
| WiFi monitor | MT7612U USB dongle (wlan1) |
| ISM radio / SDR | RTL-SDR Blog V3 dongle |
| GPS | Geekstory G72 u-blox M8130 |
| Ethernet | Optional (for setup and internet passthrough) |

### MT7612U WiFi adapter

The Mediatek MT7612U is a dual-band AC1300 USB adapter. It is well supported
in mainline Linux via the `mt76x2u` driver with no firmware files needed. It
supports monitor mode natively. The adapter must be set unmanaged in
NetworkManager so that NetworkManager never takes it out of monitor mode or
changes its channel.

### RTL-SDR dongle

Any RTL2832U based SDR dongle will work. The RTL-SDR Blog V3 has better
sensitivity and an improved oscillator. The dongle is shared between the ISM
monitor (rtl_433) and FerroSDR — only one can use it at a time. Use the
Services page to stop one before starting the other.

### GPS receiver

The Geekstory G72 uses a u-blox UBX-M8130 chip with 72 channels supporting
GPS, GLONASS, BeiDou and QZSS. It communicates at 9600 baud over USB CDC-ACM
(`/dev/ttyACM0`). The device has no backup battery — it does a full cold start
whenever power is removed, which takes 30-60 seconds to acquire a fix in good
conditions.

**Important:** The ceramic patch antenna on the G72 must face skyward. The
flat side of the dongle must point up. Installing it upside down results in
severely degraded GPS performance with weak or no satellite reception.

---

## Architecture

### Hotspot-first design

The Pi serves its UI over a WiFi hotspot (wlan0) rather than relying on an
existing network. This makes the system completely self-contained and portable
— connect your laptop or phone directly to the Pi's hotspot and access the UI
at `http://10.42.0.1`. The Pi also works on an existing Ethernet network
(accessible by its Ethernet IP) but the hotspot is always available regardless
of network infrastructure.

Hotspot clients get internet access via NAT masquerade over Ethernet when an
Ethernet cable is plugged in (configured by `config/nftables.conf`).

### 5 GHz hotspot and DFS

The hotspot is configured on channel 100 (5500 MHz) with 80 MHz width. This
band (5470–5725 MHz) is approved for outdoor use in Germany and across the EU
under ETSI EN 301 893 V2.1.1 and Commission Implementing Decision (EU)
2021/1067.

Radar detection (DFS) and Transmit Power Control (TPC) are mandatory for this
band under:

- **ETSI EN 301 893 V2.1.1** — the harmonised EU standard for 5 GHz WLANs,
  which defines DFS and TPC as mandatory requirements for the 5470–5725 MHz
  range
- **Commission Implementing Decision (EU) 2021/1067** — the EU radio spectrum
  decision that designates 5470–5725 MHz for outdoor WLANs subject to DFS+TPC
- **BNetzA Vfg. 17/2021** — the German Federal Network Agency implementation
  confirming outdoor use of this band is permitted under the above conditions

On boot, hostapd performs a 60-second radar scan before activating the AP.
This is normal — the hotspot will appear approximately 60 seconds after boot.
The `ieee80211d=1` and `ieee80211h=1` flags in `config/hostapd.conf` enable
these mandatory features.

### Port layout

| Port | Service | Technology |
|---|---|---|
| 80 | Landing page | aiohttp |
| 8080 | FerroSDR waterfall receiver | FerroSDR (Rust binary) |
| 8091 | WiFi web (APs, channels, map) | Flask |
| 8092 | ISM monitor (live feed, map) | aiohttp + WebSocket |
| 8093 | GPS dashboard | Flask |
| 8094 | 3D satellite skymap | Flask |
| 8095 | WiFi history | aiohttp |
| 8096 | Browser terminal | aiohttp + PTY WebSocket |
| 8097 | Notes | aiohttp |
| 8098 | Services control | aiohttp |

### Database file ownership

Some services (`wifi_scanner`, `wifi_history_monitor`) run as `root` because
they need to put the WiFi adapter in monitor mode. They create the SQLite
database files, which therefore end up owned by `root`. The web services that
read those databases run as `user` and need write access for SQLite WAL mode
(even read-only queries require write access to the `-shm` file).

All `User=user` services that open a database have an `ExecStartPre` step that
fixes ownership before the Python process starts:

```ini
ExecStartPre=+-/bin/bash -c 'chown user:user /path/to/db* 2>/dev/null'
```

The `+` prefix tells systemd to run that specific step with full root
privileges regardless of the service's `User=` setting. The `-` prefix
suppresses failure (e.g. if the files do not exist yet on first boot). Without
the `+` the chown runs as `user` and silently fails on root-owned files,
causing Python to crash with `sqlite3.OperationalError: attempt to write a
readonly database`.

### Database design

Four SQLite databases store data independently:

**wifi_logger.db** — Core WiFi scanner data
- `access_points` — one row per BSSID, updated on every beacon
- `sightings` — GPS-tagged sightings of each AP, throttled to avoid redundant writes
- `associations` — 802.11 association and authentication frames
- `client_sightings` — data-frame derived client↔AP relationships

**wifi_history.db** — Probe request history
- `probe_requests` — every directed probe request with source MAC and SSID
- `ie_fingerprints` — one fingerprint per unique IE profile
- `mac_fp_map` — maps each MAC to its fingerprint (handles MAC rotation)
- `beacons` — beacon frame records from the history monitor
- `associations` — association frames from the history monitor

**ism_monitor.db** — ISM signal data
- `signals` — every decoded rtl_433 signal with model, device ID, data, GPS
- `transmitters` — aggregated per-device statistics

**gps_history.db** — GPS satellite history
- `sat_history` — per-satellite azimuth, elevation and signal strength over time

All databases use WAL journal mode for concurrent read performance. They can
be cleared individually from the Services page — each is reinitialised with
empty tables immediately after clearing so services continue without errors.

### WiFi frame capture

`wifi_scanner.py` uses Scapy to capture raw 802.11 frames on the monitor
interface. It handles three frame classes:

**Beacon frames (management subtype 8) and Probe responses (subtype 5):**
These are the primary source of AP data. Each frame is parsed for SSID, BSSID,
encryption (WEP/WPA/WPA2/WPA3 via RSN IE and WPA vendor IE parsing), channel
(from the DS Parameter Set IE), frequency, and 802.11 capability flags.
Signal strength comes from the RadioTap header. GPS position is sampled at
capture time and written with each sighting.

**Association frames (management subtypes 0, 1, 2, 3, 11):**
Association request, response, reassociation request/response and
authentication frames explicitly reveal client MAC to AP BSSID relationships.
These are rate-limited to one write per (client, bssid, subtype) combination
per 5 seconds to avoid database flooding during repeated auth attempts.

**Data frames (type 2):**
Every data frame passing between a client and its AP contains both MACs. The
DS bits in the Frame Control field reveal direction: ToDS=1/FromDS=0 means
client→AP (addr2=client, addr1=BSSID), ToDS=0/FromDS=1 means AP→client
(addr1=client, addr2=BSSID). This is the most reliable method for building a
continuous picture of which clients are actively associated with which APs.
Channel is read from the RadioTap header rather than walking the IE chain
(data frames have no IEs). Rate limited to one write per (client, bssid) per
30 seconds.

A channel hopper runs in a separate thread, stepping through all 2.4 GHz
and 5 GHz channels with configurable dwell time. The scanner uses thread-local
SQLite connections to avoid locking issues.

### Device fingerprinting

The `ie_parser.py` module extracts 802.11 Information Elements from probe
request frames and computes a SHA-256 fingerprint from:

1. The sorted set of IE IDs present in the frame (identifies which
   capabilities the device advertises)
2. The raw bytes of the HT Capabilities IE (ID 45) — 26 bytes encoding
   802.11n radio capabilities specific to the chipset
3. The raw bytes of the VHT Capabilities IE (ID 191) — 12 bytes encoding
   802.11ac capabilities, only present on 5 GHz capable devices
4. The sorted list of vendor OUIs from Vendor Specific IEs (ID 221) —
   identifies proprietary extensions like Apple AWDL, Microsoft WMM, Wi-Fi
   Alliance P2P

This combination produces a hash that is stable across MAC address rotation
because none of these elements contain the MAC address. Two probe requests
from the same physical device with different randomised MACs produce identical
hashes as long as the driver version has not changed. The fingerprint changes
only when firmware is updated.

### GPS time synchronisation

The Pi 4 has no battery-backed hardware RTC. On boot the system time is
restored from `fake-hwclock` (a file written to disk every 30 minutes and on
clean shutdown), then corrected by GPS once a fix is acquired.

NTP is intentionally disabled (`timedatectl set-ntp false`) because the device
operates offline in the field. The ISM monitor (`ism_monitor.py`) takes
responsibility for clock discipline:

- Every time `gps_reader_async.py` delivers a position update with `fix=True`,
  `_on_gps_update()` checks whether a sync is due (throttled to once per 5
  minutes, skipped if drift < 5 s).
- `_sync_time_from_gps()` parses the GPS UTC timestamp, computes drift against
  `time.time()`, then calls `sudo date -s "@<unix_epoch>"`. Using the epoch
  form avoids timezone and locale issues.
- The sudoers drop-in `/etc/sudoers.d/raspi83-date` grants the `user` account
  passwordless `sudo date -s` permission.

The GPS reader (`gps_reader_async.py`) exposes a `gps_time` field populated
from the `time` key of gpsd TPV messages. Only fields explicitly present in
each TPV message update the reader's state — `msg.get("lat")` was replaced
with `if "lat" in msg` guards throughout, because gpsd can emit mode=2 TPV
messages that omit lat/lon during fix transitions, and the old code silently
clobbered valid coordinates with `None`.

### ISM monitor watchdog

`ism_monitor.py` includes a watchdog coroutine that monitors rtl_433 output.
If no signal is received for 5 minutes (with a 2 minute grace period at
startup) the watchdog kills and restarts the rtl_433 process. This handles
the case where the RTL-SDR USB device hangs with the device claimed but
producing no data — a condition that occurs occasionally with RTL-SDR dongles
under sustained use.

---

## Initial setup

### Flash and configure the Pi

Use **Raspberry Pi Imager** to flash **Raspberry Pi OS Bookworm Lite (64-bit)**
for Pi 4B. In the Imager settings:

- Set hostname (e.g. `pi4-cyberdeck`)
- Enable SSH with a password or public key
- Set your WiFi credentials for initial internet access
- Set WiFi country to your country code (e.g. `DE` for Germany)

Do not create a manual `wpa_supplicant.conf` or empty `ssh` file — these are
obsolete in Bookworm. Use the Imager settings form only.

### SSH in and update

```
ssh user@<ip-address>
sudo apt update && sudo apt upgrade -y
```

### Clone and install

```
git clone https://github.com/fotografm/pi4-cyberdeck.git
cd pi4-cyberdeck
sudo bash install.sh
```

The install script will:
1. Install system packages (`gpsd`, `rtl-433`, `iw`, `rfkill`, `sqlite3`)
2. Create the deployment directory and copy all files
3. Create a Python venv and install dependencies
4. Download the IEEE OUI database for vendor lookup
5. Initialise all SQLite databases
6. Configure gpsd to use `/dev/ttyACM0`
7. Mark wlan1 as unmanaged in NetworkManager
8. Install and enable all systemd services

After install:
```
sudo systemctl start rfkill-unblock ism-wifi-landing ism-wifi-gps \
  ism-wifi-ism ism-wifi-skymap3d ism-wifi-wifi-scan ism-wifi-wifi-web \
  ism-wifi-history-monitor ism-wifi-history-web \
  ism-wifi-terminal ism-wifi-notes ism-wifi-services
sudo reboot
```

### Configure the hotspot

The `config/hostapd.conf` in this repo is the reference hostapd configuration
for the 5 GHz hotspot. If hostapd is not already configured on your Pi:

```
sudo cp config/hostapd.conf /etc/hostapd/hostapd.conf
sudo systemctl enable hostapd
sudo reboot
```

The SSID defaults to `raspi83` — edit the file to match your hostname before
copying. The default password is `password`.

### Configure internet passthrough (optional)

If you want hotspot clients to share the Pi's Ethernet internet connection:

```
sudo cp config/nftables.conf /etc/nftables.conf
echo "net.ipv4.ip_forward=1" | sudo tee -a /etc/sysctl.conf
sudo sysctl -p
sudo systemctl enable nftables
sudo systemctl start nftables
```

### Install FerroSDR (optional)

FerroSDR is a Rust-based wideband SDR waterfall receiver. The pre-built static
binary for Pi 4B (ARM 32-bit musl) can be deployed manually:

```
sudo systemctl stop ism-wifi-ism
cp ferrosdr /home/user/ism-wifi-monitor/ferrosdr
chmod +x /home/user/ism-wifi-monitor/ferrosdr
cp profiles.json /home/user/ism-wifi-monitor/profiles.json
sudo cp systemd/ferrosdr.service /etc/systemd/system/
sudo cp systemd/ferrosdr-watchdog.service /etc/systemd/system/
sudo cp systemd/ferrosdr-watchdog.timer /etc/systemd/system/
sudo cp systemd/99-rtlsdr-power.rules /etc/udev/rules.d/
sudo udevadm control --reload-rules
sudo systemctl daemon-reload
sudo systemctl enable ferrosdr ferrosdr-watchdog.timer
```

FerroSDR and the ISM monitor (`ism-wifi-ism`) share the RTL-SDR dongle and
have a systemd `Conflicts=` relationship — starting one will stop the other.
Use the Services page at port 8098 to switch between them.

### Access the UI

Connect your device to the hotspot (SSID = Pi hostname, e.g. `pi4-cyberdeck`).
Password: `password`

> **Change the default password** before deploying in any environment where
> unauthorised access would be a concern:
> ```
> sudo nano /etc/hostapd/hostapd.conf   # edit wpa_passphrase=
> sudo systemctl restart hostapd
> ```
> Also update `config/hostapd.conf` in this repo to match.

Open `http://10.42.0.1` in your browser.

If accessing over Ethernet, use the Pi's Ethernet IP address instead.

---

## Time and timezone

All timestamps are stored and displayed in **UTC**. NTP is disabled; the GPS
receiver is the sole time reference. The ISM monitor syncs the OS clock from
GPS UTC every 5 minutes when a fix is held. On boot, `fake-hwclock` provides
an approximate starting time until GPS corrects it (typically within 1–5
minutes outdoors).

All web pages that display timestamps show an **ALL TIMES UTC** label in the
topbar.

## GPS notes

The G72 receiver has no backup battery. Every time USB power is removed it
loses its almanac and ephemeris data and must do a full cold start. Cold start
time is typically 30-60 seconds outdoors with clear sky view. After a cold
start it may take 5-15 minutes for the full almanac to download, during which
satellite count will be low.

If the receiver is not getting a fix:

1. **Check antenna orientation** — the flat ceramic patch must face skyward
2. **Check gpsd config** — `/etc/default/gpsd` must have `DEVICES="/dev/ttyACM0"`
3. **Force a cold start** — `sudo ubxtool -p COLDSTART`
4. **Check raw output** — `sudo systemctl stop gpsd && sudo timeout 10 cat /dev/ttyACM0`
   should show NMEA sentences. `ANTSTATUS=OK` confirms the antenna is connected.

The GPS dashboard is at `http://<ip>:8093`. The 3D skymap is at port 8094.

---

## RTL-SDR notes

The ISM monitor uses `rtl_433` with a 5-minute watchdog. Signals are decoded
from 433 MHz, 868 MHz and 315 MHz and displayed in a live WebSocket feed.
Decoded device types include weather stations, TPMS sensors, remote controls
and many others — see the rtl_433 documentation for the full device list.

If the RTL-SDR is not connected the ISM services will fail silently. Stop them
from the Services page at port 8098 to avoid log spam.

The RTL-SDR dongle is shared between the ISM monitor and FerroSDR. Only one
can hold the device at a time. Use the Services page to stop one before
starting the other.

---

## FerroSDR notes

FerroSDR listens on port 8080 and serves a browser-based waterfall display.
Tune by clicking the frequency bar or entering a value directly. Frequency
presets (profiles) are saved to `profiles.json` in the deploy directory.

The FerroSDR USB watchdog (`ferrosdr-watchdog.timer`) monitors the service
and automatically restarts it if the RTL-SDR USB device becomes unresponsive.
This runs independently in the background and does not need manual management.

---

## Services page

The Services page at `http://<ip>:8098` provides:

- **Real-time service status** — live systemd status with green/red indicators
  polling every 5 seconds. A crashed service shows red immediately.
- **Start/Stop buttons** — start or stop individual services without SSH
- **Database management** — shows current row counts and file sizes for all
  four databases. Each database has a Clear button with a confirmation step.
  Clearing a database reinitialises it with empty tables immediately so
  services continue without errors.

---

## Customisation

### Changing the hotspot SSID and password

Edit `/etc/hostapd/hostapd.conf` and restart hostapd:
```
sudo nano /etc/hostapd/hostapd.conf
sudo systemctl restart hostapd
```

### Changing the monitor interface

If the MT7612U enumerates as something other than `wlan1`, update
`/home/user/ism-wifi-monitor/config.py`:

```
WIFI_IFACE = 'wlan2'  # or whatever iw dev shows
```

Then update the NM unmanaged config:
```
sudo bash -c 'echo "[keyfile]
unmanaged-devices=interface-name:wlan2" > /etc/NetworkManager/conf.d/99-ism-wifi-unmanaged.conf'
sudo systemctl reload NetworkManager
sudo systemctl restart ism-wifi-wifi-scan ism-wifi-history-monitor
```

### Adjusting channel dwell time

In `config.py`, `CHANNEL_DWELL` controls how long the scanner stays on each
channel before hopping. The default is 0.3 seconds. Increase this to capture
more frames per channel at the cost of slower full-spectrum coverage.

### Tile caching

The WiFi map and GPS map use OpenStreetMap tiles. Tiles are cached locally
in `~/ism-wifi-monitor/tile_cache/` after first access. The ISM settings page
has a tile pre-cache function to download tiles for your area in advance for
offline use.

---

## Troubleshooting

### Services not starting

Check the journal:
```
sudo journalctl -u ism-wifi-wifi-scan --since "5 min ago" --no-pager
```

Common causes:
- `RTNETLINK: Operation not possible due to RF-kill` — run `sudo rfkill unblock all`
- `name '_parse_ssid' is not defined` — redeploy `wifi_scanner.py` from the repo
- `no such table: associations` — the database was not initialised, run
  `python3 db_wifi.py` from the venv

### Hotspot not appearing after reboot

The 5 GHz hotspot (channel 100) performs a mandatory 60-second DFS radar scan
before activating. This is normal — wait 60–90 seconds after boot before
expecting the SSID to appear.

### GPS not working

- Check `sudo gpspipe -w -n 5` — if it hangs, gpsd is not connected to the device
- Check `/etc/default/gpsd` has `DEVICES="/dev/ttyACM0"` not `DEVICES=""`
- Check `sudo dmesg | grep ttyACM` confirms the device is present
- Check antenna orientation — flat side must face up

### WiFi scanner not seeing APs

- Check `iw dev` shows wlan1 in monitor mode
- Check `sudo systemctl status ism-wifi-wifi-scan` for errors

### Database files owned by root / `attempt to write a readonly database`

After a fresh install or a manual database reset run as root, the SQLite files
may be owned by `root:root`. The web services run as `user` and cannot write
to them. The `ExecStartPre=+-chown` step in each service unit fixes this on
every startup — if it is failing for some reason, fix manually:

```
sudo chown user:user ~/ism-wifi-monitor/db/*.db ~/ism-wifi-monitor/db/*.db-* 2>/dev/null
sudo systemctl restart ism-wifi-ism ism-wifi-gps ism-wifi-wifi-web ism-wifi-history-web
```

### Terminal not connecting on mobile browsers

The browser terminal uses a WebSocket to the PTY server on port 8096. Some
mobile browsers (and browsers accessed over HTTPS) drop idle WebSocket
connections aggressively. The PTY server sends a WebSocket ping every 30
seconds (`WebSocketResponse(heartbeat=30)`) to keep the connection alive. If
the terminal shows "connecting" and never connects, check that
`ism-wifi-terminal.service` is active and that port 8096 is reachable.

### Web UI not loading

- Check the relevant service: `sudo systemctl status ism-wifi-landing`
- Check the venv exists: `ls ~/ism-wifi-monitor/venv/bin/python`
- Check port conflicts: `sudo ss -tlnp | grep <port>`

---

## File structure

```
pi4-cyberdeck/
├── config.py                   # All configuration constants
├── db_wifi.py                  # WiFi database schema + init
├── db_history.py               # WiFi history database schema + init
├── db_ism.py                   # ISM database schema + init
├── gps_reader_async.py         # Async gpsd client
├── gps_reader_sync.py          # Sync gpsd client (for scanner thread)
├── ie_parser.py                # 802.11 IE parser + SHA-256 fingerprinting
├── oui.py                      # IEEE OUI vendor lookup
├── wifi_scanner.py             # Main WiFi frame capture (runs as root)
├── wifi_web.py                 # Flask WiFi web server (port 8091)
├── wifi_history_monitor.py     # Passive probe request recorder (runs as root)
├── wifi_history_web.py         # WiFi history aiohttp server (port 8095)
├── ism_monitor.py              # ISM monitor + rtl_433 wrapper (port 8092)
├── gps_web.py                  # GPS dashboard Flask server (port 8093)
├── skymap3d.py                 # 3D satellite skymap Flask server (port 8094)
├── landing_server.py           # Landing page aiohttp server (port 80)
├── terminal_server.py          # PTY terminal aiohttp server (port 8096)
├── notes_server.py             # Notes aiohttp REST server (port 8097)
├── services_server.py          # Services control aiohttp server (port 8098)
├── raspi-style.css             # Shared dark theme stylesheet
├── install.sh                  # Installer for Pi 4B
├── config/
│   ├── hostapd.conf            # 5 GHz hotspot configuration (channel 100, DFS)
│   └── nftables.conf           # NAT masquerade for hotspot internet passthrough
├── data/
│   └── oui.csv                 # IEEE OUI vendor database
├── templates/                  # Jinja2 / standalone HTML templates
│   ├── landing.html
│   ├── wifi_index.html         # Channel usage dashboard
│   ├── wifi_aps.html           # Sortable AP list
│   ├── wifi_ap_detail.html     # Per-AP detail with clients and map
│   ├── wifi_map.html           # Leaflet AP map
│   ├── ism_feed.html           # Live ISM signal feed
│   ├── ism_map.html            # ISM transmitter map
│   ├── ism_settings.html       # ISM settings + tile cache + service status
│   ├── history_base.html       # Shared history page base template
│   ├── history_index.html      # Recent probe requests
│   ├── history_ssids.html      # Directed SSID list with device chips
│   ├── history_devices.html    # Device fingerprint list
│   ├── history_device_detail.html
│   ├── history_aps.html        # Beacon-derived AP history
│   ├── history_associations.html
│   ├── history_probes.html
│   ├── terminal.html           # xterm.js browser terminal
│   ├── notes.html              # Two-panel notes app
│   └── services.html           # Services control panel
└── systemd/                    # systemd service unit files
    ├── rfkill-unblock.service
    ├── ism-wifi-landing.service
    ├── ism-wifi-wifi-scan.service
    ├── ism-wifi-wifi-web.service
    ├── ism-wifi-history-monitor.service
    ├── ism-wifi-history-web.service
    ├── ism-wifi-ism.service
    ├── ism-wifi-skymap3d.service
    ├── ism-wifi-gps.service
    ├── ism-wifi-terminal.service
    ├── ism-wifi-notes.service
    ├── ism-wifi-services.service
    ├── ferrosdr.service         # FerroSDR waterfall receiver (port 8080)
    ├── ferrosdr-watchdog.service
    ├── ferrosdr-watchdog.timer
    └── 99-rtlsdr-power.rules   # udev rule for RTL-SDR USB power management
```

Note: The `ferrosdr` binary and `profiles.json` are deployed to
`/home/user/ism-wifi-monitor/` separately and are not tracked in this repo.

---

## Dependencies

Python packages (installed in venv):

| Package | Use |
|---|---|
| aiohttp | Async HTTP/WebSocket servers |
| flask | Synchronous web routes |
| scapy | Raw 802.11 packet capture |
| manuf | OUI vendor lookup (fallback) |
| aiofiles | Async file I/O |

System packages:

| Package | Use |
|---|---|
| gpsd, gpsd-clients | GPS daemon and tools |
| rtl-433 | ISM signal decoder |
| iw | WiFi interface control |
| rfkill | Radio kill switch control |
| sqlite3 | Database CLI |

---

## Colour scheme

All pages use a consistent dark theme defined in `raspi-style.css`:

| Variable | Value | Use |
|---|---|---|
| `--bg` | `#080818` | Page background |
| `--panel` | `#0d0d20` | Card/panel background |
| `--border` | `#4a4a8a` | Panel borders |
| `--text` | `#f0f0ff` | Body text |
| `--heading` | `#8888cc` | Section headings |
| `--value-green` | `#88ee88` | Positive values, good signal |
| `--value-warn` | `#ddaa44` | Warning values |
| `--value-alert` | `#ff6666` | Alert/error values |
| `--muted` | `#aaaadd` | Secondary text |
| `--dim` | `#7878aa` | Tertiary text |

Text is never darker than `#777799` to ensure readability on the dark background.

---

## Licence

MIT — see LICENSE file.
