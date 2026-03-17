# -*- coding: utf-8 -*-

from database import init_database, db_session, create_department
from auth import hash_password

DEPARTMENTS = [
    {"name": "Geral", "description": "Atendimento geral"},
    {"name": "Vendas", "description": "Equipe comercial"},
    {"name": "Suporte", "description": "Suporte tecnico"},
    {"name": "Financeiro", "description": "Cobranca e pagamentos"},
]

USERS = [
    {"username": "izael", "display_name": "Izael Castro", "password": "castro@2026", "department": "Geral", "role": "admin"},
    {"username": "rafael", "display_name": "Rafael Castro", "password": "castro@2026", "department": "Geral", "role": "supervisor"},
]


def seed():
    init_database()

    # Criar setores
    dept_map = {}
    for d in DEPARTMENTS:
        did = create_department(d["name"], d["description"])
        dept_map[d["name"]] = did
        print(f"  Setor '{d['name']}' (id={did})")

    # Criar usuarios
    with db_session() as conn:
        for u in USERS:
            exists = conn.execute("SELECT id FROM users WHERE username = ?", (u["username"],)).fetchone()
            if exists:
                # Atualizar role se necessario
                conn.execute(
                    "UPDATE users SET role = ? WHERE username = ?",
                    (u["role"], u["username"])
                )
                print(f"  '{u['username']}' ja existe. Role atualizado para '{u['role']}'.")
                continue
            h = hash_password(u["password"])
            dept_id = dept_map.get(u["department"])
            conn.execute(
                "INSERT INTO users (username, display_name, password_hash, department_id, role) "
                "VALUES (?, ?, ?, ?, ?)",
                (u["username"], u["display_name"], h, dept_id, u["role"]),
            )
            print(f"  '{u['username']}' criado (setor: {u['department']}, cargo: {u['role']})")

    print("\nCredenciais:")
    print("  izael  / castro@2026  (admin)")
    print("  rafael / castro@2026  (supervisor)")
    print("\nSetores: " + ", ".join(d["name"] for d in DEPARTMENTS))


if __name__ == "__main__":
    seed()
