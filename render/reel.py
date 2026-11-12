"""Reel-Vorlage @alltags.psychologie: 9:16-Video mit Text-Animation und eigenem Ambient-Sound."""
import os, subprocess, wave
import numpy as np
from PIL import Image, ImageDraw
from vorlage import font, wrap, TINTE, PAPIER, GELB, TAUBE, HANDLE, TextZuLang
from blotlib import blot

W, H, FPS = 1080, 1920, 30
ML, MR = 96, 170             # rechts Platz für die Instagram-Buttons
TOP, BOTTOM = 330, 1480      # sichere Zone (oben Statusleiste, unten Caption/UI)
MW = W - ML - MR


def fade(im, p):
    """Nur den Alpha-Kanal skalieren, damit nichts grau wird."""
    if p >= 1:
        return im
    r, g, b, a = im.split()
    return Image.merge("RGBA", (r, g, b, a.point(lambda v: int(v * p))))


def ease(t):
    t = max(0, min(1, t))
    return 1 - (1 - t) ** 3


def layer_text(card, nr):
    t = card["typ"]
    bg = GELB if t == "aha" else PAPIER
    L = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(L)
    items = []  # (text, font, farbe, zeilenhöhe, abstand_danach)
    if t == "hook":
        items = [(card["text"], font(96, "ExtraBold"), TINTE, 1.08, 0)]
    elif t == "text":
        if card.get("titel"):
            items.append((card["titel"], font(70, "ExtraBold"), TINTE, 1.1, 44))
        items.append((card["text"], font(58, "Regular"), TINTE, 1.3, 0))
    elif t == "zahlen":
        items.append((card["titel"], font(62, "ExtraBold"), TINTE, 1.1, 60))
        for z in card["werte"]:
            if d.textlength(z["zahl"], font=font(190, "ExtraBold")) > MW:
                raise TextZuLang(f"Karte {nr}: Zahl zu breit, bitte kürzer schreiben")
            items.append((z["zahl"], font(190, "ExtraBold"), TINTE if z.get("hervor") else TAUBE, 1.0, 10))
            items.append((z["label"], font(50, "Medium"), TINTE, 1.25, 56))
    elif t == "aha":
        items = [(card["text"], font(92, "ExtraBold"), TINTE, 1.1, 0)]
    elif t == "outro":
        items = [(card["text"], font(78, "ExtraBold"), TINTE, 1.1, 70)]
        if card.get("quelle"):
            items.append((card["quelle"], font(36, "Regular"), TAUBE, 1.35, 0))
    else:
        raise ValueError(f"Unbekannter Kartentyp: {t}")
    blocks = [(wrap(d, tx, f, MW), f, c, lh, gap) for tx, f, c, lh, gap in items]
    total = sum(len(ls) * int(f.size * lh) + gap for ls, f, c, lh, gap in blocks)
    top = TOP + 520 if t == "hook" else TOP
    if total > BOTTOM - top:
        raise TextZuLang(f"Karte {nr}: Text passt nicht ins Reel, bitte kürzen")
    y = top + (BOTTOM - top - total) // 2
    for ls, f, c, lh, gap in blocks:
        for ln in ls:
            d.text((ML, y), ln, font=f, fill=c)
            y += int(f.size * lh)
        y += gap
    d.text((ML, BOTTOM + 60), HANDLE, font=font(34, "Medium"), fill=TINTE if bg == GELB else TAUBE)
    return bg, L


def dauer(card):
    if card["typ"] == "hook":
        return 3.0
    if card["typ"] == "outro":
        return 3.6
    txt = " ".join([card.get("titel", ""), card.get("text", "")] +
                   [z["zahl"] + " " + z["label"] for z in card.get("werte", [])])
    return float(np.clip(1.4 + len(txt.split()) * 0.27, 2.6, 6.0))


def ambient(sek, cuts, path, sr=44100):
    """Eigener, rechtefreier Klangteppich mit leisem Tropfen bei jedem Kartenwechsel."""
    n = int(sek * sr)
    t = np.arange(n) / sr
    out = np.zeros(n)
    chords = [[220, 261.63, 329.63], [174.61, 220, 261.63], [130.81, 196, 261.63], [196, 246.94, 293.66]]
    seg = 4.0
    for k in range(int(sek / seg) + 1):
        a = int(k * seg * sr)
        b = min(n, int((k + 1) * seg * sr) + sr)
        if a >= n:
            break
        tt = t[a:b] - k * seg
        env = np.minimum(1, tt / 1.2) * np.exp(-np.maximum(0, tt - seg) * 2.5)
        for f in chords[k % 4]:
            for det in (-0.6, 0.6):
                out[a:b] += 0.05 * np.sin(2 * np.pi * (f + det) * tt) * env
    out *= 0.85 + 0.15 * np.sin(2 * np.pi * 0.1 * t)
    for c in cuts:
        a = int(c * sr)
        m = min(n - a, int(0.25 * sr))
        tt = np.arange(m) / sr
        out[a:a + m] += 0.18 * np.sin(2 * np.pi * 880 * tt * np.exp(-tt * 6)) * np.exp(-tt * 18)
    out *= np.minimum(1, np.minimum(t / 0.8, (sek - t) / 1.2))
    out = out / np.max(np.abs(out)) * 0.5
    with wave.open(path, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes((out * 32767).astype(np.int16).tobytes())


def render(spec, outdir):
    """Rendert das Reel. Gibt (mp4, cover_jpg, dauer_sekunden) zurück."""
    os.makedirs(outdir, exist_ok=True)
    slug, cards = spec["slug"], spec["karten"]
    pre = [layer_text(c, i) for i, c in enumerate(cards, 1)]  # prüft vorab alle Längen
    durs = [dauer(c) for c in cards]
    total = sum(durs)
    cuts = list(np.cumsum([0] + durs[:-1]))
    B = blot(spec["klecks_seed"], 560, TINTE, PAPIER).convert("RGBA")
    wav = os.path.join(outdir, slug + ".wav")
    ambient(total, cuts, wav)
    mp4 = os.path.join(outdir, slug + ".mp4")
    ff = subprocess.Popen(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
         "-r", str(FPS), "-i", "-", "-i", wav, "-c:v", "libx264", "-preset", "medium", "-crf", "20",
         "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-movflags", "+faststart",
         "-shortest", mp4], stdin=subprocess.PIPE)
    cover = None
    for ci, (c, (bg, L), d) in enumerate(zip(cards, pre, durs)):
        base = Image.new("RGB", (W, H), bg)
        for fi in range(int(round(d * FPS))):
            s = fi / FPS
            img = base.copy()
            if c["typ"] == "hook":
                p = ease(s / 0.7)
                sz = int(560 * (0.82 + 0.18 * p))
                bl = fade(B.resize((sz, sz)), p)
                img.paste(bl, ((W - sz) // 2, TOP + 40 + (560 - sz) // 2), bl)
            p = ease((s - (0.25 if c["typ"] == "hook" else 0)) / 0.25)
            if p > 0:
                Lp = fade(L, p)
                img.paste(Lp, (0, int(30 * (1 - p))), Lp)
            if ci == 0 and fi == int(1.5 * FPS):
                cover = img.copy()
            ff.stdin.write(img.tobytes())
    ff.stdin.close()
    if ff.wait() != 0:
        raise RuntimeError("ffmpeg ist fehlgeschlagen")
    os.remove(wav)
    cp = os.path.join(outdir, slug + "_cover.jpg")
    cover.save(cp, "JPEG", quality=92)
    return mp4, cp, round(total, 1)
