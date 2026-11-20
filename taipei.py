#!/usr/bin/env python3
"""
ASCII Taipei - a night view of Taipei drawn stage by stage with coloured
ASCII characters: Guanyin Mountain, the Tamsui River, the Grand Hotel, an
MRT train, Taipei 101 lighting up floor by floor, a countdown and fireworks.

    pip install numpy
    python taipei.py                      # Ctrl+C to quit
    python taipei.py --speed 1.5 --fps 24
    python taipei.py --once --at 31       # print one frame and exit

    pip install numpy pillow              # plus ffmpeg, to record a video
    python taipei.py --record taipei.mp4 --tag @yourname
    python taipei.py --record taipei.mp4 --code   # with the source typing out below
    python taipei.py --record still.png --at 31
    python taipei.py --record music.wav           # just the soundtrack

How it works
    1. The scene is built once for the terminal size as a stack of layers.
       Every cell of a layer holds a character, a colour and a reveal
       "order" between 0 and 1.
    2. A timeline splits the 39-second loop into stages. A stage's progress
       p shows the cells whose order <= p, so mountains sweep in from the
       left, buildings grow upwards and Taipei 101 is built floor by floor.
       The newest cells flash white like a pen tip.
    3. Moving things (stars, moon, Ferris wheel, MRT train, meteor,
       fireworks) are drawn on top each frame, then the river mirrors
       whatever is lit above it, broken up by waves.
    4. The frame is printed with 24-bit ANSI colour codes.

Needs a terminal with 24-bit colour (Windows Terminal, VS Code, iTerm2,
macOS Terminal, most Linux terminals). Make the window big (120x40 or more)
and the font small for the best look.
"""

import argparse
import colorsys
import math
import os
import re
import shutil
import subprocess
import sys
import time

import numpy as np

ASPECT = 2.0  # a terminal cell is about twice as tall as it is wide

# ------------------------------------------------------------------ timeline
STAGES = [  # name, start, end (seconds)
    ("sky", 0.0, 3.0),
    ("mountains", 1.5, 5.0),
    ("river", 4.0, 7.0),
    ("city", 6.0, 11.0),
    ("grand_hotel", 10.0, 13.5),
    ("taipei101", 13.0, 18.0),
    ("lights", 18.0, 21.5),
    ("mrt", 21.5, 24.0),
    ("countdown", 24.0, 29.0),
    ("fireworks", 29.0, 36.5),
    ("new_year", 30.5, 36.5),
]
STAGE_T = {name: (a, b) for name, a, b in STAGES}
LOOP = 39.0
FADE = 37.0  # everything fades out from here, then the loop starts again
METEOR = 22.2

# ------------------------------------------------------------------ palette
STAR = (0.80, 0.85, 1.00)
MOON = (1.00, 0.93, 0.70)
RIDGE = (0.36, 0.44, 0.68)
HILLSIDE = (0.13, 0.16, 0.28)
WALL = (0.40, 0.45, 0.64)
WIN_OFF = (0.20, 0.23, 0.36)
WIN_ON = [(1.00, 0.80, 0.42), (1.00, 0.90, 0.62), (0.92, 0.95, 1.00), (0.55, 0.80, 1.00)]
TREES = (0.10, 0.26, 0.16)
STONE = (0.55, 0.52, 0.48)
RED = (0.90, 0.16, 0.12)
GOLD = (0.98, 0.70, 0.18)
ORANGE = (0.92, 0.48, 0.12)
AMBER_OFF = (0.36, 0.22, 0.10)
AMBER_ON = (1.00, 0.72, 0.32)
GLASS = (0.20, 0.42, 0.40)
GLASS_EDGE = (0.38, 0.62, 0.58)
STEEL = (0.62, 0.66, 0.74)
TRACK = (0.30, 0.32, 0.44)
WATER = np.array([0.10, 0.22, 0.45], np.float32)
HUD = (0.45, 0.50, 0.64)
WHITE = (1.00, 1.00, 1.00)

# Fireworks: seconds after the fireworks stage starts, x and y as fractions of
# the screen, hue, number of sparks, speed. A fixed list (not random) so the
# terminal, the video, the web page and the soundtrack all agree on when
# and where every shell bursts.
SHELLS = [
    (1.02, 0.161, 0.231, 0.335, 70, 0.235), (1.16, 0.474, 0.336, 0.316, 54, 0.236),
    (1.43, 0.894, 0.146, 0.779, 69, 0.175), (1.87, 0.656, 0.165, 0.176, 78, 0.193),
    (2.14, 0.638, 0.398, 0.087, 51, 0.243), (2.32, 0.371, 0.256, 0.555, 50, 0.187),
    (2.63, 0.814, 0.258, 0.336, 76, 0.229), (3.05, 0.526, 0.157, 0.511, 61, 0.178),
    (3.19, 0.355, 0.142, 0.702, 52, 0.245), (3.58, 0.164, 0.209, 0.424, 62, 0.241),
    (4.00, 0.474, 0.163, 0.906, 52, 0.195), (4.17, 0.233, 0.174, 0.744, 73, 0.194),
    (4.59, 0.660, 0.244, 0.106, 55, 0.192), (4.87, 0.411, 0.260, 0.713, 63, 0.214),
    (5.13, 0.697, 0.189, 0.559, 65, 0.202), (5.29, 0.806, 0.361, 0.466, 56, 0.181),
    (5.68, 0.846, 0.323, 0.623, 75, 0.195), (5.93, 0.493, 0.149, 0.619, 70, 0.242),
    (6.25, 0.642, 0.317, 0.265, 51, 0.195), (6.70, 0.656, 0.396, 0.189, 74, 0.204),
]
FINALE_SHELL = (6.10, 0.120, 90, 0.298)   # time, hue, sparks, speed; bursts at 101's spire

DIGITS = {  # 3x5 font for the countdown on Taipei 101's face
    "1": [".#.", "##.", ".#.", ".#.", "###"],
    "2": ["###", "..#", "###", "#..", "###"],
    "3": ["###", "..#", ".##", "..#", "###"],
    "4": ["#.#", "#.#", "###", "..#", "..#"],
    "5": ["###", "#..", "###", "..#", "###"],
}


def clamp01(v):
    return min(max(v, 0.0), 1.0)


def smooth(v):
    v = clamp01(v)
    return v * v * (3 - 2 * v)


def hash01(a, b):
    """Repeatable pseudo-random number in [0, 1); index.html uses the same formula."""
    v = np.sin(np.asarray(a) * 12.9898 + b * 78.233) * 43758.5453
    return v - np.floor(v)


def stage_progress(name, t):
    a, b = STAGE_T[name]
    return clamp01((t - a) / (b - a))


def hsv(h, s=1.0, v=1.0):
    return colorsys.hsv_to_rgb(h % 1.0, s, v)


def new_year():
    now = time.localtime()
    return now.tm_year if now.tm_mon <= 2 else now.tm_year + 1


# ------------------------------------------------------------------ layers
class Layer:
    """A character, a colour and a reveal order (0..1) per cell; inf = empty.
    A space with an order is solid: it hides whatever was drawn behind it."""

    def __init__(self, h, w):
        self.h, self.w = h, w
        self.ch = np.full((h, w), " ", "<U1")
        self.rgb = np.zeros((h, w, 3), np.float32)
        self.order = np.full((h, w), np.inf, np.float32)

    def put(self, y, x, c, rgb, order):
        if 0 <= y < self.h and 0 <= x < self.w:
            self.ch[y, x] = c
            self.rgb[y, x] = rgb
            self.order[y, x] = order


