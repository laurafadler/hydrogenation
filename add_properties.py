import json
import re
import os

def get_previous_char(text, start_idx):
    """
    Findet das erste Zeichen vor start_idx, das kein Whitespace und kein Kommentar ist.
    """
    idx = start_idx - 1
    while idx >= 0:
        char = text[idx]
        if char.isspace():
            idx -= 1
            continue
        
        # Zeilenanfang suchen, um Kommentare zu überspringen
        line_start = text.rfind('\n', 0, idx + 1)
        if line_start == -1:
            line_start = 0
        else:
            line_start += 1
            
        line_text = text[line_start:idx + 1].strip()
        if line_text.startswith('%'):
            # Es ist eine Kommentarzeile, überspringe sie komplett
            idx = line_start - 1
            continue
            
        return char
    return None

def find_matching_brace(text, start_index):
    """
    Findet die öffnende und schließende geschweifte Klammer für die Entity,
    die den gefundenen @id-String enthält, unter Berücksichtigung von Strings und Escapes.
    """
    open_brace_idx = text.rfind('{', 0, start_index)
    if open_brace_idx == -1:
        return None, None
    
    depth = 0
    in_string = False
    escape = False
    for i in range(open_brace_idx, len(text)):
        char = text[i]
        if escape:
            escape = False
            continue
        if char == '\\':
            escape = True
            continue
        if char == '"':
            in_string = not in_string
            continue
        if not in_string:
            if char == '{':
                depth += 1
            elif char == '}':
                depth -= 1
                if depth == 0:
                    return open_brace_idx, i
    return None, None

def clean_json_text(text):
    """
    Entfernt zeilenweise %-Kommentare aus dem spezifischen JSON-Block,
    damit er fehlerfrei als JSON interpretiert werden kann.
    """
    lines = text.split('\n')
    cleaned_lines = [line for line in lines if not re.match(r'^\s*%', line)]
    return '\n'.join(cleaned_lines)

def is_primary_entity(text, open_idx, parsed_obj):
    """
    Prüft, ob es sich bei dem JSON-Objekt um die primäre Definition der Entity handelt
    oder nur um eine Referenz (wie z.B. in einer Property oder einem Array).
    """
    # 1. Referenzen in JSON-LD enthalten typischerweise nur "@id" und keine weiteren Attribute
    if len(parsed_obj.keys()) <= 1 and "@type" not in parsed_obj:
        return False
        
    # 2. Wenn vor der öffnenden Klammer ein Doppelpunkt ':' steht, ist es ein Property-Wert (also nested/Referenz)
    prev_char = get_previous_char(text, open_idx)
    if prev_char == ':':
        return False
        
    return True

def merge_properties(existing_obj, new_properties):
    """
    Führt die Properties zusammen. Listen (wie ex:contextDescribedBy) werden 
    ohne Duplikate (basierend auf der @id der enthaltenen Objekte) gemergt.
    """
    for prop, new_val in new_properties.items():
        if prop == "@id":
            continue
        if prop not in existing_obj:
            existing_obj[prop] = new_val
        else:
            existing_val = existing_obj[prop]
            if isinstance(existing_val, list) and isinstance(new_val, list):
                # Merge von Listen von Objekten (z.B. [{"@id": "..."}, ...]) ohne Duplikate
                merged = list(existing_val)
                existing_ids = {item["@id"] for item in existing_val if isinstance(item, dict) and "@id" in item}
                for item in new_val:
                    if isinstance(item, dict) and "@id" in item:
                        if item["@id"] not in existing_ids:
                            merged.append(item)
                            existing_ids.add(item["@id"])
                    else:
                        if item not in merged:
                            merged.append(item)
                existing_obj[prop] = merged
            else:
                existing_obj[prop] = new_val
    return existing_obj

