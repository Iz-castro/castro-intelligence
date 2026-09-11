# -*- coding: utf-8 -*-
"""Simulador do picker v2.1 — helpers puros de busca (FASE F2a).

Exercita build_contact_search_fields / normalize_search_text do codigo REAL
(database_firestore), sem Firestore (funcoes puras). Matriz da secao 15.1/15.2
do docs/PICKER_V2_1_AGENDA_PAGINADA.md. Exit 0/1.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database_firestore import (  # noqa: E402
    SEARCH_SCHEMA_VERSION,
    _search_fields_for_update,
    build_contact_search_fields,
    normalize_search_text,
)

CHECKS = 0
FAILS = []


def check(cond, label):
    global CHECKS
    CHECKS += 1
    print(("      ✓ " if cond else "      X ") + label)
    if not cond:
        FAILS.append(label)


def run():
    print("Simulador picker v2.1 — helpers puros (codigo real)")

    print("\n== normalize_search_text ==")
    check(normalize_search_text("João da Silva") == "joao da silva", "acento + caixa")
    check(normalize_search_text("JOAO") == normalize_search_text("joao") == "joao", "casefold estavel")
    check(normalize_search_text("D'Ávila") == "d avila", "apostrofo vira espaco")
    check(normalize_search_text("Ana-Maria") == "ana maria", "hifen vira espaco")
    check(normalize_search_text("  CLÍNICA   SÃO JOSÉ  ") == "clinica sao jose", "espacos colapsados")
    check(normalize_search_text("") == "" and normalize_search_text(None) == "", "vazio/None")
    check(normalize_search_text("Jo​ao") == "joao", "ZWSP e DELETADO (nao parte a palavra)")
    check(normalize_search_text("Jo­ao") == "joao", "soft-hyphen deletado")
    check(normalize_search_text("Jo‍ao Silva") == "joao silva", "ZWJ deletado, espaco real preservado")

    print("\n== build_contact_search_fields: Joao Silva celular BR ==")
    f = build_contact_search_fields({
        "declared_name": "João Silva", "whatsapp_profile_name": "",
        "display_name": "João Silva", "wa_id": "5531983440484",
    })
    check(f["sort_key"] == "0_joao silva", f"sort_key 0_ ({f['sort_key']})")
    check(f["name_normalized"] == "joao silva", "name_normalized")
    for p in ("jo", "joa", "joao", "si", "sil", "silv", "silva"):
        check(p in f["name_prefixes"], f"prefixo '{p}' presente")
    check(all(len(p) >= 2 for p in f["name_prefixes"]), "nenhum prefixo de 1 char")
    check(f["name_prefixes"] == sorted(set(f["name_prefixes"])), "prefixos ordenados/dedupados")
    check(f["phone_e164_digits"] == "5531983440484", "e164 digits")
    check(f["phone_national"] == "31983440484", "national (sem 55)")
    check(f["phone_local"] == "983440484", "local 9 digitos (sem DDD)")
    check(f["wa_id_reversed"] == "4840443891355", "reversed (sufixo vira prefixo)")
    check(f["search_schema_version"] == SEARCH_SCHEMA_VERSION == 1, "schema v1")

    print("\n== aliases: declarado + perfil WhatsApp ==")
    f = build_contact_search_fields({
        "declared_name": "Maria Souza", "whatsapp_profile_name": "Mari Cliente",
        "display_name": "Maria Souza", "wa_id": "5531988887777",
    })
    check(f["sort_key"] == "0_maria souza", "sort_key usa precedencia declared")
    check("mari" in f["name_prefixes"], "alias do WhatsApp entra nos prefixos (mari)")
    check("cl" in f["name_prefixes"] and "cliente" in f["name_prefixes"],
          "palavra do alias indexada inteira (cl..cliente)")
    check("so" in f["name_prefixes"] and "souza" in f["name_prefixes"], "palavra do declarado presente")

    print("\n== sem nome util + canonizacao do nono digito ==")
    f = build_contact_search_fields({
        "declared_name": "", "whatsapp_profile_name": "",
        "display_name": "+55 31 8344-0484", "wa_id": "553183440484",
    })
    # wa_id legado de 12 digitos (celular sem o 9): os campos derivados usam a
    # forma CANONICA (revisao F2a) — buscar o numero REAL acha o lead.
    check(f["sort_key"] == "1_5531983440484", f"sort_key usa digits canonicos ({f['sort_key']})")
    check(f["name_normalized"] == "" and f["name_prefixes"] == [], "sem name_normalized/prefixos")
    check(f["phone_national"] == "31983440484" and f["phone_local"] == "983440484",
          "celular sem 9 armazenado: national/local na forma COM 9")
    f13 = build_contact_search_fields({"declared_name": "", "whatsapp_profile_name": "",
                                       "display_name": "", "wa_id": "5531983440484"})
    check(f13["phone_national"] == f["phone_national"] and f13["phone_local"] == f["phone_local"]
          and f13["wa_id_reversed"] == f["wa_id_reversed"],
          "12-dig e 13-dig do MESMO numero produzem os MESMOS campos")
    f_fixo = build_contact_search_fields({"declared_name": "", "whatsapp_profile_name": "",
                                          "display_name": "", "wa_id": "553133334444"})
    check(f_fixo["phone_national"] == "3133334444" and f_fixo["phone_local"] == "33334444",
          "fixo de verdade (local comeca 2-5): 12 digitos preservados, local de 8")

    print("\n== nome que comeca com numero/emoji ==")
    f = build_contact_search_fields({"declared_name": "3M Equipamentos",
                                     "whatsapp_profile_name": "", "display_name": "3M Equipamentos",
                                     "wa_id": "5531977776666"})
    check(f["sort_key"] == "0_3m equipamentos", "3M = nome util (tem letra)")
    f = build_contact_search_fields({"declared_name": "\U0001f525Joao",
                                     "whatsapp_profile_name": "", "display_name": "\U0001f525Joao",
                                     "wa_id": "5531977776666"})
    check(f["sort_key"] == "0_joao", "emoji na frente nao derruba o nome")

    print("\n== limites anti-fan-out ==")
    f = build_contact_search_fields({"declared_name": "a" * 30, "whatsapp_profile_name": "",
                                     "display_name": "", "wa_id": "5531966665555"})
    check(max(len(p) for p in f["name_prefixes"]) == 15, "prefixo max 15 chars")
    # 8 palavras de 14 chars (119 chars com espacos — cabe no teto de 120 do
    # alias) geram 8x13=104 candidatos > 100: estoura o teto DE VERDADE.
    longas = " ".join(ch * 14 for ch in "abcdefgh")
    f = build_contact_search_fields({"declared_name": longas, "whatsapp_profile_name": "",
                                     "display_name": "", "wa_id": "5531966665555"})
    check(len(f["name_prefixes"]) == 100, f"teto de 100 prefixos atingido ({len(f['name_prefixes'])})")
    check(all((ch * 2) in f["name_prefixes"] for ch in "abcdefgh"),
          "round-robin: TODA palavra mantem o prefixo curto mesmo no teto")
    # Alias acima de 120 chars e truncado ANTES da tokenizacao: palavra que
    # cai fora do corte nao indexa (limite documentado, nao surpresa).
    f = build_contact_search_fields({"declared_name": " ".join(ch * 15 for ch in "abcdefghijkl"),
                                     "whatsapp_profile_name": "", "display_name": "",
                                     "wa_id": "5531966665555"})
    check("ll" not in f["name_prefixes"] and "aa" in f["name_prefixes"],
          "teto de 120 chars por alias corta palavras excedentes (documentado)")
    f = build_contact_search_fields({"declared_name": "e", "whatsapp_profile_name": "",
                                     "display_name": "", "wa_id": "5531966665555"})
    check(f["name_prefixes"] == [], "palavra de 1 char nao gera prefixo")

    print("\n== numero nao-BR ==")
    f = build_contact_search_fields({"declared_name": "John", "whatsapp_profile_name": "",
                                     "display_name": "John", "wa_id": "14155552671"})
    check(f["phone_e164_digits"] == "14155552671" and f["phone_national"] == ""
          and f["phone_local"] == "", "nao-BR: e164/reversed ok, national/local vazios")
    check(f["wa_id_reversed"] == "14155552671"[::-1], "reversed nao-BR")

    print("\n== idempotencia e update parcial ==")
    base = {"declared_name": "Ana Clara", "whatsapp_profile_name": "Aninha",
            "display_name": "Ana Clara", "wa_id": "5531955554444"}
    f1 = build_contact_search_fields(base)
    f2 = build_contact_search_fields({**base, **f1})
    check(f1 == f2, "reaplicar sobre o proprio output = identico (backfill idempotente)")
    merged = _search_fields_for_update(
        {**base, **f1}, {"declared_name": "Ana Beatriz", "display_name": "Ana Beatriz"})
    check(merged["sort_key"] == "0_ana beatriz" and "be" in merged["name_prefixes"],
          "update parcial recalcula do doc inteiro")
    check("aninha"[:2] in merged["name_prefixes"], "alias antigo preservado no recalculo")

    print("\n" + "=" * 60)
    if FAILS:
        print(f"RESULTADO: {len(FAILS)} de {CHECKS} asserts FALHARAM:")
        for x in FAILS:
            print(f"  - {x}")
        return 1
    print(f"RESULTADO: todos os {CHECKS} asserts passaram.")
    return 0


if __name__ == "__main__":
    sys.exit(run())
