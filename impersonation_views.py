# -*- coding: utf-8 -*-
"""Leituras HTTP do Ver como, sem listeners, mutacoes ou fallback amplo."""

from contextlib import contextmanager
from datetime import datetime, timezone
import logging

from fastapi import HTTPException

from firestore_common import collection, document, normalize_record, tenant_context, utcnow
from impersonation_identity import is_impersonation_uid
from rbac import can_see_all_tenant, default_perfil_for_role, effective_toggles, impersonation_perfil_context

logger = logging.getLogger("castro_crm.impersonation_views")
VIEWS = frozenset({"novos", "meus", "nao_qualificados", "equipe", "bot", "backup"})


def normalize_snapshot_record(record):
    """Replica Timestamp.toDate().toISOString do SDK sem mudar strings legadas."""
    def value(item):
        if isinstance(item, datetime):
            aware = item if item.tzinfo else item.replace(tzinfo=timezone.utc)
            return aware.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        if isinstance(item, dict):
            return {key: value(child) for key, child in item.items()}
        if isinstance(item, (list, tuple)):
            return [value(child) for child in item]
        return item
    return normalize_record(value(record))


@contextmanager
def _context(user):
    imp = (user or {}).get("impersonation") or {}
    uid = (user or {}).get("firebase_uid")
    tid = (user or {}).get("tenant_id")
    if (not isinstance(tid, str) or not tid or not isinstance(uid, str) or not uid
            or is_impersonation_uid(uid) or not is_impersonation_uid(imp.get("auth_uid"))):
        raise HTTPException(status_code=403, detail="Leitura exclusiva da propria visualizacao")
    with tenant_context(tid), impersonation_perfil_context(user):
        yield


def _positive(value, label):
    if type(value) is not int or value <= 0:
        raise HTTPException(status_code=400, detail=f"{label} invalido")
    return value


def _meta(user):
    return {"read_at": utcnow().isoformat(), "expires_at": user["impersonation"]["expires_at"]}


def _raw(snap):
    if not snap.exists:
        return None
    row = snap.to_dict() or {}
    if not row:
        return None
    # Os IDs numericos do CRM continuam numericos mesmo em docs legados.
    doc_id = snap.id
    row.setdefault("id", int(doc_id) if str(doc_id).isdigit() else doc_id)
    return row


def _query_rows(query, user, cap=None, raw_rows=None):
    snaps = list(query.stream())
    broad = can_see_all_tenant(user)
    rows = []
    for snap in snaps:
        row = _raw(snap)
        if row and raw_rows is not None:
            raw_rows.append((str(snap.id), row))
        # Filtra antes de normalizar/serializar. Campo ausente continua falso.
        if row and (broad or not row.get("is_backup")):
            rows.append(normalize_snapshot_record(row))
    return rows, cap is not None and len(snaps) >= cap


def _window(name, user, owner=None, cap=50, all_scope=False, unread=False, raw_rows=None):
    query = collection(name)
    if name == "wa_contacts":
        query = query.where("is_archived", "==", 0)
    if not all_scope:
        query = query.where("assigned_to_uid", "==", owner)
    if unread:
        query = query.where("unread_count", ">", 0).order_by("unread_count", direction="DESCENDING")
    query = query.order_by("last_message_at", direction="DESCENDING").limit(cap)
    return _query_rows(query, user, cap, raw_rows)


def _targets(user):
    return [("unassigned:blank", ""), ("unassigned:null", None),
            ("mine:" + user["firebase_uid"], user["firebase_uid"])]


