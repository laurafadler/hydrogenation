import re
from pathlib import Path


# ============================================================
# EINSTELLUNGEN
# ============================================================

MAIN_FILE = Path("hydrogenation_V1_6.jsonld")
CONNECTION_FILE = Path("context_connections.json")
OUTPUT_FILE = Path("hydrogenation_with_context_connections.jsonld")


# ============================================================
# HILFSFUNKTIONEN
# ============================================================

def find_matching_brace(text, start_pos):
    """
    Findet die schließende } für eine öffnende {.
    Berücksichtigt verschachtelte Objekte, Arrays und Strings.
    """

    depth = 0
    in_string = False
    escape = False

    for i in range(start_pos, len(text)):

        char = text[i]

        # String-Behandlung
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False

            continue

        if char == '"':
            in_string = True

        elif char == "{":
            depth += 1

        elif char == "}":
            depth -= 1

            if depth == 0:
                return i

    return None


def extract_connection_objects(text):
    """
    Extrahiert alle kleinen Connection-Entities aus der
    separaten Connection-Datei.

    Erwartetes Format:

    {
        "@id": "#Sparger_Energy",
        "ex:contextDescribedBy": [
            ...
        ]
    },

    {
        "@id": "#Sparger_Time",
        ...
    }
    """

    connections = {}

    # Suche nach jedem @id innerhalb der Connection-Datei
    id_pattern = re.compile(
        r'"@id"\s*:\s*"([^"]+)"'
    )

    for match in id_pattern.finditer(text):

        entity_id = match.group(1)

        # Beginn des umgebenden Objekts suchen
        object_start = text.rfind("{", 0, match.start())

        if object_start == -1:
            continue

        object_end = find_matching_brace(text, object_start)

        if object_end is None:
            continue

        object_text = text[object_start:object_end + 1]

        # Nur Objekte mit contextDescribedBy berücksichtigen
        if '"ex:contextDescribedBy"' not in object_text:
            continue

        connections[entity_id] = object_text

    return connections


def find_primary_entity(text, entity_id):
    """
    Sucht die primäre Definition einer Entity.

    Eine gültige Definition muss enthalten:

        "@id": "<entity_id>"
        "@type": ...

    Referenzen wie

        {"@id": "#Sparger_Energy"}

    werden dadurch ignoriert.
    """

    id_pattern = re.compile(
        r'"@id"\s*:\s*"' + re.escape(entity_id) + r'"'
    )

    for match in id_pattern.finditer(text):

        # Das umgebende Objekt bestimmen
        object_start = text.rfind("{", 0, match.start())

        if object_start == -1:
            continue

        object_end = find_matching_brace(text, object_start)

        if object_end is None:
            continue

        object_text = text[object_start:object_end + 1]

        # Prüfen, ob dieses Objekt einen @type besitzt
        if re.search(
            r'"@type"\s*:',
            object_text
        ):
            return object_start, object_end, object_text

    return None


def insert_property(entity_text, connection_text):
    """
    Fügt die Properties aus dem Connection-Objekt
    in das bestehende Entity-Objekt ein.

    Der @id-Eintrag aus dem Connection-Objekt wird entfernt.
    """

    # @id entfernen
    connection_body = re.sub(
        r'"@id"\s*:\s*"[^"]+"\s*,?',
        "",
        connection_text,
        count=1
    ).strip()

    # Äußere { } entfernen
    if connection_body.startswith("{"):
        connection_body = connection_body[1:]

    if connection_body.endswith("}"):
        connection_body = connection_body[:-1]

    connection_body = connection_body.strip()

    if not connection_body:
        return entity_text

    # Prüfen, ob die Entity bereits diese Property besitzt
    property_names = re.findall(
        r'"([^"]+)"\s*:',
        connection_body
    )

    for prop in property_names:

        if re.search(
            r'"' + re.escape(prop) + r'"\s*:',
            entity_text
        ):
            print(
                f"    ! Property '{prop}' bereits vorhanden – "
                f"wird nicht erneut eingefügt."
            )
            return entity_text

    # Position der letzten } bestimmen
    closing_brace = entity_text.rfind("}")

    if closing_brace == -1:
        return entity_text

    before = entity_text[:closing_brace].rstrip()
    after = entity_text[closing_brace:]

    # Bestehendes letztes Element mit Komma versehen,
    # falls nötig
    if before and not before.endswith(","):
        before += ","

    # Einrückung anhand der bestehenden Entity bestimmen
    lines = before.splitlines()

    if lines:
        last_line = lines[-1]

        indentation = re.match(
            r"\s*",
            last_line
        ).group()
    else:
        indentation = "    "

    # Connection-Property einfügen
    connection_lines = connection_body.splitlines()

    formatted_connection = []

    for line in connection_lines:
        if line.strip():
            formatted_connection.append(
                indentation + line.strip()
            )

    inserted = "\n".join(formatted_connection)

    return (
        before
        + "\n"
        + inserted
        + "\n"
        + after
    )


