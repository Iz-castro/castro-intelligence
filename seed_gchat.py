# -*- coding: utf-8 -*-

"""
Script de seed para popular o Firestore com dados de teste do Google Chat.
Simula conversas entre operadores e supervisores.

Uso:
  python seed_gchat.py

Requer FIRESTORE_PROJECT_ID configurado no .env ou variavel de ambiente.
"""

from datetime import datetime, timedelta, timezone

from firestore_common import collection, document, next_sequence, utcnow


def seed():
    now = utcnow()

    # --- Conversa 1: Patio de Maquinas ---
    conv1_id = next_sequence("gc_conversations")
    document("gc_conversations", conv1_id).set({
        "id": conv1_id,
        "space_id": "spaces/test_patio_001",
        "space_name": "Patio de Maquinas",
        "participants": ["ana@centralloc.com.br", "beto@centralloc.com.br"],
        "last_message": "Tem 3 betoneiras disponiveis, pode fechar",
        "last_message_at": now - timedelta(minutes=2),
        "unread_count": {},
        "created_at": now - timedelta(days=5),
    })

    messages_patio = [
        ("ana@centralloc.com.br", "Ana Silva", "crm", "Beto, tem betoneira 400L disponivel?", -30),
        ("beto@centralloc.com.br", "Beto Souza", "google_chat", "Deixa eu verificar aqui no patio", -28),
        ("beto@centralloc.com.br", "Beto Souza", "google_chat", "Tem 3 unidades. Todas revisadas semana passada", -25),
        ("ana@centralloc.com.br", "Ana Silva", "crm", "O cliente quer desconto de 10%, posso dar?", -20),
        ("beto@centralloc.com.br", "Beto Souza", "google_chat", "10% pode sim, ta parada ha 2 semanas", -18),
        ("ana@centralloc.com.br", "Ana Silva", "crm", "Fechado! Vou confirmar com o cliente", -15),
        ("beto@centralloc.com.br", "Beto Souza", "google_chat", "Tem 3 betoneiras disponiveis, pode fechar", -2),
    ]

    for sender_email, sender_name, source, content, minutes_ago in messages_patio:
        msg_id = next_sequence("gc_messages")
        document("gc_messages", msg_id).set({
            "id": msg_id,
            "conversation_id": conv1_id,
            "gchat_message_id": f"spaces/test_patio_001/messages/test_{msg_id}",
            "sender_email": sender_email,
            "sender_name": sender_name,
            "msg_type": "text",
            "content": content,
            "media_path": "",
            "media_mime": "",
            "source": source,
            "create_time": now + timedelta(minutes=minutes_ago),
            "created_at": now + timedelta(minutes=minutes_ago),
        })

    # --- Conversa 2: Logistica ---
    conv2_id = next_sequence("gc_conversations")
    document("gc_conversations", conv2_id).set({
        "id": conv2_id,
        "space_id": "spaces/test_logistica_002",
        "space_name": "Logistica e Entregas",
        "participants": ["carlos@centralloc.com.br", "diana@centralloc.com.br"],
        "last_message": "Caminhao saiu as 14h, chega em 2h",
        "last_message_at": now - timedelta(hours=1),
        "unread_count": {},
        "created_at": now - timedelta(days=3),
    })

    messages_logistica = [
        ("carlos@centralloc.com.br", "Carlos Lima", "crm", "Diana, qual o status da entrega do pedido #4521?", -120),
        ("diana@centralloc.com.br", "Diana Rocha", "google_chat", "Estou carregando o caminhao agora", -115),
        ("diana@centralloc.com.br", "Diana Rocha", "google_chat", "2 escoras + 1 andaime, tudo conferido", -110),
        ("carlos@centralloc.com.br", "Carlos Lima", "crm", "Beleza, o cliente ta perguntando previsao de chegada", -90),
        ("diana@centralloc.com.br", "Diana Rocha", "google_chat", "Caminhao saiu as 14h, chega em 2h", -60),
    ]

    for sender_email, sender_name, source, content, minutes_ago in messages_logistica:
        msg_id = next_sequence("gc_messages")
        document("gc_messages", msg_id).set({
            "id": msg_id,
            "conversation_id": conv2_id,
            "gchat_message_id": f"spaces/test_logistica_002/messages/test_{msg_id}",
            "sender_email": sender_email,
            "sender_name": sender_name,
            "msg_type": "text",
            "content": content,
            "media_path": "",
            "media_mime": "",
            "source": source,
            "create_time": now + timedelta(minutes=minutes_ago),
            "created_at": now + timedelta(minutes=minutes_ago),
        })

    # --- Conversa 3: Manutencao (vazia - so o space) ---
    conv3_id = next_sequence("gc_conversations")
    document("gc_conversations", conv3_id).set({
        "id": conv3_id,
        "space_id": "spaces/test_manutencao_003",
        "space_name": "Manutencao Preventiva",
        "participants": [],
        "last_message": "",
        "last_message_at": now - timedelta(days=1),
        "unread_count": {},
        "created_at": now - timedelta(days=1),
    })

    print(f"Seed concluido!")
    print(f"  - Conversa '{conv1_id}': Patio de Maquinas (7 mensagens)")
    print(f"  - Conversa '{conv2_id}': Logistica e Entregas (5 mensagens)")
    print(f"  - Conversa '{conv3_id}': Manutencao Preventiva (vazia)")


if __name__ == "__main__":
    seed()
