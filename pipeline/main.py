"""Pipeline @alltags.psychologie.

Befehle:
  pruefen                      Instagram-Zugang testen
  vorbereiten --modus M        Thema wählen, Text erstellen, prüfen, rendern (M = auto | check | post)
  veroeffentlichen --base-url U [--nur-test]
"""
import argparse, json, os, re, sys, time, datetime, random
from zoneinfo import ZoneInfo
import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "render"))
import vorlage, reel  # noqa: E402

P = lambda *a: os.path.join(ROOT, *a)
CFG = json.load(open(P("pipeline", "config.json"), encoding="utf-8"))
HIST_PATH = P("state", "historie.json")
SITE = P("site")
BUILD = P("build")
HOSTS = ["https://graph.facebook.com", "https://graph.instagram.com"]


def log(*a):
    print(*a, flush=True)


def ausgabe(**kv):
    """Werte an GitHub Actions übergeben."""
    path = os.environ.get("GITHUB_OUTPUT")
    for k, v in kv.items():
        log(f"  -> {k}={v}")
        if path:
            with open(path, "a") as f:
                f.write(f"{k}={v}\n")


def jetzt():
    return datetime.datetime.now(ZoneInfo(CFG["zeitzone"]))


def lade_hist():
    return json.load(open(HIST_PATH, encoding="utf-8"))


# ---------------------------------------------------------------- Instagram

class ApiFehler(Exception):
    pass


def api(method, host, pfad, **params):
    params["access_token"] = os.environ["IG_ACCESS_TOKEN"]
    ver = CFG.get("graph_version") or ""
    url = f"{host}/{ver + '/' if ver else ''}{pfad}"
    for versuch in range(4):
        try:
            r = requests.request(method, url, params=params if method == "GET" else None,
                                 data=params if method == "POST" else None, timeout=90)
            j = r.json()
        except Exception as e:  # Netzwerkfehler: kurz warten, nochmal
            if versuch == 3:
                raise ApiFehler(f"Netzwerkfehler: {e}")
            time.sleep(10 * (versuch + 1))
            continue
        if "error" in j:
            err = j["error"]
            if err.get("is_transient") and versuch < 3:
                time.sleep(15 * (versuch + 1))
                continue
            raise ApiFehler(f"{err.get('code')} {err.get('error_subcode', '')}: {err.get('message')}")
        return j


def finde_host():
    ig = CFG["ig_user_id"]
    fehler = []
    for h in HOSTS:
        try:
            j = api("GET", h, ig, fields="username")
            return h, j.get("username")
        except ApiFehler as e:
            fehler.append(f"{h}: {e}")
    raise ApiFehler("Der Instagram-Token wird nicht akzeptiert.\n" + "\n".join(fehler))


def cmd_pruefen(_):
    if not os.environ.get("IG_ACCESS_TOKEN"):
        sys.exit("FEHLER: Secret IG_ACCESS_TOKEN fehlt. Bitte in GitHub unter Settings > Secrets eintragen.")
    host, name = finde_host()
    log(f"Instagram-Zugang OK: @{name} über {host}")
    if name and name.lower() != "alltags.psychologie":
        sys.exit(f"FEHLER: Token gehört zu @{name}, nicht zu @alltags.psychologie.")


def warte_fertig(host, cid, max_sek=600):
    t0 = time.time()
    while True:
        j = api("GET", host, cid, fields="status_code,status")
        code = j.get("status_code")
        if code == "FINISHED":
            return
        if code in ("ERROR", "EXPIRED"):
            raise ApiFehler(f"Instagram konnte die Datei nicht verarbeiten: {j.get('status')}")
        if time.time() - t0 > max_sek:
            raise ApiFehler("Zeitüberschreitung bei der Verarbeitung durch Instagram")
        time.sleep(8)


def warte_url(url, max_sek=300):
    t0 = time.time()
    while time.time() - t0 < max_sek:
        try:
            if requests.head(url, timeout=20, allow_redirects=True).status_code == 200:
                return
        except Exception:
            pass
        time.sleep(10)
    raise ApiFehler(f"Datei ist nicht öffentlich erreichbar: {url}")


