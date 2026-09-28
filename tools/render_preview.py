"""Render every balloon color in several poses to PNG contact sheets.

    /usr/bin/python3 tools/render_preview.py [OUTDIR]
"""
import os
import sys

import cairo

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from hourtracker import balloon_art as art  # noqa: E402

POSES = {
    "rest": {},
    "squished": {"squash": 0.22, "squint": True},
    "stretched": {"squash": -0.15},
    "lean_left": {"tilt": -0.3},
    "lean_right": {"tilt": 0.3},
}
BACKGROUNDS = {"dark": (0.12, 0.12, 0.13), "light": (0.96, 0.96, 0.95)}
SCALE = 2


def main(outdir):
    os.makedirs(outdir, exist_ok=True)
    for bg_name, bg in BACKGROUNDS.items():
        for color, palette in art.PALETTES.items():
            surface = cairo.ImageSurface(cairo.FORMAT_ARGB32,
                                         art.WIDTH * SCALE * len(POSES),
                                         art.HEIGHT * SCALE)
            cr = cairo.Context(surface)
            cr.set_source_rgb(*bg)
            cr.paint()
            cr.scale(SCALE, SCALE)
            for i, pose in enumerate(POSES.values()):
                cr.save()
                cr.translate(i * art.WIDTH, 0)
                art.draw_balloon(cr, palette, **pose)
                cr.restore()
            path = os.path.join(outdir, f"balloon_{color}_{bg_name}.png")
            surface.write_to_png(path)
            print(path)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "build/previews")
