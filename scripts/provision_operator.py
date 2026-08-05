# -*- coding: utf-8 -*-
"""Provisiona um operador num tenant (claim tenant_id + users doc + profile).

Supre a falta da UI de cadastro na pagina Equipe: o backend ja tem o fluxo
completo (provision_operator, mesmo usado por POST /api/admin/users), este
script so o expoe na linha de comando para o backoffice.

ORDEM IMPORTA: crie a conta no console do Firebase ANTES de rodar o script.
O provision_operator e lookup-only (nao cria conta Firebase) — com a conta
ja existente ele linka o uid e grava o claim NA HORA; sem a conta, so nasce
o doc local e o claim depende do sync no primeiro login (que exige dominio
casando allowed_email_domains do tenant).

Uso (PowerShell, da raiz do repo, com ADC apontando pra prod):

  $env:FIRESTORE_PROJECT_ID = "project-4a851bf9-f475-418c-800"
  $env:FIRESTORE_COLLECTION_PREFIX = "castro_crm"
  .\\.venv\\Scripts\\python.exe -m scripts.provision_operator `
      --tenant varizemed --email tanusa@clinicavarizemed.com.br `
      --name "Tanusa" --role operador

Apos rodar, o usuario so precisa LOGAR (ou relogar — o script revoga os
refresh tokens quando muda claim) para o JWT ja vir com o tenant.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import ROLE_OPTIONS  # noqa: E402


def main():
    ap = argparse.ArgumentParser(
        description="Provisiona operador num tenant (claim + users doc + operator_profile)"
    )
    ap.add_argument("--tenant", required=True, help="tenant_id (ex: varizemed)")
    ap.add_argument("--email", required=True, help="email do operador")
    ap.add_argument("--name", required=True, help="nome de exibicao")
    ap.add_argument("--role", default="operador", choices=ROLE_OPTIONS,
                    help="cargo (default: operador)")
    ap.add_argument("--department-id", type=int, default=None,
                    help="id numerico do setor (opcional; da pra ajustar depois na Equipe)")
    args = ap.parse_args()

    email = args.email.strip().lower()
    tenant_id = args.tenant.strip()

    from firestore_common import tenant_context
    from tenant_service import get_tenant, normalize_email_domains

    tenant = get_tenant(tenant_id)
    if not tenant:
        print(f"  ERRO: tenant '{tenant_id}' nao existe.")
        sys.exit(1)

    # Guarda-corpo SOFT (mesmo do POST /api/admin/users): email fora dos
    # dominios do tenant e permitido (o claim autoriza, nao o dominio), mas
    # avisa pra nao botar operador no tenant errado por engano.
    domains = normalize_email_domains(tenant.get("allowed_email_domains"))
    email_domain = email.split("@", 1)[1] if "@" in email else ""
    if domains and email_domain and email_domain not in domains:
        print(f"  AVISO: dominio '{email_domain}' fora dos dominios do tenant "
              f"({', '.join(domains)}). Seguindo mesmo assim.")

    from tenant_bootstrap import (
        DeactivatedUserError, TenantConflictError, provision_operator,
    )

    with tenant_context(tenant_id):
        try:
            user = provision_operator(
                email,
                display_name=args.name.strip(),
                role=args.role,
                department_id=args.department_id,
            )
        except TenantConflictError:
            print(f"  ERRO: {email} ja esta vinculado a OUTRO tenant "
                  f"(um email = um tenant). Nada foi gravado.")
            sys.exit(1)
        except DeactivatedUserError:
            print(f"  ERRO: {email} ja existe DESATIVADO no tenant '{tenant_id}'. "
                  f"Reative o doc original (nao recriar).")
            sys.exit(1)

    if not user:
        print("  ERRO: upsert do usuario falhou (ver logs).")
        sys.exit(1)

    uid = user.get("firebase_uid", "")
    print(f"  users doc ok | id={user.get('id')} tenant={tenant_id} role={args.role}")

    if uid:
        from firebase_admin_client import get_user_claims
        claims = get_user_claims(uid)
        print(f"  conta Firebase linkada | uid={uid}")
        print(f"  claims atuais: tenant_id={claims.get('tenant_id')!r} "
              f"role={claims.get('role')!r} perfil={claims.get('perfil_acesso_id')!r}")
        if str(claims.get("tenant_id") or "") == tenant_id:
            print("  OK: claim gravado. Basta o usuario logar (sessao antiga foi revogada).")
        else:
            print("  AVISO: claim ainda nao reflete o tenant (Auth indisponivel?). "
                  "Ele converge no primeiro login SE o dominio casar; ou rode de novo.")
    else:
        print(f"  AVISO: conta Firebase de {email} NAO existe ainda — so o doc local "
              f"foi criado. Crie a conta no console e rode o script de novo (ou "
              f"garanta que o dominio casa allowed_email_domains pro sync no login).")

    # Rastro no audit global (best-effort, mesmo espirito do grant_super_admin).
    try:
        from super_admin import log_system_audit
        log_system_audit(
            "bootstrap", "provision_operator",
            detail=f"tenant={tenant_id} email={email} role={args.role}",
            target=uid or email,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"  (audit nao gravado: {exc})")


if __name__ == "__main__":
    main()
