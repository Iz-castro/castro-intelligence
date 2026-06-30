# -*- coding: utf-8 -*-

DEFAULT_DEPARTMENTS = [
    {"name": "Geral", "description": "Atendimento geral", "bot_key": None},
    {"name": "Vendas", "description": "Equipe comercial", "bot_key": "comercial"},
    {"name": "Suporte", "description": "Suporte tecnico", "bot_key": "sac"},
    {"name": "Financeiro", "description": "Cobranca e pagamentos", "bot_key": "financeiro"},
]


def ensure_default_departments(create_department_fn, emit=None, existing_departments=None):
    """Semeia os setores default.

    Pula um default cujo NOME ou BOT_KEY ja esta coberto por um setor ATIVO
    existente — evita recriar uma funcao que ja existe sob outro nome (ex.:
    'Comercial' ja cobre bot_key=comercial -> nao recria 'Vendas'). Blindagem
    para chamadas diretas (init_db / tenant ja populado); o caminho de boot ja
    e protegido pelo gate em bootstrap_departments (so semeia tenant vazio).
    """
    covered_bot_keys = set()
    covered_names = set()
    for dept in (existing_departments or []):
        if not dept.get("is_active", 1):
            continue
        bot_key = (dept.get("bot_key") or "").strip().lower()
        if bot_key:
            covered_bot_keys.add(bot_key)
        covered_names.add((dept.get("name") or "").strip().lower())

    dept_map = {}
    for department in DEFAULT_DEPARTMENTS:
        bot_key = (department.get("bot_key") or "").strip().lower()
        name_norm = department["name"].strip().lower()
        if name_norm in covered_names or (bot_key and bot_key in covered_bot_keys):
            continue
        department_id = create_department_fn(
            department["name"],
            department["description"],
            bot_key=department.get("bot_key"),
        )
        dept_map[department["name"]] = department_id
        if emit:
            emit(department, department_id)
    return dept_map
