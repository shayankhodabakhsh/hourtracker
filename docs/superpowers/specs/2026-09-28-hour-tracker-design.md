# Hour Tracker: design

Date: 2026-09-28
Status: approved (v1). Focus tracking is phase 2 and gets its own spec.
Repo: git@github.com:shayankhodabakhsh/hourtracker.git

## Goal

A study-time tracker for Ubuntu (GNOME, Wayland) with two parts:

1. **Timer pill**: a tiny floating pill that tracks study time in the background
   and shows today's total. Totals by day, week, and month live in a small stats
   window. If the user starts using the laptop and forgets to start the timer,
   the pill buzzes.
2. **Balloon**: a matte black balloon with a smiley face, floating on the desktop.
   It is only a fidget toy: drag it around and click it to squish it. It exists so
   there's something to play with instead of opening a browser.

The UI must stay minimal and quiet: no sounds and no motion unless the user
touches something. The only notification is the forgot-to-start buzz.

## What the user sees

### Timer pill

- A small rounded pill, about 32 px tall, that floats above all windows on every
  workspace. It is not in the dock or Alt+Tab and never takes keyboard focus.
- Contents: a play/pause button and today's total as `h:mm`, like `|| 1:24`.
  The total includes the running session and resets at local midnight.
  - Running: pause icon, time at full brightness.
  - Paused: play icon, time dimmed.
- Click the play/pause button to start or pause.
- Click the time to open the stats window.
- Drag anywhere on the pill (except the button) to move it. It remembers where it
  was left.
- Right-click menu: Stats, Show balloon (checkbox), Remind me to start (checkbox,
  on by default), Start at login (checkbox, off by default), Quit.
- The time updates once a minute. There are no seconds.

### Away check

While the timer runs, if there was no keyboard or mouse input for 15+ minutes, or
the laptop slept for 15+ minutes, the pill expands when the user is back:

```
|| 1:24
Away 23m. Were you studying?   [Yes] [No]
```

- **Yes**: the time counts, and the question closes.
- **No**: that stretch is removed from the record and the timer pauses.
- Breaks shorter than 15 minutes count silently.
- If the question is ignored, the time counts. If a second away stretch happens
  while a question is still open, the first one counts and the question switches
  to the new stretch.
- Pausing leaves an open question in place, so No still works. Starting the
  timer again, or a new stretch at the laptop, counts it as Yes.

### Forgot-to-start buzz

A **stretch at the laptop** begins when the app starts (usually at login), when
the user comes back after a 15+ minute break, or when the laptop wakes after 15+
minutes asleep. If the timer is still off after 3 minutes of that stretch, and the
user touched the keyboard or mouse in the last minute:

- The pill shakes side to side, like a phone buzzing, and expands:

  ```
  > 0:00
  Studying? The timer is off.   [Start] [Not now]
  ```

- A GNOME notification appears with the same **Start** and **Not now** buttons.
  Answering in either place closes the other.
- **Start** starts the timer from zero, like the play button. (Counting from the
  beginning of the stretch was dropped: a buzz left open for hours could then
  add hours that were never studied.)
- **Not now** stays quiet until the next stretch.
- The buzz happens at most once per stretch. Starting or pausing the timer by
  hand, or answering the away question, also silences it until the next stretch.
- The pill's "Remind me to start" checkbox turns the buzz off entirely.

### Balloon

- A matte black balloon with a white smiley face, a small knot, and a string,
  about 85 × 100 px for the body. It floats above all windows on every workspace,
  is not in the dock or Alt+Tab, and never takes keyboard focus.
- **Click**: it squashes and wobbles like jelly, then settles in about a second.
  The eyes squint while it is squished. Rapid clicks stack, capped so it never
  deforms absurdly.
- **Drag**: it moves with the mouse. It leans with the motion, and its string
  trails behind, then it sways back upright when released. It remembers where it
  was left.
- It is fully static when untouched: no bobbing and no blinking.
- Clicks on the transparent area around the balloon pass through to the window
  below.
- Right-click menu: Color (Matte black, Electric blue, Army green, Fire red), Hide
  balloon. To show it again, use the pill's menu.
- The balloon has no connection to the timer.

### Stats window

A small normal window. It follows the system dark or light theme (currently Yaru
dark).

