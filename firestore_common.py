# -*- coding: utf-8 -*-

from datetime import date, datetime, timezone
from functools import lru_cache

from google.cloud import firestore

from config import FIRESTORE_COLLECTION_PREFIX, FIRESTORE_PROJECT_ID


@lru_cache(maxsize=1)
def get_firestore_client():
    if FIRESTORE_PROJECT_ID:
        return firestore.Client(project=FIRESTORE_PROJECT_ID)
    return firestore.Client()


def collection_name(name):
    prefix = FIRESTORE_COLLECTION_PREFIX.strip("_")
    return f"{prefix}_{name}" if prefix else name


def collection(name):
    return get_firestore_client().collection(collection_name(name))


def document(name, doc_id):
    return collection(name).document(str(doc_id))


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
    """Alias semantico de collection() para colecoes FORA de tenants/.

    Usado para tornar explicito quando estamos lendo/escrevendo em
    colecoes nao escopadas a um tenant (phone_routing, _meta, tenants
    root listing). Aplica o prefix do ambiente.
    """
    return collection(name)


def global_document(name, doc_id):
    return document(name, doc_id)


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

    - Se tenant_id e fornecido: counter fica em
      tenants/{tenant_id}/_meta/counters (per-tenant — recomendado para
      contact_id, channel_id, etc., garantindo isolamento total).
    - Se tenant_id e None: counter global em _meta/counters (legado;
      usado para contadores realmente cross-tenant ou recursos globais
      como tenants/ root).
    """
    client = get_firestore_client()
    if tenant_id is not None:
        counters_ref = tenant_document(tenant_id, "_meta", "counters")
    else:
        counters_ref = document("_meta", "counters")
    return _next_sequence_transaction(client.transaction(), counters_ref, counter_name)
