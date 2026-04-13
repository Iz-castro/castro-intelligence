# -*- coding: utf-8 -*-
"""
Cria 4 usuarios de teste no Firebase Auth via Admin SDK.

Uso:
    cd castro-intelligence
    python -m scripts.create_test_users

Requisitos:
    - Provider Email/Password ativado no Firebase Console
    - Credenciais: ou GOOGLE_APPLICATION_CREDENTIALS apontando para uma service account
      do projeto, ou `gcloud auth application-default login` ja executado.

Para remover depois, rode com --delete.
"""

import sys
from pathlib import Path

# Permite rodar de dentro de castro-intelligence/ sem setar PYTHONPATH
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import argparse
from firebase_admin import auth

from firebase_admin_client import get_firebase_app


TEST_USERS = [
    {"email": "teste1@centralloc.com.br", "password": "teste1", "display_name": "Teste - Vendas"},
    {"email": "teste2@centralloc.com.br", "password": "teste2", "display_name": "Teste - Suporte"},
    {"email": "teste3@centralloc.com.br", "password": "teste3", "display_name": "Teste - Geral"},
    {"email": "teste4@centralloc.com.br", "password": "teste4", "display_name": "Teste - Financeiro"},
]


def create_users(app):
    for u in TEST_USERS:
        try:
            user = auth.create_user(
                email=u["email"],
                email_verified=False,
                password=u["password"],
                display_name=u["display_name"],
                disabled=False,
                app=app,
            )
            print(f"  [OK] Criado: {u['email']} (uid={user.uid})")
        except auth.EmailAlreadyExistsError:
            existing = auth.get_user_by_email(u["email"], app=app)
            auth.update_user(existing.uid, password=u["password"], display_name=u["display_name"], app=app)
            print(f"  [UPDATE] Ja existia, senha atualizada: {u['email']} (uid={existing.uid})")
        except Exception as e:
            print(f"  [ERRO] {u['email']}: {e}")


def delete_users(app):
    for u in TEST_USERS:
        try:
            existing = auth.get_user_by_email(u["email"], app=app)
            auth.delete_user(existing.uid, app=app)
            print(f"  [OK] Deletado: {u['email']}")
        except auth.UserNotFoundError:
            print(f"  [SKIP] Nao existia: {u['email']}")
        except Exception as e:
            print(f"  [ERRO] {u['email']}: {e}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--delete", action="store_true", help="Deleta os usuarios de teste")
    args = parser.parse_args()

    app = get_firebase_app()
    if args.delete:
        print("Deletando usuarios de teste...")
        delete_users(app)
    else:
        print("Criando usuarios de teste...")
        create_users(app)
    print("Done.")


if __name__ == "__main__":
    main()
