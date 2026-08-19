#!/usr/bin/env python3
"""
extract_ids.py
--------------
Extrahiert alle "@id"-Werte aus einer (pseudo-)JSON-LD-Datei, die mit
manuellen Cluster-Markern wie

    {=== (H) Devices ========================================...
    {· · · (H) - 1  · · · · · · Reactor · · ·
    {— (G1) Material Representations --------------------------

durchsetzt ist, und sortiert sie nach der jeweils groben Top-Level-Kategorie
(z.B. "(G) Materials", "(H) Devices").

Regeln:
- Nur Top-Level-Cluster (Marker, die direkt nach "{" mit "=" beginnen, z.B.
  "{=== (H) Devices ===...") bestimmen die Kategorie, in die eine ID einsortiert
  wird. Tiefere Cluster-Marker (z.B. "{· · · (H) - 1 ...", "{— (G1) ...")
  werden ignoriert (nicht als eigene Kategorie behandelt), man "sieht nur
  hindurch" zur aktuell gültigen Top-Level-Kategorie.
- Eine ID (Wert von "@id") wird bei ihrer ERSTEN Sichtung (egal ob als bloße
  Referenz wie {"@id": "#Vessel"} oder als echte Definition mit weiteren
  Properties) in die aktuell gültige Top-Level-Kategorie einsortiert.
- Wird dieselbe ID SPÄTER an anderer Stelle als "Definition" (JSON-Objekt mit
  "@id" UND mindestens einer weiteren Property, z.B. "@type") gefunden, und
  gehört diese Definition zu einer ANDEREN Top-Level-Kategorie als der
  bisherigen Zuordnung, wird die ID dorthin VERSCHOBEN.
- Sobald eine ID einmal als "definiert" markiert wurde, wird sie durch
  spätere reine Referenzen nicht mehr verschoben.
- Jede ID erscheint in der Ausgabedatei genau einmal.
- Kommentare / Freitext außerhalb von JSON-Strings werden ignoriert
  (z.B. "// ..." Zeilenkommentare), sofern vorhanden.

Nutzung:
    python extract_ids.py input.jsonld output.txt
"""

import re
import sys
from collections import defaultdict


# ---------------------------------------------------------------------------
# Hilfsfunktionen: String-bewusstes Scannen
# ---------------------------------------------------------------------------

def strip_line_comments(text: str) -> str:
    """Entfernt '// ...' Zeilenkommentare außerhalb von JSON-Strings.
    Lässt alles innerhalb von "..."-Strings unangetastet (z.B. URLs mit //)."""
    out = []
    i = 0
    n = len(text)
    in_string = False
    escape = False
    while i < n:
        c = text[i]
        if in_string:
            out.append(c)
            if escape:
                escape = False
            elif c == '\\':
                escape = True
            elif c == '"':
                in_string = False
            i += 1
            continue
        if c == '"':
            in_string = True
            out.append(c)
            i += 1
            continue
        if c == '/' and i + 1 < n and text[i + 1] == '/':
            # bis Zeilenende überspringen
            j = text.find('\n', i)
            if j == -1:
                break
            i = j
            continue
        out.append(c)
        i += 1
    return ''.join(out)


def skip_container(text: str, i: int) -> int:
    """i zeigt auf '{' oder '['. Liefert Index der zugehörigen schließenden
    Klammer, unter Berücksichtigung von String-Literalen. Zählt generisch
    alle {,[,},] als Tiefe (funktioniert korrekt, da JSON-Strukturen
    wohlgeformt verschachtelt sind). Bei fehlendem Match: len(text)-1."""
    n = len(text)
    depth = 0
    in_string = False
    escape = False
    while i < n:
        c = text[i]
        if in_string:
            if escape:
                escape = False
            elif c == '\\':
                escape = True
            elif c == '"':
                in_string = False
        else:
            if c == '"':
                in_string = True
            elif c in '{[':
                depth += 1
            elif c in '}]':
                depth -= 1
                if depth == 0:
                    return i
        i += 1
    return n - 1


TOP_HEADER_RE = re.compile(r'^=+\s*\(([^)]+)\)\s*(.*?)\s*=+\s*$')


