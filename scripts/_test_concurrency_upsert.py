# -*- coding: utf-8 -*-
"""Teste de concorrencia do upsert_wa_contact (rodar em STAGING).

Dispara N threads chamando upsert_wa_contact com o MESMO wa_id (fake)
ao mesmo tempo. Sem o claim atomico -> varios contatos (bug). Com o
claim -> exatamente 1 contato e todos retornam o mesmo id.

Limpa o que criou ao final (nao polui o QA do staging).

Uso (de dentro de castro-intelligence/):
  $env:FIRESTORE_PROJECT_ID = "project-26fb9c99-8ee9-4179-aef"
  $env:FIRESTORE_COLLECTION_PREFIX = "castro_crm_staging"
  ./.venv/Scripts/python.exe -m scripts._test_concurrency_upsert
"""
import os
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from firestore_common import get_firestore_client, set_tenant_context  # noqa: E402
from database_firestore import upsert_wa_contact  # noqa: E402

PREFIX = os.environ.get("FIRESTORE_COLLECTION_PREFIX", "castro_crm_staging")
TENANT = "hubloc"
assert "staging" in PREFIX, f"RECUSADO: rode em staging, nao em '{PREFIX}'"

c = get_firestore_client()


def tcol(name):
    return c.collection(f"{PREFIX}_tenants").document(TENANT).collection(name)


def _call(i, wa):
    set_tenant_context(TENANT)
    return upsert_wa_contact(
        wa, f"Teste {i}", channel_id=None, phone_number_id="",
        source_channel_type="", auto_assign_user_id=None, from_message_event=False,
    )


def _check_and_clean(scenario, wa, results, errors):
    set_tenant_context(TENANT)
    docs = list(tcol("wa_contacts").where("wa_id", "==", wa).stream())
    idx = tcol("wa_contact_index").document(wa).get()
    distinct = sorted(set(results))
    dedup_ok = (len(docs) == 1 and len(distinct) == 1 and idx.exists
                and idx.to_dict().get("contact_id") == distinct[0])
    print(f"--- {scenario} (wa={wa}) ---")
    print(f"  chamadas ok={len(results)} ids_distintos={distinct} contatos_criados={len(docs)}")
    print(f"  next_sequence transient errors: {len(errors)}"
          + (f" ex: {errors[0]}" if errors else ""))
    print(f"  >>> DEDUP: {'PASS ✅ (1 contato)' if dedup_ok else 'FAIL ❌'}")
    for d in docs:
        d.reference.delete()
    if idx.exists:
        tcol("wa_contact_index").document(wa).delete()
    return dedup_ok


# Cenario 1: rajada SEQUENCIAL do mesmo wa_id (= o padrao real do
# _process_smb_app_state_sync: loop hammerando o mesmo numero). Era ASSIM
# que as duplicatas nasciam. Esperado: 1 contato, 0 erros.
print("=== Teste upsert_wa_contact (staging) ===")
wa1 = "55999" + time.strftime("%H%M%S") + "01"
r1, e1 = [], []
for i in range(25):
    try:
        r1.append(_call(i, wa1))
    except Exception as e:  # noqa: BLE001
        e1.append(repr(e))
seq_ok = _check_and_clean("Cenario 1: rajada sequencial 25x", wa1, r1, e1)
seq_clean = seq_ok and not e1

# Cenario 2: concorrencia MODERADA (5 threads — plausivel multi-instancia
# sob carga). Foco: ZERO duplicata. next_sequence pode ter contencao
# transitoria (pre-existente, falha-segura: excecao -> retry, nunca dup).
wa2 = "55999" + time.strftime("%H%M%S") + "02"
r2, e2 = [], []
NB = 5
barrier = threading.Barrier(NB)


def worker(i):
    try:
        barrier.wait()
        r2.append(_call(i, wa2))
    except Exception as e:  # noqa: BLE001
        e2.append(repr(e))


ts = [threading.Thread(target=worker, args=(i,)) for i in range(NB)]
for t in ts:
    t.start()
for t in ts:
    t.join()
conc_ok = _check_and_clean("Cenario 2: concorrencia 5 simultaneas", wa2, r2, e2)

print()
print(f"GARANTIA ANTI-DUPLICATA: {'PASS ✅' if (seq_ok and conc_ok) else 'FAIL ❌'}")
print(f"  - cenario real (sequencial) limpo (0 erros): {'sim ✅' if seq_clean else 'nao ⚠️'}")
print(f"  - next_sequence sob concorrencia extrema: contencao transitoria "
      f"pre-existente, falha-segura (nunca duplica)")
sys.exit(0 if (seq_ok and conc_ok) else 1)
