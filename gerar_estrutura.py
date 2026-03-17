# -*- coding: utf-8 -*-
# gerar_estrutura.py

import os
from pathlib import Path

exclude_folders = {'__pycache__', '.git', 'node_modules', '.pytest_cache', 'venv', 'logs', 'media', '.env', '.venv', 'dist', 'build', '.idea', '.vscode'}
exclude_files = {'.db', '.sqlite', '.sqlite3'}

code_types = {
    '.py': 'python',
    '.js': 'javascript',
    '.html': 'html',
    '.css': 'css',
    '.json': 'json',
    '.sh': 'bash',
    '.ps1': 'powershell',
    '.md': 'markdown',
    '.txt': 'text',
    '.sql': 'sql'
}

def should_exclude(path):
    """Verifica se o arquivo/pasta deve ser excluido"""
    parts = Path(path).parts
    for part in parts:
        if part in exclude_folders:
            return True
    
    if Path(path).suffix in exclude_files:
        return True
    
    return False

def print_tree(directory, prefix="", output_file=None):
    """Gera a arvore de arquivos"""
    try:
        entries = sorted(os.listdir(directory))
    except PermissionError:
        return
    
    dirs = [e for e in entries if os.path.isdir(os.path.join(directory, e)) and e not in exclude_folders]
    files = [e for e in entries if os.path.isfile(os.path.join(directory, e))]
    
    all_entries = dirs + files
    
    for i, entry in enumerate(all_entries):
        path = os.path.join(directory, entry)
        
        if should_exclude(path):
            continue
        
        is_last = (i == len(all_entries) - 1)
        current_prefix = "|   " if not is_last else "    "
        
        if os.path.isdir(path):
            line = f"{prefix}+-- {entry}/"
        else:
            line = f"{prefix}+-- {entry}"
        
        if output_file:
            output_file.write(line + "\n")
        else:
            print(line)
        
        if os.path.isdir(path):
            new_prefix = prefix + current_prefix
            print_tree(path, new_prefix, output_file)

def get_code_type(filename):
    """Retorna o tipo de codigo para syntax highlighting"""
    ext = Path(filename).suffix
    return code_types.get(ext, 'text')

def main():
    output_filename = "estrutura_projeto.md"
    
    with open(output_filename, 'w', encoding='utf-8') as f:
        f.write("# Estrutura do Projeto\n\n")
        f.write("## Arvore de Arquivos\n\n")
        f.write("```\n")
        
        print_tree(".", "", f)
        
        f.write("```\n\n")
        f.write("## Codigo dos Arquivos\n\n")
        
        all_files = []
        for root, dirs, files in os.walk("."):
            dirs[:] = [d for d in dirs if d not in exclude_folders]
            
            for file in files:
                filepath = os.path.join(root, file)
                if not should_exclude(filepath):
                    all_files.append(filepath)
        
        for filepath in sorted(all_files):
            filename = os.path.basename(filepath)
            code_type = get_code_type(filename)
            
            f.write(f"## {filename}\n\n")
            f.write(f"```{code_type}\n")
            
            try:
                with open(filepath, 'r', encoding='utf-8') as source:
                    content = source.read()
                    f.write(content)
            except Exception as e:
                f.write(f"# Erro ao ler arquivo: {e}\n")
            
            f.write("\n```\n\n")
    
    print(f"Estrutura completa gerada em: {output_filename}")

if __name__ == "__main__":
    main()