def read_snapshot(user):
    """Reproduz top-50 por target e top-300 global, sem corte agregado previo."""
    with _context(user):
        contact_groups, conversation_groups = {}, {}
        contact_saturated, conversation_saturated = {}, {}
        raw_conversations = []
        for key, owner in _targets(user):
            contact_groups[key], contact_saturated[key] = _window("wa_contacts", user, owner)
            conversation_groups[key], conversation_saturated[key] = _window(
                "wa_conversations", user, owner, raw_rows=raw_conversations)
        if can_see_all_tenant(user):
            contact_groups["all"], contact_saturated["all"] = _window("wa_contacts", user, all_scope=True)
            conversation_groups["all"], conversation_saturated["all"] = _window(
                "wa_conversations", user, cap=300, all_scope=True, raw_rows=raw_conversations)
            # Target dedicado existente: igualdade indexada, sem cap silencioso.
            conversation_groups["backup"], conversation_saturated["backup"] = _query_rows(
                collection("wa_conversations").where("is_backup", "==", True), user,
                raw_rows=raw_conversations)
        # O gate legado conta a uniao bruta dos targets antes do filtro visual.
        # Expor apenas o booleano preserva esse gate sem revelar IDs de backup.
        unique_raw = dict(raw_conversations)
        mine_load_more = sum(row.get("assigned_to") == user["id"] or
                             row.get("assigned_to_uid") == user["firebase_uid"]
                             for row in unique_raw.values()) >= 50
        perfil_id = user.get("perfil_acesso_id") or default_perfil_for_role(user.get("role"))
        return {"contact_groups": contact_groups, "conversation_groups": conversation_groups,
                "contact_saturated": contact_saturated, "conversation_saturated": conversation_saturated,
                "perfil": {"id": perfil_id, "role": user["role"], "toggles": effective_toggles(user)},
                "mine_load_more": mine_load_more,
                **_meta(user)}


def read_page(user, scope, view, limit):
    """Limites crescentes preservam as mesmas consultas da camada estatica."""
    with _context(user):
        _positive(limit, "Limite")
        if view not in VIEWS or scope not in {"mine", "pool", "all", "unread"}:
            raise HTTPException(status_code=403, detail="Escopo ou caixa nao autorizado")
        unread = scope == "unread"
        selected = scope
        if unread:
            selected = {"meus": "mine", "novos": "pool", "bot": "pool", "equipe": "all"}.get(view)
        if (selected == "mine" and view != "meus") or (
                selected == "pool" and view not in ("novos", "bot")) or (
                selected == "all" and view != "equipe") or selected is None:
            raise HTTPException(status_code=403, detail="Escopo nao corresponde a caixa")
        if selected == "all" and not can_see_all_tenant(user):
            raise HTTPException(status_code=403, detail="Acesso negado a caixa Equipe")
        groups, saturated = {}, {}
        targets = {"mine": [("mine:" + user["firebase_uid"], user["firebase_uid"])],
                   "pool": [("unassigned:blank", ""), ("unassigned:null", None)],
                   "all": [("all", None)]}[selected]
        for key, owner in targets:
            groups[key], saturated[key] = _window("wa_conversations", user, owner, cap=limit,
                                                  all_scope=selected == "all", unread=unread)
        return {"groups": groups, "saturated": saturated, **_meta(user)}


def _doc(name, doc_id):
    return _raw(document(name, str(doc_id)).get())


def _direct_contact_scope(user, contact):
    return can_see_all_tenant(user) or contact.get("assigned_to_uid") in (user["firebase_uid"], "", None)


def _require_contact(user, contact):
    if not contact:
        raise HTTPException(status_code=404, detail="Contato nao encontrado")
    if contact.get("is_backup") and not can_see_all_tenant(user):
        raise HTTPException(status_code=403, detail="Acesso negado ao contato")
    if _direct_contact_scope(user, contact):
        return
    # Um lead de outra pessoa pode ser hidratado para uma THREAD propria.
    own = (collection("wa_conversations").where("contact_id", "==", contact["id"])
           .where("assigned_to_uid", "==", user["firebase_uid"]))
    if any(not (snap.to_dict() or {}).get("is_backup") for snap in own.stream()):
        return
    raise HTTPException(status_code=403, detail="Acesso negado ao contato")


def _thread_allowed(user, thread):
    if not thread:
        return False
    if thread.get("is_backup") and not can_see_all_tenant(user):
        return False
    return can_see_all_tenant(user) or thread.get("assigned_to_uid") in (user["firebase_uid"], "", None)


