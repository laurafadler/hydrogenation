from pathlib import Path
from copy import deepcopy
import json
import re


# Die Kategorien sind reine, nicht-standardisierte Textmarker.  Sie stehen
# jeweils allein in einer Zeile, z. B. ``{++++++ Reactions ++++++`` oder
# ``------ Reactions ------},``.  Der Inhalt zwischen zwei Markern ist
# regulärer Dateinhalt und darf deshalb nicht übersprungen werden.
CATEGORY_MARKER = re.compile(
    r"^(?:\{\+{6,}.*\+{6,}|-{6,}.*-{6,}\}\s*,?)$"
)


def json_tokens(text):
    """Liefert JSON-Tokens samt ihrer Positionen, ohne Leerraum zu verändern."""
    tokens = []
    position = 0
    separators = "{}[],:"

    while position < len(text):
        if text[position].isspace():
            position += 1
            continue

        start = position
        character = text[position]

        if character in separators:
            tokens.append((character, start, start + 1))
            position += 1
        elif character == '"':
            position += 1
            while position < len(text):
                if text[position] == "\\":
                    position += 2
                elif text[position] == '"':
                    position += 1
                    break
                else:
                    position += 1
            tokens.append(("string", start, position))
        else:
            while (
                position < len(text)
                and not text[position].isspace()
                and text[position] not in separators
            ):
                position += 1
            tokens.append(("value", start, position))

    return tokens


def repair_commas(text):
    """Entfernt überflüssige und ergänzt fehlende JSON-Kommas.

    Die Funktion arbeitet nur mit Strukturzeichen außerhalb von Strings. Dadurch
    bleiben beispielsweise Kommas in Beschreibungen oder Namen unverändert.
    """
    tokens = json_tokens(text)
    edits = []  # (Position, Anzahl zu löschender Zeichen, Ersatztext)
    stack = []
    previous = None

    def expected_after_comma(container):
        return "key_or_end" if container == "object" else "value_or_end"

    def is_value(token):
        return token in {"string", "value", "{", "["}

    for index, (token, start, end) in enumerate(tokens):
        # Ein Komma ist nur nach einem vollständigen Objekt-/Array-Element bzw.
        # nach einem Schlüssel-Wert-Paar zulässig.
        if token == ",":
            next_token = tokens[index + 1][0] if index + 1 < len(tokens) else None
            # Vor ] oder } ist ein Komma immer überflüssig.
            if next_token in {"]", "}"}:
                edits.append((start, end - start, ""))
                previous = token
                continue
            if stack and stack[-1][1] == "comma_or_end":
                stack[-1][1] = expected_after_comma(stack[-1][0])
            else:
                edits.append((start, end - start, ""))
            previous = token
            continue

        if stack and stack[-1][1] == "comma_or_end":
            # Ein neues Element ohne Trennzeichen: Komma direkt hinter dem
            # vorherigen Token ergänzen, damit Einrückung erhalten bleibt.
            if is_value(token):
                edits.append((previous[2], 0, ","))
                stack[-1][1] = expected_after_comma(stack[-1][0])

        if token == "{":
            stack.append(["object", "key_or_end"])
        elif token == "[":
            stack.append(["array", "value_or_end"])
        elif token in {"}", "]"}:
            if stack:
                stack.pop()
                if stack:
                    stack[-1][1] = "comma_or_end"
        elif token == ":":
            if stack and stack[-1][0] == "object":
                stack[-1][1] = "value"
        elif stack:
            container, state = stack[-1]
            if container == "object" and state == "key_or_end":
                stack[-1][1] = "colon"
            elif state in {"value", "value_or_end"}:
                stack[-1][1] = "comma_or_end"

        previous = (token, start, end)

    # Mehrere Änderungen werden von hinten angewandt, sodass alle Positionen
    # auf den ursprünglichen Text bezogen bleiben.
    for position, delete_count, replacement in sorted(edits, reverse=True):
        text = text[:position] + replacement + text[position + delete_count :]
    return text


