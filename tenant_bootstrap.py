# -*- coding: utf-8 -*-
"""Provisionamento de tenant (M-A2 do roadmap multi-tenant).

`bootstrap_tenant(tid, ...)` e a porta unica de criacao/seed de tenant:

- O startup usa pra garantir o `hubloc` (idempotente — em boot repetido e
  no-op: tenant existe, setores existem, admin ja tem claim correto).
- O painel super-admin (Cloud Run B, milestone D3) vai chama-la no
  onboarding de cada cliente novo.

Politica D6 (claim atomico): o admin do tenant e provisionado com a conta
Firebase resolvida ANTES do upsert local — users doc + operator_profile +
custom claims (tenant_id/role) nascem linkados, e os refresh tokens sao
revogados quando o claim muda. Resultado: a primeira sessao do admin ja
enxerga o proprio tenant, sem depender do sync assincrono do login.

Ver docs/ROADMAP_MULTITENANT_FASE2.md e docs/decisions/0007.
"""

import logging

from bootstrap_data import ensure_default_departments
from database_firestore import (
    create_department,
    get_all_departments,
    upsert_firebase_user,
)
from firestore_common import get_tenant_context, tenant_context
from pii_redaction import redact_name
from tenant_service import create_tenant, tenant_exists

logger = logging.getLogger("castro_crm.tenant_bootstrap")


def bootstrap_departments():
    # So semeia os defaults se o tenant ainda nao tem NENHUM setor (inclusive
    # inativos). Sem esse gate, ensure_default_departments rodava a CADA startup
    # e recriava setores default cujo nome foi renomeado (o nome default ficava
    # orfao) — causa-raiz das duplicatas 'Geral'(6) e 'Vendas'(7,8). Apos o seed
    # inicial, qualquer ajuste de setor e feito pela UI (admin), nao pelo boot.
    existing = get_all_departments(include_inactive=True)
    if existing:
        logger.info("Setores ja existentes (%d) — seed de defaults pulado", len(existing))
        return
    dept_map = ensure_default_departments(create_department)
    logger.info("Setores padrao semeados | total=%d", len(dept_map))


def _resolve_admin_department(department_name):
    # Resolve o setor do admin SEM recriar default: usa o setor existente por
    # nome (ativo ou nao); so cria se o tenant ainda estiver vazio. Sem este
    # gate, rodar a cada boot recriaria um 'Geral' fantasma num tenant cujo
    # 'Geral' foi renomeado — mesma causa-raiz do gate em bootstrap_departments.
    existing_depts = get_all_departments(include_inactive=True)
    dept_norm = (department_name or "").strip().lower()
    match = next(
        (d for d in existing_depts if (d.get("name") or "").strip().lower() == dept_norm),
        None,
    )
    if match:
        return match["id"]
    if not existing_depts and department_name:
        return create_department(
            department_name,
            "Setor criado automaticamente no primeiro deploy",
        )
    return None