# ============================================================
# HAUPTPROGRAMM
# ============================================================

def main():

    print("=" * 70)
    print("Context Connections werden eingefügt")
    print("=" * 70)

    # --------------------------------------------------------
    # Dateien lesen
    # --------------------------------------------------------

    if not MAIN_FILE.exists():
        print(f"\nFEHLER: Main-Datei nicht gefunden:")
        print(f"       {MAIN_FILE}")
        return

    if not CONNECTION_FILE.exists():
        print(f"\nFEHLER: Connection-Datei nicht gefunden:")
        print(f"       {CONNECTION_FILE}")
        return

    main_text = MAIN_FILE.read_text(
        encoding="utf-8"
    )

    connection_text = CONNECTION_FILE.read_text(
        encoding="utf-8"
    )

    # --------------------------------------------------------
    # Connection-Entities extrahieren
    # --------------------------------------------------------

    connections = extract_connection_objects(
        connection_text
    )

    print(
        f"\nGefundene Context Connections: "
        f"{len(connections)}"
    )

    if not connections:
        print(
            "\nKeine Context Connections gefunden."
        )
        return

    # --------------------------------------------------------
    # Main-Datei bearbeiten
    # --------------------------------------------------------

    inserted = []
    not_found = []
    already_present = []

    # Wichtig:
    # Von hinten nach vorne bearbeiten.
    #
    # Dadurch verändern sich die Positionen der vorherigen
    # Treffer nicht.

    modifications = []

    for entity_id, connection in connections.items():

        result = find_primary_entity(
            main_text,
            entity_id
        )

        if result is None:
            not_found.append(entity_id)
            continue

        start, end, entity_text = result

        # Prüfen, ob Property bereits vorhanden
        if '"ex:contextDescribedBy"' in entity_text:
            already_present.append(entity_id)
            continue

        new_entity_text = insert_property(
            entity_text,
            connection
        )

        modifications.append(
            (
                start,
                end,
                new_entity_text,
                entity_id
            )
        )

    # --------------------------------------------------------
    # Änderungen von hinten nach vorne durchführen
    # --------------------------------------------------------

    modifications.sort(
        key=lambda x: x[0],
        reverse=True
    )

    for start, end, new_entity_text, entity_id in modifications:

        main_text = (
            main_text[:start]
            + new_entity_text
            + main_text[end + 1:]
        )

        inserted.append(entity_id)

    # --------------------------------------------------------
    # Ergebnis speichern
    # --------------------------------------------------------

    OUTPUT_FILE.write_text(
        main_text,
        encoding="utf-8"
    )

    # --------------------------------------------------------
    # Bericht
    # --------------------------------------------------------

    print("\n" + "=" * 70)
    print("ERGEBNIS")
    print("=" * 70)

    print(
        f"\n✓ Eingefügt:          {len(inserted)}"
    )

    print(
        f"! Bereits vorhanden:  {len(already_present)}"
    )

    print(
        f"⚠ Nicht gefunden:     {len(not_found)}"
    )

    if inserted:
        print("\nEingefügte Connections:")

        for entity_id in inserted:
            print(f"  ✓ {entity_id}")

    if already_present:
        print("\nBereits vorhandene Connections:")

        for entity_id in already_present:
            print(f"  ! {entity_id}")

    if not_found:
        print("\nNICHT GEFUNDEN:")

        for entity_id in not_found:
            print(f"  ⚠ {entity_id}")

    print("\n" + "=" * 70)
    print(f"Ausgabedatei:")
    print(f"  {OUTPUT_FILE}")
    print("=" * 70)


if __name__ == "__main__":
    main()