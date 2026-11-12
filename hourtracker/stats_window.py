"""The stats window: today, this week, this month, a bar chart you can
switch between weeks and months, and the selected day's sittings, which you
can edit."""
import math
from datetime import datetime, timedelta

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
gi.require_version("Pango", "1.0")
gi.require_version("PangoCairo", "1.0")
from gi.repository import Gdk, GLib, Gtk, Pango, PangoCairo  # noqa: E402

from . import APP_NAME
from . import stats
from .stats import fmt_duration, local_date, local_midnight, period, period_label, shift

CSS = b"""
.card { background-color: alpha(@theme_fg_color, 0.07); border-radius: 10px; padding: 10px 12px; }
.card-caption { font-size: 12px; opacity: 0.65; }
.card-value { font-size: 20px; font-weight: bold; }
.day-title { font-weight: bold; }
.sittings, .sittings row { background-color: transparent; }
.sittings row { padding: 4px 2px; border-radius: 6px; }
.problem { color: #e5a50a; }
"""
LABEL_HEIGHT, HEAD_HEIGHT = 18, 16      # chart margins below and above the bars


def nice_max(values, goal=0.0) -> float:
    """Top of the chart scale: the next whole hour above the tallest bar or the
    goal (1h minimum)."""
    top = max(max(values, default=0.0), goal)
    return max(3600.0, math.ceil(top / 3600.0) * 3600.0)


def bar_index(x, width, count):
    """Which bar a horizontal position falls on, or None outside the chart."""
    if count <= 0 or not 0 <= x < width:
        return None
    return int(x / (width / count))


def _rounded_top_rect(cr, x, y, w, h, r):
    r = min(r, h)
    cr.move_to(x, y + h)
    cr.line_to(x, y + r)
    cr.arc(x + r, y + r, r, math.pi, 1.5 * math.pi)
    cr.line_to(x + w - r, y)
    cr.arc(x + w - r, y + r, r, 1.5 * math.pi, 2 * math.pi)
    cr.line_to(x + w, y + h)
    cr.close_path()


