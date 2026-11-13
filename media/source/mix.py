"""Builds the final soundtrack (voice + ducked music) and muxes it with the rendered video."""
import json
import subprocess
import sys
from pathlib import Path

D = Path(sys.argv[1])
B = D / "build"
OUT = Path(sys.argv[2])
tl = json.loads((B / "timeline.json").read_text())

inputs = ["-i", str(B / "music.wav")]
chains = []
labels = []
for n, v in enumerate(tl["vo"], start=1):
    inputs += ["-i", str(D / "vo" / f"vo_{v['id']:02d}.wav")]
    ms = int(v["at"] * 1000)
    chains.append(f"[{n}:a]adelay={ms}|{ms}[v{n}]")
    labels.append(f"[v{n}]")
k = len(labels)
fc = ";".join(chains) + ";" + "".join(labels) + f"amix=inputs={k}:normalize=0,apad[vo];"
fc += "[vo]asplit=2[voa][vosc];"
fc += "[0:a]volume=-18dB,highpass=f=35,equalizer=f=3000:t=q:w=1.5:g=-4[mus];"
fc += "[mus][vosc]sidechaincompress=threshold=0.012:ratio=8:attack=20:release=450:knee=3[duck];"
fc += f"[duck][voa]amix=inputs=2:normalize=0,atrim=0:{tl['total']:.3f},afade=t=out:st={tl['total'] - 1.4:.3f}:d=1.4,"
fc += "alimiter=limit=0.89:attack=5:release=60,loudnorm=I=-14:TP=-1.5:LRA=11[mix]"

subprocess.run(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", fc, "-map", "[mix]", "-ar", "48000", "-ac", "2",
                str(B / "soundtrack.wav")], check=True)
subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(B / "silent.mp4"), "-i", str(B / "soundtrack.wav"),
                "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "320k", "-shortest",
                "-movflags", "+faststart", "-metadata", "title=RackOps Lab — Product Film", str(OUT)], check=True)
print("wrote", OUT)
