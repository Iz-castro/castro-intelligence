# -*- coding: utf-8 -*-
"""Bootstrap / grant de super-admin (Sprint 0 — PLANO_RBAC §6, entregavel 2).

Uso (rodar da raiz do repo, com ADC + FIRESTORE_PROJECT_ID apontando pra prod):

  # 1) semear os docs super_admins/{uid} dos founders (idempotente)
  FIRESTORE_PROJECT_ID=project-4a851bf9-f475-418c-800 \
    python scripts/grant_super_admin.py --seed

  # 2) listar
  python scripts/grant_super_admin.py --list

  # 3) conceder o claim super_admin (APOS o MFA estar enrolled — ver runbook)
  python scripts/grant_super_admin.py --grant <uid>

  # kill switch (parte): revoga claim + desativa doc + revoga refresh tokens
  python scripts/grant_super_admin.py --revoke <uid>

O --grant valida que o doc existe e esta is_active. Por padrao EXIGE
mfa_enrolled=true (o painel B seta isso no enrollment); use --allow-no-mfa
so em bootstrap controlado. Setar o claim NAO autoriza sozinho operacao
nuclear — o Cloud Run B revalida doc + MFA-na-sessao a cada request.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Founders (§4.4). UIDs Firebase — nao sao segredo. Seed idempotente.
FOUNDERS = [
    {"uid": "mbg9JRY86MUADtfja6pi3zxs7Az2", "email": "rafaluisc@outlook.com",
     "display_name": "Rafael Castro", "reason": "founder-primary"},
    {"uid": "dFn2kayBsEOnS7A9BFmbBivNUGt1", "email": "izaeldecastro@gmail.com",
     "display_name": "Izael Castro", "reason": "founder-secondary"},
]


def cmd_seed():
    from super_admin import seed_super_admin
    for f in FOUNDERS:
        doc = seed_super_admin(
            f["uid"], f["email"], display_name=f["display_name"], reason=f["reason"],
        )
        print(f"  seed ok | {f['email']} | uid={f['uid']} | is_active={doc.get('is_active')} "
              f"mfa_enrolled={doc.get('mfa_enrolled')}")


def cmd_list():
    from super_admin import list_super_admins
    rows = list_super_admins()
    if not rows:
        print("  (nenhum super_admin)")
        return
    for d in rows:
        print(f"  {d.get('email'):32} | uid={d.get('uid')} | is_active={d.get('is_active')} "
              f"| mfa_enrolled={d.get('mfa_enrolled')} | scopes={d.get('scopes')}")


def cmd_grant(uid, allow_no_mfa):
    from super_admin import get_super_admin, log_system_audit
    from firebase_admin_client import set_super_admin_claim, revoke_refresh_tokens
    doc = get_super_admin(uid)
    if not doc:
        print(f"  ERRO: super_admins/{uid} nao existe. Rode --seed antes.")
        sys.exit(1)
    if not doc.get("is_active"):
        print(f"  ERRO: super_admin {uid} nao esta is_active.")
        sys.exit(1)
    if not doc.get("mfa_enrolled") and not allow_no_mfa:
        print(f"  ERRO: super_admin {uid} sem mfa_enrolled. Enrole o TOTP (painel B) "
              f"ou use --allow-no-mfa para bootstrap controlado.")
        sys.exit(1)
    if not set_super_admin_claim(uid, True):
        print("  ERRO: falha ao setar o claim (get_user/Auth). Tente de novo.")
        sys.exit(1)
    revoke_refresh_tokens(uid)  # forca reissue do ID token com o claim novo
    log_system_audit("bootstrap", "grant_super_admin", detail=f"uid={uid} allow_no_mfa={allow_no_mfa}", target=uid)
    print(f"  OK: claim super_admin=true concedido a {uid} (+ refresh revogado). "
          f"O usuario precisa relogar para o ID token carregar o claim.")


def cmd_revoke(uid):
    from super_admin import deactivate_super_admin, log_system_audit
    from firebase_admin_client import set_super_admin_claim, revoke_refresh_tokens
    log_system_audit("bootstrap", "kill_super_admin", detail=f"uid={uid}", target=uid)
    deactivate_super_admin(uid)
    set_super_admin_claim(uid, False)
    revoke_refresh_tokens(uid)
    print(f"  OK: super_admin {uid} DESATIVADO (doc is_active=false + claim removido + tokens revogados).")


def main():
    ap = argparse.ArgumentParser(description="Bootstrap/grant de super-admin (Sprint 0)")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--seed", action="store_true", help="cria os docs dos founders (idempotente)")
    g.add_argument("--list", action="store_true", help="lista os super_admins")
    g.add_argument("--grant", metavar="UID", help="concede o claim super_admin ao uid")
    g.add_argument("--revoke", metavar="UID", help="kill switch: desativa doc + remove claim + revoga tokens")
    ap.add_argument("--allow-no-mfa", action="store_true", help="permite --grant sem mfa_enrolled (bootstrap)")
    args = ap.parse_args()

    if args.seed:
        cmd_seed()
    elif args.list:
        cmd_list()
    elif args.grant:
        cmd_grant(args.grant, args.allow_no_mfa)
    elif args.revoke:
        cmd_revoke(args.revoke)


if __name__ == "__main__":
    main()