def _find_thread(user, contact, channel_id):
    channel_id = channel_id if channel_id is not None else contact.get("channel_id")
    if channel_id is None:
        return None
    _positive(channel_id, "Canal")
    wa_id = contact.get("wa_id")
    if not wa_id:
        return None
    canonical_id = f"{channel_id}__{wa_id}"
    thread = _doc("wa_conversations", canonical_id)
    if thread and (thread.get("contact_id") != contact["id"] or not _thread_allowed(user, thread)):
        raise HTTPException(status_code=403, detail="Acesso negado a thread")
    if thread:
        thread["id"] = canonical_id
    return thread


def read_thread(user, contact_id, channel_id=None):
    """Apenas thread existente e autorizada, sem criar/atribuir/marcar lida."""
    with _context(user):
        contact = _doc("wa_contacts", _positive(contact_id, "Contato"))
        _require_contact(user, contact)
        thread = _find_thread(user, contact, channel_id)
        return {"conversation": normalize_snapshot_record(thread), **_meta(user)}


def filter_message_rows(user, contact, rows):
    """Filtra timeline/protocolo por thread sem mudar a ordem recebida."""
    with _context(user):
        _require_contact(user, contact)
        broad, result, thread_cache = can_see_all_tenant(user), [], {}
        for row in rows:
            if not row or (row.get("is_backup") and not broad):
                continue
            if row.get("contact_id") not in (None, contact["id"]):
                continue
            if not broad:
                conv_id = row.get("conversation_id")
                if conv_id:
                    if conv_id not in thread_cache:
                        thread_cache[conv_id] = _doc("wa_conversations", conv_id)
                    thread = thread_cache[conv_id]
                    if not thread or thread.get("contact_id") != contact["id"] or not _thread_allowed(user, thread):
                        continue
                elif not _direct_contact_scope(user, contact):
                    continue
            result.append(normalize_snapshot_record(row))
        return result


def read_messages(user, contact_id, channel_id=None, limit=10):
    """Thread canonica ou timeline legada; nunca entrega outra thread por IDOR."""
    with _context(user):
        _positive(limit, "Limite")
        contact = _doc("wa_contacts", _positive(contact_id, "Contato"))
        _require_contact(user, contact)
        query = collection("wa_messages")
        selected = None
        if channel_id is not None:
            selected = _find_thread(user, contact, channel_id)
            if not selected:
                return {"messages": [], **_meta(user)}
            query = query.where("conversation_id", "==", selected["id"])
        else:
            query = query.where("contact_id", "==", contact_id)
        snaps = list(query.order_by("timestamp_wa", direction="DESCENDING").limit(limit).stream())
        result = filter_message_rows(user, contact, [_raw(snap) for snap in snaps])
        # Sort estavel preserva a ordem original do snapshot em empates.
        result.sort(key=lambda row: str(row.get("timestamp_wa") or row.get("created_at") or ""))
        return {"messages": result, **_meta(user)}


def read_internal_chat(user, kind, conversation_id=None):
    """Preserva as janelas globais atuais: 50 conversas e 100 mensagens."""
    with _context(user):
        if kind == "conversations":
            if conversation_id is not None:
                raise HTTPException(status_code=400, detail="Conversa nao permitida nesta consulta")
            items, _ = _query_rows(collection("gc_conversations").order_by(
                "last_message_at", direction="DESCENDING").limit(50), user, 50)
        elif kind == "messages":
            _positive(conversation_id, "Conversa")
            if not _doc("gc_conversations", conversation_id):
                raise HTTPException(status_code=404, detail="Conversa nao encontrada")
            items, _ = _query_rows(collection("gc_messages").order_by(
                "created_at", direction="DESCENDING").limit(100), user, 100)
            items = [row for row in items if row.get("conversation_id") == conversation_id]
            items.sort(key=lambda row: str(row.get("created_at") or ""))
        else:
            raise HTTPException(status_code=400, detail="Consulta de chat interno invalida")
        return {"items": items, **_meta(user)}
