#!/usr/bin/env python3
"""Gera SISTEMA_COMPLETO.md — dump unificado do codigo-fonte do projeto.

Varre o repositorio e concatena os arquivos de codigo em um unico Markdown
com sumario clicavel, para que humanos e agentes possam ler tudo de uma vez.

Uso:
    python scripts/build_sistema_completo.py

Pode ser rodado de qualquer diretorio — resolve caminhos relativo a si mesmo.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "SISTEMA_COMPLETO.md"

# Diretorios ignorados em qualquer nivel da arvore.
EXCLUDE_DIRS = {
    "docs",
    "node_modules",
    ".venv",
    "venv",
    "frontend_dist",
    "dist",
    "build",
    "__pycache__",
    ".git",
    ".idea",
    ".vscode",
    ".pytest_cache",
    ".mypy_cache",
}

# Arquivos ignorados por nome exato (basename).
EXCLUDE_FILES = {
    ".env",
    "package-lock.json",
    "SISTEMA_COMPLETO.md",
    "CLAUDE.md",
    ".DS_Store",
    ".gitignore",
    ".dockerignore",
    ".gcloudignore",
}

# Extensao -> linguagem do fence Markdown.
LANG_BY_EXT = {
    ".py": "python",
    ".ts": "ts",
    ".tsx": "tsx",
    ".js": "javascript",
    ".jsx": "jsx",
    ".json": "json",
    ".html": "html",
    ".css": "css",
    ".scss": "scss",
    ".yml": "yaml",
    ".yaml": "yaml",
    ".md": "markdown",
    ".sh": "bash",
    ".ps1": "powershell",
    ".rules": "",
    ".txt": "text",
    ".toml": "toml",
    ".ini": "ini",
    ".sql": "sql",
}

# Nomes especiais (sem extensao ou com convencao propria).
LANG_BY_NAME = {
    "Dockerfile": "dockerfile",
    ".env.example": "bash",
    "firebase.json": "json",
}

# Prioridade de categorias dentro de cada diretorio (menor = primeiro).
# Configs/infra antes de codigo; codigo antes de testes.
CATEGORY_PRIORITY: dict[str, int] = {
    # Infra / configuracao
    ".env.example": 0,
    "Dockerfile": 1,
    "docker-compose.yml": 2,
    "requirements.txt": 3,
    "package.json": 3,
    "tsconfig.json": 4,
    "tsconfig.app.json": 4,
    "tsconfig.node.json": 4,
    "vite.config.ts": 5,
    "firebase.json": 6,
    "firestore.indexes.json": 7,
    "firestore.rules": 8,
    "storage.rules": 9,
    "deploy.ps1": 10,
    "deploy.sh": 11,
    "start.example.ps1": 12,
    "index.html": 13,
}

# Prioridade por extensao (fallback quando o nome nao esta no mapa acima).
EXT_PRIORITY: dict[str, int] = {
    ".json": 20,
    ".yml": 21,
    ".yaml": 21,
    ".rules": 22,
    ".html": 23,
    ".css": 24,
    ".ps1": 25,
    ".sh": 26,
    ".txt": 27,
    ".py": 40,
    ".ts": 50,
    ".tsx": 51,
    ".js": 52,
    ".jsx": 53,
    ".md": 80,
}


def get_lang(path: Path) -> str | None:
    """Retorna a tag de linguagem para o fence; None se o arquivo deve ser ignorado."""
    if path.name in LANG_BY_NAME:
        return LANG_BY_NAME[path.name]
    ext = path.suffix.lower()
    if ext in LANG_BY_EXT:
        return LANG_BY_EXT[ext]
    return None


def slugify(rel: str) -> str:
    """Gera ancora estilo GitHub-friendly compativel com o formato existente."""
    s = rel.lower().replace("\\", "/")
    # Remove barras e pontos; preserva hifen/underscore.
    out = []
    for ch in s:
        if ch in ("/", "."):
            continue
        out.append(ch)
    return "".join(out)


def sort_key(path: Path) -> tuple:
    """Ordem: raiz primeiro, depois subdirs alfabeticos; dentro de cada nivel,
    configs antes de codigo, depois nome."""
    rel = path.relative_to(ROOT)
    parts = rel.parts
    # Top-level bucket: "" para raiz, nome do dir caso contrario.
    top = "" if len(parts) == 1 else parts[0]
    cat = CATEGORY_PRIORITY.get(
        path.name,
        EXT_PRIORITY.get(path.suffix.lower(), 99),
    )
    # Dentro do mesmo top-level e categoria, ordenar por profundidade e nome.
    return (top, cat, len(parts), str(rel).lower())


def collect_files() -> list[Path]:
    files: list[Path] = []
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(ROOT)
        if any(part in EXCLUDE_DIRS for part in rel.parts):
            continue
        if path.name in EXCLUDE_FILES:
            continue
        if get_lang(path) is None:
            continue
        files.append(path)
    files.sort(key=sort_key)
    return files


def render(files: list[Path]) -> str:
    rels = [str(p.relative_to(ROOT)).replace("\\", "/") for p in files]

    out: list[str] = []
    out.append("# Hubloc / Castro Intelligence — Sistema Completo")
    out.append("")
    out.append("Codigo-fonte completo do projeto (backend Python + frontend React/TS + configs).")
    out.append(
        "Exclui: `docs/`, `node_modules/`, `.venv/`, `frontend_dist/`, "
        "`__pycache__/`, `.env`, `package-lock.json`, `CLAUDE.md`."
    )
    out.append("")
    out.append("Gerado por `scripts/build_sistema_completo.py`. Nao editar a mao.")
    out.append("")
    out.append("---")
    out.append("")
    out.append("## Sumario")
    out.append("")
    for rel in rels:
        out.append(f"- [{rel}](#{slugify(rel)})")
    out.append("")
    out.append("---")
    out.append("")

    for path, rel in zip(files, rels):
        lang = get_lang(path) or ""
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            content = path.read_text(encoding="latin-1")
        # Garante newline final unica.
        content = content.rstrip("\n")
        out.append(f"## {rel}")
        out.append("")
        out.append(f"```{lang}")
        out.append(content)
        out.append("```")
        out.append("")

    return "\n".join(out) + "\n"


def main() -> None:
    files = collect_files()
    text = render(files)
    OUTPUT.write_text(text, encoding="utf-8")
    size_kb = OUTPUT.stat().st_size / 1024
    print(f"OK: {OUTPUT.relative_to(ROOT)} ({len(files)} arquivos, {size_kb:.1f} KB)")


if __name__ == "__main__":
    main()