def parse(text: str):
    """Parst den gesamten Text und liefert:
    - cluster_order: Liste der Top-Level-Cluster-Namen in Reihenfolge des ersten Auftretens
    - cluster_ids: dict cluster_name -> Liste der IDs (Reihenfolge = erste Zuordnung)
    """
    cluster_ids = defaultdict(list)     # cluster_name -> [ids]
    cluster_id_set = defaultdict(set)   # cluster_name -> set(ids) für schnellen Check
    id_to_cluster = {}                  # id -> aktuell zugeordneter cluster_name
    defined_ids = set()                 # ids, die bereits "definiert" wurden
    cluster_order = []                  # Reihenfolge der Top-Level-Cluster

    def register_cluster(name):
        if name not in cluster_ids:
            cluster_order.append(name)

    def add_id(id_value, cluster_name):
        register_cluster(cluster_name)
        cluster_ids[cluster_name].append(id_value)
        cluster_id_set[cluster_name].add(id_value)
        id_to_cluster[id_value] = cluster_name

    def move_id(id_value, new_cluster):
        old_cluster = id_to_cluster.get(id_value)
        if old_cluster == new_cluster:
            return
        if old_cluster is not None and id_value in cluster_id_set[old_cluster]:
            cluster_ids[old_cluster].remove(id_value)
            cluster_id_set[old_cluster].discard(id_value)
        add_id(id_value, new_cluster)

    def handle_id_occurrence(id_value, direct_other_keys, current_cluster):
        if current_cluster is None:
            current_cluster = "(ohne Top-Level-Cluster)"
        if direct_other_keys:
            # Es ist eine DEFINITION
            if id_value in id_to_cluster and id_value not in defined_ids:
                move_id(id_value, current_cluster)
            elif id_value not in id_to_cluster:
                add_id(id_value, current_cluster)
            else:
                # bereits im gleichen Cluster (evtl. schon definiert) -> nichts tun
                if id_to_cluster.get(id_value) != current_cluster:
                    move_id(id_value, current_cluster)
            defined_ids.add(id_value)
        else:
            # Es ist nur eine REFERENZ
            if id_value not in id_to_cluster:
                add_id(id_value, current_cluster)
            # sonst: schon irgendwo gesehen (als Referenz oder Definition) -> unverändert lassen

    def process_json_object(start, end, current_cluster):
        """start/end: Indizes von '{' und zugehörigem '}'. Extrahiert direkte
        Keys dieses Objekts (ohne in verschachtelte {..}/[..] hineinzuschauen)
        und rekursiert danach in die verschachtelten Strukturen."""
        content_start = start + 1
        content_end = end
        i = content_start
        in_string = False
        escape = False
        direct_keys = []
        id_value = None

        while i < content_end:
            c = text[i]
            if in_string:
                if escape:
                    escape = False
                elif c == '\\':
                    escape = True
                elif c == '"':
                    in_string = False
                i += 1
                continue
            if c == '"':
                str_start = i
                i += 1
                while i < content_end and text[i] != '"':
                    if text[i] == '\\':
                        i += 1
                    i += 1
                key_val = text[str_start + 1:i]
                i += 1  # schließendes Anführungszeichen überspringen
                # prüfen, ob direkt danach ein ':' folgt (=> es ist ein Key)
                j = i
                while j < content_end and text[j] in ' \t\r\n':
                    j += 1
                if j < content_end and text[j] == ':':
                    direct_keys.append(key_val)
                    if key_val == '@id':
                        k = j + 1
                        while k < content_end and text[k] in ' \t\r\n':
                            k += 1
                        if k < content_end and text[k] == '"':
                            vstart = k
                            k += 1
                            while k < content_end and text[k] != '"':
                                if text[k] == '\\':
                                    k += 1
                                k += 1
                            id_value = text[vstart + 1:k]
                    i = j + 1
                    continue
                continue
            if c == '{' or c == '[':
                close = skip_container(text, i)
                i = close + 1
                continue
            i += 1

        other_keys = [k for k in direct_keys if k != '@id']
        if id_value is not None:
            handle_id_occurrence(id_value, other_keys, current_cluster)

        # Rekursion in verschachtelte Strukturen (gleiches Top-Level-Cluster)
        scan_region(content_start, content_end, current_cluster)

    def process_brace_block(open_idx, close_idx, current_cluster):
        content_start = open_idx + 1
        i = content_start
        while i < close_idx and text[i] in ' \t\r\n':
            i += 1
        if i >= close_idx:
            return current_cluster_used_below  # unreachable placeholder
        if text[i] == '"':
            process_json_object(open_idx, close_idx, current_cluster)
            return current_cluster
        else:
            # Cluster-/Fold-Header-Block (kein echtes JSON-Objekt)
            newline_idx = text.find('\n', i)
            if newline_idx == -1 or newline_idx > close_idx:
                header_line = text[i:close_idx]
            else:
                header_line = text[i:newline_idx]
            new_cluster = current_cluster
            if header_line.lstrip().startswith('='):
                m = TOP_HEADER_RE.match(header_line.strip())
                if m:
                    code = m.group(1).strip()
                    name = m.group(2).strip()
                    new_cluster = f"({code}) {name}".strip()
            # tiefere Cluster-Marker (·, —, - ...) -> new_cluster bleibt current_cluster
            scan_region(content_start, close_idx, new_cluster)
            return current_cluster

    def scan_region(region_start, region_end, current_cluster):
        i = region_start
        in_string = False
        escape = False
        while i < region_end:
            c = text[i]
            if in_string:
                if escape:
                    escape = False
                elif c == '\\':
                    escape = True
                elif c == '"':
                    in_string = False
                i += 1
                continue
            if c == '"':
                in_string = True
                i += 1
                continue
            if c == '{':
                close = skip_container(text, i)
                if close > region_end:
                    close = region_end
                process_brace_block(i, close, current_cluster)
                i = close + 1
                continue
            i += 1

    scan_region(0, len(text), None)
    return cluster_order, cluster_ids


def main():
    if len(sys.argv) < 3:
        print("Nutzung: python extract_ids.py <input_datei> <output_datei>")
        sys.exit(1)

    in_path = sys.argv[1]
    out_path = sys.argv[2]

    with open(in_path, 'r', encoding='utf-8') as f:
        raw = f.read()

    text = strip_line_comments(raw)
    cluster_order, cluster_ids = parse(text)

    with open(out_path, 'w', encoding='utf-8') as f:
        for cluster in cluster_order:
            ids = cluster_ids[cluster]
            if not ids:
                continue
            f.write(f"=== {cluster} ===\n")
            for id_value in sorted(ids):   # alphabetisch sortiert innerhalb des Clusters
                f.write(f"{id_value}\n")
            f.write("\n")

    total = sum(len(v) for v in cluster_ids.values())
    print(f"Fertig. {total} eindeutige IDs in {len(cluster_order)} Clustern nach '{out_path}' geschrieben.")


if __name__ == "__main__":
    main()