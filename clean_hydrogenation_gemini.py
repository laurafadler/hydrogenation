import re
import json
import os
import sys

def is_cluster_line(line):
    """
    Erkennt, ob eine Zeile ein Kommentar (%) oder ein einklappbarer Cluster-Trenner ist.
    Dazu gehören Sektions-Header und -Footer mit ===, ---, ——, · · ·.
    """
    stripped = line.strip()
    
    # 1. Zeilenweise Kommentare (%) entfernen
    if stripped.startswith('%'):
        return True
    
    # 2. Cluster-Trenner erkennen (haben charakteristische Trennzeichen)
    indicators = ['===', '---', '——', '· · ·', '···', '— END', '— END', '— END']
    if any(ind in stripped for ind in indicators):
        # Struktur-Check: Ein Trenner beginnt/endet meist mit geschweiften Klammern
        if stripped.startswith('{') or stripped.endswith('}') or stripped.endswith('},') or stripped.endswith('}}'):
            # Um Fehlalarme bei echten JSON-Attributen zu vermeiden: Zeile darf nicht mit Anführungszeichen beginnen
            if not (stripped.startswith('"') or stripped.startswith("'")):
                return True
    return False

def clean_and_repair_jsonld(text):
    """
    Bereinigt den Text von Kommentaren und Trennern und korrigiert einfache Syntaxfehler.
    """
    lines = text.split('\n')
    cleaned_lines = []
    removed_count = 0
    
    for line_num, line in enumerate(lines, 1):
        if is_cluster_line(line):
            removed_count += 1
            continue
        cleaned_lines.append(line)
        
    cleaned_text = '\n'.join(cleaned_lines)
    
    # Automatische Reparaturen
    # 1. Fehlende Kommata zwischen zwei JSON-Objekten (z.B. } { -> }, {)
    repaired_text = re.sub(r'\}\s*\{', '},\n{', cleaned_text)
    
    # 2. Zuviele Kommata am Ende von Objekten/Listen entfernen (Trailing Commas)
    repaired_text = re.sub(r',\s*\}', '}', repaired_text)
    repaired_text = re.sub(r',\s*\]', ']', repaired_text)
    
    return repaired_text, removed_count

def print_error_context(text, error):
    """
    Gibt den genauen Kontext eines JSON-Dekodierungsfehlers im Terminal aus.
    """
    lines = text.split('\n')
    err_line = error.lineno
    start_line = max(1, err_line - 5)
    end_line = min(len(lines), err_line + 5)
    
    print(f"\n[SYNTAX-FEHLER] In Zeile {err_line}, Spalte {error.colno}: {error.msg}")
    print(f"--- Fehlerausschnitt (Zeilen {start_line} bis {end_line}) ---")
    
    for l_num in range(start_line, end_line + 1):
        line_content = lines[l_num - 1]
        marker = ">>> " if l_num == err_line else "    "
        print(f"{marker}{l_num:4d}: {line_content}")
    print("-" * 50)

def main():
    input_file = "hydrogenation_main.jsonld"
    output_file = "ro-crate-metadata.json"  # Offizieller Standardname
    
    print("=== Starte JSON-LD Bereinigung und Validierung ===")
    
    # Prüfen, ob eine alternative Eingabedatei übergeben wurde
    if len(sys.argv) > 1:
        input_file = sys.argv[1]
    if len(sys.argv) > 2:
        output_file = sys.argv[2]
        
    if not os.path.exists(input_file):
        print(f"[FEHLER] Eingabedatei '{input_file}' nicht gefunden!")
        print("Tipp: Platziere das Skript im selben Ordner wie deine .jsonld Datei.")
        return

    print(f"Lese Datei: {input_file}...")
    with open(input_file, 'r', encoding='utf-8') as f:
        raw_content = f.read()
        
    print("Entferne Kommentare und Trenner-Cluster...")
    cleaned_content, removed_lines = clean_and_repair_jsonld(raw_content)
    print(f"-> {removed_lines} Kommentar-/Trenner-Zeilen erfolgreich entfernt.")
    
    print("Validiere bereinigtes JSON-LD...")
    try:
        # Versuche das bereinigte JSON zu parsen
        parsed_json = json.loads(cleaned_content)
        print("[ERFOLG] Die Syntax ist fehlerfrei und valides JSON-LD!")
        
        # Schreibt die Datei formatiert zurück
        print(f"Schreibe formatiertes und bereinigtes JSON-LD in '{output_file}'...")
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(parsed_json, f, indent=4, ensure_ascii=False)
        print("[FERTIG] Datei erfolgreich bereinigt und gespeichert!")
        
    except json.JSONDecodeError as e:
        print("\n[WARNUNG] Das JSON-LD enthält noch Syntaxfehler, die nicht automatisch repariert werden konnten.")
        print_error_context(cleaned_content, e)
        print("Tipp: Korrigiere den markierten Fehler in deiner Quelldatei und lasse das Skript erneut laufen.")

if __name__ == "__main__":
    main()
