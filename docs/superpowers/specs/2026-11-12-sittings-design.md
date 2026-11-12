# Sittings, editing, subjects, goal, auto-pause: design

Date: 2026-11-12
Status: draft, awaiting approval
Builds on: `2026-09-28-hour-tracker-design.md` (v1)

## Why

The user writes "studying 14:53 to 16:53" on paper notes, loses the notes, and
can no longer tell how long each sitting was. The app already saves every
start/pause as a session row with exact times, but only shows daily totals.

Their totals are also wrong on some days. When they forget to stop the timer
at night, it runs until morning. Their data has three runs of 13–14 hours
(Oct 14, Oct 28, Nov 9). On Nov 9 the app asked at 09:27 "away 21:16 to 09:27,
were you studying?". They paused and pressed start without answering, and an
unanswered question counts as yes, so the 12 hours stayed.

Success: they open the stats window and can trust and read, for any day, each
sitting with its start, end and length, what subject it was, and how the day
compares to their goal. The app stays quiet and minimal (the user has ADHD;
dark, low-distraction UI, no pink).

## Goals

1. **Sittings list**: for a selected day, one line per sitting.
2. **Edit, delete and add sittings** by hand. The user says they won't cheat; no
   audit trail or locking is needed.
3. **Auto-pause** when the user has clearly left (hours, not minutes), so a
   forgotten timer doesn't count the night.
4. **Subjects**: tag sittings with a subject and see where a week's or month's
   hours went.
5. **Daily goal**: a faint line on the chart. Nothing nags.

## Non-goals and anti-goals

- No merging of sittings. Any pause, however short, starts a new sitting. (User's
  decision.)
- No streaks, badges, sounds, or new popups. No notes on sittings, no export.
- Anti-goal: the app silently losing real study time, or totals that disagree
  with the list.
- Anti-goal: anything that writes to the user's real database during development
  or tests. Tests use `:memory:` or temp files.

## What the user sees

### Stats window

Order top to bottom: the three cards (unchanged), the week/month nav (unchanged),
the chart, then the new **day section**.

