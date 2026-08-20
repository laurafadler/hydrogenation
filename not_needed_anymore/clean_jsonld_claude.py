"""
Bereinigt eine "annotierte" JSON-LD-Datei:

Schritt 1 (clean_lines):
    - Entfernt Zeilenkommentare, die mit '%' beginnen.
    - Entfernt die dekorativen Cluster-Marker-Zeilen (z.B. "{=== (A) General ====...",
      "==== (A) General -- END ====...}", "{-- (B1) Snapshot ----...",
      "{... (D1.2) Columns ...}" usw.), OHNE den eigentlichen JSON-Inhalt zu verlieren.
      Diese Marker sind reine Gliederungshilfen und keine gueltige JSON-Struktur
      (sie umschliessen jeweils mehrere Komma-getrennte Geschwister-Objekte).

Schritt 2 (validate_and_fix):
    - Versucht die bereinigten Zeilen mit json.loads zu parsen.
    - Bei einem JSONDecodeError wird an der gemeldeten Fehlerposition versucht,
      automatisch ein fehlendes oder ueberzaehliges Komma zu reparieren.
    - Das Ganze wird iterativ wiederholt, bis das JSON gueltig ist (oder ein
      Sicherheitslimit erreicht wird).

Am Ende wird eine neue, sauber eingerueckte, valide .jsonld-Datei geschrieben.
Die Originaldatei bleibt unveraendert.
"""

import json
import re
import sys
import os
from pathlib import Path

# -----------------------------------------------------------------------
# Regex zur Erkennung der Marker-Zeilen.
#
# Oeffnende Marker: "{" wird OHNE Leerzeichen direkt von einem der
# Dekor-Zeichen '=', '—' (em dash) oder '·' gefolgt, z.B.:
#   {=== (A) General ====...
#   {— (B1) Snapshot ----...
#   {· · · (D1.2) - 1.1 · · · Columns of File 1 · · ·
#
# Schliessende Marker: die Zeile beginnt (nach Einrueckung) direkt mit einem
# dieser Dekor-Zeichen und endet mit "}" oder "},", z.B.:
#   ==== (A) General — END ====...}
#   — (B1) Snapshot — END ----...}
#   · · · (D1.2) - 1.1 · · · — END · · ·},
#
# Echte JSON-Zeilen beginnen dagegen immer mit {, }, [, ], ", einer Zahl,
# true/false/null oder einem Komma -- nie mit '=', '—' oder '·'.
# -----------------------------------------------------------------------
DECOR_CHARS = "=\u2014\u00b7"  # '=', '—' (em dash), '·' (middle dot)

OPEN_MARKER_RE = re.compile(rf"^\s*\{{[{DECOR_CHARS}]")
CLOSE_MARKER_RE = re.compile(rf"^\s*[{DECOR_CHARS}].*\}}\s*,?\s*$")
COMMENT_RE = re.compile(r"^\s*%")

# Vereinzelt kommen auch "verwaiste" Trenner-Zeilen ohne { } vor, z.B.:
#   ------------------------- Task Times and Offsets -----------------------
# Diese enthalten keine Anfuehrungszeichen/Klammern/Doppelpunkte/Kommas,
# aber eine laengere Folge von Dekor-Zeichen ('-', '=', '—', '·') -- also
# eindeutig kein JSON-Inhalt.
BARE_DIVIDER_RE = re.compile(r'[\-=\u2014\u00b7]{4,}')


def _is_bare_divider(line: str) -> bool:
    if not line.strip():
        return False
    # Enthaelt die Zeile JSON-Syntaxzeichen, ist es sicher KEIN Divider.
    if any(ch in line for ch in '{}"[]:,'):
        return False
    # Enthaelt sie eine laengere Folge von Dekor-Zeichen -> Divider.
    return bool(BARE_DIVIDER_RE.search(line))


