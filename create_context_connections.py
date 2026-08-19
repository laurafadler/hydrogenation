import pandas as pd
import json

# --------------------------------------------------
# Einstellungen
# --------------------------------------------------

INPUT_FILE = "context_connections.xlsx"
OUTPUT_FILE = "context_connections.json"

CONTEXT_COLUMNS = [
    "Information",
    "Energy",
    "Time",
    "Space",
    "Structure",
    "Substance"
]


# --------------------------------------------------
# Excel einlesen
# --------------------------------------------------

df = pd.read_excel(INPUT_FILE)


# --------------------------------------------------
# Context-Verbindungen sammeln
# --------------------------------------------------

contexts = {}

for _, row in df.iterrows():

    entity = row["Entity"]

    if pd.isna(entity) or entity == 0:
        continue

    entity = str(entity).strip()

    for context_type in CONTEXT_COLUMNS:

        value = row[context_type]

        if pd.isna(value) or value == 0:
            continue

        described_entity = str(value).strip()

        if not described_entity:
            continue

        # Context-ID erzeugen
        context_id = f"{entity}_{context_type}"

        # Context anlegen, falls noch nicht vorhanden
        if context_id not in contexts:
            contexts[context_id] = {
                "@id": context_id,
                "ex:contextDescribedBy": []
            }

        # Entity als beschreibende Entity hinzufügen
        if described_entity not in contexts[context_id]["ex:contextDescribedBy"]:
            contexts[context_id]["ex:contextDescribedBy"].append(
                described_entity
            )


# --------------------------------------------------
# Bidirektionale Connections erzeugen
# --------------------------------------------------

entities = {}

for context_id, context_data in contexts.items():

    for described_entity in context_data["ex:contextDescribedBy"]:

        if described_entity not in entities:
            entities[described_entity] = {
                "@id": described_entity,
                "ex:describesContext": []
            }

        if context_id not in entities[described_entity]["ex:describesContext"]:
            entities[described_entity]["ex:describesContext"].append(
                context_id
            )


# --------------------------------------------------
# Output zusammenbauen
# --------------------------------------------------

output = []

# Context Entities
output.extend(contexts.values())

# Describing Entities
output.extend(entities.values())


# --------------------------------------------------
# JSON speichern
# --------------------------------------------------

with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    json.dump(output, f, indent=4, ensure_ascii=False)

print(f"JSON erfolgreich erstellt: {OUTPUT_FILE}")