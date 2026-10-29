# Handoff — UI dos Perfis de acesso (worktree `feature/perfil-acesso-ui`)

Pedido do PO (Rafael, 2026-10-29): a tela **Perfis de acesso** (editor de perfis RBAC por tenant) "está uma
bagunça". Objetivo desta branch: **reorganizar a UI** do editor sem mudar a semântica de permissões nem o
backend (a não ser que algo pequeno seja indispensável e esteja justificado aqui).

Base: `develop @ 8322c2b` (2026-10-28). O develop vai andar (guias de conversa no `App.tsx` e no
`CrmContext.tsx`, mudanças só no painel do chat); faça `git merge develop` antes de abrir o PR. Quem faz o
merge final é o Claude, depois da revisão.

## Onde mexer

| O quê | Onde |
|---|---|
| Modal do editor (tela inteira) | `frontend/src/App.tsx` → `PerfisAcessoModal` (~linha 2934) |
| Entrada no menu | `App.tsx` ~177 (`openSettingsPage("perfis")`, exige `gerenciar_perfis_acesso`) e ~2645 |
| Atribuição de perfil ao usuário (card "Usuarios e Roles") | `App.tsx` ~2186–2230 (`startEditUser`, dropdown de perfil) |
| Tipos | `frontend/src/types.ts` (`PerfilAcesso`, `PerfilCatalogoItem`) |
| API | `main.py` ~1357–1460: `GET/POST /api/admin/perfis-acesso`, `PUT/DELETE /api/admin/perfis-acesso/{id}` |
| Catálogo e seeds | `rbac.py`: `PERMISSION_CATALOG` (tuplas `(grupo, chave, rótulo)` — grupos: Visibilidade, Atendimento, Lead, Follow-up, Canais, Auditoria, Gestão), `SEED_PERFIS` (perfil_admin/supervisor/operador), `_fill_missing_toggles`, `toggles_beyond_user`, `sanitize_toggles` |
| Estilos | `frontend/src/styles.css` (variáveis `--panel`, `--border`, `--accent`, `--text`, `--muted`; tema escuro já coberto pelas variáveis) |

O `GET` já devolve `{ perfis: [...], catalogo: [{grupo, chave, rotulo}] }` — a UI atual ignora os grupos e
lista tudo plano. O PO quer algo legível: agrupar por categoria, explicar cada chave, deixar claro o que
difere do padrão do cargo e quem usa cada perfil.

## O que NÃO pode mudar (invariantes do backend que a UI precisa respeitar)

1. **Anti-amplificação** (`toggles_beyond_user`): ninguém concede o que não tem; só o papel `admin` passa por
   cima. O backend recusa — a UI deve mostrar essas chaves como indisponíveis (não só esconder o erro).
2. **`perfil_admin` é travado** (`is_system_locked`): não dá para desligar chaves dele nem apagá-lo. Perfis seed
   não podem ser apagados; perfil em uso por usuários não pode ser apagado (o backend devolve 409).
3. **Chaves escondidas por feature**: Follow-up (5 chaves) só aparece com `followupEnabled` da sessão;
   `ver_como_usuario` só com a flag do Ver como (`config.feature_impersonate`). Veja o `ocultas` no modal
   atual (~2975) e mantenha a lógica: chave oculta **não** entra no PUT (senão regrava o seed).
4. **Chave ausente no doc = valor do seed do cargo** (`_fill_missing_toggles` já faz isso na listagem). Ao
   salvar, mande o mapa completo que a UI mostra; não invente chaves fora do catálogo (`sanitize_toggles`
   descarta).
5. **Teto por cargo**: `ver_todos_leads` só tem efeito de dados para `admin`/`supervisor` (`can_see_all_tenant`).
   Um perfil de operador com essa chave ligada **não** amplia a visibilidade (rules do Firestore) — a UI deve
   avisar isso em vez de sugerir que funciona.
6. **Gotcha conhecido (Roberta, 14/10):** trocar o **cargo** de um usuário na tela de usuários zera o perfil
   escolhido na UI. Se mexer nesse card, corrija isso de propósito (perfil deve ser mantido ou perguntado).
7. Cache de perfis no backend: 60 s por instância; o PUT invalida a própria instância. Não precisa de
   nada na UI além do que já existe (recarregar a lista após salvar).

## Ideias que o PO vai gostar (escolha e justifique)

