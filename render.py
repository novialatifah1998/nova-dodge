#!/usr/bin/env python3
"""render.py — render the NOVA DODGE video frames and encode the segments.

Reads the game design (PROMPT.txt) and renders a 30.0 s vertical video in
three beats, 1080x1920 at 30 fps:
  0-4 s   hook:     "ONE PROMPT." + the prompt typing out in a chat bubble
  4-10 s  terminal: the agent's build log + a code pane typing
  10-30 s gameplay: a scripted, seeded playthrough of NOVA DODGE
Frames go straight into ffmpeg (rawvideo pipe) — no PNGs on disk — and the
three segments land in assets/ as hook.mp4, terminal.mp4, gameplay.mp4.
main.ts then assembles them with the press-kit badge and end card.

Deterministic: one seeded RNG (mulberry32) drives every spawn and every
twinkle, so re-running this file reproduces the same segments byte for byte
(ffmpeg is run with fixed flags and no timestamps).
"""
import json
import math
import os
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFont

W, H = 1080, 1920
FPS = 30
SEED = 20261123

# ---- shared tuning with game.html (logical 480x720, scale 2.25) ----
S = 1080 / 480
ROCKET_Y = 640 * S
ROCKET_SPEED = 340 * S
ROCKET_R = 20 * S
METEOR_VY0 = 140 * S
METEOR_VY_LEVEL = 14 * S
STAR_VY = 95 * S
METEOR_EVERY = 0.85
STAR_EVERY = 1.05
INVULN_SEC = 1.5

PROMPT = (
    "Build a tiny browser game in one HTML file: NOVA DODGE. "
    "A little rocket at the bottom of a starfield dodges falling meteors "
    "and collects stars. Arrow keys or touch-drag to move. "
    "Score +1 per star, +1 per meteor dodged, 3 lives, speed ramps up. "
    "Big readable score, game-over screen with restart. "
    "No libraries, no images — draw everything on canvas. "
    "Make it feel fast and fun in 30 seconds."
)

BUILD_LINES = [
    "$ makefun build nova-dodge",
    "> reading prompt.txt ............ ok",
    "> writing game.html (canvas, no libraries)",
    "> writing main.ts (ffmpeg assembly)",
    "> writing render.py (900 frames, seeded)",
    "> node --check game.html ....... ok",
    "> render.py .................... 900 frames",
    "> ffmpeg hook + terminal + gameplay",
    "> video.mp4  30.0 s  1080x1920",
    "ok  build complete - NOVA DODGE ready",
]

CODE_PANE = [
    "const rocket = { x: 240, y: 640 };",
    "function spawnMeteor() {",
    "  meteors.push({ x: rand(14, 466), y: -30 });",
    "}",
    "function loop(t) {",
    "  update(t); draw(t);",
    "  requestAnimationFrame(loop);",
    "}",
]


def mulberry32(seed):
    """Deterministic RNG (same family game.html could use for a replay)."""
    state = seed & 0xFFFFFFFF

    def rnd():
        nonlocal state
        state = (state + 0x6D2B79F5) & 0xFFFFFFFF
        t = state
        t = ((t ^ (t >> 15)) * (t | 1)) & 0xFFFFFFFF
        t ^= t + (((t ^ (t >> 7)) * (t | 61)) & 0xFFFFFFFF)
        t &= 0xFFFFFFFF
        return ((t ^ (t >> 14)) & 0xFFFFFFFF) / 4294967296.0

    return rnd


def clamp(v, a, b):
    return a if v < a else (b if v > b else v)


def lerp(a, b, t):
    return a + (b - a) * t