def ensure_tenant_admin(admin_email, admin_display_name="", department_name=None, role="admin"):
    """Garante o usuario admin do tenant ATUAL (rodar dentro de tenant_context).

    Idempotente: em re-run com admin ja provisionado e claim correto, nao
    escreve claim nem revoga token (admin NAO e deslogado em deploy).
    """
    if not admin_email:
        logger.info("Bootstrap admin Firebase nao configurado")
        return None

    tenant_id = get_tenant_context() or "hubloc"
    department_id = _resolve_admin_department(department_name)

    # Resolve a conta Firebase ANTES do upsert local (D6). Falha aqui nao e
    # fatal: degrada pro comportamento antigo (doc local sem uid; claim
    # sincroniza no primeiro login via auth.py).
    firebase_uid = ""
    uid_created = False
    try:
        from firebase_admin_client import get_or_create_firebase_user
        firebase_uid, uid_created = get_or_create_firebase_user(admin_email, admin_display_name)
    except Exception as exc:
        logger.warning(
            "ensure_tenant_admin: sem conta Firebase (%s) — segue so com doc local",
            exc,
        )

    # Le os claims ANTES do upsert, com leitura ESTRITA (erro != vazio):
    # - claims=None  -> leitura falhou; nao decidir nada com base nisso
    #   (pular set+revoke; proximo boot/login corrige). Sem esse guard, um
    #   blip no Auth num cold start pareceria "claim errado" e deslogaria
    #   o admin em prod.
    # - conta ja pertencente a OUTRO tenant -> ABORTA antes de criar
    #   qualquer doc no tenant novo (um email = um tenant; re-apontar claim
    #   silenciosamente moveria um admin entre clientes — risco LGPD).
    claims = None
    if firebase_uid:
        try:
            from firebase_admin_client import get_user_claims_strict
            claims = get_user_claims_strict(firebase_uid)
        except Exception as exc:
            logger.warning(
                "ensure_tenant_admin: leitura de claims falhou (%s) — claims nao serao alterados neste boot",
                exc,
            )
        if claims is not None:
            claimed_tid = str(claims.get("tenant_id") or "")
            if claimed_tid and claimed_tid != str(tenant_id):
                logger.error(
                    "ensure_tenant_admin: conta %s ja pertence ao tenant '%s' — "
                    "provisionamento em '%s' ABORTADO (um email = um tenant; "
                    "transferencia exige acao explicita do super-admin)",
                    redact_name(admin_email), claimed_tid, tenant_id,
                )
                return None

    user = upsert_firebase_user(
        firebase_uid=firebase_uid,
        email=admin_email,
        display_name=admin_display_name,
        role=role,
        department_id=department_id,
    )
    if not user:
        logger.warning(
            "Falha ao sincronizar bootstrap admin Firebase | email=%s",
            redact_name(admin_email),
        )
        return None

    uid = user.get("firebase_uid", "") or firebase_uid
    if uid and claims is not None and (
        str(claims.get("tenant_id") or "") != str(tenant_id)
        or str(claims.get("role") or "") != str(role)
    ):
        try:
            from firebase_admin_client import revoke_refresh_tokens, set_tenant_claims
            # D6: revoga refresh tokens SO se o claim foi de fato gravado —
            # revoke com set falho seria logout sem beneficio. Conta recem-
            # criada nao tem sessao (revoke inocuo); conta existente com
            # claim errado precisa re-logar mesmo.
            if set_tenant_claims(uid, tenant_id, role=role, base_claims=claims):
                revoke_refresh_tokens(uid)
                logger.info(
                    "Claims do admin provisionados | tenant=%s uid_created=%s",
                    tenant_id, uid_created,
                )
            else:
                logger.warning(
                    "set_tenant_claims falhou — revoke pulado (retry no proximo boot/login)"
                )
        except Exception as exc:
            logger.warning("Falha ao setar custom_claim tenant_id no admin: %s", exc)

    logger.info(
        "Bootstrap admin Firebase sincronizado | email=%s tenant_id=%s",
        redact_name(admin_email), tenant_id,
    )
    return user


def bootstrap_tenant(
    tenant_id,
    name,
    plan="professional",
    cnpj="",
    admin_email="",
    admin_display_name="",
    admin_department_name=None,
):
    """Garante tenant + setores default + admin com claim atomico.

    Idempotente (roda em todo boot pro hubloc; o Cloud Run B chama pra
    tenants novos). Nao atualiza name/plan de tenant que ja existe — ajuste
    de metadata e via update_tenant (super-admin), nao pelo boot.

    Restricao: UM EMAIL = UM TENANT. Se a conta do admin_email ja pertence
    a outro tenant (claim tenant_id divergente), o provisionamento do admin
    e ABORTADO (log de erro) — transferir um usuario entre tenants exige
    acao explicita do super-admin, nunca efeito colateral de onboarding.

    Limitacoes conhecidas (relevantes so pro caller one-shot tipo Cloud Run B;
    inertes no boot idempotente do hubloc):
    - O guard "um email = um tenant" so barra conta com claim tenant_id de
      OUTRO tenant. Conta SEM claim (ex: operador convidado que nunca logou)
      nao e barrada — o painel super-admin deve PRE-CHECAR o email por tenant
      (lookup) antes de onboardar.
    - Se a leitura estrita de claims falhar, o admin e provisionado (docs) mas
      o claim NAO e setado; num caller one-shot o estado nao converge sozinho
      (no hubloc o proximo boot corrige). O painel deve verificar/re-tentar.
    """
    created = False
    if tenant_exists(tenant_id):
        logger.info("Tenant '%s' ja existe", tenant_id)
    else:
        create_tenant(tenant_id=tenant_id, name=name, plan=plan, cnpj=cnpj)
        created = True
        logger.info("Tenant '%s' criado", tenant_id)

    with tenant_context(tenant_id):
        bootstrap_departments()
        admin = ensure_tenant_admin(
            admin_email,
            admin_display_name=admin_display_name,
            department_name=admin_department_name,
        )

    return {
        "tenant_id": tenant_id,
        "created": created,
        "admin_user_id": (admin or {}).get("id"),
        "admin_firebase_uid": (admin or {}).get("firebase_uid", ""),
    }
