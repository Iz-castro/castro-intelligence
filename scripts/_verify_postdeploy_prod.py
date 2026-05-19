# -*- coding: utf-8 -*-
"""Verificacao pos-deploy EM PROD do get-or-create atomico.

Escrita minima e reversivel: 1 wa_id fake com DDD '00' (impossivel ser
numero real), contato so de agenda (from_message_event=False -> sem
conversa/thread), rajada SEQUENCIAL (padrao real do state_sync, sem
concorrencia). Limpeza imediata + verificacao; se sobrar algo, grita o
id pra remocao manual. try/finally garante cleanup ate em falha.

Uso (de dentro de castro-intelligence/):
  $env:FIRESTORE_PROJECT_ID = "project-26fb9c99-8ee9-4179-aef"
  $env:FIRESTORE_COLLECTION_PREFIX = "castro_crm"
  ./.venv/Scripts/python.exe -m scripts._verify_postdeploy_prod
"""
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from firestore_common import get_firestore_client, set_tenant_context  # noqa: E402
from database_firestore import upsert_wa_contact  # noqa: E402

PREFIX = os.environ.get("FIRESTORE_COLLECTION_PREFIX", "")
TENANT = "hubloc"
# DDD "00" nao existe no Brasil -> jamais colide com contato real.
FAKE_WA = "5500" + time.strftime("%H%M%S") + "000"  # 13 digitos, DDD 00
N = 20

c = get_firestore_client()


def tcol(name):
    return c.collection(f"{PREFIX}_tenants").document(TENANT).collection(name)


print(f"=== Verificacao pos-deploy PROD | prefix={PREFIX} wa={FAKE_WA} seq={N} ===")
if "staging" in PREFIX:
    print("  (prefixo staging — ok tambem, mas este script e p/ validar prod)")

results = []
errors = []
try:
    set_tenant_context(TENANT)
    for i in range(N):
        try:
            results.append(upsert_wa_contact(
                FAKE_WA, f"VERIFY POSDEPLOY {i}",
                channel_id=None, phone_number_id="", source_channel_type="",
                auto_assign_user_id=None, from_message_event=False,
            ))
        except Exception as e:  # noqa: BLE001
            errors.append(repr(e))

    set_tenant_context(TENANT)
    docs = list(tcol("wa_contacts").where("wa_id", "==", FAKE_WA).stream())
    idx = tcol("wa_contact_index").document(FAKE_WA).get()
    distinct = sorted(set(results))
    print(f"  chamadas ok={len(results)} ids_distintos={distinct} erros={len(errors)}")
    print(f"  contatos criados c/ esse wa_id: {len(docs)} (esperado 1)")
    print(f"  wa_contact_index existe: {idx.exists} "
          f"contact_id={idx.to_dict().get('contact_id') if idx.exists else None}")
    ok = (len(docs) == 1 and len(distinct) == 1 and not errors
          and idx.exists and idx.to_dict().get("contact_id") == distinct[0])
    print(f"  >>> CAMINHO CREATE+CLAIM EM PROD: {'PASS ✅' if ok else 'FAIL ❌'}")
finally:
    # Cleanup SEMPRE.
    set_tenant_context(TENANT)
    rm = 0
    for d in tcol("wa_contacts").where("wa_id", "==", FAKE_WA).stream():
        d.reference.delete()
        rm += 1
    idx_ref = tcol("wa_contact_index").document(FAKE_WA)
    had_idx = idx_ref.get().exists
    if had_idx:
        idx_ref.delete()
    # Verifica limpeza
    left = list(tcol("wa_contacts").where("wa_id", "==", FAKE_WA).stream())
    left_idx = tcol("wa_contact_index").document(FAKE_WA).get().exists
    print(f"  limpeza: removidos {rm} contato(s) + {'1' if had_idx else '0'} indice")
    if left or left_idx:
        print(f"  ⚠️ SOBROU em prod! wa_id={FAKE_WA} "
              f"contatos={[s.id for s in left]} indice={left_idx} — REMOVER MANUAL")
    else:
        print(f"  ✅ prod limpo (0 contatos / 0 indice com wa_id={FAKE_WA})")