class StatsWindow(Gtk.Window):
    def __init__(self, tracker, first_weekday, goal_seconds=0.0):
        super().__init__(title=APP_NAME)
        self._tracker = tracker
        self._first_weekday = first_weekday
        self._goal = goal_seconds       # 0 = no goal line
        self._view = "week"
        self._anchor = self.today()
        self._first = self._anchor
        self._selected = self._anchor   # whose sittings are listed
        self._totals = []               # seconds per day in the shown period
        self._refresh_id = 0
        self._editor = None             # the open edit popover, if any
        self.set_default_size(460, 620)

        provider = Gtk.CssProvider()
        provider.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_screen(
            self.get_screen(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.set_titlebar(Gtk.HeaderBar(title=APP_NAME, show_close_button=True))

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        content.set_margin_top(16)
        content.set_margin_bottom(16)
        content.set_margin_start(16)
        content.set_margin_end(16)

        cards = Gtk.Box(spacing=10, homogeneous=True)
        self._today_value = self._card(cards, "Today")
        self._week_value = self._card(cards, "This week")
        self._month_value = self._card(cards, "This month")
        content.pack_start(cards, False, False, 0)

        nav = Gtk.Box(spacing=4)
        self._prev = self._icon_button("go-previous-symbolic", lambda: self._move(-1))
        self._next = self._icon_button("go-next-symbolic", lambda: self._move(1))
        self._label = Gtk.Label()
        nav.pack_start(self._prev, False, False, 0)
        nav.pack_start(self._label, False, False, 6)
        nav.pack_start(self._next, False, False, 0)
        switch = Gtk.Box()
        switch.get_style_context().add_class("linked")
        week = Gtk.RadioButton(label="Week", draw_indicator=False)
        month = Gtk.RadioButton(label="Month", draw_indicator=False, group=week)
        week.connect("toggled", self._on_view, "week")
        month.connect("toggled", self._on_view, "month")
        self._view_buttons = {"week": week, "month": month}
        switch.pack_start(week, False, False, 0)
        switch.pack_start(month, False, False, 0)
        nav.pack_end(switch, False, False, 0)
        content.pack_start(nav, False, False, 0)

        self._chart = Gtk.DrawingArea()
        self._chart.set_size_request(-1, 170)
        self._chart.set_has_tooltip(True)
        self._chart.connect("draw", self._draw_chart)
        self._chart.connect("query-tooltip", self._on_tooltip)
        self._chart.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        self._chart.connect("button-press-event", self._on_chart_click)
        content.pack_start(self._chart, True, True, 0)

        self._breakdown = Gtk.Label(xalign=0, wrap=True)
        self._breakdown.get_style_context().add_class("dim-label")
        content.pack_start(self._breakdown, False, False, 0)

        head = Gtk.Box(spacing=6)
        self._day_title = Gtk.Label(xalign=0)
        self._day_title.get_style_context().add_class("day-title")
        add = Gtk.Button(label="Add")
        add.set_relief(Gtk.ReliefStyle.NONE)
        add.connect("clicked", lambda button: self._open_editor(button, None))
        head.pack_start(self._day_title, False, False, 0)
        head.pack_end(add, False, False, 0)
        content.pack_start(head, False, False, 0)

        self._list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        self._list.get_style_context().add_class("sittings")
        self._list.connect("row-activated",
                           lambda _box, row: self._open_editor(row, row.sitting))
        empty = Gtk.Label(label="No sittings", xalign=0)
        empty.get_style_context().add_class("dim-label")
        empty.show()
        self._list.set_placeholder(empty)
        scroller = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
        scroller.set_propagate_natural_height(True)
        scroller.set_max_content_height(230)
        scroller.add(self._list)
        content.pack_start(scroller, False, False, 0)
        self.add(content)

        self.connect("delete-event", self._on_close)
        self.connect("show", lambda _window: self._start_refreshing())
        self.connect("hide", lambda _window: self._stop_refreshing())

    # Building blocks ----------------------------------------------------

    def _card(self, parent, caption):
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        card.get_style_context().add_class("card")
        title = Gtk.Label(label=caption, xalign=0)
        title.get_style_context().add_class("card-caption")
        value = Gtk.Label(label="0m", xalign=0)
        value.get_style_context().add_class("card-value")
        card.pack_start(title, False, False, 0)
        card.pack_start(value, False, False, 0)
        parent.pack_start(card, True, True, 0)
        return value

    def _icon_button(self, icon, callback):
        button = Gtk.Button.new_from_icon_name(icon, Gtk.IconSize.BUTTON)
        button.set_relief(Gtk.ReliefStyle.NONE)
        button.connect("clicked", lambda _button: callback())
        return button

    # State --------------------------------------------------------------

    def today(self):
        return local_date(self._tracker.clock())

    def set_view(self, view):
        self._view_buttons[view].set_active(True)

    def _on_view(self, button, view):
        if button.get_active():
            self._view = view
            self._anchor = self._selected = self.today()
            self.refresh()

    def _move(self, steps):
        self._anchor = shift(self._view, self._anchor, steps)
        self.refresh()

    def refresh(self):
        today = self.today()
        week_first, _ = period("week", today, self._first_weekday)
        month_first, month_days = period("month", today, self._first_weekday)
        self._today_value.set_text(fmt_duration(self._tracker.day_totals(today, 1)[0]))
        self._week_value.set_text(fmt_duration(sum(self._tracker.day_totals(week_first, 7))))
        self._month_value.set_text(
            fmt_duration(sum(self._tracker.day_totals(month_first, month_days))))
        self._first, days = period(self._view, self._anchor, self._first_weekday)
        self._totals = self._tracker.day_totals(self._first, days)
        self._label.set_text(period_label(self._view, self._first, days))
        self._next.set_sensitive(self._first + timedelta(days=days) <= today)
        self._chart.queue_draw()
        self._show_breakdown(days)
        if self._editor is None:        # don't pull rows out from under the edit box
            self._show_day()

    def _show_breakdown(self, days):
        a = local_midnight(self._first)
        b = local_midnight(self._first + timedelta(days=days))
        totals = stats.subject_totals(self._tracker.sittings_between(a, b), a, b)
        self._breakdown.set_visible(any(subject for subject, _seconds in totals))
        self._breakdown.set_text("  ·  ".join(
            f"{subject or 'No subject'} {fmt_duration(seconds)}"
            for subject, seconds in totals))

    def _show_day(self):
        day = self._selected
        self._day_title.set_text(f"{day:%a, %b} {day.day}")
        for row in self._list.get_children():
            self._list.remove(row)
        a = local_midnight(day)
        for sitting in stats.day_sittings(
                self._tracker.sittings_between(a, local_midnight(day + timedelta(days=1))),
                day):
            _id, start, end, subject, running = sitting
            line = Gtk.Box(spacing=12)
            span = Gtk.Label(label=stats.fmt_span(start, end, running), xalign=0)
            length = Gtk.Label(label=fmt_duration(end - start), xalign=0)
            length.get_style_context().add_class("dim-label")
            topic = Gtk.Label(label=subject or "", xalign=0,
                              ellipsize=Pango.EllipsizeMode.END)
            line.pack_start(span, False, False, 0)
            line.pack_start(length, False, False, 0)
            line.pack_end(topic, False, False, 0)
            row = Gtk.ListBoxRow()
            row.sitting = sitting
            row.add(line)
            self._list.add(row)
        self._list.show_all()

    # Editing ------------------------------------------------------------

    def _open_editor(self, anchor_widget, sitting):
        """The edit box for a sitting, or an empty one (sitting=None) to add."""
        if self._editor is not None:
            self._editor.popdown()
        running = sitting is not None and sitting[4]
        day = local_date(sitting[1]) if sitting else self._selected
        popover = Gtk.Popover(relative_to=anchor_widget, position=Gtk.PositionType.TOP)
        grid = Gtk.Grid(column_spacing=8, row_spacing=6)
        for side in ("top", "bottom", "start", "end"):
            getattr(grid, f"set_margin_{side}")(10)
        start = Gtk.Entry(width_chars=6, placeholder_text="14:53", activates_default=True)
        end = Gtk.Entry(width_chars=6, placeholder_text="16:53", activates_default=True)
        subject = Gtk.ComboBoxText.new_with_entry()
        for name in self._tracker.store.subjects():
            subject.append_text(name)
        subject.get_child().set_placeholder_text("No subject")
        subject.get_child().set_activates_default(True)
        if sitting:
            start.set_text(f"{datetime.fromtimestamp(sitting[1]):%H:%M}")
            end.set_text("now" if running else f"{datetime.fromtimestamp(sitting[2]):%H:%M}")
            subject.get_child().set_text(sitting[3] or "")
        start.set_sensitive(not running)
        end.set_sensitive(not running)
        problem = Gtk.Label(xalign=0, wrap=True, max_width_chars=28)
        problem.get_style_context().add_class("dim-label" if running else "problem")
        if running:
            problem.set_text("Pause to edit times.")
        for row, (caption, widget) in enumerate(
                (("Start", start), ("End", end), ("Subject", subject))):
            grid.attach(Gtk.Label(label=caption, xalign=0), 0, row, 1, 1)
            grid.attach(widget, 1, row, 1, 1)
        grid.attach(problem, 0, 3, 2, 1)
        buttons = Gtk.Box(spacing=6)
        save = Gtk.Button(label="Save", can_default=True)
        save.get_style_context().add_class("suggested-action")
        buttons.pack_end(save, False, False, 0)
        if sitting and not running:
            delete = Gtk.Button(label="Delete")
            delete.get_style_context().add_class("destructive-action")
            delete.connect("clicked", lambda _b: self._delete(popover, sitting))
            buttons.pack_start(delete, False, False, 0)
        grid.attach(buttons, 0, 4, 2, 1)
        save.connect("clicked", lambda _b: self._save(
            popover, sitting, day, start.get_text(), end.get_text(),
            subject.get_child().get_text().strip(), problem))
        popover.add(grid)
        popover.connect("closed", self._on_editor_closed)
        self._editor = popover
        grid.show_all()
        popover.popup()
        save.grab_default()

    def _save(self, popover, sitting, day, start_text, end_text, subject, problem):
        subject = subject or None
        if sitting is not None and sitting[4]:          # running: subject only
            self._tracker.set_subject(subject)
            popover.popdown()
            return
        try:
            start, end = stats.sitting_times(day, start_text, end_text)
        except ValueError as err:
            problem.set_text(str(err))
            return
        near = self._tracker.sittings_between(
            local_midnight(day - timedelta(days=1)), local_midnight(day + timedelta(days=2)))
        others = [(s[1], s[2]) for s in near if sitting is None or s[0] != sitting[0]]
        why = stats.sitting_problem(start, end, others, self._tracker.clock())
        if why:
            problem.set_text(why)
            return
        store = self._tracker.store
        if sitting is None:
            store.add(start, end, subject)
        else:
            store.update(sitting[0], start, end, subject)
        popover.popdown()

    def _delete(self, popover, sitting):
        self._tracker.store.delete(sitting[0])
        popover.popdown()

    def _on_editor_closed(self, popover):
        if self._editor is popover:
            self._editor = None
        GLib.idle_add(popover.destroy)
        self.refresh()

    def _on_close(self, *_args):
        self.hide()
        return True

    def _start_refreshing(self):
        self.refresh()
        if not self._refresh_id:
            self._refresh_id = GLib.timeout_add_seconds(30, self._on_timer)

    def _stop_refreshing(self):
        if self._refresh_id:
            GLib.source_remove(self._refresh_id)
            self._refresh_id = 0

    def _on_timer(self):
        self.refresh()
        return GLib.SOURCE_CONTINUE

    # Chart --------------------------------------------------------------

    def _draw_chart(self, widget, cr):
        count = len(self._totals)
        if count == 0:
            return False
        width = widget.get_allocated_width()
        height = widget.get_allocated_height()
        style = widget.get_style_context()
        fg = style.get_color(Gtk.StateFlags.NORMAL)
        found, accent = style.lookup_color("theme_selected_bg_color")
        if not found:
            accent = Gdk.RGBA(0.21, 0.52, 0.89, 1.0)
        top = nice_max(self._totals, self._goal)
        chart_h = height - LABEL_HEIGHT - HEAD_HEIGHT
        slot = width / count
        bar_w = slot * (0.6 if count <= 7 else 0.68)
        today = self.today()

        cr.set_source_rgba(fg.red, fg.green, fg.blue, 0.12)
        cr.rectangle(0, HEAD_HEIGHT, width, 1)
        cr.rectangle(0, HEAD_HEIGHT + chart_h, width, 1)
        cr.fill()
        self._text(cr, widget, fmt_duration(top), width, 0, fg, 0.55, "right")
        if self._goal:
            goal_y = HEAD_HEIGHT + chart_h - self._goal / top * chart_h
            cr.set_source_rgba(accent.red, accent.green, accent.blue, 0.45)
            cr.set_dash([4.0, 4.0])
            cr.set_line_width(1.0)
            cr.move_to(0, round(goal_y) + 0.5)
            cr.line_to(width, round(goal_y) + 0.5)
            cr.stroke()
            cr.set_dash([])
        if not any(self._totals):
            self._text(cr, widget, "No study time yet", width / 2,
                       HEAD_HEIGHT + chart_h / 2 - 8, fg, 0.55, "center")

        for i, seconds in enumerate(self._totals):
            day = self._first + timedelta(days=i)
            is_today = day == today
            color = accent if is_today else fg
            if seconds > 0:
                h = max(2.0, seconds / top * chart_h)
                x = i * slot + (slot - bar_w) / 2
                _rounded_top_rect(cr, x, HEAD_HEIGHT + chart_h - h, bar_w, h,
                                  min(4.0, bar_w / 2))
                cr.set_source_rgba(color.red, color.green, color.blue,
                                   1.0 if is_today else 0.3)
                cr.fill()
            if count <= 7 or day.day in (1, 5, 10, 15, 20, 25) or i == count - 1:
                text = f"{day:%a}" if count <= 7 else str(day.day)
                self._text(cr, widget, text, i * slot + slot / 2,
                           height - LABEL_HEIGHT + 2, color,
                           1.0 if is_today else 0.6, "center")
            if day == self._selected:           # a short underline under the bar
                cr.set_source_rgba(fg.red, fg.green, fg.blue, 0.8)
                cr.rectangle(i * slot + (slot - bar_w) / 2, HEAD_HEIGHT + chart_h + 2,
                             bar_w, 2)
                cr.fill()
        return False

    def _on_chart_click(self, widget, event):
        index = bar_index(event.x, widget.get_allocated_width(), len(self._totals))
        if index is None or event.button != Gdk.BUTTON_PRIMARY:
            return False
        day = self._first + timedelta(days=index)
        if day <= self.today():
            self._selected = day
            self.refresh()
        return True

    def _text(self, cr, widget, text, x, y, color, alpha, align):
        layout = widget.create_pango_layout(text)
        font = layout.get_context().get_font_description().copy()
        font.set_size(9 * Pango.SCALE)
        layout.set_font_description(font)
        text_w, _text_h = layout.get_pixel_size()
        if align == "center":
            x -= text_w / 2
        elif align == "right":
            x -= text_w
        cr.move_to(x, y)
        cr.set_source_rgba(color.red, color.green, color.blue, alpha)
        PangoCairo.show_layout(cr, layout)

    def _on_tooltip(self, widget, x, _y, _keyboard, tooltip):
        index = bar_index(x, widget.get_allocated_width(), len(self._totals))
        if index is None:
            return False
        day = self._first + timedelta(days=index)
        tooltip.set_text(f"{day:%a, %b} {day.day} · {fmt_duration(self._totals[index])}")
        return True
