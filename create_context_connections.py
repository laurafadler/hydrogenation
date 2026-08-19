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

        # Context anlegen
        if context_id not in contexts:
            contexts[context_id] = {
                "@id": context_id,
                "ex:contextDescribedBy": []
            }

        # Entity als JSON-Objekt hinzufügen
        reference = {
            "@id": described_entity
        }

        if reference not in contexts[context_id]["ex:contextDescribedBy"]:
            contexts[context_id]["ex:contextDescribedBy"].append(reference)


# --------------------------------------------------
# Bidirektionale Connections erzeugen
# --------------------------------------------------

entities = {}

for context_id, context_data in contexts.items():

    for reference in context_data["ex:contextDescribedBy"]:

        described_entity = reference["@id"]

        if described_entity not in entities:
            entities[described_entity] = {
                "@id": described_entity,
                "ex:describesContext": []
            }

        context_reference = {
            "@id": context_id
        }

        if context_reference not in entities[described_entity]["ex:describesContext"]:
            entities[described_entity]["ex:describesContext"].append(
                context_reference
            )


# --------------------------------------------------
# Output zusammenbauen
# --------------------------------------------------

output = []

output.extend(contexts.values())
output.extend(entities.values())


# --------------------------------------------------
# JSON speichern
# --------------------------------------------------

with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    json.dump(
        output,
        f,
        indent=4,
        ensure_ascii=False
    )

print(f"JSON erfolgreich erstellt: {OUTPUT_FILE}")