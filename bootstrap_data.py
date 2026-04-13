# -*- coding: utf-8 -*-

DEFAULT_DEPARTMENTS = [
    {"name": "Geral", "description": "Atendimento geral", "bot_key": None},
    {"name": "Vendas", "description": "Equipe comercial", "bot_key": "comercial"},
    {"name": "Suporte", "description": "Suporte tecnico", "bot_key": "sac"},
    {"name": "Financeiro", "description": "Cobranca e pagamentos", "bot_key": "financeiro"},
]


def ensure_default_departments(create_department_fn, emit=None):
    dept_map = {}
    for department in DEFAULT_DEPARTMENTS:
        department_id = create_department_fn(
            department["name"],
            department["description"],
            bot_key=department.get("bot_key"),
        )
        dept_map[department["name"]] = department_id
        if emit:
            emit(department, department_id)
    return dept_map
