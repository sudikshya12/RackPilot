"""Renders the RackOps Lab product film (1920x1080 @ 60 fps) from real app screenshots.

Usage: python render.py <video_dir>
Writes <video_dir>/build/silent.mp4 and <video_dir>/build/timeline.json (voiceover start times).
"""
import json
import math
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

D = Path(sys.argv[1])
SHOTS = D / "shots"
BUILD = D / "build"
BUILD.mkdir(exist_ok=True)
W, H, FPS = 1920, 1080, 60
XF = 0.7  # scene crossfade seconds
BOXES = json.loads((SHOTS / "boxes.json").read_text())

NAVY = (16, 24, 39)
TEAL = (93, 179, 188)
MUTED = (159, 176, 200)

# ---------------------------------------------------------------- fonts
FONT_PATH = "/System/Library/Fonts/SFNS.ttf"
_font_cache = {}


def font(size, weight=400):
    key = (size, weight)
    if key in _font_cache:
        return _font_cache[key]
    f = ImageFont.truetype(FONT_PATH, size)
    try:
        axes = f.get_variation_axes()
        vals = []
        for a in axes:
            name = (a.get("name") or b"").decode() if isinstance(a.get("name"), bytes) else str(a.get("name"))
            lo, hi, dflt = a["minimum"], a["maximum"], a["default"]
            if "eight" in name:
                vals.append(max(lo, min(hi, weight)))
            elif "ptical" in name:
                vals.append(max(lo, min(hi, size)))
            else:
                vals.append(dflt)
        f.set_variation_by_axes(vals)
    except Exception:
        pass
    _font_cache[key] = f
    return f


# ---------------------------------------------------------------- easing
def ease(x):
    x = max(0.0, min(1.0, x))
    return 4 * x ** 3 if x < 0.5 else 1 - (-2 * x + 2) ** 3 / 2


def ease_out(x):
    x = max(0.0, min(1.0, x))
    return 1 - (1 - x) ** 3


def lerp(a, b, k):
    return a + (b - a) * k


# ---------------------------------------------------------------- backgrounds
def background(glow_x, glow_y, glow_r=900, glow_strength=0.20):
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    top = np.array([9, 14, 26], np.float32)
    bot = np.array([14, 21, 36], np.float32)
    k = (yy / H)[..., None]
    img = top * (1 - k) + bot * k
    d = np.sqrt((xx - glow_x) ** 2 + (yy - glow_y) ** 2) / glow_r
    glow = np.exp(-d ** 2 * 1.6)[..., None]
    img = img + np.array([8, 127, 140], np.float32) * glow * glow_strength
    d2 = np.sqrt((xx - W * 0.15) ** 2 + (yy - H * 1.05) ** 2) / 1100
    img = img + np.array([91, 75, 168], np.float32) * np.exp(-d2 ** 2 * 2)[..., None] * 0.07
    vig = 1 - 0.32 * (np.sqrt(((xx - W / 2) / (W / 1.6)) ** 2 + ((yy - H / 2) / (H / 1.4)) ** 2)) ** 2.2
    img = img * np.clip(vig, 0.55, 1)[..., None]
    rng = np.random.default_rng(7)
    img = img + rng.normal(0, 1.1, img.shape)  # fine dither prevents banding
    return Image.fromarray(np.clip(img, 0, 255).astype(np.uint8), "RGB")


# ---------------------------------------------------------------- app window
CHROME = 30
RADIUS = 16


