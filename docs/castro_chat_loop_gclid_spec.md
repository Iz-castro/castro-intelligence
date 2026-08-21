# Castro Chat + Loop de Conversão de Lead (Google + Meta)
**Especificação técnica para desenvolvimento · Castro Intelligence**
*Documento interno de engenharia — v2*

---

## 1. O problema que este loop resolve

Hoje o Google e a Meta otimizam **por clique**, não por conversa real. Trazem gente para o site ou para o WhatsApp, mas não sabem quais desses cliques viraram **lead de verdade** — alguém que chegou no atendimento e conversou. Resultado: as campanhas aprendem a buscar "quem clica", e não "quem vira cliente".

O loop fecha esse buraco: leva o identificador do clique até a conversa do Castro Chat e, **quando o lead conversa de fato com a atendente**, devolve essa conversão para a plataforma que o trouxe. A partir daí a campanha passa a otimizar por conversa real.

**Definição de conversão (leia com atenção — é o ponto mais importante).** A conversão que este loop devolve **automaticamente** é a do **lead qualificado**: a pessoa chegou no chat e houve conversa real com a atendente, dentro do prazo de validade do identificador do clique. O **contrato** que fecha depois no Sisloc **não** é o gatilho automático — ele fecha dias ou semanas mais tarde, muitas vezes fora da janela do identificador, e é etapa comercial **manual**. O valor do contrato pode enriquecer o dado num segundo momento (ajuste de conversão), mas não se deve prometer "contrato fechado → conversão automática", porque na maioria dos ciclos longos isso simplesmente não casa.

O Castro Chat é a peça central porque já enxerga a conversa inteira do WhatsApp (Meta Cloud API direta). Ele dispensa qualquer ferramenta de terceiro para "verificar se a conversão efetivou no Whats".

---

## 2. Dois loops, um por plataforma (a distinção que define tudo)

O mecanismo **muda conforme o canal**, e confundir os dois leva a construir o que não precisa.

**Loop Meta (Click-to-WhatsApp) — o mais simples, sem trabalho no site.**
Quando alguém clica num anúncio de Click-to-WhatsApp, a Meta injeta um identificador chamado **`ctwa_clid`** no objeto `referral` do webhook, junto da **primeira mensagem** que o usuário envia. O Castro Chat só precisa **ler esse campo** e guardar. Não há captura no site, não há token, não há handoff. E como o Castro Chat usa a **Meta Cloud API direta** (sem intermediário), recebe o webhook cru com o `referral` intacto — muitos provedores de WhatsApp descartam esse objeto; nós não. A devolução é feita pela **Conversions API for Business Messaging** da Meta.

**Loop Google — o mais difícil, exige o site.**
O identificador do Google (`gclid`) chega na **URL do site**, não no WhatsApp. Quando a pessoa pula para o WhatsApp, nada da URL sobrevive. Por isso, no caso do Google, é preciso **carregar o gclid do site até a conversa** por meio de um token embutido na mensagem (detalhado na seção 3). A devolução é feita pela **Google Ads API / Data Manager API**.

| | **Meta (CTWA)** | **Google** |
|---|---|---|
| Identificador | `ctwa_clid` | `gclid` |
| Como chega ao Castro Chat | nativo, no `referral` do webhook | via token embutido na mensagem |
| Precisa de trabalho no site? | **Não** | **Sim** (captura + token) |
| Devolução da conversão | CAPI for Business Messaging | Google Ads API / Data Manager API |

---

## 3. O detalhe que define a arquitetura do lado Google: o WhatsApp apaga o rastro

*(Esta seção só vale para o Google. A Meta resolve nativamente, ver seção 2.)*

Quando o usuário clica num link `wa.me`, **nada além do texto pré-preenchido da mensagem sobrevive** até o WhatsApp — não há referrer, não há query string, não há cookie compartilhado. O único canal para levar o gclid do site até a conversa é **o corpo da primeira mensagem**.

Não dá para colar o gclid inteiro (é longo e o usuário pode apagar). A solução é um **token curto** (6–8 caracteres) que referencia, no backend, o gclid e o contexto. O site troca "gclid → token" antes de abrir o WhatsApp; o Castro Chat troca "token → gclid" quando a mensagem chega.

**Recomendação de projeto:** gerar o token **no carregamento da página** (não no clique). Assim o `wa.me` já sai com o token embutido, o clique continua nativo e síncrono (sem bloqueio de pop-up, sem quebrar o rastreamento atual do GTM que lê o `href`).