- Toggles agrupados por categoria do catálogo, com busca e contador "N de M ligadas".
- Comparação com o padrão do cargo (`SEED_PERFIS`): marcar o que está diferente do seed.
- "Quem usa este perfil" (lista de usuários) antes de apagar/alterar.
- Diff antes de salvar ("vai ligar X, desligar Y") e confirmação.
- Criar perfil a partir de um modelo já existe (`newBase`); deixar isso claro.
- Layout em duas colunas (lista de perfis | editor), responsivo até ~1024 px.

## Regras do repositório

- Leia `CLAUDE.md` e `AGENTS.md`. Comentários e docstrings em pt-BR **sem acento**; strings para o usuário com
  acento normal. Sem dependências novas no frontend.
- Não commitar segredos/PII; não tocar em `.py` sem necessidade (se tocar, rode os simuladores Python da raiz
  com `..\castro-intelligence\.venv\Scripts\python.exe` — o venv fica na pasta principal).
- Gates obrigatórios antes do PR (em `frontend/`): `npm run build` (tsc estrito + vite),
  `node tools\check_wa_format.mjs`, `node tools\check_message_correction.mjs`; na raiz:
  `node tools\sim_followup_frontend.mjs`, `node tools\sim_followup_lifecycle.mjs`,
  `node tools\sim_chat_tabs.mjs` (depois do merge do develop).
- `npm ci` já foi rodado em `frontend/` desta worktree.
- Abrir o PR contra `develop` descrevendo o antes/depois (prints ajudam) e o que ficou de fora.

## Implementação Codex — 2026-10-29

Escopo confirmado pelo Rafael: alinhar os checkboxes e destacar a linha inteira ao passar o mouse
sobre a opção, como nas configurações do Chrome. A implementação mantém o editor por perfil e os grupos
do catálogo (o código desta base **já agrupava** as permissões; a observação acima era anterior).

- `App.tsx`: permissões em uma coluna, cada opção em um `label` que inclui caixa, texto e cadeado;
  o clique no texto continua acionando o checkbox nativo. O perfil de sistema continua travado.
- `styles.css`: estilos restritos ao modal, checkbox de 18 px sem o `width: 100%`/padding global dos
  campos de texto, hover na linha inteira inclusive das opções travadas, foco visível pelo teclado e
  cores dos temas existentes. A lista de perfis fica ao lado no desktop e acima do editor no celular.
- Guardas do handoff: o PUT agora recebe só as chaves visíveis do catálogo. As ocultas são preservadas
  pela mesclagem já existente no backend, em vez de serem regravadas com os valores da listagem.
  A UI impede novas concessões que o editor não possui, respeitando o bypass do cargo admin e a
  revogação de permissões já ligadas. A opção de visibilidade explica o teto por cargo.
- Sem mudanças no backend, nas regras do Firestore ou na atribuição de cargo/perfil aos usuários.
  Busca, comparação com o seed e novos fluxos de confirmação ficam fora deste ajuste visual.

Validação da implementação: build TypeScript/Vite, 32 verificações da formatação WhatsApp,
26 cenários da correção de mensagens, 19 verificações do frontend de follow-up e 25 de seu lifecycle.
O Vite mantém o aviso de bundle acima de 500 kB. A validação visual usa o componente extraído da fonte
real e dados fictícios locais, sem acesso ao backend.

Validação no Chrome headless: **39 verificações aprovadas**, cobrindo 1440, 1024, 390 e 320 px,
temas claro/escuro, ausência de overflow, alinhamento com textos longos, hover (inclusive bloqueado),
foco, clique no texto, tecla Espaço, perfil de sistema, modo somente leitura, anti-amplificação e PUT.
Prévias e relatório locais em `build/perfil-acesso-ui/` (ignorado pelo Git); o build final não os apaga.

Preparação do PR (autorizada pelo Rafael): o fetch confirmou `origin/develop` em `0ac4dc7` e a
`develop` local em `8322c2b`, um commit de desempenho ainda não publicado. A checagem de integração
com `develop` não trouxe novos commits à base original. O commit desta UI foi reaplicado sobre
`origin/develop` para que o PR inclua somente `App.tsx`, `styles.css` e este handoff, sem publicar o
commit de desempenho pelo PR de interface. A branch `develop` local permanece independente.
`tools/sim_chat_tabs.mjs` ainda não existe nas duas bases; executar quando as guias forem integradas.
O merge final do PR cabe à revisão combinada com o Rafael. Sem deploy nesta entrega.