class Canvas:
    def __init__(self, h, w):
        self.h, self.w = h, w
        self.ch = np.full((h, w), " ", "<U1")
        self.rgb = np.zeros((h, w, 3), np.float32)

    def blit(self, layer, p, tip=0.05):
        """Show the cells of a layer whose order <= p; the newest ones glow."""
        if p <= 0:
            return
        m = layer.order <= p
        self.ch[m] = layer.ch[m]
        self.rgb[m] = layer.rgb[m]
        if p < 1 and tip > 0:
            fresh = m & (layer.order > p - tip)
            self.rgb[fresh] = self.rgb[fresh] * 0.3 + 0.85

    def put(self, y, x, c, rgb):
        y, x = int(round(y)), int(round(x))
        if 0 <= y < self.h and 0 <= x < self.w:
            self.ch[y, x] = c
            self.rgb[y, x] = rgb

    def spark(self, y, x, c, rgb):
        """Like put, but only if brighter than what is already there (light adds up)."""
        y, x = int(round(y)), int(round(x))
        if 0 <= y < self.h and 0 <= x < self.w and max(rgb) >= self.rgb[y, x].max():
            self.ch[y, x] = c
            self.rgb[y, x] = rgb

    def text(self, y, x, s, rgb):
        for i, c in enumerate(s):
            if c != " ":
                self.put(y, x + i, c, rgb)


def edge_char(top, left, right):
    """Character for a ridge cell given its own and its neighbours' top rows."""
    if left > top and right > top:
        return "^"
    if left > top:
        return "/"
    if right > top:
        return "\\"
    return "_"