def clean_lines(raw_text: str) -> str:
    """Schritt 1: Kommentare und Cluster-Marker entfernen."""
    # Zeilenenden vereinheitlichen (CRLF -> LF)
    text = raw_text.replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")

    kept = []
    removed_comments = 0
    removed_open = 0
    removed_close = 0
    removed_bare = 0

    for line in lines:
        if COMMENT_RE.match(line):
            removed_comments += 1
            continue
        if OPEN_MARKER_RE.match(line):
            removed_open += 1
            continue
        if CLOSE_MARKER_RE.match(line):
            removed_close += 1
            continue
        if _is_bare_divider(line):
            removed_bare += 1
            continue
        kept.append(line)

    print(f"  - Kommentarzeilen entfernt:      {removed_comments}")
    print(f"  - Oeffnende Cluster-Marker:       {removed_open}")
    print(f"  - Schliessende Cluster-Marker:    {removed_close}")
    print(f"  - Klammerlose Trenner entfernt:   {removed_bare}")
    if removed_open != removed_close:
        print(
            f"  WARNUNG: Anzahl oeffnender ({removed_open}) und schliessender "
            f"({removed_close}) Marker stimmt nicht ueberein!"
        )

    return "\n".join(kept)


# -----------------------------------------------------------------------
# Schritt 2: JSON-Syntax pruefen und ggf. Kommafehler automatisch reparieren
# -----------------------------------------------------------------------

def _fix_one_comma_error(text: str, err: json.JSONDecodeError) -> str | None:
    """
    Versucht, EINEN von json.loads gemeldeten Fehler zu beheben, indem an der
    Fehlerposition ein Komma eingefuegt oder entfernt wird. Gibt den
    korrigierten Text zurueck, oder None, wenn keine Heuristik gepasst hat.
    """
    pos = err.pos
    msg = err.msg

    # Fall 1: "Expecting ',' delimiter" -> an dieser Stelle fehlt ein Komma.
    if "Expecting ',' delimiter" in msg:
        # Komma direkt an der Fehlerposition einfuegen.
        return text[:pos] + "," + text[pos:]

    # Fall 2: "Expecting property name enclosed in double quotes", "Expecting
    # value" oder (je nach Python-Version) "Illegal trailing comma before
    # end of object/array" -> es gibt ein ueberzaehliges (trailing) Komma vor
    # einer schliessenden Klammer.
    if (
        "Expecting property name enclosed in double quotes" in msg
        or "Expecting value" in msg
        or "Illegal trailing comma" in msg
    ):
        before = text[:pos]
        # Suche das letzte Komma vor der Fehlerposition (ueber Whitespace hinweg).
        m = re.search(r",(\s*)$", before)
        if m:
            comma_start = m.start()
            return text[:comma_start] + text[comma_start + 1:]

    return None


def validate_and_fix(text: str, max_attempts: int = 500) -> str:
    """Schritt 2: iterativ pruefen/parsen und Kommafehler automatisch fixen."""
    attempt = 0
    current = text
    while True:
        try:
            json.loads(current)
            print(f"  - JSON ist gueltig (nach {attempt} Korrektur(en)).")
            return current
        except json.JSONDecodeError as err:
            attempt += 1
            if attempt > max_attempts:
                raise RuntimeError(
                    f"Konnte JSON nach {max_attempts} Versuchen nicht reparieren. "
                    f"Letzter Fehler: {err}"
                ) from err

            fixed = _fix_one_comma_error(current, err)
            if fixed is None or fixed == current:
                raise RuntimeError(
                    f"Automatische Reparatur fehlgeschlagen bei Zeile {err.lineno}, "
                    f"Spalte {err.colno}: {err.msg}\n"
                    f"Kontext: ...{current[max(0, err.pos - 80):err.pos + 80]}..."
                ) from err
            current = fixed


def main(input_path: str, output_path: str) -> None:
    src = Path(input_path)
    raw_text = src.read_text(encoding="utf-8")

    print("Schritt 1: Kommentare und Cluster-Marker entfernen ...")
    cleaned = clean_lines(raw_text)

    print("Schritt 2: JSON-Syntax pruefen und ggf. Kommas reparieren ...")
    fixed_text = validate_and_fix(cleaned)

    # Sauber eingerueckt neu ausgeben
    data = json.loads(fixed_text)
    out = Path(output_path)
    out.write_text(json.dumps(data, indent=4, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\nFertig! Bereinigte, valide Datei geschrieben nach: {out}")


if __name__ == "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))

    in_path = os.path.join(script_dir, "hydrogenation_main.jsonld")
    out_path = os.path.join(script_dir, "hydrogenation_main_clean.jsonld")

    main(in_path, out_path)