- Three totals: **Today**, **This week**, **This month**, formatted like `2h 15m`.
- A bar chart with a **Week | Month** toggle and `‹ ›` arrows to browse earlier and
  later periods. Today's bar is highlighted. Hovering a bar shows its date and
  total.
- Weeks follow the system locale, which starts weeks on Sunday. Months are
  calendar months.
- While open, it refreshes every 30 s and right after any start, pause, or answer.
- Closing the window hides it; tracking continues.
- Opened from the pill (click the time, or Stats in the menu), or by launching
  Hour Tracker again from the app grid.

### Startup and quit

- On launch, the pill and balloon appear at their saved positions. The first run
  places the pill at the top right and the balloon at the bottom right of the
  primary monitor.
- The timer always starts **paused**, including after a reboot or crash, so it
  never counts time the user didn't choose to count.
- Quit (from the menu, Ctrl+C, or SIGTERM) ends a running session at that moment.

## Architecture

**Stack**: the system Python 3 (`/usr/bin/python3`, which has PyGObject) with GTK 3,
Cairo, libnotify, and SQLite from the standard library. One Ubuntu package must be
added: `python3-gi-cairo`, which lets GTK pass Cairo drawing contexts to Python.
Nothing is installed with pip.

**Why GTK 3 on XWayland**: GNOME on Wayland doesn't let apps position their own
windows or keep them on top. The app forces `GDK_BACKEND=x11` and runs under
XWayland, where keep-above, sticky, self-positioning, window-manager-driven drags,
and per-pixel transparency all work. Mutter's `xwayland-native-scaling` is on, so
it renders sharply at the laptop's 133% scale. GTK 4 is ruled out because it
removed window positioning.

**Process**: one `Gtk.Application` (ID `io.github.shayankhodabakhsh.HourTracker`),
single instance. Launching it again opens the stats window in the running
instance. The launcher must call `/usr/bin/python3` explicitly, because the
`python3` on PATH is conda's, which lacks GTK bindings.

### Modules (package `hourtracker/`)

| Module | Responsibility | Depends on |
|---|---|---|
| `store.py` | SQLite session storage: begin, extend the end, remove a time range (clip or split), and query sessions overlapping a range | sqlite3 |
| `stats.py` | Pure time math: local midnights, per-day totals (splitting sessions at midnight), week and month ranges, locale week start, formatting (`1:24`, `2h 15m`) | stdlib only |
| `tracker.py` | Timer state machine: start, pause, checkpointing, away detection (idle and suspend), the forgot-to-start buzz, and the answers. Clock and idle source are injected, and there is no GTK code | store, stats |
| `idle.py` | Reads idle time from GNOME's `org.gnome.Mutter.IdleMonitor` over D-Bus. Returns `None` if unavailable | Gio |
| `settings.py` | JSON settings with atomic writes and defaults on a corrupt file | stdlib |
| `autostart.py` | Adds or removes `~/.config/autostart/hour-tracker.desktop` | stdlib |
| `physics.py` | A damped spring, for squish, wobble, and lean | stdlib |
| `floating.py` | Shared floating-window behavior: RGBA transparency, keep-above, sticky, skip taskbar and pager, no focus, telling a click from a drag (a 4 px threshold, then a window-manager move), saving position, and clamping to visible monitors | Gtk |
| `balloon_art.py` | Pure Cairo drawing of the balloon given color, squash, tilt, and squint. Testable by rendering to PNG | cairo |
| `balloon.py` | Balloon window: springs for squish and lean, run on the frame clock only while moving, plus its input shape and menu | floating, balloon_art, physics |
| `pill.py` | Pill window, built from GTK widgets and CSS: play/pause button, time label, question row (a revealer), the buzz shake, and the menu | floating |
| `notifier.py` | The forgot-to-start GNOME notification with Start and Not now buttons | libnotify |
| `stats_window.py` | Totals, the bar chart (a Cairo drawing area with tooltips), and week/month navigation | stats |
| `app.py` | Wires everything together: timers (a 5 s tick), menus, settings, signals, and lifecycle | all |

### Tracker rules

- **Tick**: every 5 s. On each tick it reads the clock and idle time and updates
  `last_active = max(last_active, now - idle)`.
- **Checkpoint**: while running, the session's end is written to SQLite every 30 s.
  A crash loses at most 30 s, and no recovery step is needed.
