"""The Blinky 2350's LED panel is NOT a clean 39x26 rectangle - five
physical buttons are embedded directly in the grid's footprint (genuine
notches cut into the panel, not just caps resting atop present LEDs).

Confirmed live on 2026-10-02 by photographing the badge with every LED lit
to 50% brightness, which makes the panel's actual silhouette obvious. See
the SkolDisplayWDDDK repo's docs/DEVICE_SPECS.md (commit around that date)
for the photos this was derived from and the full writeup.

Regions below are in the logical 39x26 `(x, y)` coordinate space, as
(x0, y0, x1, y1) inclusive-exclusive rectangles - estimated from photo
proportions against the known grid size, NOT precision-measured. Good
enough to design around, not pixel-exact.
"""

DEAD_ZONES = [
    (34, 5, 39, 10),   # right button, upper
    (34, 13, 39, 18),  # right button, lower
    (10, 22, 14, 26),  # bottom button, left
    (18, 22, 22, 26),  # bottom button, middle
    (26, 22, 30, 26),  # bottom button, right
]


def is_dead_zone(x, y):
    for x0, y0, x1, y1 in DEAD_ZONES:
        if x0 <= x < x1 and y0 <= y < y1:
            return True
    return False
