import re
from collections import defaultdict


# ============================================================
# Einstellungen
# ============================================================

JSONLD_FILE = "deine_datei.jsonld"


# ============================================================
# Datei einlesen
# ============================================================

with open(JSONLD_FILE, "r", encoding="utf-8") as file:
    content = file.read()


# ============================================================
# Entity IDs nach Cluster sortieren
# ============================================================

entities_by_cluster = defaultdict(list)

current_cluster = "Uncategorized"


# Sucht nach Cluster-Markierungen wie:
# (A) - 1 ··· ...
# (B) - 2 ··· ...
# (J) - 1.X ··· ...
cluster_pattern = re.compile(
    r"\(\s*([A-Z])\s*\)\s*-\s*[\dA-Za-z.]+"
)


# Sucht nach "@id": "#..."
id_pattern = re.compile(
    r'"@id"\s*:\s*"([^"]+)"'
)


for line in content.splitlines():

    # --------------------------------------------------------
    # Prüfen, ob eine neue Cluster-Kategorie beginnt
    # --------------------------------------------------------

    cluster_match = cluster_pattern.search(line)

    if cluster_match:
        current_cluster = cluster_match.group(1)

    # --------------------------------------------------------
    # Prüfen, ob die Zeile eine @id enthält
    # --------------------------------------------------------

    id_match = id_pattern.search(line)

    if id_match:
        entity_id = id_match.group(1)

        # Nur Entity IDs mit # berücksichtigen
        if entity_id.startswith("#"):
            entities_by_cluster[current_cluster].append(entity_id)


# ============================================================
# Ausgabe
# ============================================================

print("\n" + "=" * 70)
print("ENTITY IDs NACH CLUSTER")
print("=" * 70)


for cluster in sorted(entities_by_cluster):

    print(f"\n({cluster})")
    print("-" * 50)

    for entity_id in entities_by_cluster[cluster]:
        print(entity_id)


# ============================================================
# Gesamtliste
# ============================================================

all_entities = [
    entity_id
    for cluster in sorted(entities_by_cluster)
    for entity_id in entities_by_cluster[cluster]
]

print("\n" + "=" * 70)
print(f"GESAMT: {len(all_entities)} ENTITY IDs")
print("=" * 70)