- **Idle away**: if a tick finds that the latest activity is 15+ minutes after the
  previous known activity, the user was away from `last_active` until the new
  activity time. While running, the tracker opens a question. While paused, a
  new stretch at the laptop begins.
- **Suspend away**: a gap of more than 60 s between ticks means the machine slept.
  The away stretch runs from `last_active` to now. If it lasted 15+ minutes, the
  tracker asks (running) or begins a new stretch (paused); otherwise the time
  counts silently. The monotonic idle counter excludes suspend time, so it isn't
  trusted on this tick.
- **No**: pause at now if running, then `remove_range(away_start, away_end)`.
- **Paused**: no new away questions. A question that was already open stays open
  (see "Away check"). Starting the timer resets `last_active` to now.
- **Buzz**: see "Forgot-to-start buzz". Without an idle monitor there is no buzz,
  because the app can't tell whether anyone is at the laptop.
- **Locked screen**: while GNOME's screen lock is up (`org.gnome.ScreenSaver`
  `GetActive`), nothing counts as someone at the laptop: no new stretch, no
  return from away, and no buzz. GNOME's idle counter can reset while locked with
  nobody there; on 2026-09-29 that started a stretch at 05:20 with the lid closed.
  The user's first input after unlocking counts as coming back.
- **Clock going backwards**: no away detection on that tick, and a session's end
  never moves backwards.

## Data

- Sessions: `~/.local/share/hour-tracker/hours.db`, table
  `sessions(id INTEGER PRIMARY KEY, start REAL, end REAL)`, in Unix seconds.
  Days, weeks, and months are computed from local time when read, so they stay
  correct across midnight and daylight-saving changes.
- Settings: `~/.config/hour-tracker/settings.json`. It holds the pill and balloon
  positions (in logical pixels), the balloon color, whether the balloon is
  visible, whether the buzz is on, the buzz delay in minutes (default 3), the away
  threshold in minutes (default 15), and the week start (`auto`, `sunday`, or
  `monday`).

## Error handling

- **Idle monitor unavailable**: idle detection and the buzz are off, and suspend
  detection still works. A warning is logged once.
- **Notification server unavailable**: the pill still buzzes. The failure is
  logged.
- **SQLite write fails**: the error is logged and the write is retried at the next
  checkpoint. The app keeps running.
- **Settings file corrupt or missing**: defaults are used.
- **Saved position off-screen** (for example, after unplugging a monitor): the
  window is clamped into the nearest monitor's work area, at startup and whenever
  monitors change.
- **Logout**: XWayland closes and the app exits. The last checkpoint stands.

## Testing

- **Unit tests** with `unittest`, since pytest isn't installed for the system Python:
  - `stats`: sessions spanning midnight, 23 h and 25 h daylight-saving days
    (`TZ=America/New_York`), Sunday and Monday week starts, month lengths, and
    formatting.
  - `store`: every `remove_range` case (inside, split, clip left, clip right, full
    delete, no overlap) and persistence across reopen.
  - `tracker`, with a fake clock and fake idle source: asks at exactly 15:00 but
    not at 14:59, suspend gaps, Yes, No, a question being replaced, no questions
    while paused, checkpoint cadence, and every buzz rule.
  - `physics`, `floating` (position clamping), and chart math.
- **Visual check**: `tools/render_preview.py` renders balloon poses in every color
  to PNGs, and `tools/snapshot.py` saves PNGs of the real pill, balloon, and stats
  windows.
- **Live smoke test**: launch on the real desktop, and use `tools/check_windows.py`
  to confirm the windows are above, sticky, and skip the taskbar, and that the
  balloon has an input shape. Then quit cleanly.

## Install and run

- `./hour-tracker` runs it from the project folder.
- `./install.sh` adds an app-grid launcher. `./install.sh --uninstall` removes it
  (and the autostart entry). Study history is kept.
- Start at login is a toggle in the pill's menu, off by default.

## Out of scope for v1

Subjects and tags, daily goals, sounds, editing past sessions, global keyboard
shortcuts, and running on Windows or Mac.

**Phase 2 (separate spec)**: focus tracking. A small GNOME Shell extension reports
the focused app and window title. The app notes distractions (for example
YouTube, or titles on a list the user edits) during study sessions, learns how
long the user usually stays focused and at which hours, and recommends a
personalized focus/break timeline.
