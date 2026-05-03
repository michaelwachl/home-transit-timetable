# home-transit-timetable

A local web app for Raspberry Pi that shows real-time public transport departures (MVG Munich) and today's weather forecast — designed to sit on a small screen near your door.

## Features

- Real-time MVG departures with live delay info (U-Bahn, S-Bahn, Tram, Bus)
- Current weather + hourly forecast via Open-Meteo (no API key needed)
- Configurable refresh interval, stop filter, and location
- Dark / light theme
- Responsive layout — works on any screen size

## Setup

```bash
# Clone and install
git clone https://github.com/michaelwachl/home-transit-timetable
cd home-transit-timetable
pip3 install -r requirements.txt

# Configure your stops and location
nano config.yaml

# Run
./start.sh
# → open http://localhost:8080
```

## Configuration (`config.yaml`)

```yaml
transit:
  stops:
    - global_id: "de:09162:70"   # Candidplatz
      name: "Candidplatz"
      lines: []                  # empty = all lines; or e.g. ["U3", "U6"]
      max_departures: 8

weather:
  latitude: 48.1197
  longitude: 11.5756
  location_name: "Candidplatz, München"

display:
  refresh_interval: 60   # seconds
  theme: "dark"           # "dark" or "light"
  title: "Home Transit"
```

### Finding your stop ID

```
http://localhost:8080/api/stops/search?q=Candidplatz
```

Returns the `global_id` to put in `config.yaml`.

## Raspberry Pi display (kiosk mode)

```bash
# Install Chromium
sudo apt install chromium-browser

# Start in kiosk mode (add to /etc/rc.local or a systemd service)
chromium-browser --kiosk --noerrdialogs --disable-infobars http://localhost:8080
```

### Systemd service

```ini
# /etc/systemd/system/transit-board.service
[Unit]
Description=Home Transit Board
After=network-online.target

[Service]
WorkingDirectory=/home/pi/home-transit-timetable
ExecStart=uvicorn app:app --host 0.0.0.0 --port 8080
Restart=always
User=pi

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now transit-board
```
