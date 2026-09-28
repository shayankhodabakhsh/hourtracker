"""A damped spring, used to make the balloon squish, wobble, and sway."""


class Spring:
    """Pulls `value` toward `target` and overshoots a little, like jelly."""

    def __init__(self, stiffness: float, damping: float, limit: float = 1.0):
        self.stiffness = stiffness
        self.damping = damping
        self.limit = limit          # |value| never goes past this
        self.value = 0.0
        self.velocity = 0.0
        self.target = 0.0

    def kick(self, velocity: float, max_velocity: float) -> None:
        """Add a push. Repeated pushes stack, up to max_velocity."""
        self.velocity = max(-max_velocity, min(max_velocity, self.velocity + velocity))

    def step(self, dt: float) -> None:
        """Advance the simulation by dt seconds, in small sub-steps."""
        steps = max(1, int(dt / 0.004))
        h = dt / steps
        for _ in range(steps):
            force = (-self.stiffness * (self.value - self.target)
                     - self.damping * self.velocity)
            self.velocity += force * h
            self.value = max(-self.limit, min(self.limit, self.value + self.velocity * h))

    @property
    def settled(self) -> bool:
        """Close enough to rest that another frame wouldn't show a change."""
        return abs(self.value - self.target) < 0.002 and abs(self.velocity) < 0.03

    def settle(self) -> None:
        self.value, self.velocity = self.target, 0.0
