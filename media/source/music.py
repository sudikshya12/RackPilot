"""Original ambient-tech music bed, synthesized from scratch (no samples).

Progression (A minor / C major colour): Fmaj9 - G6 - Am9 - Em7, 100 BPM, one chord per bar of 4 beats.
Layers: detuned warm pad, sub bass, plucked arpeggio with ping-pong delay, soft pulse, noise riser, FFT reverb.
"""
import sys
import wave

import numpy as np

SR = 48000
OUT = sys.argv[1]
DUR = float(sys.argv[2])            # total length in seconds
INTRO = float(sys.argv[3])          # seconds of pad-only intro (title card)
BPM = 100
BEAT = 60 / BPM
BAR = BEAT * 4
t = np.arange(int(SR * DUR)) / SR


def midi(n):
    return 440.0 * 2 ** ((n - 69) / 12)


CHORDS = [  # (bass root, voicing)
    (41, [53, 57, 60, 64, 67]),   # Fmaj9: F2 | F3 A3 C4 E4 G4
    (43, [55, 59, 62, 64, 69]),   # G6/9:  G2 | G3 B3 D4 E4 A4
    (45, [57, 60, 64, 67, 71]),   # Am9:   A2 | A3 C4 E4 G4 B4
    (40, [55, 59, 62, 64, 66]),   # Em7add9 colour: E2 | G3 B3 D4 E4 F#4
]


