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
def _next_sequence_transaction(transaction, counter_name):
    counters_ref = document("_meta", "counters")
    snapshot = counters_ref.get(transaction=transaction)
    data = snapshot.to_dict() or {}
    next_value = int(data.get(counter_name, 0)) + 1
    transaction.set(counters_ref, {counter_name: next_value}, merge=True)
    return next_value


def next_sequence(counter_name):
    client = get_firestore_client()
    return _next_sequence_transaction(client.transaction(), counter_name)