---

## 4. Visão geral dos dois fluxos

**Google (5 passos):**
1. Site captura o `gclid` na chegada (parâmetro na URL) e guarda em cookie.
2. Site registra o gclid no backend e recebe um **token curto**, embutido no texto do `wa.me`.
3. Castro Chat, ao receber a primeira mensagem, lê o token, recupera o gclid e amarra à conversa.
4. Quando há **conversa real com a atendente** (lead qualificado), dispara-se a conversão de lead.
5. Backend envia a conversão para o Google (gclid + data + dado do usuário com hash).

**Meta (3 passos):**
1. Usuário clica no anúncio de Click-to-WhatsApp e manda a primeira mensagem.
2. Castro Chat lê o `ctwa_clid` do `referral` do webhook e amarra à conversa.
3. Quando há **conversa real com a atendente**, dispara-se a conversão via CAPI for Business Messaging (ctwa_clid + `action_source=business_messaging`).

Em ambos, o contrato/valor no Sisloc é enriquecimento manual posterior — não o gatilho.

---

## 5. Arquitetura e componentes

| Componente | Responsabilidade | Aplica a | Stack |
|---|---|---|---|
| **A. Site (hubloc-wp)** | Capturar gclid, obter token, embutir no `wa.me` | Google | JS (`hubloc.js`) |
| **B. Backend — vínculo** | Emitir token e amarrar gclid (Google); ler `ctwa_clid` do webhook (Meta) | Ambos | FastAPI + Firestore |
| **C. Disparo da conversão de lead** | Detectar "conversa real com a atendente" e enfileirar a conversão | Ambos | Castro Chat |
| **D. Uploader** | Enviar a conversão à plataforma certa | Ambos | Serviço no Cloud Run |

---

## 6. Componente A — Site (só Google): captura e token

Adição ao `hubloc.js`. Capturar o identificador na chegada e, **no load**, trocar por token e embutir no `href` do `wa.me`.

```javascript
// (ilustrativo) 1) Na chegada: captura gclid/gbraid/wbraid + utm
(function captureClickId(){
  const p = new URLSearchParams(location.search);
  const ids = { gclid: p.get('gclid'), gbraid: p.get('gbraid'), wbraid: p.get('wbraid') };
  const utm = {};
  ['utm_source','utm_medium','utm_campaign','utm_term','utm_content']
    .forEach(k => { if (p.get(k)) utm[k] = p.get(k); });
  if (ids.gclid || ids.gbraid || ids.wbraid) {
    document.cookie = `hubloc_click=${encodeURIComponent(JSON.stringify({...ids, utm, ts: Date.now()}))};max-age=${90*86400};path=/;SameSite=Lax`;
  }
})();

// (ilustrativo) 2) No load (com consentimento): troca gclid -> token e injeta no href do wa.me
async function hublocInjetarRef(){
  const click = lerCookie('hubloc_click');
  if (!click || !temConsentimentoAds()) return;         // sem consentimento, segue sem ref
  try {
    const r = await fetch('https://api.castrochat.example/leads/track', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ ...JSON.parse(click), page_url: location.href,
        consent:{ ad_user_data:true, ad_personalization:true } })
    });
    const { token } = await r.json();
    document.querySelectorAll('[data-wpp]').forEach(el => {
      const texto = encodeURIComponent(el.dataset.wpp + (token ? `\n\n(ref: ${token})` : ''));
      el.setAttribute('href', `https://wa.me/${HUBLOC.whatsapp}?text=${texto}`);
    });
  } catch(e){ /* backend fora: mantém o href normal, sem ref */ }
}
// rodar no load e também após o aceite de cookies
document.addEventListener('DOMContentLoaded', hublocInjetarRef);
window.addEventListener('cookie_consent_accept', hublocInjetarRef);
```

Pontos de projeto:
- **Token no load, não no clique:** o clique segue nativo, o GTM continua lendo o `href` com `wa.me` e a conversão atual de WhatsApp não quebra.
- **Só injeta o `ref` com consentimento.** Sem consentimento, o `wa.me` fica sem ref — o lead entra normal, só sem atribuição. É conformidade, não perda evitável.
- **Fallback:** backend fora → mantém o `href` de sempre.

---

## 7. Componente B — Backend (vínculo dos dois lados)

### B.1 Google — endpoint que emite o token

```python
# (ilustrativo) POST /leads/track
import secrets, time
@app.post("/leads/track")
async def track(body: TrackIn):
    token = secrets.token_urlsafe(5)[:6].upper()
    firestore.collection("lead_tracking").document(token).set({
        **body.dict(), "created_at": time.time(),
        "expires_at": time.time() + 90*86400, "status": "pending",
    })
    return {"token": token}