# ------------------------------------------------------------------ scene
class Scene:
    def __init__(self, w, h, tag="", seed=101, hud=True):
        self.w, self.h, self.tag, self.hud = w, h, tag, hud
        self.hz = int(round(h * 0.70))   # first row of the river
        self.S = h * ASPECT               # scene height measured in columns
        self.Sx = min(self.S, 1.1 * w)    # size scale that still fits a narrow (phone) screen
        self.x101 = int(round(w * 0.77))
        self.xhotel = int(round(w * 0.22))
        self.xwheel = int(round(w * 0.52))
        self.year = new_year()
        rng = np.random.default_rng(seed)
        self._stars(rng)
        self.mountains = self._mountains(rng)
        self.city, self.city_win = self._city(rng)
        self.hotel, self.hotel_win = self._hotel(rng)
        self.t101 = self._taipei101()
        self.viaduct = self._viaduct()
        self._fireworks()

    # ---------------------------------------------------------- static parts
    def _stars(self, rng):
        n = int(self.w * self.hz * 0.025)
        self.star_y = rng.integers(0, self.hz - 2, n)
        self.star_x = rng.integers(0, self.w, n)
        self.star_phase = rng.uniform(0, 2 * math.pi, n)
        self.star_rate = rng.uniform(1.0, 3.0, n)
        self.star_order = rng.uniform(0, 1, n)

    def _mountains(self, rng):
        W, H, hz = self.w, self.h, self.hz
        L = Layer(H, W)
        x = np.linspace(0, 1, W)

        def bump(c, s, a):
            return a * np.exp(-((x - c) / s) ** 2)

        # Guanyin Mountain on the left, lower hills across the rest
        prof = (bump(0.04, 0.07, 0.24) + bump(0.15, 0.06, 0.33) + bump(0.30, 0.08, 0.25)
                + bump(0.42, 0.06, 0.10) + bump(0.62, 0.20, 0.05) + bump(0.95, 0.09, 0.10) + 0.02)
        ridge = np.clip(np.round(hz - 1 - prof * self.Sx / ASPECT).astype(int), 1, hz - 1)
        for xi in range(W):
            top = ridge[xi]
            left = ridge[xi - 1] if xi > 0 else top
            right = ridge[xi + 1] if xi < W - 1 else top
            c = edge_char(top, left, right)
            low = max(top, max(left, right) - 1)
            for y in range(top, hz):
                o = 0.92 * xi / W + 0.08 * (y - top) / max(1, hz - top)
                if y <= low:
                    cc = c if y == top or c != "^" else ("/" if left >= right else "\\")
                    L.put(y, xi, cc, RIDGE, o)
                elif rng.random() < 0.16:
                    k = 1 - 0.4 * (y - top) / max(1, hz - top)
                    L.put(y, xi, rng.choice([".", ":", "'"]), tuple(v * k for v in HILLSIDE), o)
                else:
                    L.put(y, xi, " ", (0, 0, 0), o)
        return L

    def _building(self, L, win, rng, x0, bw, bh, st):
        hz = self.hz
        top, x1 = hz - bh, x0 + bw - 1
        for y in range(top, hz):
            o = st + 0.36 * (hz - 1 - y) / max(bh - 1, 1)
            for x in range(x0, x1 + 1):
                if y == top:
                    if x0 < x < x1:
                        L.put(y, x, "_", WALL, o)
                elif x in (x0, x1):
                    L.put(y, x, "|", WALL, o)
                elif (x - x0) % 2 == 1 and (y - top) % 2 == 0:
                    L.put(y, x, ":", WIN_OFF, o)
                    if rng.random() < 0.8:
                        rgb = WIN_ON[rng.choice(4, p=[0.45, 0.25, 0.18, 0.12])]
                        win.put(y, x, "#" if rng.random() < 0.7 else "=", rgb, rng.random())
                else:
                    L.put(y, x, " ", (0, 0, 0), o)
        if bh >= 0.15 * self.h and rng.random() < 0.7:
            xc = x0 + bw // 2
            L.put(top - 1, xc, "|", WALL, st + 0.37)
            self.blinkers.append((top - 2, xc, L, top - 1, rng.uniform(0, 1)))

    def _city(self, rng):
        W, H, hz = self.w, self.h, self.hz
        L, win = Layer(H, W), Layer(H, W)
        self.blinkers = []
        x = 0
        while x < W:
            bw = int(rng.integers(3, 8))
            near = math.exp(-(((x + bw / 2) / W - self.x101 / W) / 0.15) ** 2)
            hmax = 0.12 + 0.14 * near   # Xinyi's towers cluster around 101
            bh = max(3, int(round(rng.uniform(0.4, 1.0) * hmax * H)))
            self._building(L, win, rng, x, bw, bh, rng.uniform(0, 0.62))
            x += bw + int(rng.integers(0, 2))
        # the mall under the Ferris wheel
        self.wheel_r = max(4, int(round(0.07 * self.Sx)))
        mw = 2 * self.wheel_r + 5
        self.mall_top = hz - 4
        self._building(L, win, rng, self.xwheel - mw // 2, mw, 4, 0.6)
        return L, win

    def _hotel(self, rng):
        """The Grand Hotel on its hill: red columns under a golden double roof."""
        W, H, hz = self.w, self.h, self.hz
        L, win = Layer(H, W), Layer(H, W)
        xc = self.xhotel
        a, b = max(10, round(0.19 * self.Sx)), max(3, round(0.08 * H))
        tops = {}
        for x in range(xc - a - 1, xc + a + 2):
            u = (x - xc) / a
            tops[x] = int(round(hz - 1 - b * math.sqrt(max(0.0, 1 - u * u)))) if abs(u) <= 1 else hz
        for x in range(xc - a, xc + a + 1):
            top = tops[x]
            c = edge_char(top, tops[x - 1], tops[x + 1])
            low = max(top, max(tops[x - 1], tops[x + 1]) - 1)
            o = 0.30 * (x - xc + a) / (2 * a)
            for y in range(top, hz):
                if y <= low:
                    L.put(y, x, c if y == top else ("/" if x < xc else "\\"), (0.22, 0.42, 0.28), o)
                elif rng.random() < 0.35:
                    L.put(y, x, rng.choice([".", ",", ":", "*"]), TREES, o)
                else:
                    L.put(y, x, " ", (0, 0, 0), o)

        hw = max(6, round(0.115 * self.Sx))
        nb = max(2, round(0.045 * H))
        spec = ([("base", hw + 1)] + [("body", hw)] * nb
                + [("eave", hw + 2), ("roof", round(hw * 0.82)), ("floor", round(hw * 0.55)),
                   ("eave", round(hw * 0.62) + 2), ("roof", round(hw * 0.62)), ("ridge", round(hw * 0.40))])
        y = hz - 1 - b
        n = len(spec)
        for i, (kind, half) in enumerate(spec):
            xl, xr = xc - half, xc + half
            for x in range(xl, xr + 1):
                o = 0.32 + 0.66 * i / (n - 1) + 0.02 * abs(x - xc) / half
                if kind == "base":
                    L.put(y, x, "=", STONE, o)
                elif kind in ("body", "floor"):
                    step = 3 if kind == "body" else 2
                    if x in (xl, xr) or (x - xl) % step == 0:
                        L.put(y, x, "|", RED, o)
                    else:
                        L.put(y, x, ":", AMBER_OFF, o)
                        win.put(y, x, "#", AMBER_ON, rng.uniform(0, 0.7))
                elif kind == "eave":
                    c = "`" if x == xl else ("'" if x == xr else "~")
                    L.put(y, x, c, ORANGE, o)
                elif kind == "roof":
                    c = "/" if x == xl else ("\\" if x == xr else "=")
                    L.put(y, x, c, GOLD if c == "=" else ORANGE, o)
                else:  # ridge
                    L.put(y, x, "^" if x in (xl, xr) else "-", GOLD if x in (xl, xr) else RED, o)
            y -= 1
        return L, win

    def _taipei101(self):
        """Podium, eight flared segments (eight floors each in real life), cap and spire."""
        W, H, hz = self.w, self.h, self.hz
        L = Layer(H, W)
        self.seg_id = np.full((H, W), -1, np.int8)
        self.lamp = np.zeros((H, W), bool)
        xc = self.x101
        ytop = max(3, int(round(0.07 * H)))
        yb = hz - 1
        h = yb - ytop + 1
        spire = max(3, round(0.13 * h))
        hs = max(1, (h - spire - 2 - 3) // 8)
        pod = h - spire - 2 - 8 * hs
        wt = max(3.0, 0.058 * h * ASPECT)
        wb = wt - 1.0

        rows, y = [], yb   # bottom to top: (y, kind, segment, half width, ledge?)
        for j in range(pod):
            half = (wt + 1.6) - 2.0 * j / max(pod - 1, 1)
            rows.append((y, "pod", 0, half, j == pod - 1))
            y -= 1
        for k in range(8):
            for j in range(hs):
                half = wb + (wt - wb) * j / max(hs - 1, 1)
                rows.append((y, "seg", k + 1, half, j == hs - 1))
                y -= 1
        rows.append((y, "cap", 9, wt * 0.62, False))
        rows.append((y - 1, "cap", 9, wt * 0.42, True))
        y -= 2
        while y >= ytop:
            rows.append((y, "spire", 9, 0, False))
            y -= 1

        self.ledges = []   # (y, xl, xr) of every segment's top, bottom to top
        n = len(rows)
        for i, (y, kind, seg, half, ledge) in enumerate(rows):
            o = i / (n - 1)
            hr = int(half + 0.5)
            xl, xr = xc - hr, xc + hr
            if kind == "spire":
                L.put(y, xc, "|", STEEL, o)
                self.seg_id[y, xc], self.lamp[y, xc] = seg, True
                continue
            if ledge and kind == "seg":
                self.ledges.append((y, xl, xr))
            for x in range(xl, xr + 1):
                if x in (xl, xr):
                    c = {"pod": "/\\", "seg": "\\/", "cap": "[]"}[kind][x == xr]
                    rgb = GLASS_EDGE
                elif ledge:
                    c, rgb = "=", GLASS_EDGE
                else:
                    c, rgb = ("|" if (x - xc) % 2 == 0 else ":"), GLASS
                L.put(y, x, c, rgb, o + 0.01 * abs(x - xc) / max(hr, 1))
                self.seg_id[y, x] = seg
                self.lamp[y, x] = x in (xl, xr) or ledge
        y_pod_top = yb - pod + 1
        if pod >= 3:   # the giant "ruyi" coin above the entrance
            L.put(y_pod_top + 1, xc, "O", GOLD, (pod - 2) / (n - 1))
        self.spire_top = ytop
        self.blinkers.append((ytop - 1, xc, L, ytop, 0.0))
        seg_rows = [r for r in rows if r[1] == "seg"]
        mid = [r[0] for r in seg_rows if r[2] in (4, 5)]
        self.digit_y = int(round(sum(mid) / len(mid))) if mid else (yb + ytop) // 2
        self.digit_pw = 2 if 2 * int(wb + 0.5) - 1 >= 6 else 1
        return L

    def _viaduct(self):
        W, H, hz = self.w, self.h, self.hz
        L = Layer(H, W)
        for x in range(W):
            o = x / W
            L.put(hz - 2, x, "=", TRACK, o)
            if x % 11 == 5:
                L.put(hz - 1, x, "|", TRACK, o)
        return L

    def _fireworks(self):
        W, H, S = self.w, self.h, math.sqrt(self.S * self.Sx)
        t0 = STAGE_T["fireworks"][0]
        self.flares = []   # 101's side-firing flares: (time, x, y, direction, hue)
        for wave, (start, step, hue) in enumerate([(0.0, 0.10, 0.12), (2.6, -0.10, 0.58), (5.0, 0.08, -1)]):
            order = self.ledges if step > 0 else self.ledges[::-1]
            for i, (y, xl, xr) in enumerate(order):
                tb = t0 + start + abs(step) * i
                hh = (i / 8) if hue < 0 else hue
                self.flares.append((tb, xl - 1, y, -1, hh))
                self.flares.append((tb, xr + 1, y, 1, hh))
        self.shells = []   # (time, x0, y0, hue, angles, speeds, life)
        for k, (dt, xf, yf, hue, n, sp) in enumerate(SHELLS):
            i = np.arange(n)
            ang = 2 * math.pi * i / n + 0.3 * hash01(i, k)
            spd = (0.7 + 0.3 * hash01(i + 101, k)) * sp * S
            self.shells.append((t0 + dt, xf * W, yf * H, hue, ang, spd, 1.8))
        dt, hue, n, sp = FINALE_SHELL   # a golden chrysanthemum from the top of 101
        i = np.arange(n)
        self.shells.append((t0 + dt, self.x101, self.spire_top + 2, hue, 2 * math.pi * i / n,
                            (0.8 + 0.2 * hash01(i + 101, len(SHELLS))) * sp * S, 2.4))

    # ---------------------------------------------------------- per frame
    def frame(self, t):
        t %= LOOP
        cv = Canvas(self.h, self.w)
        P = {name: stage_progress(name, t) for name in STAGE_T}
        self._draw_stars(cv, t, P["sky"])
        self._draw_moon(cv, t)
        cv.blit(self.mountains, P["mountains"])
        cv.blit(self.city, P["city"])
        cv.blit(self.city_win, P["lights"], tip=0)
        self._draw_wheel(cv, t, clamp01((P["city"] - 0.55) / 0.45))
        cv.blit(self.hotel, P["grand_hotel"])
        cv.blit(self.hotel_win, P["lights"], tip=0)
        cv.blit(self.t101, P["taipei101"])
        self._light_101(cv, t, P)
        self._draw_blinkers(cv, t, P)
        cv.blit(self.viaduct, clamp01(P["mrt"] / 0.4))
        self._draw_train(cv, t)
        self._draw_meteor(cv, t)
        self._draw_fireworks(cv, t)
        self._draw_river(cv, t, P["river"])
        self._draw_greeting(cv, t, P["new_year"])
        if t > FADE:
            cv.rgb *= 1 - smooth((t - FADE) / (LOOP - FADE))
        if self.hud:
            self._draw_hud(cv, t)
        return cv

    def _draw_stars(self, cv, t, p):
        tw = 0.55 + 0.45 * np.sin(t * self.star_rate + self.star_phase)
        for y, x, b, o in zip(self.star_y, self.star_x, tw, self.star_order):
            if o <= p:
                c = "*" if b > 0.92 else ("+" if b > 0.7 else ".")
                cv.put(y, x, c, tuple(v * (0.35 + 0.65 * b) for v in STAR))

    def _draw_moon(self, cv, t):
        r = max(4.0, 0.075 * self.Sx)
        xm = 0.37 * self.w
        y_end = 0.20 * self.h
        ym = self.hz - 1 - (self.hz - 1 - y_end) * smooth(t / 6.0)
        y0, y1 = int(ym - r / ASPECT) - 1, int(ym + r / ASPECT) + 2
        for y in range(max(0, y0), min(self.hz, y1)):
            for x in range(int(xm - r) - 1, int(xm + r) + 2):
                dx, dy = (x - xm) / r, (y - ym) * ASPECT / r
                d = dx * dx + dy * dy
                shadow = (dx + 0.62) ** 2 + (dy - 0.10) ** 2
                if d > 1 or shadow < 0.72:
                    continue
                depth = min(1 - d, shadow - 0.72)   # distance from either edge
                c = "@" if depth > 0.22 else ("#" if depth > 0.12 else ("*" if depth > 0.05 else "."))
                k = 0.75 + 0.25 * min(1.0, depth * 5)
                cv.put(y, x, c, tuple(v * k for v in MOON))

    def _draw_wheel(self, cv, t, p):
        """The Ferris wheel in Dazhi, revealed as it sweeps round."""
        if p <= 0:
            return
        R, xc = self.wheel_r, self.xwheel
        ry = R / ASPECT
        yc = self.mall_top - 1 - ry
        rot = t * 0.35
        for side in (-1, 1):   # the two legs
            for j in range(1, int(ry) + 3):
                if yc + j >= self.mall_top:
                    break
                cv.put(yc + j, xc + side * j * 0.6 * R / (ry + 2), "/" if side < 0 else "\\", STEEL)
        n = int(2 * math.pi * R * 1.4)
        for i in range(n):
            a = 2 * math.pi * i / n
            if a / (2 * math.pi) <= p:
                cv.put(yc + ry * math.sin(a + rot), xc + R * math.cos(a + rot), ".", (0.55, 0.62, 0.80))
        for i in range(8):   # spokes
            a = rot + i * math.pi / 4
            if (i / 8) > p:
                continue
            deg = (math.degrees(a) % 180)
            c = "-" if deg < 22.5 or deg >= 157.5 else ("\\" if deg < 67.5 else ("|" if deg < 112.5 else "/"))
            for f in (0.35, 0.55, 0.75):
                cv.put(yc + ry * f * math.sin(a), xc + R * f * math.cos(a), c, (0.40, 0.45, 0.60))
        for i in range(16):   # cabins
            a = rot + i * math.pi / 8
            if (i / 16) <= p:
                cv.put(yc + ry * math.sin(a), xc + R * math.cos(a), "o", hsv(i / 16 + t * 0.1, 0.6, 1.0))
        cv.put(yc, xc, "@", WHITE)

    def _light_101(self, cv, t, P):
        lp = P["lights"]
        vis = (self.t101.order <= P["taipei101"]) & (self.seg_id >= 0)
        if lp <= 0 or not vis.any():
            return
        k = np.arange(10)
        if P["fireworks"] > 0:      # gold shimmer during the fireworks
            v = 0.75 + 0.25 * np.sin(t * 9 + k * 1.3)
            table = np.array([hsv(0.11 + 0.02 * np.sin(t * 3 + kk), 0.65, vv) for kk, vv in zip(k, v)])
        elif P["countdown"] > 0:    # almost dark so the digits stand out
            table = np.tile(np.array([0.30, 0.30, 0.30]), (10, 1))
        else:                       # a slowly moving rainbow, bottom to top
            table = np.array([hsv(kk / 10 + 0.05 * t, 0.55, 1.0) for kk in k])
        table = table.astype(np.float32)
        on = vis & (self.seg_id < lp * 10)
        lamp, glass = on & self.lamp, on & ~self.lamp
        cv.rgb[lamp] = table[self.seg_id[lamp]]
        cv.rgb[glass] = cv.rgb[glass] * (0.35 if 0 < P["countdown"] < 1 else 0.6) + table[self.seg_id[glass]] * 0.35

        cd = P["countdown"]
        if 0 < cd < 1:
            n = 5 - min(4, int(cd * 5))
            pulse = 1 - 0.55 * ((cd * 5) % 1)
            pw = self.digit_pw
            x0 = self.x101 - (3 * pw) // 2
            for r, line in enumerate(DIGITS[str(n)]):
                for c, bit in enumerate(line):
                    for q in range(pw):
                        if bit == "#":
                            cv.put(self.digit_y - 2 + r, x0 + c * pw + q, "#",
                                   (1.0 * pulse, 0.95 * pulse, 0.80 * pulse))
                        else:
                            cv.put(self.digit_y - 2 + r, x0 + c * pw + q, " ", (0, 0, 0))

    def _draw_blinkers(self, cv, t, P):
        for y, x, layer, below, ph in self.blinkers:
            p = P["taipei101"] if layer is self.t101 else P["city"]
            if layer.order[below, x] <= p and (t * 1.1 + ph) % 1 < 0.45:
                cv.put(y, x, "*", (1.0, 0.18, 0.15))

    def _draw_train(self, cv, t):
        a, b = STAGE_T["mrt"]
        start = a + 0.4 * (b - a)
        if t < start:
            return
        cars = 3 if self.w >= 80 else 2
        body = "<" + "[#=#=#=#]" * cars
        speed = 0.22 * self.Sx
        span = self.w + len(body) + 0.4 * self.w
        x = self.w - ((t - start) * speed) % span
        y = self.hz - 3
        for i, c in enumerate(body):
            if c == "<":
                rgb = WHITE
            elif c == "#":
                rgb = (1.0, 0.86, 0.55)
            else:
                rgb = (0.75, 0.78, 0.86)
            cv.put(y, x + i, c, rgb)
        cv.put(y, x + len(body), "]", (1.0, 0.2, 0.15))

    def _draw_meteor(self, cv, t):
        a = t - METEOR
        if not 0 <= a < 1.3:
            return
        x0, y0 = 0.66 * self.w, 0.04 * self.h
        x1, y1 = 0.40 * self.w, 0.30 * self.h
        q = a / 1.3
        hx, hy = x0 + (x1 - x0) * q, y0 + (y1 - y0) * q
        dx, dy = x1 - x0, (y1 - y0) * ASPECT
        ln = math.hypot(dx, dy)
        ux, uy = dx / ln, dy / ln / ASPECT
        deg = math.degrees(math.atan2(dy, dx)) % 180
        c = "-" if deg < 22.5 or deg >= 157.5 else ("\\" if deg < 67.5 else ("|" if deg < 112.5 else "/"))
        fade = 1 - q * q
        for j in range(1, 12):
            k = (1 - j / 12) * fade
            cv.put(hy - uy * j, hx - ux * j, c, (0.75 * k, 0.85 * k, 1.0 * k))
        cv.put(hy, hx, "*", tuple(v * fade for v in WHITE))

    def _draw_fireworks(self, cv, t):
        hz, g = self.hz, 0.08 * self.h
        for tb, x, y, d, hue in self.flares:
            a = t - tb
            if not 0 <= a < 1.1:
                continue
            for j in range(6):
                aj = a - j * 0.05
                if aj < 0:
                    continue
                f = (1 - math.exp(-2.5 * aj)) / 2.5
                px = x + d * 0.22 * self.Sx * f
                py = y + 0.25 * g * aj * aj
                k = (1 - a / 1.1) * (1 - j * 0.14)
                rgb = hsv(hue, 0.35 + 0.15 * j, k)
                cv.spark(py, px, "=" if j == 0 else "-", rgb)
        for tb, x0, y0, hue, ang, spd, life in self.shells:
            a = t - tb
            if -0.8 < a < 0:   # the rocket climbing
                q = 1 + a / 0.8
                ry = hz - 1 - (hz - 1 - y0) * (1 - (1 - q) ** 2)
                cv.spark(ry, x0, "|", (1.0, 0.85, 0.6))
                cv.spark(ry + 1, x0 + math.sin(t * 40) * 0.6, ".", (0.6, 0.45, 0.3))
                continue
            if not 0 <= a < life:
                continue
            q = a / life
            if a < 0.12:
                cv.spark(y0, x0, "@", WHITE)
            for lag, dim in ((0.0, 1.0), (0.08, 0.45)):
                al = max(0.0, a - lag)
                f = (1 - math.exp(-1.8 * al)) / 1.8
                px = x0 + np.cos(ang) * spd * f
                py = y0 + np.sin(ang) * spd * f / ASPECT + 0.5 * g * al * al
                if lag == 0:
                    c = "*" if q < 0.2 else ("+" if q < 0.45 else ("." if q < 0.75 else "'"))
                else:
                    c = "."
                v = (1 - q) ** 1.3 * dim
                rgb = hsv(hue, min(0.85, 0.15 + q * 2.5), v)
                for i, (xx, yy) in enumerate(zip(px, py)):
                    if q > 0.55 and (i * 7 + int(t * 24)) % 3 == 0:
                        continue   # glitter
                    if yy < hz - 2:
                        cv.spark(yy, xx, c, rgb)

    def _draw_river(self, cv, t, p):
        """Waves on the Tamsui River plus the reflection of everything above."""
        if p <= 0:
            return
        H, W, hz = self.h, self.w, self.hz
        ys = np.arange(hz, H)[:, None]
        xs = np.arange(W)[None, :]
        d = (ys - hz) / max(H - hz - 1, 1)
        wave = np.sin(xs * 0.42 + ys * 1.7 - t * 2.0) + 0.6 * np.sin(xs * 0.17 - ys * 0.9 + t * 1.3)
        ch = np.where(wave > 1.0, "~", np.where(wave > 0.25, "-", np.where(wave > -0.5, ".", " ")))
        rgb = WATER[None, None, :] * (0.55 + 0.3 * wave[..., None]) * (1 - 0.45 * d[..., None])

        my = np.clip(2 * hz - 3 - ys, 0, hz - 1)
        dx = np.round(np.sin(ys * 1.3 + t * 2.4 + xs * 0.05) * (0.5 + 1.6 * d)).astype(int)
        mx = np.clip(xs + dx, 0, W - 1)
        src = cv.rgb[my, mx]
        b = src.max(-1)
        refl = (b > 0.32) & (wave + 0.7 * np.sin(xs * 1.1 + t * 3.0) > -0.9)
        rch = np.where(b > 0.75, "|", np.where(b > 0.5, "!", ":"))
        ch = np.where(refl, rch, ch)
        rgb = np.where(refl[..., None], src * (0.75 - 0.4 * d[..., None]), rgb)

        edge = p * (W + 6) + 2 * np.sin(np.arange(hz, H) * 1.7)[:, None]
        show = xs < edge
        cv.ch[hz:] = np.where(show, ch, " ")
        cv.rgb[hz:] = np.where(show[..., None], rgb, 0)

    def _draw_greeting(self, cv, t, p):
        if p <= 0:
            return
        msg = f"HAPPY NEW YEAR {self.year}"
        n = int(len(msg) * clamp01(p * 4))
        y = max(2, int(round(0.06 * self.h)))
        x = (self.w - len(msg)) // 2
        for i, c in enumerate(msg[:n]):
            k = 0.85 + 0.15 * math.sin(t * 6 + i * 0.6)
            cv.put(y, x + i, c, hsv(0.12 + 0.02 * math.sin(t * 2 + i * 0.3), 0.55, k))
        if n < len(msg) and (t * 3) % 1 < 0.6:
            cv.put(y, x + n, "_", GOLD)
        if self.tag and p * 4 > 1.2:
            cv.text(y + 1, (self.w - len(self.tag)) // 2, self.tag, HUD)

    def _draw_hud(self, cv, t):
        name = "fade" if t >= FADE else max((s for s in STAGES if s[1] <= t), key=lambda s: s[1])[0]
        pct = 100 if name == "fade" else int(100 * stage_progress(name, t))
        n = int((cv.ch != " ").sum())
        lines = [f"taipei.py  stage {name:<11} {pct:3d}%", f"chars {n:6,d}   t {t:5.2f}s"]
        for i, s in enumerate(lines):
            cv.ch[i, : len(s) + 2] = " "
            cv.text(i, 1, s, HUD)


# ------------------------------------------------------------------ terminal
def to_ansi(cv, c256=False):
    q = (np.clip(cv.rgb, 0, 1) * 255).astype(np.uint8) & 0xF8
    if c256:
        q6 = (q.astype(np.int32) * 6 // 256)
        code = (16 + 36 * q6[..., 0] + 6 * q6[..., 1] + q6[..., 2]).tolist()
    else:
        code = q.tolist()
    chars = cv.ch.tolist()
    out = []
    for y in range(cv.h):
        last, parts = None, []
        for c, col in zip(chars[y], code[y]):
            if c != " " and col != last:
                parts.append(f"\x1b[38;5;{col}m" if c256 else f"\x1b[38;2;{col[0]};{col[1]};{col[2]}m")
                last = col
            parts.append(c)
        out.append("".join(parts))
    return "\n".join(out) + "\x1b[0m"


def terminal_size(args):
    cols, rows = shutil.get_terminal_size((120, 40))
    return max(60, cols), max(24, rows - 1)


def run_terminal(args):
    if os.name == "nt":
        os.system("")   # turn on ANSI escape codes in the Windows console
    if args.once:
        w, h = terminal_size(args)
        sys.stdout.write(to_ansi(Scene(w, h, args.tag, hud=not args.no_hud).frame(args.at), args.c256) + "\n")
        return
    write = sys.stdout.write
    write("\x1b[?1049h\x1b[?25l\x1b[2J")
    scene, t0 = None, time.perf_counter()
    try:
        while True:
            start = time.perf_counter()
            w, h = terminal_size(args)
            if scene is None or (scene.w, scene.h) != (w, h):
                scene = Scene(w, h, args.tag, hud=not args.no_hud)
                write("\x1b[2J")
            t = args.at + (start - t0) * args.speed
            write("\x1b[H" + to_ansi(scene.frame(t), args.c256))
            sys.stdout.flush()
            time.sleep(max(0.0, 1 / args.fps - (time.perf_counter() - start)))
    except KeyboardInterrupt:
        pass
    finally:
        write("\x1b[0m\x1b[?25h\x1b[?1049l")
        sys.stdout.flush()


# ------------------------------------------------------------------ music
# An original soundtrack, synthesised from scratch and timed to the stages:
# a soft pad on the IV-V-iii-vi progression in D major, a rising note for
# every part of 101, a chime run when the lights come on, ticks for the
# countdown, then a pentatonic melody with fireworks booming where they burst.
SR = 44100
ROYAL = [([55, 59, 62, 66], 43), ([57, 61, 64, 69], 45),   # Gmaj7, A
         ([54, 57, 61, 64], 42), ([59, 62, 66, 69], 47)]   # F#m7, Bm7
FINALE = [([62, 66, 69, 74], 38), ([61, 64, 69, 73], 37),  # D, A/C#
          ([59, 62, 66, 69], 35), ([55, 59, 62, 66], 31)]  # Bm7, Gmaj7
MELODY = [(0, 74, 1), (1, 76, .5), (1.5, 78, .5), (2, 81, 1.5), (3.5, 78, .5),   # beats, note, length
          (4, 76, 1), (5, 74, .5), (5.5, 76, .5), (6, 78, 2),
          (8, 81, 1), (9, 83, .5), (9.5, 81, .5), (10, 78, 1), (11, 76, 1),
          (12, 74, .5), (12.5, 76, .5), (13, 74, .5), (13.5, 71, .5), (14, 74, 2)]
PENTA_HIGH = [86, 88, 90, 93, 95]   # D E F# A B, sixth octave


def hz(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def tline(dur):
    return np.arange(int(dur * SR)) / SR


def band(x, lo=None, hi=None):
    """Soft low/high-pass in the frequency domain."""
    X = np.fft.rfft(x)
    f = np.fft.rfftfreq(len(x), 1 / SR) + 1e-3
    if hi:
        X /= 1 + (f / hi) ** 4
    if lo:
        X /= 1 + (lo / f) ** 4
    return np.fft.irfft(X, len(x))


def bell(f, dur=2.5, ratio=3.5, depth=2.2):
    t = tline(dur)
    mod = np.sin(2 * np.pi * f * ratio * t) * depth * np.exp(-t / 0.35)
    return np.sin(2 * np.pi * f * t + mod) * np.exp(-t / 0.8) * np.minimum(1, t / 0.004)


def pluck(f, dur=1.2):
    t = tline(dur)
    s = sum(np.sin(2 * np.pi * f * k * t) * np.exp(-t * (2.5 + 2.0 * k)) / k for k in range(1, 7))
    return s * np.minimum(1, t / 0.003)


def pad(notes, dur, attack=0.8, release=1.2):
    t = tline(dur + release)
    s = np.zeros_like(t)
    for m in notes:
        for det in (-0.0018, 0.0, 0.0021):
            w = 2 * np.pi * hz(m) * (1 + det) * t + det * 900
            s += np.sin(w) + 0.25 * np.sin(2 * w)
    env = np.minimum(1, t / attack) * np.clip((dur + release - t) / release, 0, 1)
    return s * env * (1 + 0.08 * np.sin(2 * np.pi * 0.3 * t)) / (3 * len(notes))


def bass(m, dur):
    t = tline(dur + 0.15)
    w = 2 * np.pi * hz(m) * t
    env = (np.minimum(1, t / 0.008) * (0.6 + 0.4 * np.exp(-t / 0.25))
           * np.clip((dur + 0.15 - t) / 0.15, 0, 1))
    return np.tanh(1.4 * (np.sin(w) + 0.35 * np.sin(2 * w) + 0.12 * np.sin(3 * w)) * env)


def kick():
    t = tline(0.5)
    f = 46 + 90 * np.exp(-t / 0.04)
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.20)


def noise_hit(rng, dur, tau, lo=None, hi=None):
    t = tline(dur)
    n = band(rng.standard_normal(len(t)), lo, hi)
    return n / (np.abs(n).max() + 1e-9) * np.exp(-t / tau)


def snare(rng):
    t = tline(0.35)
    return 0.7 * noise_hit(rng, 0.35, 0.09, lo=1200, hi=9000) + 0.5 * np.sin(2 * np.pi * 185 * t) * np.exp(-t / 0.05)


def boom(rng, size=1.0):
    t = tline(2.2)
    low = np.sin(2 * np.pi * np.cumsum(38 + 60 * np.exp(-t / 0.06)) / SR) * np.exp(-t / (0.35 * size))
    return 0.8 * low + 0.9 * noise_hit(rng, 2.2, 0.45 * size, hi=320)


def crackle(rng, dur, density=60):
    out = np.zeros(int(dur * SR))
    click = noise_hit(rng, 0.006, 0.0015, lo=2000)
    for _ in range(int(density * dur)):
        u = rng.random() ** 1.6   # more pops early on
        i = int(u * (len(out) - len(click)))
        out[i: i + len(click)] += click * rng.uniform(0.3, 1.0) * (1 - u)
    return out


def whistle(dur=0.8):
    t = tline(dur)
    f = 900 + 900 * (t / dur) ** 1.5 + 25 * np.sin(2 * np.pi * 11 * t)
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * np.sin(np.pi * t / dur) ** 2


def riser(rng, dur):
    n = rng.standard_normal(int(dur * SR))
    chunk = SR // 10
    out = np.zeros_like(n)
    for i in range(0, len(n), chunk):
        cut = 400 * 20 ** (i / len(n))
        out[i: i + chunk] = band(n[i: i + chunk], lo=200, hi=cut)
    ramp = (np.arange(len(n)) / len(n)) ** 2
    return out / (np.abs(out).max() + 1e-9) * ramp


def reverb(x, rng, decay=1.8):
    t = tline(decay * 1.3)
    ir = band(rng.standard_normal(len(t)), hi=5000) * np.exp(-t * 6.9 / decay)
    N = 1 << (len(x) + len(ir) - 1).bit_length()
    y = np.fft.irfft(np.fft.rfft(x, N) * np.fft.rfft(ir, N), N)[: len(x)]
    return y * (np.sqrt(np.mean(x ** 2)) / (np.sqrt(np.mean(y ** 2)) + 1e-12))


def make_music(scene, seed=8):
    """One loop (LOOP seconds) of stereo audio, as a (2, n) float array."""
    rng = np.random.default_rng(seed)
    n = int(LOOP * SR)
    bus = {"music": np.zeros((2, n)), "sfx": np.zeros((2, n))}

    def add(t, sig, gain=1.0, pan=0.0, to="music"):
        i = int(round(t * SR))
        if i >= n:
            return
        if i < 0:
            sig, i = sig[-i:], 0
        j = min(n, i + len(sig))
        a = (max(-1.0, min(1.0, pan)) + 1) * math.pi / 4
        bus[to][0, i:j] += sig[: j - i] * gain * math.cos(a)
        bus[to][1, i:j] += sig[: j - i] * gain * math.sin(a)

    def groove(t0, t1, gain=1.0):
        t = t0
        while t < t1 - 1e-6:
            for off in (0, 0.75, 1.0):
                add(t + off, kick(), 0.55 * gain)
            for off in (0.5, 1.5):
                add(t + off, snare(rng), 0.22 * gain, 0.1)
            for k in range(8):
                add(t + k * 0.25 + (0.03 if k % 2 else 0), noise_hit(rng, 0.08, 0.02, lo=7000),
                    (0.10 if k % 2 == 0 else 0.06) * gain, -0.3)
            t += 2.0

    def arp(t0, t1, chords, gain):
        t, bar = t0, 0
        while t < t1 - 1e-6:
            notes = chords[bar % len(chords)][0]
            seq = notes + [notes[0] + 12]
            for k, idx in enumerate([0, 1, 2, 3, 4, 3, 2, 1]):
                add(t + k * 0.25, pluck(hz(seq[idx] + 12)), gain * (1.0 if k % 2 == 0 else 0.7), 0.35 - 0.1 * idx)
            t += 2.0
            bar += 1

    def bassline(t0, t1, chords, gain):
        t, bar = t0, 0
        while t < t1 - 1e-6:
            root = chords[bar % len(chords)][1]
            for off, d in ((0, 0.7), (0.75, 0.2), (1.0, 0.9)):
                add(t + off, bass(root, d), gain)
            t += 2.0
            bar += 1

    # night sky: pad fades in, stars twinkle as little bells
    for bar in range(12):
        notes, _ = ROYAL[bar % 4]
        add(bar * 2.0, pad(notes, 2.0), 0.20 * min(1.0, 0.75 + bar * 0.1), 0.0)
    add(0.0, bass(43, 1.9), 0.10)
    for _ in range(12):
        add(rng.uniform(0.3, 5.8), bell(hz(rng.choice(PENTA_HIGH)), 2.0), 0.09, rng.uniform(-0.8, 0.8))
    # the city wakes up
    bassline(6.0, 24.0, ROYAL[3:] + ROYAL[:3], 0.20)
    arp(6.0, 13.0, ROYAL[3:] + ROYAL[:3], 0.07)
    add(10.0, bell(hz(45), 4.0, ratio=1.41, depth=1.5), 0.10)   # a temple-gong for the Grand Hotel
    # Taipei 101 rises: one note per floor block, climbing the pentatonic scale
    for k, m in enumerate([57, 59, 62, 64, 66, 69, 71, 74, 76, 78]):
        add(13.0 + k * 0.5, pluck(hz(m)), 0.16, -0.5 + k * 0.1)
        add(13.0 + k * 0.5, bell(hz(m + 12), 1.2), 0.04, -0.5 + k * 0.1)
    for k in range(16):   # hats come in, then a snare roll into the lights
        add(14.0 + k * 0.25, noise_hit(rng, 0.08, 0.02, lo=7000), 0.05, -0.3)
    for k in range(8):
        add(17.0 + k * 0.125, snare(rng), 0.05 + 0.03 * k, 0.1)
    # the lights come on: a chime run, then the beat
    for k, m in enumerate([74, 76, 78, 81, 83, 86, 88, 90, 93]):
        add(18.0 + k * 0.1, bell(hz(m), 2.5), 0.10, -0.8 + k * 0.2)
    add(18.0, noise_hit(rng, 2.5, 1.0, lo=4000), 0.10)
    groove(18.0, 24.0)
    arp(18.0, 24.0, ROYAL[1:] + ROYAL[:1], 0.06)
    # a meteor: a quick falling shimmer
    for k, m in enumerate([95, 93, 90, 88, 86]):
        add(METEOR + 0.1 + k * 0.08, bell(hz(m), 1.2), 0.05, 0.3 - k * 0.12)
    # countdown: suspended chord, ticks that climb, a heartbeat and a riser
    add(24.0, pad([57, 62, 64, 69], 2.5, attack=0.3, release=0.6), 0.16)
    add(26.5, pad([57, 61, 64, 67], 2.5, attack=0.3, release=0.4), 0.16)
    add(24.0, bass(33, 4.9), 0.18)
    for k, m in enumerate([69, 71, 73, 76, 78]):
        add(24.0 + k, bell(hz(m), 0.9, ratio=2.0, depth=1.0), 0.20)
        add(24.0 + k, kick(), 0.35)
    add(26.0, riser(rng, 3.0), 0.12)
    # midnight: impact, then the melody over D - A/C# - Bm - G
    add(29.0, kick(), 0.9)
    add(29.0, noise_hit(rng, 3.0, 1.1, lo=3000), 0.18)
    for k, (notes, root) in enumerate(FINALE):
        add(29.0 + 2 * k, pad(notes, 2.0, attack=0.2), 0.18)
    bassline(29.0, 37.0, FINALE, 0.22)
    groove(29.0, 37.0)
    arp(29.0, 37.0, FINALE, 0.04)
    for b, m, d in MELODY:
        add(29.0 + b * 0.5, bell(hz(m), 0.5 + d, ratio=2.0, depth=1.2), 0.22, 0.05)
        add(29.0 + b * 0.5, pluck(hz(m)), 0.10, -0.05)
    add(37.0, pad([62, 64, 66, 69, 74], 2.0, attack=0.1, release=1.5), 0.20)
    add(37.0, bass(38, 1.8), 0.20)
    add(37.0, bell(hz(86), 3.0), 0.10)

    # fireworks, panned to where they burst
    for tb, x0, y0, hue, ang, spd, life in scene.shells:
        pan = 0.85 * (2 * x0 / scene.w - 1)
        big = life > 2.0
        add(tb - 0.8, whistle(), 0.025, pan, "sfx")
        add(tb, boom(rng, 1.6 if big else 1.0), 0.75 if big else rng.uniform(0.35, 0.5), pan, "sfx")
        add(tb + 0.3, crackle(rng, 2.0 if big else 1.4, 90 if big else 50), 0.22 if big else 0.14, pan, "sfx")
    for tb in sorted({round(f[0], 2) for f in scene.flares}):
        add(tb, noise_hit(rng, 0.9, 0.35, lo=2500), 0.04, 0.85 * (2 * scene.x101 / scene.w - 1), "sfx")

    out = np.zeros((2, n))
    for name, wet in (("music", 0.35), ("sfx", 0.25)):
        for ch in range(2):
            x = bus[name][ch]
            out[ch] += x + wet * reverb(x, rng)
    t = np.arange(n) / SR
    fade = np.where(t > FADE, 1 - np.clip((t - FADE) / (LOOP - FADE), 0, 1) ** 1.5, 1.0)
    out *= fade * np.minimum(1, t / 0.05)
    out /= np.abs(out).max() + 1e-9
    return np.tanh(1.6 * out) / np.tanh(1.6) * 0.95


def write_wav(path, stereo):
    import wave
    pcm = (np.clip(stereo.T, -1, 1) * 32767).astype("<i2")
    with wave.open(path, "wb") as f:
        f.setnchannels(2)
        f.setsampwidth(2)
        f.setframerate(SR)
        f.writeframes(pcm.tobytes())


def music_for(scene, start, seconds):
    loop = make_music(scene)
    idx = (np.round((start + np.arange(int(seconds * SR)) / SR) * SR).astype(np.int64)) % loop.shape[1]
    return loop[:, idx]


# ------------------------------------------------------------------ video
FONTS = ["DejaVuSansMono.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
         "/System/Library/Fonts/Menlo.ttc", "/Library/Fonts/Menlo.ttc",
         "C:/Windows/Fonts/consola.ttf", "C:/Windows/Fonts/cour.ttf"]
KEYWORDS = set("""def class return for in if elif else import from while not and or None True
False with as lambda try except finally break continue pass yield global raise is""".split())
BUILTINS = set("range len int float min max abs zip enumerate round sum tuple list print np math".split())
TOKEN = re.compile(r"(#.*)|(\"[^\"]*\"|'[^']*')|(\b\d+\.?\d*\b)|([A-Za-z_]\w*)|(\s+)|(.)")


def load_font(size, path=None):
    from PIL import ImageFont
    for p in ([path] if path else []) + FONTS:
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            continue
    sys.exit("No monospace font found; pass one with --font path/to/font.ttf")


def blur(a, r):
    """Box blur along both image axes, twice (close to a gaussian)."""
    for _ in range(2):
        for ax in (0, 1):
            c = np.cumsum(np.pad(a, [(r + 1, r) if i == ax else (0, 0) for i in range(3)], mode="edge"), axis=ax)
            hi = np.take(c, range(2 * r + 1, c.shape[ax]), axis=ax)
            lo = np.take(c, range(0, c.shape[ax] - 2 * r - 1), axis=ax)
            a = (hi - lo) / (2 * r + 1)
    return a


class CodePanel:
    """The source of this file, typed out and scrolling, editor style."""

    def __init__(self, width, height, font_path=None):
        from PIL import Image, ImageDraw
        self.w, self.h = width, height
        self.font = font = load_font(max(12, width // 60), font_path)
        self.cw = font.getbbox("M" * 10)[2] / 10
        self.lh = int(font.size * 1.45)
        self.head = int(self.lh * 1.6)
        self.gut = int(self.cw * 5)
        with open(os.path.abspath(__file__), encoding="utf-8") as f:
            self.lines = f.read().rstrip("\n").split("\n")
        self.starts = np.cumsum([0] + [len(s) + 1 for s in self.lines])
        img = Image.new("RGB", (width, self.lh * len(self.lines)), (0, 0, 0))
        dr = ImageDraw.Draw(img)
        colours = [(110, 128, 110), (232, 160, 96), (160, 220, 150), None, None, (205, 210, 225)]
        for i, line in enumerate(self.lines):
            y = i * self.lh
            dr.text((self.cw * 0.5, y), f"{i + 1:>3}", font=font, fill=(70, 78, 98))
            x, prev = self.gut, ""
            for m in TOKEN.finditer(line):
                s = m.group(0)
                kind = m.lastindex - 1
                fill = colours[kind]
                if kind == 3:
                    fill = ((235, 120, 170) if s in KEYWORDS else (110, 200, 235) if s in BUILTINS
                            else (240, 210, 120) if prev in ("def", "class") else (205, 210, 225))
                if kind != 4:
                    dr.text((x, y), s, font=font, fill=fill)
                    prev = s
                x += self.cw * len(s)
        self.code = np.asarray(img, np.uint8)
        head = Image.new("RGB", (width, self.head), (22, 25, 36))
        dh = ImageDraw.Draw(head)
        r = self.head // 7
        for i, c in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
            cx = int(self.cw * 1.5 + i * r * 3.2)
            dh.ellipse([cx - r, self.head // 2 - r, cx + r, self.head // 2 + r], fill=c)
        tx = int(self.cw * 1.5 + r * 10)
        dh.rectangle([tx - 6, 4, tx + self.cw * 11, self.head], fill=(12, 14, 22))
        dh.text((tx + 4, self.head // 2 - font.size // 2 - 2), "taipei.py", font=font, fill=(220, 225, 240))
        self.header = np.asarray(head, np.float32) / 255

    def render(self, t, loop):
        out = np.zeros((self.h, self.w, 3), np.float32)
        out[:] = (12 / 255, 14 / 255, 22 / 255)
        out[: self.head] = self.header
        typed = (t % loop) / (loop * 0.97) * self.starts[-1]
        li = int(np.searchsorted(self.starts, min(typed, self.starts[-1] - 1), side="right") - 1)
        col = int(typed - self.starts[li])
        view = self.h - self.head
        vis = view / self.lh
        frac = li + min(col / max(len(self.lines[li]), 1), 1)
        top_px = int(max(0.0, frac - 0.72 * vis) * self.lh)
        crop = self.code[top_px: top_px + view].astype(np.float32) / 255
        cur_y = li * self.lh - top_px
        x_cut = int(self.gut + col * self.cw)
        if 0 <= cur_y < crop.shape[0]:
            crop[max(0, cur_y): cur_y + self.lh, x_cut:] = 0
            crop[max(0, cur_y): cur_y + self.lh, :] += (0.05, 0.06, 0.10)
            if (t * 2.5) % 1 < 0.6:
                crop[max(0, cur_y + 2): cur_y + self.lh - 2, x_cut: x_cut + int(self.cw)] = (0.9, 0.9, 1.0)
        crop[max(0, cur_y + self.lh):] = 0
        np.maximum(out[self.head: self.head + crop.shape[0]], crop, out=out[self.head: self.head + crop.shape[0]])
        return out


class Renderer:
    def __init__(self, width, height, cols, tag, font_path=None, code=False, hud=True):
        from PIL import Image, ImageDraw
        self.W, self.H = width, height
        self.cw = width // cols
        self.chh = self.cw * 2
        font = load_font(int(self.cw / 0.6), font_path)
        scene_px = int(height * (0.62 if code else 1.0))
        rows = scene_px // self.chh
        self.scene = Scene(cols, rows, tag, hud=hud)
        self.sw, self.sh = cols * self.cw, rows * self.chh
        self.x0 = (width - self.sw) // 2
        atlas = np.zeros((95, self.chh, self.cw), np.float32)
        for i in range(95):
            g = Image.new("L", (self.cw, self.chh), 0)
            ImageDraw.Draw(g).text((0, (self.chh - font.size) // 2 - 1), chr(32 + i), font=font, fill=255)
            atlas[i] = np.asarray(g, np.float32) / 255
        self.atlas = atlas
        y = np.linspace(0, 1, self.sh)[:, None, None]
        hz = self.scene.hz / rows
        sky = np.array([0.012, 0.016, 0.045]) * (1 - y / hz) + np.array([0.055, 0.040, 0.085]) * (y / hz)
        water = np.array([0.010, 0.018, 0.040]) * np.ones_like(y)
        self.bg = np.where(y < hz, sky, water).astype(np.float32) * np.ones((1, self.sw, 1), np.float32)
        self.panel = CodePanel(width, height - scene_px, font_path) if code else None
        self.scene_px = scene_px

    def frame(self, t):
        cv = self.scene.frame(t)
        codes = np.clip(cv.ch.view(np.uint32).reshape(cv.h, cv.w).astype(np.int64) - 32, 0, 94)
        g = self.atlas[codes][..., None] * cv.rgb[:, :, None, None, :]
        img = g.transpose(0, 2, 1, 3, 4).reshape(self.sh, self.sw, 3)
        f = 4
        small = img[: self.sh // f * f, : self.sw // f * f].reshape(self.sh // f, f, self.sw // f, f, 3).mean((1, 3))
        glow = np.repeat(np.repeat(blur(small, 3), f, 0), f, 1)
        fade = 1 - smooth((t % LOOP - FADE) / (LOOP - FADE)) if t % LOOP > FADE else 1.0
        scene = self.bg * fade + img
        scene[: glow.shape[0], : glow.shape[1]] += 1.6 * glow
        out = np.zeros((self.H, self.W, 3), np.float32)
        out[: self.sh, self.x0: self.x0 + self.sw] = scene
        if self.panel:
            out[self.scene_px:] = self.panel.render(t, LOOP)
            out[self.scene_px: self.scene_px + 2] = (0.16, 0.18, 0.26)
        return (np.clip(out, 0, 1) * 255).astype(np.uint8)


def record(args):
    w, h = (int(v) for v in args.size.lower().split("x"))
    r = Renderer(w, h, args.cols, args.tag, args.font, code=args.code, hud=not args.no_hud)
    if args.record.lower().endswith(".png"):
        from PIL import Image
        Image.fromarray(r.frame(args.at)).save(args.record)
        print(f"saved {args.record}")
        return
    if args.record.lower().endswith(".wav"):
        write_wav(args.record, music_for(r.scene, args.at, args.seconds))
        print(f"saved {args.record}")
        return
    frames = int(args.seconds * args.fps)
    audio = []
    if not args.no_music:
        import tempfile
        wav = os.path.join(tempfile.mkdtemp(), "music.wav")
        write_wav(wav, music_for(r.scene, args.at, args.seconds))
        audio = ["-i", wav, "-map", "0:v", "-map", "1:a", "-c:a", "aac", "-b:a", "192k", "-shortest"]
    cmd = (["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
            "-s", f"{w}x{h}", "-r", str(args.fps), "-i", "-"] + audio
           + ["-c:v", "libx264", "-preset", "veryfast", "-crf", str(args.crf), "-pix_fmt", "yuv420p",
              "-movflags", "+faststart", args.record])
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    t0 = time.perf_counter()
    for i in range(frames):
        proc.stdin.write(r.frame(args.at + i / args.fps).tobytes())
        if i % args.fps == 0:
            print(f"\r{i / args.fps:5.1f}s / {args.seconds:.0f}s", end="", flush=True)
    proc.stdin.close()
    proc.wait()
    print(f"\rsaved {args.record} ({frames} frames, {time.perf_counter() - t0:.0f}s)")


def main():
    ap = argparse.ArgumentParser(description="ASCII Taipei night view")
    ap.add_argument("--fps", type=float, default=30)
    ap.add_argument("--speed", type=float, default=1.0, help="animation speed multiplier")
    ap.add_argument("--at", type=float, default=None, help="start time in seconds (31 = fireworks)")
    ap.add_argument("--once", action="store_true", help="print one frame and exit")
    ap.add_argument("--256", dest="c256", action="store_true", help="256-colour mode for older terminals")
    ap.add_argument("--tag", default="", help="text under the greeting, e.g. @yourname")
    ap.add_argument("--record", metavar="FILE",
                    help="render to .mp4 (needs pillow + ffmpeg), one .png, or just the music as .wav")
    ap.add_argument("--no-music", action="store_true", help="video without the soundtrack")
    ap.add_argument("--seconds", type=float, default=LOOP)
    ap.add_argument("--size", default="1080x1920", help="video size, WIDTHxHEIGHT")
    ap.add_argument("--cols", type=int, default=90, help="character columns in the video")
    ap.add_argument("--crf", type=int, default=20)
    ap.add_argument("--font", help="monospace .ttf/.ttc for the video")
    ap.add_argument("--code", action="store_true", help="add a panel that types out this file under the view")
    ap.add_argument("--no-hud", action="store_true", help="hide the stage / time readout in the corner")
    args = ap.parse_args()
    if args.at is None:
        args.at = 31.0 if args.once or (args.record or "").lower().endswith(".png") else 0.0
    if args.record:
        record(args)
    else:
        run_terminal(args)


if __name__ == "__main__":
    main()
