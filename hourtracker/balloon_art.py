"""Draws the balloon with Cairo. Pure drawing: no windows, no GTK."""
import math
from dataclasses import dataclass

import cairo

WIDTH, HEIGHT = 150, 215        # drawing area, in logical pixels
CENTER_X, CENTER_Y = 75, 72     # middle of the body at rest
RX, RY = 42, 50                 # half-width and half-height of the body
STRING_RGBA = (0.62, 0.62, 0.66, 0.9)


@dataclass(frozen=True)
class Palette:
    label: str
    base: tuple     # body color (r, g, b), each 0..1
    light: tuple    # lit upper-left side
    dark: tuple     # shaded edge and knot
    face: tuple     # eyes and smile
    gloss: float    # highlight strength: low looks matte, high looks shiny


PALETTES = {
    "matte_black": Palette("Matte black", (0.17, 0.17, 0.19), (0.34, 0.35, 0.38),
                           (0.07, 0.07, 0.08), (0.96, 0.96, 0.96), 0.14),
    "electric_blue": Palette("Electric blue", (0.10, 0.42, 0.95), (0.40, 0.66, 1.00),
                             (0.03, 0.19, 0.52), (1.00, 1.00, 1.00), 0.45),
    "army_green": Palette("Army green", (0.33, 0.37, 0.18), (0.52, 0.57, 0.31),
                          (0.17, 0.20, 0.08), (0.95, 0.94, 0.85), 0.25),
    "fire_red": Palette("Fire red", (0.84, 0.13, 0.13), (1.00, 0.40, 0.34),
                        (0.44, 0.04, 0.04), (1.00, 1.00, 1.00), 0.42),
}
DEFAULT_COLOR = "matte_black"


def draw_balloon(cr, palette, squash=0.0, tilt=0.0, squint=False):
    """Draw the balloon into a WIDTH x HEIGHT area.

    squash > 0 flattens it (wider and shorter); squash < 0 stretches it.
    tilt is a lean in radians; positive leans the top to the right.
    squint turns the eyes into happy arcs.
    """
    knot_depth = (RY + 7) * (1 - squash * 0.85)
    knot_x = CENTER_X - math.sin(tilt) * knot_depth
    knot_y = CENTER_Y + math.cos(tilt) * knot_depth
    _draw_string(cr, knot_x, knot_y, tilt)
    cr.save()
    cr.translate(CENTER_X, CENTER_Y)
    cr.rotate(tilt)
    cr.scale(1 + squash, 1 - squash * 0.85)
    _draw_knot(cr, palette)
    _draw_body(cr, palette)
    _draw_face(cr, palette, squint)
    cr.restore()


def input_rects(step=4, pad=3):
    """Horizontal strips (x, y, w, h) covering the resting body and knot, so
    clicks anywhere else in the window pass through to what's underneath."""
    rects = []
    y = CENTER_Y - RY - pad
    bottom = CENTER_Y + RY + 8 + pad
    while y < bottom:
        half = _half_width(y + step / 2 - CENTER_Y) + pad
        rects.append((int(CENTER_X - half), int(y), int(2 * half) + 1, step))
        y += step
    return rects


def _half_width(dy):
    """Approximate half-width of the body at height dy from its center."""
    if abs(dy) >= RY:
        return 6.0 if RY <= dy <= RY + 8 else 0.0    # the knot, or nothing
    return max(6.0, RX * math.sqrt(1 - (dy / RY) ** 2))


def _draw_string(cr, x0, y0, tilt):
    """A thin curly string that trails behind when the balloon leans."""
    length = HEIGHT - y0 - 8
    x1 = x0 + tilt * 60
    cr.save()
    cr.set_source_rgba(*STRING_RGBA)
    cr.set_line_width(1.3)
    cr.set_line_cap(cairo.LINE_CAP_ROUND)
    cr.move_to(x0, y0)
    cr.curve_to(x0 - 9 + tilt * 10, y0 + length * 0.3,
                x1 + 9 + tilt * 30, y0 + length * 0.62,
                x1, y0 + length)
    cr.stroke()
    cr.restore()


def _draw_knot(cr, palette):
    cr.move_to(-5.5, RY + 7)
    cr.line_to(5.5, RY + 7)
    cr.line_to(0, RY - 2)
    cr.close_path()
    cr.set_source_rgb(*palette.dark)
    cr.fill()


def _body_path(cr):
    """Egg shape, rounder on top and narrowing toward the knot."""
    cr.move_to(0, -RY)
    cr.curve_to(RX * 0.56, -RY, RX, -RY * 0.56, RX, -RY * 0.08)
    cr.curve_to(RX, RY * 0.46, RX * 0.46, RY * 0.92, 0, RY)
    cr.curve_to(-RX * 0.46, RY * 0.92, -RX, RY * 0.46, -RX, -RY * 0.08)
    cr.curve_to(-RX, -RY * 0.56, -RX * 0.56, -RY, 0, -RY)
    cr.close_path()


def _draw_body(cr, palette):
    _body_path(cr)
    shade = cairo.RadialGradient(-RX * 0.35, -RY * 0.45, 2, 0, 0, RY * 1.25)
    shade.add_color_stop_rgb(0.0, *palette.light)
    shade.add_color_stop_rgb(0.55, *palette.base)
    shade.add_color_stop_rgb(1.0, *palette.dark)
    cr.set_source(shade)
    cr.fill_preserve()
    cr.set_source_rgba(1, 1, 1, 0.16)    # faint rim, so it shows on dark desktops
    cr.set_line_width(1.2)
    cr.stroke()
    cr.save()                            # soft highlight on the upper left
    cr.translate(-RX * 0.42, -RY * 0.5)
    cr.rotate(-0.55)
    cr.scale(RX * 0.2, RY * 0.3)
    glow = cairo.RadialGradient(0, 0, 0, 0, 0, 1)
    glow.add_color_stop_rgba(0, 1, 1, 1, palette.gloss)
    glow.add_color_stop_rgba(1, 1, 1, 1, 0)
    cr.set_source(glow)
    cr.arc(0, 0, 1, 0, 2 * math.pi)
    cr.fill()
    cr.restore()


def _draw_face(cr, palette, squint):
    cr.set_source_rgb(*palette.face)
    cr.set_line_cap(cairo.LINE_CAP_ROUND)
    eye_y = -RY * 0.1
    for x in (-RX * 0.34, RX * 0.34):
        if squint:
            cr.set_line_width(2.8)
            cr.move_to(x - 5, eye_y + 2)
            cr.line_to(x, eye_y - 3)
            cr.line_to(x + 5, eye_y + 2)
            cr.stroke()
        else:
            cr.save()
            cr.translate(x, eye_y)
            cr.scale(4.2, 6.0)
            cr.arc(0, 0, 1, 0, 2 * math.pi)
            cr.restore()
            cr.fill()
    cr.set_line_width(3.0)
    cr.arc(0, RY * 0.05, RX * 0.36, math.radians(25), math.radians(155))
    cr.stroke()
