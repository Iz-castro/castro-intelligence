# -*- coding: utf-8 -*-

DEFAULT_DEPARTMENTS = [
    {"name": "Geral", "description": "Atendimento geral"},
    {"name": "Vendas", "description": "Equipe comercial"},
    {"name": "Suporte", "description": "Suporte tecnico"},
    {"name": "Financeiro", "description": "Cobranca e pagamentos"},
]


def ensure_default_departments(create_department_fn, emit=None):
    dept_map = {}
    for department in DEFAULT_DEPARTMENTS:
        department_id = create_department_fn(department["name"], department["description"])
        dept_map[department["name"]] = department_id
        if emit:
            emit(department, department_id)
    return dept_map