def main():
    # Dateipfade definieren
    connections_file = "context_connections.json"
    hydrogenation_file = "hydrogenation_main.jsonld"
    output_file = "hydrogenation_with_added_properties.jsonld"
    
    # Prüfen, ob Fallback-Namen genutzt werden müssen
    if not os.path.exists(connections_file) and os.path.exists("context_connections.json"):
        connections_file = "context_connections.json"
        
    print(f"--- Starte Zusammenführung (mit Primär-Entity-Erkennung) ---")
    print(f"Lese Verbindungen aus: {connections_file}")
    print(f"Lese Hydrogenation aus: {hydrogenation_file}")
    
    if not os.path.exists(connections_file):
        print(f"[FEHLER] Datei '{connections_file}' nicht gefunden!")
        return
    if not os.path.exists(hydrogenation_file):
        print(f"[FEHLER] Datei '{hydrogenation_file}' nicht gefunden!")
        return
        
    # 1. Connections einlesen
    try:
        with open(connections_file, 'r', encoding='utf-8') as f:
            connections_data = json.load(f)
    except Exception as e:
        print(f"[FEHLER] Fehler beim Lesen der Connections-Datei: {e}")
        return

    # Map der neuen Verbindungen erstellen
    connection_map = {conn["@id"]: conn for conn in connections_data if "@id" in conn}
    
    # 2. Hydrogenation-Datei als reinen Text einlesen
    with open(hydrogenation_file, 'r', encoding='utf-8') as f:
        hydrogenation_text = f.read()
        
    # 3. Finde alle @id-Vorkommen im Text
    matches = []
    for match in re.finditer(r'"@id"\s*:\s*"([^"]+)"', hydrogenation_text):
        entity_id = match.group(1)
        if entity_id in connection_map:
            open_idx, close_idx = find_matching_brace(hydrogenation_text, match.start())
            if open_idx is not None and close_idx is not None:
                # Vorläufiges JSON-Parsing zur Überprüfung, ob es eine Primär-Entity ist
                obj_text = hydrogenation_text[open_idx:close_idx+1]
                cleaned_obj_text = clean_json_text(obj_text)
                try:
                    cleaned_obj_text = re.sub(r',\s*([\]}])', r'\1', cleaned_obj_text)
                    existing_obj = json.loads(cleaned_obj_text)
                    
                    if is_primary_entity(hydrogenation_text, open_idx, existing_obj):
                        matches.append({
                            "id": entity_id,
                            "start": open_idx,
                            "end": close_idx,
                        })
                except Exception as e:
                    # Parse-Fehler ignorieren, diese Entity wird nicht als Primär-Match gelistet
                    pass
                
    # Sortiere von hinten nach vorne, um Verschiebung der Indizes bei Ersetzungen zu verhindern
    matches.sort(key=lambda x: x["start"], reverse=True)
    
    updated_text = hydrogenation_text
    applied_ids = set()
    
    for match in matches:
        entity_id = match["id"]
        start = match["start"]
        end = match["end"]
        
        # Extrahiere den originalen JSON-Block der Entity
        obj_text = updated_text[start:end+1]
        
        # Bereinige interne Kommentare für den Parser
        cleaned_obj_text = clean_json_text(obj_text)
        
        try:
            # Trailing Commas bereinigen
            cleaned_obj_text = re.sub(r',\s*([\]}])', r'\1', cleaned_obj_text)
            existing_obj = json.loads(cleaned_obj_text)
        except Exception as e:
            print(f"[WARNUNG] Konnte Entity '{entity_id}' nicht als JSON parsen. Fehler: {e}")
            continue
            
        # Mergen der Properties
        new_props = connection_map[entity_id]
        updated_obj = merge_properties(existing_obj, new_props)
        
        # Serialisieren des aktualisierten Objekts
        serialized_obj = json.dumps(updated_obj, indent=4, ensure_ascii=False)
        
        # Ersetzen im Gesamttext
        updated_text = updated_text[:start] + serialized_obj + updated_text[end+1:]
        applied_ids.add(entity_id)
        
    # 4. Warnmeldungen ausgeben für fehlende Entities
    missing_ids = set(connection_map.keys()) - applied_ids
    if missing_ids:
        print("\n--- Fehlende Entities (wurden übersprungen) ---")
        for m_id in sorted(missing_ids):
            print(f"[INFO] Entity '{m_id}' existiert nicht (oder hat keine Primärdefinition) in '{hydrogenation_file}'.")
            
    # 5. Speichern in neuer Datei
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(updated_text)
        print(f"\n[ERFOLG] Zusammenführung abgeschlossen! Gespeichert als: '{output_file}'")
    except Exception as e:
        print(f"[FEHLER] Konnte Ausgabedatei nicht schreiben: {e}")

if __name__ == "__main__":
    main()
