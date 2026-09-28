import unittest

from hourtracker.physics import Spring


def simulate(spring, seconds, fps=60):
    """Run the spring and return the largest |value| seen."""
    peak = 0.0
    for _ in range(int(seconds * fps)):
        spring.step(1 / fps)
        peak = max(peak, abs(spring.value))
    return peak


def squish_spring():
    return Spring(stiffness=220, damping=7, limit=0.3)


class SpringTest(unittest.TestCase):
    def test_a_kick_wobbles_then_settles(self):
        spring = squish_spring()
        spring.kick(3.2, max_velocity=4.0)
        self.assertGreater(simulate(spring, 1.5), 0.1)
        self.assertTrue(spring.settled)

    def test_it_overshoots_like_jelly(self):
        spring = squish_spring()
        spring.kick(3.2, max_velocity=4.0)
        values = []
        for _ in range(60):
            spring.step(1 / 60)
            values.append(spring.value)
        self.assertLess(min(values), -0.02)    # swings past rest the other way

    def test_rapid_kicks_are_capped(self):
        spring = squish_spring()
        for _ in range(20):
            spring.kick(3.2, max_velocity=4.0)
        self.assertEqual(spring.velocity, 4.0)
        self.assertLessEqual(simulate(spring, 1.0), 0.3)

    def test_follows_a_target(self):
        spring = Spring(stiffness=60, damping=6, limit=0.4)
        spring.target = 0.3
        simulate(spring, 4.0)
        self.assertAlmostEqual(spring.value, 0.3, places=2)
