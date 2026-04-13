# Guia - Usuarios de Teste (email/senha)

Provisionamento e remocao de 4 operadores de teste para validar transferencias e comportamento multi-setor via Email/Password do Firebase.

## Usuarios gerados pelo script

| Email | Senha | Display Name | Setor sugerido |
|---|---|---|---|
| teste1@centralloc.com.br | teste1 | Teste - Vendas | Vendas |
| teste2@centralloc.com.br | teste2 | Teste - Suporte | Suporte |
| teste3@centralloc.com.br | teste3 | Teste - Geral | Geral |
| teste4@centralloc.com.br | teste4 | Teste - Financeiro | Financeiro |

Os emails nao precisam existir de verdade - Firebase nao envia confirmacao.

---

## Pre-requisito (uma vez)

Ativar o provider Email/Password no Firebase Console:

1. https://console.firebase.google.com
2. Projeto → **Authentication** → **Sign-in method**
3. **Email/Password** → toggle **Enable** → **Save**
4. Deixar "Email link (passwordless)" desligado

---

## Criar os 4 usuarios

```powershell
cd c:\Projetos\Hubloc\castro-intelligence
gcloud auth application-default login   # se ainda nao rodou hoje
python -m scripts.create_test_users
```

Output esperado:
```
Criando usuarios de teste...
  [OK] Criado: teste1@centralloc.com.br (uid=...)
  [OK] Criado: teste2@centralloc.com.br (uid=...)
  [OK] Criado: teste3@centralloc.com.br (uid=...)
  [OK] Criado: teste4@centralloc.com.br (uid=...)
Done.
```

Se um ja existir, o script atualiza a senha e segue:
```
  [UPDATE] Ja existia, senha atualizada: ...
```

---

## Atribuir setor a cada um (admin UI)

Os usuarios nascem provisionados no Firestore so no primeiro login. Entao:

1. Cada teste faz **login** pelo menos uma vez em `https://castro-crm-286866630844.southamerica-east1.run.app` (botao "Entrar com email/senha")
2. Como admin em outra aba: **Administracao → Usuarios e Roles**
3. Clicar **Editar** em cada teste1..teste4 e setar:
   - role: `operador`
   - setor: conforme tabela acima
4. Salvar

### Teste em 4 janelas Chrome simultaneas

Use **perfis diferentes** do Chrome (icone do usuario no topo direito → Adicionar) para cada sessao. Abas anonimas compartilham cookies entre elas - nao funciona.

---

## Deletar os usuarios (apos os testes)

### 1. Remover do Firebase Auth

```powershell
cd c:\Projetos\Hubloc\castro-intelligence
python -m scripts.create_test_users --delete
```

Output esperado:
```
Deletando usuarios de teste...
  [OK] Deletado: teste1@centralloc.com.br
  [OK] Deletado: teste2@centralloc.com.br
  [OK] Deletado: teste3@centralloc.com.br
  [OK] Deletado: teste4@centralloc.com.br
Done.
```

### 2. Remover do Firestore (admin UI)

O script acima **so apaga do Firebase Auth**. Os docs em `users/` continuam no Firestore. Para limpar:

1. Como admin no CRM: **Administracao → Usuarios e Roles**
2. Hoje nao ha botao "Remover usuario" na UI - a alternativa e **desativar** via backend ou direto no Firestore Console
3. Alternativa direta: https://console.firebase.google.com → Firestore → colecao `castro_crm_users` → buscar pelos docs com email `teste*@centralloc.com.br` e deletar

> Observacao: se Rafal preferir nao mexer no Firestore direto, os docs de teste podem ser apenas desativados (sem remover) - nao aparecem mais no login, mas ficam no historico de auditoria.

### 3. (Opcional) Desligar o provider Email/Password

Se depois dos testes Rafal quiser que so Google Sign-In funcione:

1. Firebase Console → **Authentication → Sign-in method**
2. **Email/Password** → toggle **Disable**

Usuarios restantes com esse provider param de conseguir logar.

---

## Troubleshooting

**"Firebase: Error (auth/invalid-login-credentials)"**
→ Provider Email/Password nao esta ativado no Firebase Console.

**"Firebase: Error (auth/email-already-in-use)" ao criar**
→ Usuario ja existe. O script ja trata isso - se der esse erro, rode com `--delete` primeiro e depois sem flag.

**Login funciona mas nao aparece no "Usuarios e Roles"**
→ O usuario so e provisionado no Firestore no **primeiro login bem-sucedido**. Refresh a aba admin apos o teste logar pela primeira vez.

**"Acesso restrito ao email ou dominio autorizado"**
→ O email do teste nao bate com `ALLOWED_FIREBASE_EMAIL_DOMAIN`. Os defaults `@centralloc.com.br` passam. Se mudar o dominio, ajuste os emails no script.

**Setor nao aparece no TopBar apos atribuir**
→ Usuario precisa **deslogar e logar de novo** para a sessao carregar o `department_name` atualizado do backend.
