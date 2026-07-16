# -*- coding: utf-8 -*-

import logging
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import date, datetime, timezone
from functools import lru_cache

from google.cloud import firestore

from config import FIRESTORE_COLLECTION_PREFIX, FIRESTORE_PROJECT_ID

logger = logging.getLogger("castro_crm.firestore")

# ---------------------------------------------------------------------------
# Tenant context (Fase 2 multi-tenant)
# ---------------------------------------------------------------------------
#
# Estrategia de implementacao:
#
#   ContextVar `_current_tenant_id` carrega o tenant ativo para a request
#   ou tarefa atual. Toda funcao que usa `collection(name)` / `document(name)`
#   automaticamente roteia para `tenants/{tenant_id}/<name>` quando o
#   contextvar esta setado, ou cai em coletas flat quando ausente
#   (compatibilidade pre-migration).
#
#   Coletas listadas em _GLOBAL_COLLECTIONS NUNCA sao roteadas para
#   subcolecao do tenant — sao genuinamente globais (counters, indice
#   phone_routing, e a propria root tenants/).
#
#   Uso:
#     - FastAPI middleware ou get_current_user seta o contextvar via
#       set_tenant_context(tid) por request.
#     - Webhook seta antes de processar payload da Meta.
#     - Operacoes super-admin cross-tenant podem usar
#       `with tenant_context(None): ...` para ler/escrever no flat global.

_current_tenant_id: ContextVar[str | None] = ContextVar("castro_crm_tenant", default=None)

# Colecoes que permanecem globais mesmo com tenant context ativo.
# "channels" e FLAT/global (castro_crm_channels/{id}, com campo tenant_id pra
# isolamento) — o webhook precisa resolver o canal ANTES de saber o tenant, e o
# indice phone_routing aponta pra id global. Sem "channels" aqui, um
# collection("channels")/document("channels") rodando sob contexto de tenant
# (ex.: refresh_channels disparado numa chamada autenticada de admin) lia/escrevia
# tenants/{tid}/channels (VAZIO) -> refresh montava cache vazio -> todos os
# phone_id davam no_channel_for_phone por 60s -> mensagens caiam em pending
# (causa raiz da perda cronica; pioraria com multi-tenant). main.py ja usava
# global_document("channels") num call site — aqui unifica todos.
#
# super_admins/audit_logs_system/pending_webhook_events sao FLAT e hoje so
# acessadas via global_collection/global_document (super_admin.py, pending_events.py)
# — ja seguras. Ficam aqui como blindagem defensiva (zero mudanca de comportamento
# hoje): se algum codigo futuro acessar via collection()/document() puro, elas
# continuam globais em vez de repetir o bug do channels (auditoria 2026-07-16).
_GLOBAL_COLLECTIONS = frozenset({
    "_meta", "tenants", "phone_routing", "channels",
    "super_admins", "audit_logs_system", "pending_webhook_events",
})


def set_tenant_context(tenant_id):
    """Seta o tenant ativo para o contexto atual. Retorna token p/ reset."""
    return _current_tenant_id.set(tenant_id if tenant_id else None)


def reset_tenant_context(token):
    _current_tenant_id.reset(token)


def get_tenant_context():
    """Retorna o tenant_id ativo no contexto atual, ou None se nao setado."""
    return _current_tenant_id.get()


@contextmanager
def tenant_context(tenant_id):
    """Context manager para escopo limitado de tenant.

    Exemplo (super-admin pulando para outro tenant):
        with tenant_context("clinica-vida"):
            data = get_all_wa_contacts()
    """
    token = set_tenant_context(tenant_id)
    try:
        yield
    finally:
        reset_tenant_context(token)


@lru_cache(maxsize=1)
def get_firestore_client():
    if FIRESTORE_PROJECT_ID:
        return firestore.Client(project=FIRESTORE_PROJECT_ID)
    return firestore.Client()


def collection_name(name):
    prefix = FIRESTORE_COLLECTION_PREFIX.strip("_")
    return f"{prefix}_{name}" if prefix else name


def _flat_collection(name):
    """Coleção flat sem aplicar tenant context. Uso interno e GLOBAL_COLLECTIONS."""
    return get_firestore_client().collection(collection_name(name))


def _flat_document(name, doc_id):
    return _flat_collection(name).document(str(doc_id))


def collection(name):
    """Retorna referencia a colecao, aplicando tenant context se ativo.

    - Se name esta em _GLOBAL_COLLECTIONS: sempre flat (counters,
      phone_routing, tenants root).
    - Se tenant context setado: roteia para tenants/{tid}/<name>.
    - Se tenant context vazio: flat (compatibilidade pre-migration).
    """
    if name in _GLOBAL_COLLECTIONS:
        return _flat_collection(name)
    tid = _current_tenant_id.get()
    if tid:
        return _tenant_subcollection_raw(tid, name)
    return _flat_collection(name)