def make_novacrate_compatible(crate):
    """Create a JSON-LD variant accepted by NovaCrate's restricted importer."""
    compatible = deepcopy(crate)
    graph = compatible["@graph"]
    used_ids = {node.get("@id") for node in graph if isinstance(node, dict)}
    id_typed_properties = set()
    notes = []

    # NovaCrate accepts only string definitions in a local context. Properties
    # typed as @id are retained below as explicit {"@id": ...} references.
    contexts = compatible.get("@context")
    context_items = contexts if isinstance(contexts, list) else [contexts]
    for context in context_items:
        if not isinstance(context, dict):
            continue
        for term, definition in list(context.items()):
            if isinstance(definition, dict):
                if definition.get("@type") == "@id":
                    id_typed_properties.add(term)
                del context[term]
                notes.append(f"Local context definition removed: {term}")

    def fresh_id(owner_id, property_name):
        owner = re.sub(r"[^A-Za-z0-9]+", "_", owner_id.lstrip("#")).strip("_")
        prop = re.sub(r"[^A-Za-z0-9]+", "_", property_name).strip("_")
        base = f"#NovaCrate_{owner}_{prop}" or "#NovaCrate_embedded_value"
        candidate = base
        number = 2
        while candidate in used_ids:
            candidate = f"{base}_{number}"
            number += 1
        used_ids.add(candidate)
        return candidate

    def convert_value(value, owner_id, property_name):
        if isinstance(value, list):
            return [convert_value(item, owner_id, property_name) for item in value]

        if not isinstance(value, dict):
            if property_name in id_typed_properties and isinstance(value, str):
                return {"@id": value}
            return value

        if set(value) == {"@id"} and isinstance(value["@id"], str):
            return value

        if "@value" in value:
            notes.append(f"Typed value flattened to text: {owner_id} -> {property_name}")
            return str(value["@value"])

        # A nested node becomes an identifiable top-level entity.
        entity_id = fresh_id(owner_id, property_name)
        embedded = deepcopy(value)
        embedded["@id"] = entity_id
        embedded.setdefault("@type", "Thing")
        for key, nested_value in list(embedded.items()):
            if key not in {"@id", "@type"}:
                embedded[key] = convert_value(nested_value, entity_id, key)
        graph.append(embedded)
        notes.append(f"Embedded node moved to @graph: {entity_id}")
        return {"@id": entity_id}

    index = 0
    while index < len(graph):
        node = graph[index]
        if isinstance(node, dict):
            owner_id = node.get("@id", f"#NovaCrate_node_{index}")
            if "@type" not in node:
                node["@type"] = "schema:Thing"
                notes.append(f"Generic type added for NovaCrate: {owner_id}")
            for property_name, value in list(node.items()):
                if property_name not in {"@id", "@type"}:
                    node[property_name] = convert_value(value, owner_id, property_name)
        index += 1

    return compatible, notes


def novacrate_schema_errors(crate):
    """Check the property shapes accepted by NovaCrate's import schema."""
    errors = []
    context = crate.get("@context")
    context_items = context if isinstance(context, list) else [context]
    for item in context_items:
        if isinstance(item, dict) and any(not isinstance(value, str) for value in item.values()):
            errors.append("The local @context contains a non-string definition.")

    def valid_property_value(value):
        if isinstance(value, (str, int, float, bool)) or value is None:
            return True
        if isinstance(value, dict):
            return set(value) == {"@id"} and isinstance(value["@id"], str)
        if isinstance(value, list):
            return all(valid_property_value(item) for item in value)
        return False

    for node in crate.get("@graph", []):
        if not isinstance(node, dict) or not isinstance(node.get("@id"), str):
            errors.append("An @graph entry has no string @id.")
            continue
        if not isinstance(node.get("@type"), (str, list)):
            errors.append(f"{node['@id']} has no usable @type.")
        for key, value in node.items():
            if key not in {"@id", "@type"} and not valid_property_value(value):
                errors.append(f"Unsupported value in {node['@id']} -> {key}")
    return errors


def clean_jsonld(input_file, output_file=None, novacrate_output_file=None):
    input_path = Path(input_file)

    if output_file is None:
        output_path = input_path.with_name(input_path.stem + "_clean.jsonld")
    else:
        output_path = Path(output_file)

    with open(input_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    cleaned = []
    for line in lines:
        stripped = line.strip()

        # Kommentare: Zeilen, deren erster Nicht-Leerraumcharakter ein % ist.
        if stripped.startswith("%"):
            continue

        # Nur den künstlichen Kategorienamen entfernen, nicht den Inhalt
        # zwischen Anfangs- und Endmarker.
        if CATEGORY_MARKER.fullmatch(stripped):
            continue

        cleaned.append(line)

    cleaned_text = repair_commas("".join(cleaned))

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(cleaned_text)

    print(f"Bereinigte Datei gespeichert als: {output_path}")

    try:
        cleaned_json = json.loads(cleaned_text)
        print("Die bereinigte Datei ist gültiges JSON.")
    except json.JSONDecodeError as error:
        print(
            "Hinweis: Die Datei enthält nach der Komma-Reparatur noch einen "
            f"anderen JSON-Fehler (Zeile {error.lineno}, Spalte {error.colno}): "
            f"{error.msg}"
        )
        return

    if not isinstance(cleaned_json, dict) or "@graph" not in cleaned_json:
        print("Keine NovaCrate-Datei erstellt: Die Datei enthaelt kein @graph.")
        return

    if novacrate_output_file is None:
        novacrate_path = output_path.with_name(
            output_path.stem + "_novacrate" + output_path.suffix
        )
    else:
        novacrate_path = Path(novacrate_output_file)

    novacrate_json, notes = make_novacrate_compatible(cleaned_json)
    errors = novacrate_schema_errors(novacrate_json)
    if errors:
        print("Keine NovaCrate-Datei erstellt; verbleibende Schemafehler:")
        for error in errors:
            print(f"- {error}")
        return

    with open(novacrate_path, "w", encoding="utf-8") as f:
        json.dump(novacrate_json, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"NovaCrate-kompatible Datei gespeichert als: {novacrate_path}")
    if notes:
        print("NovaCrate-Anpassungen:")
        for note in notes:
            print(f"- {note}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Entfernt %-Kommentare und künstliche Kategorie-Marker aus JSON-LD."
    )
    parser.add_argument("input_file", help="Pfad zur JSON-LD-Eingabedatei")
    parser.add_argument(
        "-o", "--output-file", help="Pfad der Ausgabedatei (optional)"
    )
    parser.add_argument(
        "--novacrate-output",
        help="Pfad der zusaetzlichen NovaCrate-kompatiblen Datei (optional)",
    )
    args = parser.parse_args()
    clean_jsonld(args.input_file, args.output_file, args.novacrate_output)
