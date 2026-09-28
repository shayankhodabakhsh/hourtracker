"""The stats window: today, this week, this month, and a bar chart you can
switch between weeks and months."""
import math
from datetime import timedelta

import gi

gi.require_version("Gdk", "3.0")
gi.require_version("Gtk", "3.0")
gi.require_version("Pango", "1.0")
gi.require_version("PangoCairo", "1.0")
from gi.repository import Gdk, GLib, Gtk, Pango, PangoCairo  # noqa: E402

from . import APP_NAME
from .stats import fmt_duration, local_date, period, period_label, shift

CSS = b"""
.card { background-color: alpha(@theme_fg_color, 0.07); border-radius: 10px; padding: 10px 12px; }
.card-caption { font-size: 12px; opacity: 0.65; }
.card-value { font-size: 20px; font-weight: bold; }
"""
LABEL_HEIGHT, HEAD_HEIGHT = 18, 16      # chart margins below and above the bars


def nice_max(values) -> float:
    """Top of the chart scale: the next whole hour above the tallest bar (1h minimum)."""
    top = max(values, default=0.0)
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
    def __init__(self, tracker, first_weekday):
        super().__init__(title=APP_NAME)
        self._tracker = tracker
        self._first_weekday = first_weekday
        self._view = "week"
        self._anchor = self.today()
        self._first = self._anchor
        self._totals = []               # seconds per day in the shown period
        self._refresh_id = 0
        self.set_default_size(460, 380)

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
        content.pack_start(self._chart, True, True, 0)
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
            self._anchor = self.today()
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
        top = nice_max(self._totals)
        chart_h = height - LABEL_HEIGHT - HEAD_HEIGHT
        slot = width / count
        bar_w = slot * (0.6 if count <= 7 else 0.68)
        today = self.today()

        cr.set_source_rgba(fg.red, fg.green, fg.blue, 0.12)
        cr.rectangle(0, HEAD_HEIGHT, width, 1)
        cr.rectangle(0, HEAD_HEIGHT + chart_h, width, 1)
        cr.fill()
        self._text(cr, widget, fmt_duration(top), width, 0, fg, 0.55, "right")
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
        return False

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
