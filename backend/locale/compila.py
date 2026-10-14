"""
Compila i file .po in .mo senza GNU gettext (solo libreria standard).
Uso: python locale/compila.py
"""

import ast
import struct
from pathlib import Path


def leggi_po(percorso):
    voci, msgid, msgstr, campo = {}, None, None, None
    for riga in percorso.read_text(encoding="utf-8").splitlines() + [""]:
        riga = riga.strip()
        if riga.startswith("msgid "):
            if msgid is not None:
                voci[msgid] = msgstr
            msgid, msgstr, campo = ast.literal_eval(riga[6:]), "", "id"
        elif riga.startswith("msgstr "):
            msgstr, campo = ast.literal_eval(riga[7:]), "str"
        elif riga.startswith('"'):
            if campo == "id":
                msgid += ast.literal_eval(riga)
            else:
                msgstr += ast.literal_eval(riga)
    if msgid is not None:
        voci[msgid] = msgstr
    return voci


def scrivi_mo(voci, percorso):
    chiavi = sorted(voci)
    ids = b"".join(k.encode() + b"\0" for k in chiavi)
    strs = b"".join(voci[k].encode() + b"\0" for k in chiavi)
    n = len(chiavi)
    inizio_ids = 7 * 4 + 16 * n
    inizio_strs = inizio_ids + len(ids)
    tab_ids, tab_strs, o_id, o_str = [], [], 0, 0
    for k in chiavi:
        lk, lv = len(k.encode()), len(voci[k].encode())
        tab_ids += [lk, inizio_ids + o_id]
        tab_strs += [lv, inizio_strs + o_str]
        o_id += lk + 1
        o_str += lv + 1
    testata = struct.pack("Iiiiiii", 0x950412DE, 0, n, 7 * 4, 7 * 4 + 8 * n, 0, 0)
    percorso.write_bytes(testata + struct.pack(f"{2 * n}i", *tab_ids) + struct.pack(f"{2 * n}i", *tab_strs) + ids + strs)


if __name__ == "__main__":
    for po in Path(__file__).parent.rglob("*.po"):
        scrivi_mo(leggi_po(po), po.with_suffix(".mo"))
        print("compilato", po.with_suffix(".mo"))