class Window:
    def __init__(self, x, y, w, glow_xy):
        self.x, self.y, self.w = x, y, w
        self.ch = round(w * 9 / 16)
        self.h = self.ch + CHROME
        self.base = background(*glow_xy)
        # shadow
        sh = Image.new("L", (W, H), 0)
        ImageDraw.Draw(sh).rounded_rectangle([x, y + 26, x + w, y + self.h + 26], RADIUS + 6, fill=150)
        sh = sh.filter(ImageFilter.GaussianBlur(38))
        black = Image.new("RGB", (W, H), (2, 5, 12))
        self.base = Image.composite(black, self.base, sh)
        # chrome bar
        mask = Image.new("L", (w, self.h), 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, w - 1, self.h - 1], RADIUS, fill=255)
        self.mask = mask
        frame = Image.new("RGB", (w, self.h), (22, 31, 50))
        dr = ImageDraw.Draw(frame)
        for i, c in enumerate([(255, 95, 87), (254, 188, 46), (40, 200, 64)]):
            cx = 22 + i * 20
            dr.ellipse([cx - 6, CHROME / 2 - 6, cx + 6, CHROME / 2 + 6], fill=tuple(int(v * 0.85) for v in c))
        url = "rackops.lab  ·  North Lab"
        f = font(13, 500)
        tw = f.getlength(url)
        dr.rounded_rectangle([w / 2 - tw / 2 - 18, 6, w / 2 + tw / 2 + 18, CHROME - 6], 7, fill=(30, 41, 64))
        dr.text((w / 2 - tw / 2, CHROME / 2), url, font=f, fill=(150, 165, 190), anchor="lm")
        self.frame = frame
        border = Image.new("RGBA", (w, self.h), (0, 0, 0, 0))
        ImageDraw.Draw(border).rounded_rectangle([0, 0, w - 1, self.h - 1], RADIUS, outline=(255, 255, 255, 30), width=1)
        self.border = border

    def compose(self, content, overlay=None):
        frame = self.frame.copy()
        frame.paste(content, (0, CHROME))
        img = self.base.copy()
        img.paste(frame, (self.x, self.y), self.mask)
        img.paste(self.border, (self.x, self.y), self.border)
        if overlay is not None:
            img.paste(overlay, (self.x, self.y + CHROME), overlay)
        return img


# ---------------------------------------------------------------- shots & camera
_shot_cache = {}


def shot(name):
    if name not in _shot_cache:
        _shot_cache[name] = Image.open(SHOTS / f"{name}.png").convert("RGB")
    return _shot_cache[name]


def page_size(name):
    p = BOXES[name]["page"]
    return p["w"], p["h"]


def fit(name, box, pad=24, min_w=520):
    """16:9 camera rect (css px) containing box, clamped to the page."""
    pw, ph = page_size(name)
    x, y, w, h = box["x"] - pad, box["y"] - pad, box["w"] + 2 * pad, box["h"] + 2 * pad
    cw = max(w, h * 16 / 9, min_w)
    ch = cw * 9 / 16
    cx, cy = x + w / 2, y + h / 2
    cw = min(cw, pw)
    ch = cw * 9 / 16
    x0 = min(max(cx - cw / 2, 0), pw - cw)
    y0 = min(max(cy - ch / 2, 0), max(ph - ch, 0))
    return (x0, y0, cw)


def B(name, key):
    return BOXES[name][key]


def region(x, y, w, h):
    return {"x": x, "y": y, "w": w, "h": h}


def cam_at(keys, f):
    if f <= keys[0][0]:
        return keys[0][1]
    for (f0, r0), (f1, r1) in zip(keys, keys[1:]):
        if f <= f1:
            k = ease((f - f0) / (f1 - f0)) if f1 > f0 else 1
            return tuple(lerp(a, b, k) for a, b in zip(r0, r1))
    return keys[-1][1]


def crop(name, rect, out_w, out_h):
    x, y, cw = rect
    ch = cw * out_h / out_w
    s = 2.0  # screenshots are 2x DPR
    return shot(name).transform((out_w, out_h), Image.EXTENT, (x * s, y * s, (x + cw) * s, (y + ch) * s), Image.BICUBIC)


def callout_layer(size, rect, box, alpha, out_w):
    """Soft teal focus ring around `box` (css px), mapped through the camera rect."""
    if alpha <= 0.01:
        return None
    x, y, cw = rect
    sc = out_w / cw
    bx0, by0 = (box["x"] - x) * sc - 6, (box["y"] - y) * sc - 6
    bx1, by1 = bx0 + box["w"] * sc + 12, by0 + box["h"] * sc + 12
    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    dr = ImageDraw.Draw(layer)
    for i, a in enumerate((40, 70, 230)):
        g = 6 - i * 3
        dr.rounded_rectangle([bx0 - g, by0 - g, bx1 + g, by1 + g], 12 + g, outline=(93, 179, 188, int(a * alpha)), width=2 if i < 2 else 3)
    return layer


