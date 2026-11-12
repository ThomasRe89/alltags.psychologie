# @alltags.psychologie – automatische Postings

Jeden Tag ab ca. 18:30 Uhr (Wiener Zeit) erstellt und veröffentlicht dieser Ablauf einen Beitrag:
Reels am Mo, Mi, Fr, So, Karussells am Di, Do, Sa.

- `pipeline/themen.json` – geprüfte Themen mit Quellen (nur diese Fakten werden verwendet)
- `pipeline/prompt.md` – Schreibregeln für die Texte
- `pipeline/config.json` – Konto-ID, Wochenplan, Uhrzeit
- `render/` – Vorlagen für Karussell und Reel
- `state/historie.json` – bereits veröffentlichte Beiträge

Manuell starten: Reiter **Actions** > **Posting** > **Run workflow**
(`check` = nur testen, `post` = sofort echt posten).
Jeder Lauf speichert die erzeugten Dateien unter **Artifacts > vorschau**.
