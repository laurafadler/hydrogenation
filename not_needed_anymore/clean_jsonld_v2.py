import re
import json

INPUT_FILE = "hydrogenation_main.jsonld"
OUTPUT_FILE = "hydrogenation_clean.jsonld"


# ==================================================
# 1. Datei einlesen
# ==================================================

with open(INPUT_FILE, "r", encoding="utf-8") as f:
    text = f.read()


# ==================================================
# 2. % Kommentare entfernen
# ==================================================

text = re.sub(r"(?m)^\s*%.*\n?", "", text)


# ==================================================
# 3. Cluster-Markierungen entfernen
# ==================================================

# Cluster-Anfang:
#
# {=== (N) Times =========================
# {— (B1) Snapshot -----------------------
# {· · · (N) · · · Reactor · · ·
# *{—* *(E1)* *Experimental* *Series* *----,
#
# Wichtig:
# Die eigentliche JSON-Struktur innerhalb des
# Clusters bleibt erhalten.


cluster_start = re.compile(
    r"^\s*\{?\s*.*?\(\s*[A-Z]\d+\s*\).*"
    r"(?:—|={2,}|-{2,}|·|\*).*?$",
    re.MULTILINE
)

text = cluster_start.sub("", text)


# ==================================================
# 4. Cluster-Endmarkierungen entfernen
# ==================================================

# Beispiele:
#
# — (B1) Snapshot — END -----------------------
# · · · Reactor — END · · ·},
#
# Die komplette Markierungszeile wird entfernt.

text = re.sub(
    r"(?m)^\s*.*?\(\s*[A-Z]\d+\s*\).*?—\s*END.*?$",
    "",
    text
)


# ==================================================
# 5. Leere Zeilen reduzieren
# ==================================================

text = re.sub(r"\n\s*\n+", "\n\n", text)


# ==================================================
# 6. Überflüssige Kommata entfernen
# ==================================================

# ,}
# ,]

text = re.sub(r",\s*}", "}", text)
text = re.sub(r",\s*]", "]", text)


# ==================================================
# 7. Offensichtliche fehlende Kommata ergänzen
# ==================================================

# --------------------------------------------------
# Fall A:
#
# }
# {
#
# -> },
# {
#
# --------------------------------------------------

text = re.sub(
    r"}\s*\n(\s*){",
    r"},\n\1{",
    text
)


# --------------------------------------------------
# Fall B:
#
# ]
# [
#
# -> ],
# [
#
# --------------------------------------------------

text = re.sub(
    r"]\s*\n(\s*)\[",
    r"],\n\1[",
    text
)


# --------------------------------------------------
# Fall C:
#
# }
# [
#
# -> },
# [
#
# --------------------------------------------------

text = re.sub(
    r"}\s*\n(\s*)\[",
    r"},\n\1[",
    text
)


# --------------------------------------------------
# Fall D:
#
# ]
# {
#
# -> ],
# {
#
# --------------------------------------------------

text = re.sub(
    r"]\s*\n(\s*){",
    r"],\n\1{",
    text
)


# ==================================================
# 8. JSON prüfen
# ==================================================

try:

    data = json.loads(text)

except json.JSONDecodeError as e:

    print()
    print("==============================================")
    print("JSON IST NICHT GÜLTIG")
    print("==============================================")
    print()

    print(f"Fehler:   {e.msg}")
    print(f"Zeile:    {e.lineno}")
    print(f"Spalte:   {e.colno}")

    lines = text.splitlines()

    start = max(0, e.lineno - 3)
    end = min(len(lines), e.lineno + 2)

    print()
    print("Kontext:")
    print("----------------------------------------------")

    for i in range(start, end):
        marker = ">>>" if i == e.lineno - 1 else "   "
        print(f"{marker} {i + 1}: {lines[i]}")

    print("----------------------------------------------")
    print()

    raise SystemExit(
        "Die bereinigte Datei wurde NICHT gespeichert."
    )


# ==================================================
# 9. Sauber formatiert speichern
# ==================================================

with open(OUTPUT_FILE, "w", encoding="utf-8") as f:

    json.dump(
        data,
        f,
        indent=4,
        ensure_ascii=False
    )


print()
print("==============================================")
print("ERFOLGREICH")
print("==============================================")
print()
print(f"✓ JSON ist gültig.")
print(f"✓ Datei gespeichert: {OUTPUT_FILE}")