def document(name, doc_id):
    """Retorna referencia a documento. Mesma logica de collection()."""
    if name in _GLOBAL_COLLECTIONS:
        return _flat_document(name, doc_id)
    tid = _current_tenant_id.get()
    if tid:
        return _tenant_subcollection_raw(tid, name).document(str(doc_id))
    return _flat_document(name, doc_id)


def _tenant_subcollection_raw(tenant_id, name):
    """Helper interno: subcolecao do tenant sem checar contextvar (evita recursao)."""
    return (
        get_firestore_client()
        .collection(collection_name("tenants"))
        .document(str(tenant_id))
        .collection(name)
    )


# ---------------------------------------------------------------------------
# Multi-tenant helpers (Fase 2)
# ---------------------------------------------------------------------------
#
# Estrutura:
#   <prefix>_tenants/{tenant_id}                       <- doc do tenant
#   <prefix>_tenants/{tenant_id}/<sub_name>/{doc_id}    <- subcolecoes
#
# Onde <prefix> e o FIRESTORE_COLLECTION_PREFIX (castro_crm em prod,
# castro_crm_staging em staging). Garante isolamento entre ambientes
# dentro do mesmo projeto Firebase.
#
# As funcoes existentes collection()/document() continuam atendendo
# colecoes globais (fora de tenants/), como _meta, phone_routing e a
# propria coleção root 'tenants'.

def tenant_collection(tenant_id, name):
    """Retorna referencia a uma subcolecao dentro de tenants/{tenant_id}/.

    Exemplo: tenant_collection('hubloc', 'wa_contacts')
    -> <prefix>_tenants/hubloc/wa_contacts
    """
    if not tenant_id:
        raise ValueError("tenant_id obrigatorio")
    client = get_firestore_client()
    return (
        client.collection(collection_name("tenants"))
        .document(str(tenant_id))
        .collection(name)
    )


def tenant_document(tenant_id, name, doc_id):
    """Retorna referencia a um documento dentro de uma subcolecao do tenant.

    Exemplo: tenant_document('hubloc', 'wa_contacts', 42)
    -> <prefix>_tenants/hubloc/wa_contacts/42
    """
    return tenant_collection(tenant_id, name).document(str(doc_id))


def tenant_doc_ref(tenant_id):
    """Retorna referencia ao DOC do proprio tenant (nao subcolecao).

    Exemplo: tenant_doc_ref('hubloc')
    -> <prefix>_tenants/hubloc
    """
    if not tenant_id:
        raise ValueError("tenant_id obrigatorio")
    return get_firestore_client().collection(collection_name("tenants")).document(str(tenant_id))


def global_collection(name):
    """Colecao FLAT, sempre fora de tenants/ — ignora tenant context.

    Usado explicitamente para colecoes nao escopadas a um tenant
    (phone_routing, _meta, tenants root listing). Aplica o prefix do
    ambiente mas NUNCA a subcolecao do tenant.
    """
    return _flat_collection(name)


def global_document(name, doc_id):
    return _flat_document(name, doc_id)


def utcnow():
    return datetime.now(timezone.utc)


def normalize_value(value):
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value


def normalize_record(record):
    if not record:
        return None
    return {key: normalize_value(value) for key, value in dict(record).items()}


@firestore.transactional
def _next_sequence_transaction(transaction, counters_ref, counter_name):
    snapshot = counters_ref.get(transaction=transaction)
    data = snapshot.to_dict() or {}
    next_value = int(data.get(counter_name, 0)) + 1
    transaction.set(counters_ref, {counter_name: next_value}, merge=True)
    return next_value


def next_sequence(counter_name, tenant_id=None):
    """Atomico auto-increment.

    Resolucao do tenant:
      1. Se tenant_id explicito for passado, usa ele.
      2. Se nao, le do contextvar atual (set_tenant_context).
      3. Se ambos vazios, cai em counters globais flat (compat pre-migration).

    Counters per-tenant ficam em tenants/{tid}/_meta/counters; globais em
    <prefix>__meta/counters.
    """
    client = get_firestore_client()
    if tenant_id is None:
        tenant_id = _current_tenant_id.get()
    if tenant_id:
        counters_ref = _tenant_subcollection_raw(tenant_id, "_meta").document("counters")
    else:
        counters_ref = _flat_document("_meta", "counters")
    return _next_sequence_transaction(client.transaction(), counters_ref, counter_name)
