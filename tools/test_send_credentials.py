# -*- coding: utf-8 -*-

"""
Teste LOCAL de get_send_credentials (channel_service.py).

NAO toca em producao: o cache de canais e semeado em memoria e o config
e patchado no modulo. Cobre a regra do override por env:

  1. Canal standard com phone_number_id IGUAL ao env -> creds do ENV
     (rotacao de secret continua funcionando).
  2. Canal standard de OUTRO numero -> creds do PROPRIO canal
     (nunca vaza pelo numero de outro tenant).
  3. Canal coexistence -> creds do proprio canal (regressao).
  4. Canal standard de outro numero SEM access_token -> ValueError
     (fail-closed; nao cai no env).

Rodar (Windows):
    .venv\\Scripts\\python.exe tools\\test_send_credentials.py

Sai com codigo 0 se todos os asserts passarem, 1 caso contrario.
"""

import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import config
import channel_service
from channel_service import get_send_credentials

ENV_PHONE_ID = "111000111000"
ENV_TOKEN = "env-token-secreto"

CHANNELS = {
    1: {
        "id": 1,
        "channel_type": "standard",
        "tenant_id": "hubloc",
        "phone_number_id": ENV_PHONE_ID,
        "access_token": "token-firestore-hubloc",
        "is_active": True,
    },
    2: {
        "id": 2,
        "channel_type": "standard",
        "tenant_id": "varizemed-test",
        "phone_number_id": "222000222000",
        "access_token": "token-firestore-varizemed",
        "is_active": True,
    },
    3: {
        "id": 3,
        "channel_type": "coexistence",
        "tenant_id": "hubloc",
        "phone_number_id": "333000333000",
        "access_token": "token-coex",
        "is_active": True,
    },
    4: {
        "id": 4,
        "channel_type": "standard",
        "tenant_id": "varizemed-test",
        "phone_number_id": "444000444000",
        "access_token": "",
        "is_active": True,
    },
}


def _seed_cache() -> None:
    with channel_service._lock:
        channel_service._channels_by_id.clear()
        channel_service._channels_by_id.update(CHANNELS)
        channel_service._channels_by_phone_id.clear()
        for ch in CHANNELS.values():
            channel_service._channels_by_phone_id[ch["phone_number_id"]] = ch
    # Impede _ensure_cache de bater no Firestore.
    channel_service._last_refresh = time.monotonic()


def main() -> int:
    config.WHATSAPP_TOKEN = ENV_TOKEN
    config.WHATSAPP_PHONE_NUMBER_ID = ENV_PHONE_ID
    _seed_cache()

    failures = []

    def check(label, fn):
        try:
            fn()
            print(f"  OK  {label}")
        except AssertionError as exc:
            failures.append(label)
            print(f"FALHA {label}: {exc}")

    def caso_env_mesmo_numero():
        token, phone_id, _ = get_send_credentials(1)
        assert token == ENV_TOKEN, f"esperava token do env, veio {token!r}"
        assert phone_id == ENV_PHONE_ID

    def caso_standard_outro_numero():
        token, phone_id, _ = get_send_credentials(2)
        assert token == "token-firestore-varizemed", (
            f"canal standard de outro numero NAO pode cair no env; veio {token!r}"
        )
        assert phone_id == "222000222000"

    def caso_coexistence():
        token, phone_id, _ = get_send_credentials(3)
        assert token == "token-coex"
        assert phone_id == "333000333000"

    def caso_standard_sem_token_fail_closed():
        try:
            get_send_credentials(4)
        except ValueError:
            return
        raise AssertionError("canal sem token deveria dar ValueError, nao creds do env")

    check("standard mesmo numero do env -> creds do env", caso_env_mesmo_numero)
    check("standard de outro numero -> creds do canal", caso_standard_outro_numero)
    check("coexistence -> creds do canal", caso_coexistence)
    check("standard de outro numero sem token -> ValueError", caso_standard_sem_token_fail_closed)

    if failures:
        print(f"\n{len(failures)} caso(s) falharam.")
        return 1
    print("\nTodos os casos passaram.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
