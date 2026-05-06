# -*- coding: utf-8 -*-
"""
Helpers de redacao para conformidade LGPD em logs.

Diretriz CLAUDE.md secao 2: tokens, secrets e PII jamais em logs cleartext.

Estes helpers permitem manter logs informativos pra debugging sem expor
dados pessoais de clientes (telefone, nome, email) ou credenciais.
"""

from __future__ import annotations


def redact_phone(phone: str | None, keep_last: int = 4) -> str:
    """Mantem apenas os N ultimos digitos visiveis.

    >>> redact_phone("5531999998888")
    '***8888'
    >>> redact_phone("31999998888", keep_last=2)
    '***88'
    >>> redact_phone(None)
    '***'
    >>> redact_phone("")
    '***'
    """
    if not phone:
        return "***"
    digits = "".join(ch for ch in str(phone) if ch.isdigit())
    if len(digits) <= keep_last:
        return "***"
    return f"***{digits[-keep_last:]}"


def redact_name(name: str | None) -> str:
    """Retorna primeira letra + comprimento total. Ex.: 'Joao' -> 'J*** (4)'.

    Para nomes vazios/None retorna apenas '***'. Util pra distinguir
    contatos diferentes sem expor identidade.
    """
    if not name:
        return "***"
    s = str(name).strip()
    if not s:
        return "***"
    return f"{s[0]}*** ({len(s)})"


def redact_secret(value: str | None, keep_first: int = 0) -> str:
    """Retorna placeholder ou prefixo curto pra debug.

    Default: nao mostra nada do valor (keep_first=0 -> '<redacted>').
    Com keep_first>0, mostra os N primeiros chars (uso raro, pra
    distinguir versoes de token).
    """
    if not value:
        return "<empty>"
    s = str(value)
    if keep_first <= 0:
        return "<redacted>"
    return f"{s[:keep_first]}***"