# ---------------------------------------------------------------- text
def text_block(lines, width):
    """lines: list of (text, font, color, spacing_after, tracking). Returns RGBA image."""
    rendered = []
    for txt, f, color, after, tracking in lines:
        words, cur, rows = txt.split(), "", []
        for w_ in words:
            trial = (cur + " " + w_).strip()
            if f.getlength(trial) + tracking * len(trial) > width and cur:
                rows.append(cur)
                cur = w_
            else:
                cur = trial
        rows.append(cur)
        rendered.append((rows, f, color, after, tracking))
    hgt = 0
    for rows, f, _, after, _ in rendered:
        asc, desc = f.getmetrics()
        hgt += len(rows) * int((asc + desc) * 1.08) + after
    img = Image.new("RGBA", (width + 20, hgt + 10), (0, 0, 0, 0))
    dr = ImageDraw.Draw(img)
    yy = 0
    for rows, f, color, after, tracking in rendered:
        asc, desc = f.getmetrics()
        lh = int((asc + desc) * 1.08)
        for r in rows:
            if tracking:
                xx = 0
                for ch_ in r:
                    dr.text((xx, yy), ch_, font=f, fill=color)
                    xx += f.getlength(ch_) + tracking
            else:
                dr.text((0, yy), r, font=f, fill=color)
            yy += lh
        yy += after
    return img


def fade_paste(img, layer, pos, alpha, dy=0):
    if alpha <= 0.01:
        return
    a = layer.getchannel("A").point(lambda v: int(v * alpha))
    img.paste(layer.convert("RGB"), (int(pos[0]), int(pos[1] + dy)), a)


def reveal(t, start, dur=0.7):
    k = ease_out((t - start) / dur)
    return k, (1 - k) * 22


# ---------------------------------------------------------------- logo
def logo(size):
    s = size / 32
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    dr = ImageDraw.Draw(img)
    dr.rounded_rectangle([5 * s, 2 * s, 27 * s, 30 * s], 4 * s, fill=(24, 35, 58), outline=(52, 70, 104), width=max(1, int(s)))
    for i, y in enumerate([7, 12.5, 18]):
        dr.rounded_rectangle([8.5 * s, y * s, 23.5 * s, (y + 3.6) * s], 1 * s, fill=(8, 127, 140) if i == 0 else (42, 55, 85))
        cx, cy = 21 * s, (y + 1.8) * s
        dr.ellipse([cx - 0.9 * s, cy - 0.9 * s, cx + 0.9 * s, cy + 0.9 * s], fill=(93, 179, 188) if i == 1 else (59, 211, 139))
    dr.rounded_rectangle([8.5 * s, 24 * s, 23.5 * s, 26.2 * s], 1 * s, fill=(34, 48, 80))
    return img


# ---------------------------------------------------------------- voiceover durations
def wav_dur(p):
    with wave.open(str(p)) as w:
        return w.getnframes() / w.getframerate()


VO = {i: wav_dur(D / "vo" / f"vo_{i:02d}.wav") for i in range(9)}