```

### B.2 Google — ler o token na primeira mensagem
```python
# (ilustrativo) no handler do webhook: procura o token e amarra o gclid
import re
TOKEN_RE = re.compile(r"ref:\s*([A-Z0-9]{6})", re.I)
def bind_google(msg, conversa):
    m = TOKEN_RE.search((msg.get("text",{}) or {}).get("body",""))
    if not m: return
    ref = firestore.collection("lead_tracking").document(m.group(1).upper()).get()
    if ref.exists:
        d = ref.to_dict()
        conversa.update({"gclid": d.get("gclid"), "gbraid": d.get("gbraid"),
                         "wbraid": d.get("wbraid"), "ad_source":"google"})
```

### B.3 Meta — ler o `ctwa_clid` nativo do `referral`
```python
# (ilustrativo) a Meta manda o referral na PRIMEIRA mensagem de um clique CTWA
def bind_meta(msg, conversa):
    ref = msg.get("referral") or {}
    ctwa = ref.get("ctwa_clid")
    if ctwa:
        conversa.update({"ctwa_clid": ctwa, "ad_source":"meta",
                         "meta_source_id": ref.get("source_id")})
```

Notas:
- Validar a assinatura do webhook da Meta (`X-Hub-Signature-256`).
- `ctwa_clid` vem **só na primeira mensagem** e **só** se o clique veio de anúncio Click-to-WhatsApp. Guardar assim que chega.
- Guardar o `wa_id` (telefone) na conversa — serve para enriquecimento posterior (dado com hash / casamento com Sisloc, manual).

---

## 8. Componente C — Disparo da conversão de **lead**

O gatilho é **conversa real com a atendente**, não contrato. Duas formas de detectar:

**C.1 — Automático por engajamento.** Quando a conversa tem resposta da atendente (ou passa de um limiar mínimo de troca), o sistema marca `lead_qualificado = true` e enfileira a conversão. Rápido e sem depender de ação humana extra.

**C.2 — Marcação do operador.** O operador marca a conversa como "qualificada" no painel (o Castro Chat já tem qualificação de lead). Útil para filtrar engano/número errado.

Em ambos, cai numa fila (`lead_conversions_queue`) que o Componente D consome. **O contrato/valor do Sisloc não entra aqui** — se um dia for enriquecer o valor, é um ajuste de conversão posterior e manual, e só vale se dentro da janela de atribuição.

---

## 9. Componente D — Upload (a plataforma certa para cada lead)

### D.1 Google *(atenção à mudança de 2026)*
**Confirme antes de codar:** a partir de **15/06/2026**, requisições de `UploadClickConversion` da Google Ads API **falham para tokens de desenvolvedor que nunca enviaram conversões offline antes** — o Google direciona para a **Data Manager API**. Como é integração nova, provavelmente não dá para usar o caminho antigo. Verifique em:
- `https://developers.google.com/google-ads/api/docs/conversions/upload-offline`
- `https://support.google.com/google-ads/answer/13321563`

**Caminho recomendado: Enhanced Conversions for Leads** (gclid + dado do usuário com hash). Campos da conversão de lead:
- **um** de `gclid` / `gbraid` / `wbraid` (nunca mais de um);
- `conversion_action` (ação "Importar de cliques" criada na conta);
- `conversion_date_time` no formato `yyyy-mm-dd hh:mm:ss+|-hh:mm` (com fuso) — o momento da **conversa**, não do contrato;
- opcional: dado do usuário com hash SHA-256 (telefone `wa_id` em E.164, e-mail normalizado);
- `consent` (`ad_user_data`, `ad_personalization`).
Sem valor obrigatório — é conversão de lead. Valor do contrato, se um dia entrar, é ajuste posterior.

### D.2 Meta — Conversions API for Business Messaging
Enviar o evento com:
- `ctwa_clid` (do `referral`);
- `action_source = business_messaging`;
- canal de mensagem = WhatsApp;
- momento da conversa.
Documentação a confirmar: Conversions API for Business Messaging (CTWA) no developers.facebook.com.