def env_ar(n, attack, release):
    e = np.ones(n)
    a = min(int(attack * SR), n // 2)
    r = min(int(release * SR), n - a)
    e[:a] = np.linspace(0, 1, a) ** 2
    e[-r:] *= np.linspace(1, 0, r) ** 1.5
    return e


def onepole_lp(x, cutoff):
    a = np.exp(-2 * np.pi * cutoff / SR)
    y = np.empty_like(x)
    acc = 0.0
    # vectorised in blocks via cumulative filter (scipy-free): use lfilter-equivalent loop in chunks
    for i in range(len(x)):
        acc = (1 - a) * x[i] + a * acc
        y[i] = acc
    return y


L = np.zeros_like(t)
R = np.zeros_like(t)

# ---------------------------------------------------------------- pad + bass
n_bars = int(np.ceil(DUR / BAR)) + 1
for b in range(n_bars):
    root, notes = CHORDS[b % len(CHORDS)]
    start = b * BAR
    length = BAR + 1.6                      # overlap into next bar for legato
    i0 = int(start * SR)
    i1 = min(len(t), int((start + length) * SR))
    if i0 >= len(t):
        break
    tt = t[i0:i1] - start
    e = env_ar(i1 - i0, 1.4, 1.8)
    for k, n in enumerate(notes):
        f = midi(n)
        pan = (k / (len(notes) - 1)) * 0.8 - 0.4
        voice = np.zeros_like(tt)
        for det in (-0.07, 0.0, 0.065):     # detuned trio, soft harmonics
            ff = f * 2 ** (det / 12)
            ph = np.random.default_rng(n * 7 + k).uniform(0, 2 * np.pi)
            voice += np.sin(2 * np.pi * ff * tt + ph) + 0.28 * np.sin(4 * np.pi * ff * tt + ph) + 0.09 * np.sin(6 * np.pi * ff * tt)
        voice *= e * 0.030 * (1 + 0.12 * np.sin(2 * np.pi * 0.21 * tt + k))  # slow shimmer
        L[i0:i1] += voice * (1 - pan) / 2 * 2
        R[i0:i1] += voice * (1 + pan) / 2 * 2
    bass = np.sin(2 * np.pi * midi(root - 12) * tt) * e * 0.11 + np.sin(2 * np.pi * midi(root) * tt) * e * 0.025
    L[i0:i1] += bass
    R[i0:i1] += bass

# ---------------------------------------------------------------- arpeggio (enters after intro)
step = BEAT / 2
pattern = [0, 2, 4, 1, 3, 4, 2, 1]
arpL = np.zeros_like(t)
arpR = np.zeros_like(t)
nsteps = int(DUR / step)
for s in range(nsteps):
    st = s * step
    if st < INTRO - 0.2 or st > DUR - 4.0:
        continue
    bar = int(st // BAR)
    _, notes = CHORDS[bar % len(CHORDS)]
    n = notes[pattern[s % len(pattern)]] + 12
    f = midi(n)
    i0 = int(st * SR)
    i1 = min(len(t), i0 + int(0.9 * SR))
    tt = t[i0:i1] - st
    vel = 0.75 + 0.25 * ((s % 4) == 0)
    pl = (np.sin(2 * np.pi * f * tt) + 0.35 * np.sin(4 * np.pi * f * tt) * np.exp(-14 * tt)) * np.exp(-5.2 * tt) * (1 - np.exp(-tt * 400))
    pl *= 0.045 * vel
    pan = 0.25 if s % 2 else -0.25
    arpL[i0:i1] += pl * (1 - pan)
    arpR[i0:i1] += pl * (1 + pan)
# ping-pong dotted-eighth delay
d = int(BEAT * 0.75 * SR)
for rep, g in enumerate([0.42, 0.26, 0.15]):
    sh = d * (rep + 1)
    if rep % 2 == 0:
        arpR[sh:] += arpL[:-sh] * g
    else:
        arpL[sh:] += arpR[:-sh] * g
fade_in = np.clip((t - INTRO + 0.4) / 3.0, 0, 1)
L += arpL * fade_in
R += arpR * fade_in

# ---------------------------------------------------------------- soft pulse (kick on beats 1 & 3)
kick = np.zeros_like(t)
k_len = int(0.32 * SR)
kt = np.arange(k_len) / SR
kshape = np.sin(2 * np.pi * (48 * kt + 70 / 18 * (1 - np.exp(-18 * kt)))) * np.exp(-11 * kt)
beat = 0.0
while beat < DUR - 3.0:
    if beat >= INTRO + BAR:            # enter one bar after the intro
        i0 = int(beat * SR)
        i1 = min(len(t), i0 + k_len)
        kick[i0:i1] += kshape[: i1 - i0] * 0.16
    beat += BEAT * 2
L += kick
R += kick

# ---------------------------------------------------------------- riser into first scene
rng = np.random.default_rng(3)
noise = rng.standard_normal(len(t))
rz = np.zeros_like(t)
r0, r1 = INTRO - 2.6, INTRO + 0.15
m = (t >= r0) & (t < r1)
x = (t[m] - r0) / (r1 - r0)
rz[m] = noise[m] * (x ** 2.4) * 0.05
rz = onepole_lp(rz, 2600)
L += rz
R += rz

# ---------------------------------------------------------------- reverb (FFT convolution with decaying noise IR)
ir_len = int(2.8 * SR)
it = np.arange(ir_len) / SR
irL = rng.standard_normal(ir_len) * np.exp(-it * 2.4)
irR = rng.standard_normal(ir_len) * np.exp(-it * 2.4)
for ir in (irL, irR):
    ir[: int(0.012 * SR)] = 0
    ir /= np.sqrt(np.sum(ir ** 2))


def conv(x, h):
    n = len(x) + len(h) - 1
    N = 1 << (n - 1).bit_length()
    return np.fft.irfft(np.fft.rfft(x, N) * np.fft.rfft(h, N), N)[: len(x)]


wetL, wetR = conv(L, irL), conv(R, irR)
L = L * 0.78 + wetL * 0.42
R = R * 0.78 + wetR * 0.42

# ---------------------------------------------------------------- master: gentle tilt, fades, normalise
master_env = np.clip(t / 2.5, 0, 1) * np.clip((DUR - t) / 5.0, 0, 1) ** 1.3
L *= master_env
R *= master_env
peak = max(np.abs(L).max(), np.abs(R).max())
L, R = L / peak * 0.80, R / peak * 0.80
pcm = (np.stack([L, R], axis=1) * 32767).astype("<i2")
with wave.open(OUT, "wb") as w:
    w.setnchannels(2)
    w.setsampwidth(2)
    w.setframerate(SR)
    w.writeframes(pcm.tobytes())
print("music", DUR, "s ->", OUT)