# ---------------------------------------------------------------- scenes
SPLIT = Window(660, (H - (round(1140 * 9 / 16) + CHROME)) // 2, 1140, (1240, 560))
FULL = Window(304, 196, 1312, (W // 2, 700))
CARD_BG = background(W / 2, H / 2 + 40, glow_r=760, glow_strength=0.26)

TEXT_W = 470
TX, TY = 108, 318


def split_text(eyebrow, headline, body):
    return [
        text_block([(eyebrow, font(16, 650), TEAL, 0, 3.4)], TEXT_W),
        text_block([(headline, font(66, 730), (255, 255, 255), 0, -0.8)], TEXT_W),
        text_block([(body, font(25, 420), MUTED, 0, 0)], TEXT_W - 30),
    ]


FOOT = text_block([("Simulated lab data", font(14, 500), (110, 125, 150), 0, 0.6)], 300)


class Scene:
    def __init__(self, dur, vo=None, vo_at=0.65):
        self.dur, self.vo, self.vo_at = dur, vo, vo_at


class Title(Scene):
    def __init__(self):
        super().__init__(5.4, vo=0, vo_at=1.9)
        self.logo = logo(132)
        self.name = text_block([("RackOps Lab", font(104, 760), (255, 255, 255), 0, -1.2)], 1000)
        self.tag = text_block([("Data center operations, made precise.", font(31, 430), MUTED, 0, 0)], 1000)

    def render(self, t):
        img = CARD_BG.copy()
        k = ease_out(t / 1.1)
        lg = self.logo.resize((int(132 * (0.9 + 0.1 * k)),) * 2, Image.LANCZOS)
        fade_paste(img, lg, (W / 2 - lg.width / 2, 300 - lg.height / 2 + (1 - k) * 12), k)
        a, dy = reveal(t, 0.45, 0.9)
        nw = self.name.width - 20
        fade_paste(img, self.name, ((W - nw) / 2 + 6, 410), a, dy)
        a2, dy2 = reveal(t, 1.35, 0.9)
        tw = font(31, 430).getlength("Data center operations, made precise.")
        fade_paste(img, self.tag, ((W - tw) / 2, 560), a2, dy2)
        return img


class Closing(Scene):
    def __init__(self):
        super().__init__(VO[8] + 3.4, vo=8, vo_at=0.7)
        self.logo = logo(110)
        self.name = text_block([("RackOps Lab", font(88, 760), (255, 255, 255), 0, -1.0)], 1000)
        self.l1 = text_block([("Every number labeled.", font(32, 520), (220, 228, 240), 0, 0)], 1000)
        self.l2 = text_block([("Every action accounted for.", font(32, 520), TEAL, 0, 0)], 1000)
        self.foot = text_block([("Independent project  ·  Demonstrated with simulated lab data", font(15, 480), (110, 125, 150), 0, 0.4)], 1000)

    def render(self, t):
        img = CARD_BG.copy()
        k = ease_out(t / 1.0)
        fade_paste(img, self.logo, (W / 2 - 55, 250 + (1 - k) * 12), k)
        a, dy = reveal(t, 0.3)
        nw = font(88, 760).getlength("RackOps Lab")
        fade_paste(img, self.name, ((W - nw) / 2, 380), a, dy)
        for i, (lay, txt) in enumerate([(self.l1, "Every number labeled."), (self.l2, "Every action accounted for.")]):
            a, dy = reveal(t, 1.3 + i * 0.9)
            fade_paste(img, lay, ((W - font(32, 520).getlength(txt)) / 2, 530 + i * 50), a, dy)
        a, _ = reveal(t, 2.6)
        fade_paste(img, self.foot, ((W - font(15, 480).getlength("Independent project  ·  Demonstrated with simulated lab data")) / 2, 760), a * 0.9)
        out_k = ease((t - (self.dur - 1.2)) / 1.2)
        if out_k > 0:
            img = Image.blend(img, Image.new("RGB", (W, H), (0, 0, 0)), out_k)
        return img


class Product(Scene):
    """segments: list of dict(shot, keys=[(frac, rect)], callouts=[(box, f0, f1)], until=frac)."""

    def __init__(self, vo, window, segments, text=None, header=None, extra=1.85):
        super().__init__(VO[vo] + extra, vo=vo)
        self.win, self.segments, self.text, self.header = window, segments, text, header

    def content(self, seg, f):
        rect = cam_at(seg["keys"], f)
        c = crop(seg["shot"], rect, self.win.w, self.win.ch)
        ov = None
        for box, f0, f1 in seg.get("callouts", []):
            a = min(ease((f - f0) / 0.08), ease((f1 - f) / 0.08))
            if a > 0:
                lay = callout_layer((self.win.w, self.win.ch), rect, box, a, self.win.w)
                ov = lay if ov is None else Image.alpha_composite(ov, lay)
        return c, ov

    def render(self, t):
        f = t / self.dur
        idx = next((i for i, s in enumerate(self.segments) if f < s["until"]), len(self.segments) - 1)
        seg = self.segments[idx]
        c, ov = self.content(seg, f)
        if idx > 0:  # crossfade from the previous segment
            start = self.segments[idx - 1]["until"]
            k = ease((f - start) * self.dur / 0.55)
            if k < 1:
                pc, _ = self.content(self.segments[idx - 1], f)
                c = Image.blend(pc, c, k)
                ov = None if k < 0.9 else ov
        img = self.win.compose(c, ov)
        if self.text:
            eyebrow, headline, body = self.text
            y = TY
            for i, lay in enumerate((eyebrow, headline, body)):
                a, dy = reveal(t, 0.35 + i * 0.16)
                fade_paste(img, lay, (TX, y), a, dy)
                y += lay.height + (14 if i == 0 else 20)
        if self.header:
            a, dy = reveal(t, 0.3)
            fade_paste(img, self.header, ((W - self.header_w) / 2, 92), a, dy)
        fade_paste(img, FOOT, (TX if self.text else 240, H - 62), 0.9)
        return img


# camera rects per scene (css px of 1600-wide screenshots)
o1 = "01_overview"
u1 = {"x": B(o1, "rack")["x"], "y": B(o1, "rack")["y"], "w": B(o1, "attention")["x"] + B(o1, "attention")["w"] - B(o1, "rack")["x"], "h": B(o1, "rack")["h"]}
o2 = "02_overview_incident"
dev_btn = B(o2, 'button[aria-label^="lab-srv-02"]')
att = B(o2, "attention")
att_row = region(att["x"] + 6, att["y"] + 62, att["w"] - 12, 64)
i3 = "03_incident_investigation"
ev = B(i3, "evidence")
tl = B(i3, "timeline")
ver = B(i3, "verification")
i4 = "04_incident_resolved"
a5, a6 = "05_acceptance_fail", "06_acceptance_compare"
run = B(a5, "run")
cmp_ = B(a6, "compare")
r7, c8 = "07_racks", "08_cable_trace"
s9, s10 = "09_spares_workflow", "10_audit"
wf = B(s9, "workflow")

header1 = text_block([("Everything that matters, at a glance.", font(46, 700), (255, 255, 255), 0, -0.4)], 1500)

scenes = [
    Title(),
    Product(1, FULL, [dict(shot=o1, until=1.01, keys=[(0.0, (0, 0, 1600)), (0.18, (0, 0, 1600)), (0.95, fit(o1, u1, pad=18))])], header=header1, extra=2.0),
    Product(2, SPLIT, [dict(shot=o2, until=1.01, keys=[(0.0, fit(o2, u1, pad=18)), (0.32, fit(o2, B(o2, "rack"), pad=8)), (0.62, fit(o2, B(o2, "rack"), pad=8)), (0.95, fit(o2, att, pad=10))],
                            callouts=[(dev_btn, 0.30, 0.66), (att_row, 0.80, 1.0)])],
            text=split_text("INCIDENT RECOVERY", "Detect in seconds.", "Deterministic probes catch the fault and point to the exact device.")),
    Product(3, SPLIT, [dict(shot=i3, until=1.01, keys=[(0.0, fit(i3, region(ev["x"], ev["y"], ev["w"], 640), pad=8)), (0.42, fit(i3, region(ev["x"], ev["y"] + 300, ev["w"], 560), pad=8)),
                                                   (0.95, fit(i3, region(tl["x"], tl["y"], tl["w"], 520), pad=8))])],
            text=split_text("INVESTIGATION", "Evidence, not guesswork.", "Command output, interpretation and limitations. Every item timestamped and source-labeled.")),
    Product(4, SPLIT, [dict(shot=i3, until=0.52, keys=[(0.0, fit(i3, ver, pad=40)), (0.5, fit(i3, ver, pad=14))], callouts=[(ver, 0.12, 0.5)]),
                       dict(shot=i4, until=1.01, keys=[(0.5, (60, 0, 1500)), (1.0, (180, 40, 1260))])],
            text=split_text("VERIFICATION", "Proof, not promises.", "A wrong fix fails verification. Resolution requires proven recovery.")),
    Product(5, SPLIT, [dict(shot=a5, until=0.42, keys=[(0.0, fit(a5, region(run["x"], run["y"], run["w"], 560), pad=8)), (0.42, fit(a5, region(run["x"], run["y"] + 120, run["w"], 520), pad=8))]),
                       dict(shot=a6, until=1.01, keys=[(0.42, fit(a6, region(cmp_["x"], cmp_["y"], cmp_["w"], 600), pad=8)), (0.97, fit(a6, region(cmp_["x"], cmp_["y"] + 230, cmp_["w"], 560), pad=8))])],
            text=split_text("SERVER ACCEPTANCE", "Every server, checked.", "Expected versus observed. Immutable runs. A side-by-side re-test.")),
    Product(6, SPLIT, [dict(shot=r7, until=0.48, keys=[(0.0, fit(r7, B(r7, "racks"), pad=10)), (0.48, fit(r7, region(B(r7, "racks")["x"], B(r7, "racks")["y"], B(r7, "racks")["w"] * 0.62, 520), pad=6))]),
                       dict(shot=c8, until=1.01, keys=[(0.48, fit(c8, region(B(c8, "trace")["x"], B(c8, "trace")["y"] - 120, B(c8, "trace")["w"], 420), pad=10)),
                                                    (1.0, fit(c8, region(B(c8, "trace")["x"], B(c8, "trace")["y"] + 40, B(c8, "trace")["w"] * 0.72, 210), pad=10))],
                            callouts=[(region(B(c8, "trace")["x"] + 14, B(c8, "trace")["y"] + 56, B(c8, "trace")["w"] * 0.70, 124), 0.66, 1.0)])],
            text=split_text("INFRASTRUCTURE", "Know every cable.", "Rack elevations and end-to-end traces through every patch panel.")),
    Product(7, SPLIT, [dict(shot=s9, until=0.5, keys=[(0.0, fit(s9, region(wf["x"], wf["y"], wf["w"], 470), pad=8)), (0.5, fit(s9, region(wf["x"], wf["y"] + 160, wf["w"], 520), pad=8))], callouts=[(wf, 0.08, 0.42)]),
                       dict(shot=s10, until=1.01, keys=[(0.5, (256, 150, 1000)), (1.0, (256, 320, 900))])],
            text=split_text("ASSET LIFECYCLE", "Repairs that reconcile.", "Reserve, consume and return in one transactional workflow, with a full audit trail.")),
    Closing(),
]
scenes[1].header_w = font(46, 700).getlength("Everything that matters, at a glance.")

# ---------------------------------------------------------------- timeline
starts, t0 = [], 0.0
for i, s in enumerate(scenes):
    starts.append(t0)
    t0 += s.dur - (XF if i < len(scenes) - 1 else 0)
TOTAL = t0
timeline = {"total": TOTAL, "vo": [{"id": s.vo, "at": round(starts[i] + s.vo_at + (0.0 if i == 0 else XF * 0.5), 3)} for i, s in enumerate(scenes) if s.vo is not None]}
(BUILD / "timeline.json").write_text(json.dumps(timeline, indent=2))
print(f"total {TOTAL:.2f}s, {len(scenes)} scenes", flush=True)

if "--plan" in sys.argv:
    sys.exit(0)

only = None
if "--stills" in sys.argv:  # quick look: one frame from the middle of each scene
    for i, s in enumerate(scenes):
        s.render(s.dur * 0.6).save(BUILD / f"still_{i:02d}.jpg", quality=88)
    sys.exit(0)

enc = subprocess.Popen(
    ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
     "-c:v", "libx264", "-preset", "slow", "-crf", "14", "-tune", "film", "-pix_fmt", "yuv420p", "-profile:v", "high",
     "-x264-params", "aq-mode=3", str(BUILD / "silent.mp4")],
    stdin=subprocess.PIPE)
n = int(TOTAL * FPS)
for fi in range(n):
    t = fi / FPS
    active = [i for i, st in enumerate(starts) if st <= t < st + scenes[i].dur]
    cur = active[-1]
    img = scenes[cur].render(t - starts[cur])
    if len(active) > 1:
        prev = active[-2]
        k = ease((t - starts[cur]) / XF)
        img = Image.blend(scenes[prev].render(t - starts[prev]), img, k)
    enc.stdin.write(img.tobytes())
    if fi % 300 == 0:
        print(f"frame {fi}/{n}", flush=True)
enc.stdin.close()
enc.wait()
print("video done", flush=True)
