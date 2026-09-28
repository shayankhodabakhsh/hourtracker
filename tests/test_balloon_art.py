import unittest

import cairo

from hourtracker import balloon_art as art


def render(**pose):
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, art.WIDTH, art.HEIGHT)
    art.draw_balloon(cairo.Context(surface), art.PALETTES[art.DEFAULT_COLOR], **pose)
    surface.flush()
    return surface


def alpha(surface, x, y):
    # ARGB32 is stored little-endian as B, G, R, A.
    return surface.get_data()[y * surface.get_stride() + x * 4 + 3]


def body_width(surface):
    columns = [x for x in range(art.WIDTH) if alpha(surface, x, art.CENTER_Y) > 128]
    return max(columns) - min(columns)


class BalloonArtTest(unittest.TestCase):
    def test_body_is_opaque_and_corners_are_transparent(self):
        surface = render()
        self.assertEqual(alpha(surface, art.CENTER_X, art.CENTER_Y - 30), 255)
        self.assertEqual(alpha(surface, 0, 0), 0)
        self.assertEqual(alpha(surface, art.WIDTH - 1, art.HEIGHT - 1), 0)

    def test_squash_makes_it_wider(self):
        self.assertGreater(body_width(render(squash=0.2)), body_width(render()) + 10)

    def test_every_palette_and_pose_draws(self):
        for palette in art.PALETTES.values():
            surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, art.WIDTH, art.HEIGHT)
            art.draw_balloon(cairo.Context(surface), palette,
                             squash=-0.15, tilt=0.3, squint=True)

    def test_input_rects_cover_the_body_but_not_the_corners(self):
        rects = art.input_rects()

        def inside(px, py):
            return any(x <= px < x + w and y <= py < y + h for x, y, w, h in rects)

        self.assertTrue(inside(art.CENTER_X, art.CENTER_Y))
        self.assertFalse(inside(2, 2))
        self.assertFalse(inside(art.WIDTH - 2, art.HEIGHT - 2))