def font(path, size):
    for p in (path, "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            continue
    return ImageFont.load_default()


F_BIG = lambda s: font("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", s)
F_TXT = lambda s: font("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", s)
F_MONO = lambda s: font("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", s)
F_MONO_B = lambda s: font("/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf", s)


def wrap(draw, text, fnt, max_w):
    """Greedy word wrap, returns a list of lines."""
    words = text.split(" ")
    lines, cur = [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if draw.textlength(trial, font=fnt) <= max_w:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def round_rect(d, box, r, fill=None, outline=None, width=1):
    d.rounded_rectangle(box, radius=r, fill=fill, outline=outline, width=width)


# ---------------------------------------------------------------- bg ---
def make_bg_stars(rnd):
    return [(rnd() * W, rnd() * H, 1.0 + rnd() * 3.5, rnd() * 6.28, 0.4 + rnd() * 1.2)
            for _ in range(140)]


def draw_bg(d, frame, bg_stars):
    # vertical gradient, deep indigo to near-black
    for y in range(0, H, 8):
        t = y / H
        r = int(lerp(11, 5, t))
        g = int(lerp(16, 3, t))
        b = int(lerp(48, 15, t))
        d.rectangle([0, y, W, y + 8], fill=(r, g, b))
    # nebula blobs
    for (cx, cy, cr, col) in ((200, 380, 260, (196, 28, 131)),
                              (900, 900, 300, (43, 108, 255)),
                              (300, 1600, 280, (60, 20, 90))):
        d.ellipse([cx - cr, cy - cr, cx + cr, cy + cr], fill=col + (18,))
    for (x, y, r, tw, sp) in bg_stars:
        a = 0.35 + 0.65 * abs(math.sin(frame * 0.03 * sp + tw))
        v = int(255 * a)
        d.ellipse([x - r, y - r, x + r, y + r], fill=(v, v, v))


def draw_rocket(d, x, y, t, scale=1.0):
    # flame
    fl = (30 + math.sin(t * 0.9) * 12) * scale
    d.polygon([(x - 18 * scale, y + 30 * scale), (x, y + 30 * scale + fl),
               (x + 18 * scale, y + 30 * scale)], fill=(255, 154, 60))
    d.polygon([(x - 9 * scale, y + 30 * scale), (x, y + 30 * scale + fl * 0.6),
               (x + 9 * scale, y + 30 * scale)], fill=(255, 230, 109))
    # body
    d.polygon([(x, y - 58 * scale), (x + 26 * scale, y + 26 * scale),
               (x - 26 * scale, y + 26 * scale)], fill=(232, 236, 244))
    d.rectangle([x - 25 * scale, y + 4 * scale, x + 25 * scale, y + 16 * scale],
                fill=(196, 28, 131))
    # window
    d.ellipse([x - 13 * scale, y - 16 * scale, x + 13 * scale, y + 10 * scale],
              fill=(125, 249, 255))
    d.ellipse([x - 8 * scale, y - 11 * scale, x + 8 * scale, y + 5 * scale],
              fill=(11, 16, 38))
    # fins
    d.polygon([(x - 25 * scale, y + 12 * scale), (x - 44 * scale, y + 40 * scale),
               (x - 25 * scale, y + 36 * scale)], fill=(255, 90, 60))
    d.polygon([(x + 25 * scale, y + 12 * scale), (x + 44 * scale, y + 40 * scale),
               (x + 25 * scale, y + 36 * scale)], fill=(255, 90, 60))


def draw_meteor(d, m):
    x, y, r, rot = m["x"], m["y"], m["r"], m["rot"]
    d.ellipse([x - r, y - r, x + r, y + r], fill=(141, 147, 165))
    for (ox, oy, cr) in m["craters"]:
        d.ellipse([x + ox - cr, y + oy - cr, x + ox + cr, y + oy + cr],
                  fill=(110, 116, 136))
    d.arc([x - r, y - r, x + r, y + r], start=200, end=290,
          fill=(255, 255, 255), width=4)


def draw_star4(d, x, y, r, rot, color=(255, 217, 77)):
    pts = []
    for k in range(8):
        ang = rot + k * math.pi / 4
        rr = r if k % 2 == 0 else r * 0.28
        pts.append((x + rr * math.cos(ang - math.pi / 2),
                    y + rr * math.sin(ang - math.pi / 2)))
    d.polygon(pts, fill=color)


def draw_hud(d, score, lives, level):
    f_score = F_BIG(120)
    f_small = F_BIG(34)
    d.text((W / 2, 110), str(score), font=f_score, fill=(255, 255, 255),
           anchor="mm")
    d.text((W / 2, 190), "SCORE", font=f_small, fill=(255, 255, 255, 165),
           anchor="mm")
    # lives: hearts top right, clear of the badge box (x 120-450, y 272-400)
    for i in range(3):
        col = (255, 90, 122) if i < lives else (255, 255, 255, 46)
        d.text((W - 90 - i * 70, 130), "\u2665", font=F_BIG(56), fill=col,
               anchor="mm")
    d.text((W - 90, 210), "LVL %d" % level, font=F_BIG(44), fill=(125, 249, 255),
           anchor="mm")


# -------------------------------------------------------------- beats ---
def hook_frame(frame, bg_stars):
    img = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(img, "RGBA")
    draw_bg(d, frame, bg_stars)
    # title, below the badge box (badge y 272-400, keep 24 px clear)
    d.text((W / 2, 560), "ONE PROMPT.", font=F_BIG(120), fill=(255, 255, 255),
           anchor="mm")
    d.text((W / 2, 660), "one prompt. one game.", font=F_TXT(48),
           fill=(255, 217, 77), anchor="mm")
    # chat bubble with the prompt typing out
    shown = int(len(PROMPT) * min(1.0, frame / 115.0))
    bubble = (70, 760, W - 70, 1560)
    round_rect(d, bubble, 48, fill=(255, 255, 255, 24),
               outline=(255, 255, 255, 90), width=3)
    fnt = F_MONO(40)
    lines = wrap(d, PROMPT[:shown], fnt, bubble[2] - bubble[0] - 90)
    y = bubble[1] + 55
    for ln in lines:
        d.text((bubble[0] + 45, y), ln, font=fnt, fill=(255, 255, 255))
        y += 56
    # caret
    if frame % 30 < 15 and shown < len(PROMPT):
        cx = bubble[0] + 45 + d.textlength(lines[-1] if lines else "", font=fnt)
        cy = y - 56
        d.rectangle([cx + 6, cy, cx + 12, cy + 44], fill=(255, 217, 77))
    return img


def terminal_frame(frame, bg_stars):
    img = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(img, "RGBA")
    draw_bg(d, frame, bg_stars)
    d.text((W / 2, 560), "THE AGENT BUILDS.", font=F_BIG(84),
           fill=(255, 255, 255), anchor="mm")
    # terminal window, below the badge box
    box = (70, 700, W - 70, 1230)
    round_rect(d, box, 28, fill=(10, 12, 24, 235), outline=(255, 255, 255, 60),
               width=2)
    d.ellipse([box[0] + 34, box[1] + 30, box[0] + 58, box[1] + 54], fill=(255, 95, 86))
    d.ellipse([box[0] + 68, box[1] + 30, box[0] + 92, box[1] + 54], fill=(255, 189, 46))
    d.ellipse([box[0] + 102, box[1] + 30, box[0] + 126, box[1] + 54], fill=(39, 201, 63))
    d.text((box[0] + 150, box[1] + 42), "agent — build log", font=F_MONO(32),
           fill=(255, 255, 255, 170), anchor="lm")
    per = 180 / len(BUILD_LINES)
    n = min(len(BUILD_LINES), int(frame / per) + 1)
    y = box[1] + 90
    for ln in BUILD_LINES[:n]:
        d.text((box[0] + 40, y), ln, font=F_MONO(33),
               fill=(51, 255, 102) if ln.startswith("ok") else (220, 230, 220))
        y += 42
    # code pane
    cbox = (70, 1290, W - 70, 1680)
    round_rect(d, cbox, 28, fill=(16, 18, 40, 235), outline=(255, 255, 255, 60),
               width=2)
    d.text((cbox[0] + 40, cbox[1] + 30), "game.html — canvas, no libraries",
           font=F_MONO_B(30), fill=(125, 249, 255))
    chars = int(sum(len(s) + 1 for s in CODE_PANE) * min(1.0, frame / 175.0))
    y = cbox[1] + 88
    left = chars
    for ln in CODE_PANE:
        show = ln[:max(0, min(len(ln), left))]
        d.text((cbox[0] + 40, y), show, font=F_MONO(30), fill=(230, 236, 244))
        left -= len(ln) + 1
        y += 40
        if left <= 0:
            break
    return img


# ----------------------------------------------------------- gameplay ---
class Sim:
    def __init__(self, rnd):
        self.rnd = rnd
        self.x = W / 2
        self.y = ROCKET_Y
        self.score = 0
        self.lives = 3
        self.level = 1
        self.meteors = []
        self.stars = []
        self.parts = []
        self.meteor_t = 0.4
        self.star_t = 0.2
        self.invuln = 0.0
        self.banner = None  # (text, frames_left)
        self.scripted_done = False
        self.events = []

    def level_for(self, s):
        return 1 + s // 10

    def step(self, dt, frame):
        rnd = self.rnd
        if self.invuln > 0:
            self.invuln -= dt
        # pilot: chase the nearest star, dodge meteors overhead
        target = None
        best = 1e9
        for s in self.stars:
            if s["y"] < self.y and abs(s["x"] - self.x) < best:
                best = abs(s["x"] - self.x)
                target = s["x"]
        danger = 0.0
        for m in self.meteors:
            if m.get("scripted"):
                continue
            if 0 < self.y - m["y"] < 340 and abs(m["x"] - self.x) < 190:
                danger = -1.0 if m["x"] >= self.x else 1.0
                break
        if danger:
            self.x += danger * ROCKET_SPEED * dt
        elif target is not None:
            dx = target - self.x
            self.x += clamp(dx, -ROCKET_SPEED * dt, ROCKET_SPEED * dt)
        self.x = clamp(self.x, 54, W - 54)

        # scripted single hit near the end of the run
        if frame == 660 and self.lives == 3 and not self.scripted_done:
            self.meteors.append({"x": self.x, "y": self.y - 1100, "r": 52,
                                 "vy": 1500, "rot": 0.0, "vr": 0.0,
                                 "craters": [(0, 0, 10)], "scripted": True})
            self.scripted_done = True

        m_every = max(0.45, METEOR_EVERY - 0.05 * (self.level - 1))
        s_every = max(0.6, STAR_EVERY - 0.03 * (self.level - 1))
        self.meteor_t -= dt
        self.star_t -= dt
        if self.meteor_t <= 0:
            r = 32 + rnd() * 26
            self.meteors.append({
                "x": r + rnd() * (W - 2 * r), "y": -r - 8, "r": r,
                "vy": (METEOR_VY0 + METEOR_VY_LEVEL * (self.level - 1)) * (0.85 + rnd() * 0.35),
                "rot": rnd() * 6.28, "vr": (rnd() - 0.5) * 2.4,
                "craters": [(rnd() * 20 - 10, rnd() * 20 - 10, 6 + rnd() * 8)
                            for _ in range(3)]})
            self.meteor_t = m_every * (0.8 + rnd() * 0.4)
        if self.star_t <= 0:
            self.stars.append({"x": 54 + rnd() * (W - 108), "y": -44, "r": 29,
                               "vy": STAR_VY * (0.9 + rnd() * 0.25),
                               "rot": rnd() * 6.28})
            self.star_t = s_every * (0.8 + rnd() * 0.4)

        for m in list(self.meteors):
            m["y"] += m["vy"] * dt
            m["rot"] += m["vr"] * dt
            if m.get("scripted"):
                # the scripted hit tracks the rocket so it lands for sure
                m["x"] = self.x
            if m["y"] - m["r"] > H:
                self.meteors.remove(m)
                self.score += 1
                continue
            if self.invuln <= 0:
                dx, dy = m["x"] - self.x, m["y"] - self.y
                rr = m["r"] + ROCKET_R - 14
                if dx * dx + dy * dy < rr * rr:
                    self.meteors.remove(m)
                    self.lives -= 1
                    self.invuln = INVULN_SEC
                    self.events.append((frame, "hit lives=%d" % self.lives))
                    for _ in range(26):
                        a = rnd() * 6.28
                        sp = 90 + rnd() * 400
                        self.parts.append({"x": self.x, "y": self.y,
                                           "vx": math.cos(a) * sp,
                                           "vy": math.sin(a) * sp,
                                           "life": 0.3 + rnd() * 0.4,
                                           "max": 0.7, "color": (255, 90, 60),
                                           "r": 4 + rnd() * 5})
        for s in list(self.stars):
            s["y"] += s["vy"] * dt
            s["rot"] += 1.5 * dt
            if s["y"] - s["r"] > H:
                self.stars.remove(s)
                continue
            dx, dy = s["x"] - self.x, s["y"] - self.y
            rr = s["r"] + ROCKET_R + 14
            if dx * dx + dy * dy < rr * rr:
                self.stars.remove(s)
                self.score += 1
        for p in list(self.parts):
            p["x"] += p["vx"] * dt
            p["y"] += p["vy"] * dt
            p["life"] -= dt
            if p["life"] <= 0:
                self.parts.remove(p)
        nl = self.level_for(self.score)
        if nl != self.level:
            self.level = nl
            self.banner = ("LEVEL UP!  ·  LVL %d" % nl, 42)
            self.events.append((frame, "level=%d score=%d" % (nl, self.score)))
        if self.banner:
            txt, left = self.banner
            self.banner = (txt, left - 1) if left > 1 else None

    def draw(self, d, frame, bg_stars):
        draw_bg(d, frame, bg_stars)
        for m in self.meteors:
            draw_meteor(d, m)
        for s in self.stars:
            draw_star4(d, s["x"], s["y"], s["r"], s["rot"])
        for p in self.parts:
            a = max(0.0, p["life"] / p["max"])
            d.ellipse([p["x"] - p["r"], p["y"] - p["r"], p["x"] + p["r"], p["y"] + p["r"]],
                      fill=p["color"] + (int(255 * a),))
        t = frame / FPS
        if not (self.invuln > 0 and int(t * 12) % 2 == 0):
            draw_rocket(d, self.x, self.y, t)
        draw_hud(d, self.score, self.lives, self.level)
        if self.banner:
            txt, left = self.banner
            d.text((W / 2, 420), txt, font=F_BIG(64), fill=(125, 249, 255),
                   anchor="mm")
        if 720 <= frame <= 809:
            # YOUR TURN banner, 24-27 s
            d.rectangle([0, 880, W, 1060], fill=(196, 28, 131, 235))
            d.text((W / 2, 940), "YOUR TURN", font=F_BIG(92),
                   fill=(255, 255, 255), anchor="mm")
            d.text((W / 2, 1020), "COME BUILD ON make.fun", font=F_BIG(52),
                   fill=(255, 217, 77), anchor="mm")


# ------------------------------------------------------------- encode ---
def encode_segment(path, frames_iter, count):
    """Pipe raw RGB frames into ffmpeg; deterministic flags, no timestamps."""
    cmd = ["ffmpeg", "-y", "-v", "error",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", "%dx%d" % (W, H),
           "-r", str(FPS), "-i", "-",
           "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p",
           "-crf", "20", "-preset", "medium",
           "-fflags", "+bitexact", "-flags", "+bitexact",
           "-metadata", "creation_time=0",
           "-movflags", "+faststart", path]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for img in frames_iter:
        proc.stdin.write(img.tobytes())
    proc.stdin.close()
    proc.wait()
    if proc.returncode != 0:
        raise RuntimeError("ffmpeg failed for %s" % path)


def main():
    outdir = sys.argv[1] if len(sys.argv) > 1 else "assets"
    os.makedirs(outdir, exist_ok=True)
    rnd = mulberry32(SEED)
    bg_stars = make_bg_stars(rnd)

    encode_segment(os.path.join(outdir, "hook.mp4"),
                   (hook_frame(f, bg_stars) for f in range(0, 120)), 120)
    print("hook.mp4: frames 0-119", flush=True)

    encode_segment(os.path.join(outdir, "terminal.mp4"),
                   (terminal_frame(f, bg_stars) for f in range(0, 180)), 180)
    print("terminal.mp4: frames 0-179", flush=True)

    sim = Sim(rnd)
    gen = gameplay_frames(sim, bg_stars)
    encode_segment(os.path.join(outdir, "gameplay.mp4"), gen, 600)
    print("gameplay.mp4: frames 300-899", flush=True)
    print(json.dumps({"seed": SEED, "final_score": sim.score,
                      "final_lives": sim.lives, "final_level": sim.level,
                      "events": sim.events}))


def gameplay_frames(sim, bg_stars):
    for f in range(300, 900):
        sim.step(1.0 / FPS, f)
        img = Image.new("RGB", (W, H))
        d = ImageDraw.Draw(img, "RGBA")
        sim.draw(d, f, bg_stars)
        if f in (300, 420, 540, 660, 780, 899):
            print("  frame %d score=%d lives=%d level=%d" %
                  (f, sim.score, sim.lives, sim.level), flush=True)
        yield img


if __name__ == "__main__":
    main()