Regras comuns: respeitar a **janela do identificador** (gclid ~90 dias, com aviso a partir de ~25; a Meta tem sua própria janela) — por isso a conversão é a do lead, que acontece cedo; e **sem dupla contagem** (dedup por identificador + evento + data/hora).

---

## 10. Modelo de dados (Firestore)

**`lead_tracking/{token}`** *(Google)*
```
gclid, gbraid, wbraid, utm{}, page_url, consent{}, created_at, expires_at, status
```

**Conversa/contato — campos novos**
```
ad_source (google|meta),
gclid|gbraid|wbraid,        # Google
ctwa_clid, meta_source_id,  # Meta
wa_id, lead_qualificado, qualificado_em
```

**`lead_conversions_queue/{id}`**
```
conversation_id, ad_source, identificador (gclid|ctwa_clid|...),
conversion_action|event_name, conversion_date_time,
user_data_hashed{sha256_phone?, sha256_email?},
status (queued|uploaded|error), attempts, uploaded_at, error?
```

---

## 11. LGPD e consentimento

- **Só capturar/enviar com consentimento.** No Google, o `ref` só entra na mensagem com aceite de anúncio. Na Meta, o `ctwa_clid` vem do próprio clique no anúncio (base legítima do anúncio), mas o envio de dado do usuário com hash segue a mesma disciplina de consentimento.
- O site já dispara `cookie_consent_accept`; usar o mesmo estado.
- Hash sempre SHA-256 sobre valor normalizado (e-mail minúsculo/trim; telefone E.164). Nunca subir dado pessoal em texto puro.
- Alinhar com a Helenice (DPO da Hub Loc).

---

## 12. Casos de borda

- **Lead orgânico (sem gclid nem ctwa_clid):** conversa entra sem atribuição. Normal.
- **Meta destino-site (não CTWA):** não há `ctwa_clid`; o rastreio da Meta passa a ser Pixel/CAPI web, fora deste loop. **Confirmar com a M2P qual é o caso.**
- **Usuário apaga o `(ref: …)` (Google):** perde atribuição daquele lead; mitiga com dado do usuário com hash.
- **iOS (gbraid/wbraid):** subir no campo certo; nunca junto com gclid.
- **`ctwa_clid` só na 1ª mensagem:** amarrar na primeira; ignorar nas seguintes.
- **Fora da janela do identificador:** conversão de lead acontece cedo, então cabe na janela; o contrato tardio fica como fato comercial manual, não como upload.

---

## 13. Segurança

- Validar `X-Hub-Signature-256` do webhook da Meta.
- `/leads/track` com rate-limit e CORS restrito a `hubloc.com.br`.
- Credenciais (Google Ads API, Meta) em Secret Manager.
- Token é só chave de lookup, sem dado sensível embutido.

---

## 14. Pré-requisitos por plataforma (lado da conta / M2P)

**Google:** auto-tagging ligado; ação de conversão "Importar de cliques" (ou Enhanced Conversions for Leads) criada; acesso de API (developer token, OAuth, customer ID).

**Meta:** confirmar que os anúncios são **Click-to-WhatsApp** (senão não há `ctwa_clid`); acesso para enviar eventos pela **Conversions API for Business Messaging** (dataset/pixel, token de acesso, WABA vinculada).

---

## 15. Plano de implementação (fases)

1. **Fase 1 — Vínculo Meta.** Ler e guardar `ctwa_clid` do webhook. É a mais rápida, sem trabalho no site. Entregável mensurável: toda conversa vinda de anúncio Meta nasce com o identificador gravado.
2. **Fase 2 — Vínculo Google.** Componentes A e B: captura do gclid, token, amarração.
3. **Fase 3 — Disparo do lead.** Componente C: detectar conversa real com a atendente e enfileirar.
4. **Fase 4 — Upload.** Componente D: Meta (CAPI Business Messaging) e Google (Data Manager API / Enhanced Conversions for Leads).
5. **Fase 5 — Enriquecimento (opcional).** Valor do contrato do Sisloc como ajuste posterior, quando dentro da janela.

---

## 16. Pontos a verificar na documentação atual (não assumir)

- Endpoint atual de conversão offline do Google (Data Manager API vs. Google Ads API), por causa da mudança de 15/06/2026.
- Formato atual do evento da Conversions API for Business Messaging da Meta (campos e janela).
- Estrutura atual do `referral`/`ctwa_clid` no webhook da Meta Cloud API.
- Janela vigente de cada identificador.

A arquitetura acima é estável; a sintaxe fina sai da doc oficial no momento de codar.
