"""Karussell-Vorlage @alltags.psychologie (1080 x 1350, JPEG)."""
import os
from PIL import Image, ImageDraw, ImageFont
from blotlib import blot

W, H = 1080, 1350
M = 96
TINTE = (35, 35, 74); PAPIER = (233, 236, 239); GELB = (242, 193, 78); TAUBE = (122, 134, 184)
FONT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Archivo.ttf")
HANDLE = "@alltags.psychologie"


class TextZuLang(Exception):
    pass


def font(size, weight="Regular"):
    f = ImageFont.truetype(FONT, size)
    f.set_variation_by_name(weight)
    return f


def wrap(d, text, f, maxw):
    lines = []
    for para in text.split("\n"):
        cur = ""
        for w in para.split(" "):
            t = (cur + " " + w).strip()
            if d.textlength(t, font=f) <= maxw:
                cur = t
            else:
                if d.textlength(w, font=f) > maxw:
                    raise TextZuLang(f"Wort zu lang für eine Zeile: {w}")
                lines.append(cur)
                cur = w
        lines.append(cur)
    return lines


def height(d, text, f, maxw, lh):
    return len(wrap(d, text, f, maxw)) * int(f.size * lh)


def block(d, text, f, x, y, maxw, fill, lh=1.18):
    for ln in wrap(d, text, f, maxw):
        d.text((x, y), ln, font=f, fill=fill)
        y += int(f.size * lh)
    return y


TOP, BOTTOM = 120, H - M - 90


def centered_y(total, nr):
    if total > BOTTOM - TOP:
        raise TextZuLang(f"Folie {nr}: Text passt nicht auf die Folie, bitte kürzen")
    return TOP + (BOTTOM - TOP - total) // 2


def frame(d, i, n, bg):
    c = TINTE if bg == GELB else TAUBE
    sf = font(28, "Medium")
    d.text((M, H - M), HANDLE, font=sf, fill=c, anchor="ls")
    d.text((W - M, H - M), f"{i}/{n}", font=sf, fill=c, anchor="rs")


def slide(s, i, n, seed):
    t = s["typ"]
    mw = W - 2 * M
    bg = GELB if t == "aha" else PAPIER
    img = Image.new("RGB", (W, H), bg)
    d = ImageDraw.Draw(img)
    if t == "cover":
        img.paste(blot(seed, 640, TINTE, bg), ((W - 640) // 2, 70))
        fu = font(42, "Medium")
        for gr in (92, 84, 76):  # Schrift bei langen Titeln etwas verkleinern
            ft = font(gr, "ExtraBold")
            hoehe = height(d, s["titel"], ft, mw, 1.08) + (30 + height(d, s["untertitel"], fu, mw, 1.18) if s.get("untertitel") else 0)
            if 720 + hoehe <= H - M - 60:
                break
        else:
            raise TextZuLang("Cover: Titel zu lang, bitte kürzen")
        y = block(d, s["titel"], ft, M, 720, mw, TINTE, 1.08)
        if s.get("untertitel"):
            block(d, s["untertitel"], fu, M, y + 30, mw, TAUBE)
    elif t == "text":
        ft, fb = font(74, "ExtraBold"), font(50, "Regular")
        tot = height(d, s["text"], fb, mw, 1.36)
        if s.get("titel"):
            tot += height(d, s["titel"], ft, mw, 1.1) + 56
        y = centered_y(tot, i)
        if s.get("titel"):
            y = block(d, s["titel"], ft, M, y, mw, TINTE, 1.1) + 56
        block(d, s["text"], fb, M, y, mw, TINTE, 1.36)
    elif t == "zahlen":
        ft, fl, fz = font(64, "ExtraBold"), font(44, "Medium"), font(170, "ExtraBold")
        for z in s["werte"]:
            if d.textlength(z["zahl"], font=fz) > mw:
                raise TextZuLang(f"Folie {i}: Zahl zu breit, bitte kürzer schreiben")
        tot = height(d, s["titel"], ft, mw, 1.1) + 80
        tot += sum(190 + height(d, z["label"], fl, mw, 1.25) + 56 for z in s["werte"])
        y = block(d, s["titel"], ft, M, centered_y(tot, i), mw, TINTE, 1.1) + 80
        for z in s["werte"]:
            d.text((M, y), z["zahl"], font=fz, fill=TINTE if z.get("hervor") else TAUBE, anchor="la")
            y += 190
            y = block(d, z["label"], fl, M, y, mw, TINTE, 1.25) + 56
    elif t == "aha":
        f = font(84, "ExtraBold")
        block(d, s["text"], f, M, centered_y(height(d, s["text"], f, mw, 1.12), i), mw, TINTE, 1.12)
    elif t == "outro":
        y = block(d, s["text"], font(70, "ExtraBold"), M, 200, mw, TINTE, 1.12) + 90
        if s.get("quelle"):
            d.text((M, y), "Quelle", font=font(32, "SemiBold"), fill=TAUBE)
            y += 52
            y = block(d, s["quelle"], font(32, "Regular"), M, y, mw - 40, TAUBE, 1.35)
        if y > H - M - 270:
            raise TextZuLang("Outro: Text zu lang, bitte kürzen")
        img.paste(blot(seed, 170, TINTE, bg), (W - M - 150, H - M - 250))
    else:
        raise ValueError(f"Unbekannter Folientyp: {t}")
    frame(d, i, n, bg)
    return img


def render(spec, outdir):
    """Rendert alle Folien als JPEG und gibt die Dateipfade zurück."""
    os.makedirs(outdir, exist_ok=True)
    folien = spec["folien"]
    n = len(folien)
    imgs = [slide(s, i, n, spec["klecks_seed"]) for i, s in enumerate(folien, 1)]  # erst alles prüfen
    files = []
    for i, img in enumerate(imgs, 1):
        p = os.path.join(outdir, f"{spec['slug']}_{i:02d}.jpg")
        img.save(p, "JPEG", quality=92)
        files.append(p)
    return files
