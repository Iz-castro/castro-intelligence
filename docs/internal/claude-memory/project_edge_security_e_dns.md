---
name: project-edge-security-e-dns
description: DNS do domínio está no Cloudflare (www=GitHub Pages); decisão de borda do painel super-admin em aberto — IAP+LB (GCP) vs Cloudflare Access
metadata: 
  node_type: memory
  type: project
  originSessionId: 2ea021ab-1790-4bcc-84a4-5cd01dc049de
  modified: 2026-07-23T19:53:17.567Z
---

**DNS descoberto 2026-07-23 (via nslookup):** `castrointelligence.com.br` é
registrado no `registro.br` (obrigatório p/ `.com.br`) mas o **DNS é gerenciado no
Cloudflare** (`archer.ns` / `laila.ns.cloudflare.com`). `www` e raiz apontam pro
**GitHub Pages** (site institucional) — daí a confusão de "registrei pelo GitHub".
Adicionar subdomínios (`crm.`, `admin.`) é no painel Cloudflare, não toca o site.

**Decisão de borda EM ABERTO** para proteger o Cloud Run B (`castro-superadmin`):
- **Opção A** = IAP + HTTPS Load Balancer do GCP (plano original, ~US$20/mês, mata a
  `.run.app` direta via ingress `internal-and-cloud-load-balancing`).
- **Opção B (recomendada)** = **Cloudflare Access / Zero Trust** — US$0 (grátis até 50
  users), sem LB, webhook da Meta intocado; NÃO mata a `.run.app` por padrão (fecha com
  header secreto no app).

**Regras que valem nos dois caminhos:** gate de identidade vai SÓ no `admin`, NUNCA no
`crm` (trancaria os clientes). A trava real do painel B segue sendo a auth do app
(`require_super_admin` + MFA + `check_revoked`). Domínio por cliente (`crm.hubloc.com.br`)
é viável via Cloudflare for SaaS, mas isolamento LGPD **nunca** depende do hostname —
segue no claim de tenant.

Detalhes e as duas posições lado a lado: `docs/HANDOFF_IAP_E_TENANT2.md`
(seção "⚖️ Decisão de borda em aberto"). Ver também [[project_oregon_prod_cutover]],
[[project_multitenant_fase2_roadmap]].
