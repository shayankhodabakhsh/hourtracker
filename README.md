# Hour Tracker

A minimal study-hour tracker for Ubuntu (GNOME), plus a balloon to fidget with.

- **Timer pill**: floats above your windows and shows today's study time. Click
  the play/pause button to start or pause, click the time for stats, drag it
  anywhere, and right-click for the menu.
- **Away check**: after 15+ minutes with no keyboard or mouse input (or with the
  laptop asleep), it asks whether you were studying. "No" removes that time.
- **Forgot-to-start buzz**: after 3 minutes of using the laptop with the timer
  off, the pill shakes and a notification asks if you're studying. "Start"
  counts from when you sat down.
- **Stats**: today, this week, and this month, with a week/month bar chart.
- **Balloon**: a matte black balloon you can drag around and squish. It's only a
  toy.

## Requirements

Ubuntu with GNOME (built on 26.04 with Wayland) and one extra package:

```bash
sudo apt install python3-gi-cairo
```

## Run

```bash
./hour-tracker
```

`./install.sh` adds it to the app grid, and `./install.sh --uninstall` removes it.
To start it at login, right-click the pill and turn on "Start at login".

## Your data

- Study sessions: `~/.local/share/hour-tracker/hours.db` (SQLite)
- Settings: `~/.config/hour-tracker/settings.json`

## Development

Use `/usr/bin/python3`, which has the GTK bindings. A conda or venv Python may not.

```bash
/usr/bin/python3 -m unittest -v
/usr/bin/python3 tools/render_preview.py build/previews
/usr/bin/python3 tools/snapshot.py pill build/pill.png
```

Design and plan: `docs/superpowers/`.

## Roadmap

Phase 2: focus tracking. The app will learn how long you usually stay focused and
suggest a focus/break rhythm that fits you.
