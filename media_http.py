# -*- coding: utf-8 -*-
"""Respostas de midia com intervalos HTTP e streaming fora do event loop."""

import re

from fastapi import Request
from fastapi.responses import Response, StreamingResponse


def _media_range(value, size):
    """Retorna intervalo inclusivo; ignora unidades e multiranges nao suportados."""
    if not value or not value.startswith("bytes=") or "," in value:
        return None
    match = re.fullmatch(r"bytes=([0-9]*)-([0-9]*)", value.strip())
    if not match or not any(match.groups()) or size == 0:
        raise ValueError("Intervalo invalido")
    first, last = match.groups()
    if not first:
        suffix = int(last)
        if suffix <= 0:
            raise ValueError("Intervalo invalido")
        return max(0, size - suffix), size - 1
    start = int(first)
    end = min(int(last), size - 1) if last else size - 1
    if start >= size or start > end:
        raise ValueError("Intervalo fora do arquivo")
    return start, end


def media_stream_response(asset, request: Request):
    size = asset["size"]
    headers = {"Accept-Ranges": "bytes", "Cache-Control": "private, no-store"}
    interval = None
    # Sem um validador de If-Range, a resposta correta e o corpo completo.
    # Range so se aplica a GET; HEAD descreve a representacao inteira.
    if request.method == "GET" and not request.headers.get("if-range"):
        try:
            interval = _media_range(request.headers.get("range"), size)
        except ValueError:
            headers["Content-Range"] = f"bytes */{size}"
            return Response(status_code=416, headers=headers)
    start, end = interval if interval else (0, size - 1)
    headers["Content-Length"] = str(end - start + 1)
    if interval:
        headers["Content-Range"] = f"bytes {start}-{end}/{size}"
    if request.method == "HEAD":
        return Response(headers=headers, media_type=asset["mime_type"])
    # StreamingResponse executa next() de iteradores sincronos no threadpool.
    return StreamingResponse(
        asset["iter_content"](start, end),
        status_code=206 if interval else 200,
        headers=headers, media_type=asset["mime_type"],
    )
