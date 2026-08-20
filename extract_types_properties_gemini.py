import json
import os
import sys

# JSON-LD System-Keywords, die wir separat erfassen und nicht als standardmäßige Properties auflisten
JSONLD_KEYWORDS = {
    "@context", "@graph", "@id", "@type", "@value", "@language", 
    "@list", "@set", "@reverse", "@index", "@base", "@vocab", 
    "@version", "@import"
}

def classify_value(val):
    """
    Klassifiziert den Wert einer Property in eine der vier Kategorien:
    - entity (Einzelnes verlinktes Objekt mit @id)
    - entity list (Liste von verlinkten Objekten mit @id)
    - inline value (Wertobjekt mit @value und @type)
    - value (Primitiver Wert oder Liste von primitiven Werten)
    """
    if isinstance(val, dict):
        if "@value" in val:
            return "inline value"
        elif "@id" in val:
            return "entity"
        else:
            # Falls ein anderes Dictionary vorliegt, das z.B. einen Typen deklariert
            return "entity" if "@type" in val else "value"
    elif isinstance(val, list):
        if not val:
            return "value"
        # Prüfen, ob alle Elemente verlinkte Entities sind
        if all(isinstance(item, dict) and "@id" in item and "@value" not in item for item in val):
            return "entity list"
        # Prüfen, ob alle Elemente inline typisierte Werte sind
        if all(isinstance(item, dict) and "@value" in item for item in val):
            return "inline value"
        return "value"
    else:
        return "value"

def main():
    # Standard-Pfade
    input_file = "ro-crate-metadata.json"
    output_file = "extracted_types_and_properties.txt"

    # Optionale Argumente über das Terminal ermöglichen
    if len(sys.argv) > 1:
        input_file = sys.argv[1]
    if len(sys.argv) > 2:
        output_file = sys.argv[2]

    print("=== Starte Typen- und Property-Extraktion ===")
    print(f"Lese JSON-LD-Datei: {input_file}")

    if not os.path.exists(input_file):
        print(f"[FEHLER] Die Datei '{input_file}' konnte nicht gefunden werden.")
        print("Tipp: Führe zuerst das Bereinigungs-Skript 'clean_hydrogenation.py' aus,")
        print("oder übergib den korrekten Pfad als Argument: python extract_metadata.py dateiname.jsonld")
        return

    try:
        with open(input_file, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print(f"[FEHLER] Die JSON-Datei konnte nicht gelesen werden. Details: {e}")
        return

    system_keywords = set()
    used_types = set()
    used_properties = {}

    def traverse(node):
        if isinstance(node, dict):
            # 1. System-Keywords erfassen
            for key in JSONLD_KEYWORDS:
                if key in node:
                    system_keywords.add(key)

            # 2. Verwendete Typen (@type) erfassen
            if "@type" in node:
                t_val = node["@type"]
                if isinstance(t_val, list):
                    for t in t_val:
                        used_types.add(str(t))
                else:
                    used_types.add(str(t_val))

            # 3. Properties und deren Ziel-Typen erfassen
            for k, v in node.items():
                if k in JSONLD_KEYWORDS:
                    # Wir traversieren tiefer (z.B. in @graph oder @context), 
                    # listen das Keyword selbst aber nicht als Property auf
                    if k in ["@context", "@graph"]:
                        traverse(v)
                    continue

                # Bestimme den Ziel-Typen des Wertes
                target_type = classify_value(v)
                if k not in used_properties:
                    used_properties[k] = set()
                used_properties[k].add(target_type)

                # Rekursive Traversion für verschachtelte Objekte
                traverse(v)

        elif isinstance(node, list):
            for item in node:
                traverse(item)

    # Starte die Traversion
    traverse(data)

    # Schreiben der Ergebnisse in die Textdatei
    try:
        with open(output_file, "w", encoding="utf-8") as f:
            f.write("=== JSON-LD System-Keywords ===\n")
            for kw in sorted(system_keywords):
                f.write(f"{kw}\n")
            f.write("\n")

            f.write("=== Verwendete Types ===\n")
            for ut in sorted(used_types):
                f.write(f"{ut}\n")
            f.write("\n")

            f.write("=== Verwendete Properties ===\n")
            for prop in sorted(used_properties.keys()):
                types_list = sorted(list(used_properties[prop]))
                types_str = ", ".join(types_list)
                f.write(f"{prop} ({types_str})\n")

        print(f"\n[ERFOLG] Analyse abgeschlossen!")
        print(f"Die Ergebnisse wurden in '{output_file}' gespeichert.")
        print(f"Gefundene System-Keywords: {len(system_keywords)}")
        print(f"Gefundene Typen: {len(used_types)}")
        print(f"Gefundene Properties: {len(used_properties)}")

    except Exception as e:
        print(f"[FEHLER] Konnte die Ausgabedatei '{output_file}' nicht schreiben. Details: {e}")

if __name__ == "__main__":
    main()
