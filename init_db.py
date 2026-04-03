# -*- coding: utf-8 -*-

from bootstrap_data import DEFAULT_DEPARTMENTS, ensure_default_departments
from config import (
    BOOTSTRAP_ADMIN_EMAIL,
    BOOTSTRAP_ADMIN_DISPLAY_NAME,
    BOOTSTRAP_ADMIN_DEPARTMENT,
)
from database import (
    create_department,
    get_user_by_email,
    init_database,
    upsert_firebase_user,
)

def seed_departments():
    return ensure_default_departments(
        create_department,
        emit=lambda department, department_id: print(f"  Setor '{department['name']}' (id={department_id})"),
    )


def seed_bootstrap_admin(dept_map):
    department_name = BOOTSTRAP_ADMIN_DEPARTMENT or "Geral"
    department_id = dept_map.get(department_name)
    if department_id is None:
        department_id = create_department(
            department_name,
            "Setor criado automaticamente pelo bootstrap",
        )
        dept_map[department_name] = department_id
        print(f"  Setor '{department_name}' criado automaticamente (id={department_id})")

    display_name = BOOTSTRAP_ADMIN_DISPLAY_NAME or "Administrador"
    email = BOOTSTRAP_ADMIN_EMAIL.strip().lower()
    if not email:
        print(
            "\nBootstrap admin Firebase nao configurado. "
            "Defina BOOTSTRAP_ADMIN_EMAIL para provisionar o primeiro admin."
        )
        return

    existing = get_user_by_email(email)
    user = upsert_firebase_user("", email, display_name, "admin", department_id)
    if user and existing:
        print(f"  '{email}' ja existe. Perfil bootstrap Firebase sincronizado como admin.")
    elif user:
        print(f"  '{email}' provisionado para login com Google (cargo: admin)")


def seed():
    init_database()
    dept_map = seed_departments()
    seed_bootstrap_admin(dept_map)
    print("\nSetores: " + ", ".join(department["name"] for department in DEFAULT_DEPARTMENTS))


if __name__ == "__main__":
    seed()
