import re
from pathlib import Path


MAIN_FILE = Path("hydrogenation_V1_6.jsonld")
CONNECTION_FILE = Path("context_connections.json")
OUTPUT_FILE = Path("main_with_context_connections.jsonld")


def find_end(text, start):
    """Findet die passende schließende } für ein Objekt."""
    depth = 0
    in_string = False
    escape = False

    for i in range(start, len(text)):
        char = text[i]

        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
        else:
            if char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1

                if depth == 0:
                    return i

    return None


def get_connections(text):
    """
    Liest ID und Property aus der Connection-Datei.
    Die Property wird automatisch erkannt.
    """

    connections = {}

    pattern = re.compile(r'"@id"\s*:\s*"([^"]+)"')

    for match in pattern.finditer(text):

        entity_id = match.group(1)

        start = text.rfind("{", 0, match.start())
        end = find_end(text, start)

        if start == -1 or end is None:
            continue

        obj = text[start:end + 1]

        # @id entfernen
        obj_without_id = re.sub(
            r'"@id"\s*:\s*"[^"]+"\s*,?',
            "",
            obj,
            count=1
        ).strip()

        # Alles zwischen { und } behalten
        obj_without_id = obj_without_id[1:-1].strip()

        if obj_without_id:
            connections[entity_id] = obj_without_id

    return connections


def find_entity(text, entity_id):
    """Findet die primäre Entity mit @id und @type."""

    pattern = re.compile(
        r'"@id"\s*:\s*"' + re.escape(entity_id) + r'"'
    )

    for match in pattern.finditer(text):

        start = text.rfind("{", 0, match.start())
        end = find_end(text, start)

        if start == -1 or end is None:
            continue

        obj = text[start:end + 1]

        # Nur echte Entity-Definitionen
        if re.search(r'"@type"\s*:', obj):
            return start, end, obj

    return None


def add_connection(entity, connection):
    """Fügt die erkannte Property in die Entity ein."""

    # Property-Namen aus der Connection erkennen
    properties = re.findall(
        r'"([^"]+)"\s*:',
        connection
    )

    # Falls eine der Properties schon vorhanden ist:
    # nichts hinzufügen.
    for prop in properties:

        if re.search(
            r'"' + re.escape(prop) + r'"\s*:',
            entity
        ):
            return entity, False

    end = entity.rfind("}")

    before = entity[:end].rstrip()
    after = entity[end:]

    if not before.endswith(","):
        before += ","

    new_entity = (
        before
        + "\n"
        + "                "
        + connection
        + "\n"
        + after
    )

    return new_entity, True


# ============================================================
# MAIN
# ============================================================

main = MAIN_FILE.read_text(encoding="utf-8")
connection_text = CONNECTION_FILE.read_text(encoding="utf-8")

connections = get_connections(connection_text)

print(f"Gefundene Connections: {len(connections)}")

changes = []
not_found = []
already_exists = []

for entity_id, connection in connections.items():

    result = find_entity(main, entity_id)

    if result is None:
        not_found.append(entity_id)
        continue

    start, end, entity = result

    new_entity, added = add_connection(
        entity,
        connection
    )

    if not added:
        already_exists.append(entity_id)
        continue

    changes.append(
        (start, end, new_entity, entity_id)
    )


# Von hinten nach vorne einsetzen
for start, end, new_entity, entity_id in sorted(
    changes,
    reverse=True
):

    main = (
        main[:start]
        + new_entity
        + main[end + 1:]
    )


OUTPUT_FILE.write_text(
    main,
    encoding="utf-8"
)


print()
print(f"Eingefügt:        {len(changes)}")
print(f"Schon vorhanden:  {len(already_exists)}")
print(f"Nicht gefunden:   {len(not_found)}")

if not_found:
    print("\nNicht gefundene IDs:")

    for entity_id in not_found:
        print("  ", entity_id)

print()
print("Fertig:", OUTPUT_FILE)