def cmd_veroeffentlichen(args):
    post = json.load(open(os.path.join(BUILD, "post.json"), encoding="utf-8"))
    base = args.base_url.rstrip("/")
    urls = [f"{base}/{os.path.basename(f)}" for f in post["dateien"]]
    for u in urls:
        warte_url(u)
    host, name = finde_host()
    ig = CFG["ig_user_id"]
    log(f"Erstelle Beitrag {post['slug']} ({post['format']}) für @{name}")
    if post["format"] == "karussell":
        kinder = []
        for u in urls:
            kinder.append(api("POST", host, f"{ig}/media", image_url=u, is_carousel_item="true")["id"])
        for k in kinder:
            warte_fertig(host, k)
        cid = api("POST", host, f"{ig}/media", media_type="CAROUSEL", children=",".join(kinder),
                  caption=post["caption"])["id"]
    else:
        video = [u for u in urls if u.endswith(".mp4")][0]
        cover = [u for u in urls if u.endswith("_cover.jpg")][0]
        cid = api("POST", host, f"{ig}/media", media_type="REELS", video_url=video, cover_url=cover,
                  caption=post["caption"], share_to_feed="true")["id"]
    warte_fertig(host, cid)
    if args.nur_test:
        log("TEST erfolgreich: Instagram hat den Beitrag angenommen und verarbeitet.")
        log("Er wurde NICHT veröffentlicht (Testmodus). Der Entwurf verfällt automatisch nach 24 Stunden.")
        return
    mid = api("POST", host, f"{ig}/media_publish", creation_id=cid)["id"]
    link = ""
    try:
        link = api("GET", host, mid, fields="permalink").get("permalink", "")
    except ApiFehler:
        pass
    log(f"VERÖFFENTLICHT: {link or mid}")
    hist = lade_hist()
    eintrag = post["eintrag"]
    eintrag.update({"media_id": mid, "link": link, "zeit": jetzt().isoformat(timespec="minutes")})
    hist.append(eintrag)
    json.dump(hist, open(HIST_PATH, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


# ---------------------------------------------------------------- Text

def zahlen(text):
    return set(re.findall(r"\d+(?:[.,]\d+)?", text))


def claude(system, user):
    key = os.environ.get("ANTHROPIC_API_KEY")
    if os.environ.get("MOCK_ANTWORT"):  # nur für lokale Tests
        return open(os.environ["MOCK_ANTWORT"], encoding="utf-8").read()
    if not key:
        sys.exit("FEHLER: Secret ANTHROPIC_API_KEY fehlt.")
    letzter = None
    for modell in CFG["modelle"]:
        r = requests.post("https://api.anthropic.com/v1/messages", timeout=180, headers={
            "x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            json={"model": modell, "max_tokens": 4000, "system": system,
                  "messages": [{"role": "user", "content": user}]})
        if r.status_code == 404 or (r.status_code == 400 and "model" in r.text.lower()):
            letzter = f"Modell {modell} nicht verfügbar"
            continue
        if r.status_code != 200:
            raise RuntimeError(f"Anthropic-API Fehler {r.status_code}: {r.text[:500]}")
        return "".join(b.get("text", "") for b in r.json()["content"])
    raise RuntimeError(letzter or "Kein Modell verfügbar")


def pruefe(spec, thema, fmt):
    """Gibt eine Liste von Problemen zurück (leer = alles gut)."""
    p = []
    teile = spec.get("folien") if fmt == "karussell" else spec.get("karten")
    if not isinstance(teile, list):
        return ["Feld 'folien' bzw. 'karten' fehlt"]
    if not 6 <= len(teile) <= 8:
        p.append(f"Es müssen 6 bis 8 Folien/Karten sein, nicht {len(teile)}")
    erst = "cover" if fmt == "karussell" else "hook"
    typen = [t.get("typ") for t in teile]
    if typen[:1] != [erst] or typen[-1:] != ["outro"] or typen[-2:-1] != ["aha"]:
        p.append(f"Reihenfolge falsch: erste '{erst}', vorletzte 'aha', letzte 'outro'")
    if typen.count("zahlen") > 1:
        p.append("Höchstens eine zahlen-Folie")
    cap = spec.get("caption", "")
    if not cap or len(cap) > 2000:
        p.append("Caption fehlt oder ist länger als 2000 Zeichen")
    tags = re.findall(r"#\w+", cap)
    if len(tags) > 5:
        p.append("Höchstens 5 Hashtags")
    if "#alltagspsychologie" not in tags:
        p.append("#alltagspsychologie fehlt")
    if thema["quelle"] not in cap:
        p.append("Die Quelle muss exakt in der Caption stehen")
    if teile and teile[-1].get("quelle") != thema["quelle"]:
        p.append("Die Quelle auf der letzten Folie muss exakt wie vorgegeben sein")
    gesamt = json.dumps(teile, ensure_ascii=False) + cap
    if "–" in gesamt or "—" in gesamt:
        p.append("Keine Gedankenstriche verwenden")
    erlaubt = zahlen(thema["kern"] + " " + thema["quelle"] + " " + thema.get("hinweis", "") + " " + thema["titel"])
    fremd = zahlen(gesamt) - erlaubt
    if fremd:
        p.append(f"Diese Zahlen stehen nicht in den Fakten und sind verboten: {', '.join(sorted(fremd))}")
    return p


def waehle_thema(hist):
    themen = json.load(open(P("pipeline", "themen.json"), encoding="utf-8"))
    benutzt = {h["thema_id"] for h in hist}
    offen = [t for t in themen if t["id"] not in benutzt and t.get("status") != "manuell"]
    if not offen:
        sys.exit("FEHLER: Alle Themen sind verbraucht. Bitte neue Themen in pipeline/themen.json ergänzen.")
    letzte = hist[-1]["saeule"] if hist else None
    anders = [t for t in offen if t["saeule"] != letzte]
    return (anders or offen)[0], len(offen)


def cmd_vorbereiten(args):
    hist = lade_hist()
    now = jetzt()
    heute = now.date().isoformat()
    if args.modus == "auto":
        h, m = map(int, CFG["frueheste_uhrzeit"].split(":"))
        if (now.hour, now.minute) < (h, m):
            log(f"Noch zu früh ({now:%H:%M}), dieser Lauf wird übersprungen.")
            return ausgabe(go="false", publish="false")
        if any(e.get("datum") == heute for e in hist):
            log("Heute wurde bereits gepostet, nichts zu tun.")
            return ausgabe(go="false", publish="false")
    elif args.modus == "post" and any(e.get("datum") == heute for e in hist):
        log("Hinweis: Heute wurde bereits gepostet. Es wird trotzdem ein weiterer Beitrag erstellt.")

    thema, rest = waehle_thema(hist)
    fmt = args.format or CFG["wochenplan"][str(now.weekday())]
    nr = max(e["nr"] for e in hist) + 1 if hist else 1
    slug = f"{nr:03d}_{re.sub('[^a-z0-9]+', '-', thema['id'].lower()).strip('-')}"
    log(f"Beitrag {nr}: {thema['titel']} als {fmt} (noch {rest} Themen offen)")
    if rest <= 7:
        log(f"WARNUNG: Nur noch {rest} Themen in der Liste. Bitte bald ergänzen.")

    system = open(P("pipeline", "prompt.md"), encoding="utf-8").read()
    letzte_hooks = "\n".join(f"- {e.get('hook', '')}" for e in hist[-6:])
    user = (f"FORMAT = {fmt}\n\nTHEMA:\n{json.dumps(thema, ensure_ascii=False, indent=1)}\n\n"
            f"Die letzten Hooks (formuliere deine Hook bewusst anders):\n{letzte_hooks}")
    spec, probleme = None, []
    for versuch in range(1, 5):
        msg = user if not probleme else user + "\n\nDein letzter Entwurf hatte diese Probleme, behebe sie:\n- " + "\n- ".join(probleme)
        roh = claude(system, msg).strip()
        roh = re.sub(r"^```(?:json)?|```$", "", roh, flags=re.M).strip()
        try:
            spec = json.loads(roh[roh.index("{"): roh.rindex("}") + 1])
        except Exception:
            probleme = ["Die Antwort war kein gültiges JSON"]
            continue
        probleme = pruefe(spec, thema, fmt)
        if not probleme:
            spec.update({"slug": slug, "klecks_seed": nr * 101 + random.randint(0, 50)})
            os.makedirs(SITE, exist_ok=True)
            try:
                if fmt == "karussell":
                    dateien = vorlage.render(spec, SITE)
                else:
                    mp4, cover, dauer = reel.render(spec, SITE)
                    dateien = [mp4, cover]
                    log(f"Reel-Länge: {dauer} Sekunden")
                break
            except vorlage.TextZuLang as e:
                probleme = [str(e)]
        log(f"Versuch {versuch} nicht in Ordnung: {probleme}")
    else:
        sys.exit("FEHLER: Nach 4 Versuchen kein fehlerfreier Beitrag. Nichts wurde gepostet.")

    os.makedirs(BUILD, exist_ok=True)
    with open(os.path.join(SITE, f"{slug}_caption.txt"), "w", encoding="utf-8") as f:
        f.write(spec["caption"])
    eintrag = {"nr": nr, "datum": heute, "thema_id": thema["id"], "format": fmt, "slug": slug,
               "saeule": thema["saeule"], "hook": spec.get("hook", "")}
    json.dump({"slug": slug, "format": fmt, "caption": spec["caption"], "dateien": dateien,
               "eintrag": eintrag, "spec": spec}, open(os.path.join(BUILD, "post.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    log("Caption:\n" + spec["caption"])
    ausgabe(go="true", publish="true")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("pruefen")
    v = sub.add_parser("vorbereiten"); v.add_argument("--modus", default="auto", choices=["auto", "check", "post"]); v.add_argument("--format", choices=["karussell", "reel"])
    p = sub.add_parser("veroeffentlichen"); p.add_argument("--base-url", required=True); p.add_argument("--nur-test", action="store_true")
    a = ap.parse_args()
    try:
        {"pruefen": cmd_pruefen, "vorbereiten": cmd_vorbereiten, "veroeffentlichen": cmd_veroeffentlichen}[a.cmd](a)
    except ApiFehler as e:
        sys.exit(f"FEHLER bei Instagram: {e}")


if __name__ == "__main__":
    main()
