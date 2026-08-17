import re
from collections import defaultdict


# ============================================================
# EINSTELLUNGEN
# ============================================================

JSONLD_FILE = "hydrogenation_V1_6.jsonld"
OUTPUT_FILE = "Entity_IDs_by_Cluster.txt"


# ============================================================
# DATEI EINLESEN
# ============================================================

with open(JSONLD_FILE, "r", encoding="utf-8") as file:
    lines = file.readlines()


# ============================================================
# CLUSTER ERKENNEN
# ============================================================

# Erkennt z.B.:
#
# (A) - 1
# (B) - 2
# (K1) - 5
# (J) - 1.X
#
# Für die Kategorie wird nur der Inhalt der Klammer verwendet.

cluster_pattern = re.compile(
    r"\(\s*([A-N])(?:\d+)?\s*\)"
)


# ============================================================
# ENTITY IDs ERKENNEN
# ============================================================

id_pattern = re.compile(
    r'"@id"\s*:\s*"([^"]+)"'
)


# ============================================================
# DATENSTRUKTUR
# ============================================================

entities_by_cluster = defaultdict(list)

# Hier speichern wir alle IDs, die bereits gefunden wurden.
# Dadurch wird jede ID nur EINMAL ausgegeben.

seen_ids = set()


# Standardkategorie
current_cluster = "Uncategorized"


# ============================================================
# DATEI DURCHLAUFEN
# ============================================================

for line in lines:

    # --------------------------------------------------------
    # Prüfen, ob eine neue Kategorie beginnt
    # --------------------------------------------------------

    cluster_match = cluster_pattern.search(line)

    if cluster_match:
        current_cluster = cluster_match.group(1)


    # --------------------------------------------------------
    # @id suchen
    # --------------------------------------------------------

    id_match = id_pattern.search(line)

    if not id_match:
        continue

    entity_id = id_match.group(1)


    # Nur IDs mit # berücksichtigen
    if not entity_id.startswith("#"):
        continue


    # --------------------------------------------------------
    # Doppelte IDs verhindern
    # --------------------------------------------------------

    if entity_id in seen_ids:
        continue


    seen_ids.add(entity_id)


    # --------------------------------------------------------
    # Entity der aktuellen Kategorie zuordnen
    # --------------------------------------------------------

    entities_by_cluster[current_cluster].append(entity_id)


# ============================================================
# AUSGABE-DATEI ERSTELLEN
# ============================================================

with open(OUTPUT_FILE, "w", encoding="utf-8") as file:

    file.write("=" * 70 + "\n")
    file.write("ENTITY IDs NACH CLUSTER\n")
    file.write("=" * 70 + "\n\n")


    total_entities = 0


    # --------------------------------------------------------
    # A bis N
    # --------------------------------------------------------

    for letter in "ABCDEFGHIJKLMN":

        if letter not in entities_by_cluster:
            continue

        file.write(f"({letter})\n")
        file.write("-" * 50 + "\n")

        for entity_id in entities_by_cluster[letter]:
            file.write(f"{entity_id}\n")
            total_entities += 1

        file.write("\n")


    # --------------------------------------------------------
    # Uncategorized ganz am Ende
    # --------------------------------------------------------

    if "Uncategorized" in entities_by_cluster:

        file.write("Uncategorized\n")
        file.write("-" * 50 + "\n")

        for entity_id in entities_by_cluster["Uncategorized"]:
            file.write(f"{entity_id}\n")
            total_entities += 1

        file.write("\n")


    # --------------------------------------------------------
    # Gesamtzahl
    # --------------------------------------------------------

    file.write("=" * 70 + "\n")
    file.write(f"GESAMT: {total_entities} ENTITY IDs\n")
    file.write("=" * 70 + "\n")


# ============================================================
# KONSOLE
# ============================================================

print()
print("=" * 70)
print("FERTIG")
print("=" * 70)
print()
print(f"Gefundene eindeutige Entity IDs: {total_entities}")
print()
print(f"Ausgabedatei: {OUTPUT_FILE}")