- **Chart**: clicking a bar selects that day. Today is selected when the window
  opens and when switching week/month. The selected day's bar or label gets a
  clear but quiet marker (builder's choice, e.g. a stronger label). Hover
  tooltips stay.
- **Goal line**: a thin, faint horizontal line across the chart at the daily
  goal, if one is set. The scale's top must be at least the goal, so the line is
  always visible.
- **Subject breakdown**: one line under the chart for the shown week or month,
  largest first, e.g. `Calculus 5h 10m · Biology 3h 00m · No subject 4h 05m`.
  Hidden when no sitting in the period has a subject.
- **Day section**: a heading with the date (`Thu, Nov 12`) and an **Add**
  button, then the list:

  ```
  10:57 – 12:23   1h 26m   Calculus
  15:00 – 15:55   55m
  16:23 – now     30m      Biology
  ```

  - One row per sitting that *starts* on that day, oldest first. A sitting past
    midnight reads `19:24 – 09:27 (next day)` and appears only on its start day.
    (Day totals keep splitting it at midnight as today.)
  - Sittings shorter than 60 seconds are hidden from the list. They still count
    in totals.
  - The running sitting shows `– now` and updates with the window's existing
    30-second refresh.
  - Empty day: a dim `No sittings`.
  - If the list is long, it scrolls. The window must not grow off-screen.

### Edit box

Clicking a row opens a small popover (or dialog) with:

- **Start** and **End** as `HH:MM` text fields. They're on the sitting's start
  date. An end earlier than the start means the next day.
- **Subject**: a text field with a dropdown of subjects used before. Empty
  means no subject.
- **Save**, **Delete**, and closing the box cancels.
- **Add** opens the same box, empty, for the selected day. Delete is hidden.

Rules:

- The running sitting can't have its times edited or be deleted; only its subject
  can change. The time fields are disabled with a short hint ("Pause to edit
  times").
- Refuse, with one short line of text in the box, when: the time isn't valid
  `HH:MM`; the sitting would be 0 minutes or longer than 24 hours; it would
  end in the future; or it overlaps another sitting (including the running one).
- After saving, the cards, chart and list update right away.

### Auto-pause

While the timer runs, once the user has been away for `auto_pause_minutes`
(default 120), the timer pauses itself and the away stretch is cut, the same as
answering No. "Away" uses the same signals as the away check: no input, screen
locked, or the laptop asleep. The sitting then ends at the last input, e.g.
`19:24 – 21:16`.

- Idle or locked: it pauses as soon as the threshold passes, without waiting
  for the user to come back.
- Asleep: it's detected on wake, and the cut runs from the last input to the
  wake time.
- It shows one GNOME notification, kept in the list until dismissed:
  "Timer paused at 21:16. You were away." No buttons.
- Away stretches between `away_minutes` and `auto_pause_minutes` keep v1
  behavior (the question in the pill).
- If an earlier away question is still open when auto-pause triggers, the
  earlier stretch follows v1 rules: it counts unless answered No. Auto-pause
  cuts only its own stretch, from the last input. (Builder's call: the user can
  fix a wrong earlier stretch with the edit box, and this keeps v1 behavior.)
- The three past bad nights are not fixed by code. The user fixes them by
  hand with the edit box.

### Subjects: choosing one

Both ways (user's decision):

- **Afterwards**: the Subject field in the edit box.
- **Ahead / while studying**: a **Subject** submenu in the pill's right-click
  menu. It lists subjects used before (most recent first, at most about 8),
  plus **New subject…** (a tiny entry dialog) and **None**. The current one is
  marked. Picking one tags the running sitting, if there is one, and every new
  sitting after it until changed. It's saved in settings as `subject` (string,
  `""` = none), so it survives a restart.
- Editing a sitting's subject in the edit box doesn't change the current subject.

### Daily goal

A new setting, `daily_goal_minutes` (default 240 = 4h; 0 hides the line). It's
set by editing `settings.json` like the other settings, with no in-app control.
(Builder's call: the user didn't answer this, so it can be revisited.)

## Data

- Add a nullable `subject TEXT` column to `sessions`. Migrate the existing
  database in place with `ALTER TABLE ... ADD COLUMN` when the column is missing.
  Existing rows get `NULL` (no subject). Nothing else changes in old rows.
- `remove_range` splitting a session in two must copy its subject to the new
  half.
- The store gains: list sittings with id and subject in a range, update one
  (start, end, subject), delete one, add one. `sessions_between` keeps its
  current `(start, end)` shape for totals.
- The overlap check, `HH:MM` parsing (with next-day rule), the hide-under-60s
  filter, row formatting, and the subject breakdown are pure functions with unit
  tests.
- Settings: `auto_pause_minutes` (int ≥ 1, default 120) and `daily_goal_minutes`
  (int ≥ 0, where 0 means no goal, default 240). The existing `_valid` rule
  for `_minutes` keys requires ≥ 1, so `daily_goal_minutes` needs its own
  rule. README's Settings section documents both.

## Constraints

- GTK 3 via PyGObject. Always run `/usr/bin/python3`. All 98 existing tests must
  still pass. Run tests with `/usr/bin/python3 -m unittest -v`.
- Keep the existing structure: pure logic in `stats.py` / `tracker.py` (no GTK),
  storage in `store.py`, UI in `stats_window.py` / `app.py` / `notifier.py`.
- The user's real data in `~/.local/share/hour-tracker` may only be read,
  and the app may be running. The migration will run on it the next time the
  app starts, so it must be safe to run twice and on a database with existing
  rows.
- Visual check with `tools/snapshot.py stats build/stats.png`.
- Commit trailer: `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

## Left to the builder

Exact widget choices (popover vs dialog, how the selected bar looks), spacing,
how the running row's subject edit is wired, notification wording within the
spirit above, and test layout.

## Builder's calls to check

- Auto-pause after 120 minutes away, adjustable as `auto_pause_minutes`.
- Daily goal of 4h, set only in `settings.json`.
- Sittings under 60 s are hidden from the list but still counted.
- A sitting past midnight is listed only on its start day.
- An unanswered earlier away question still counts when auto-pause fires.
