# Relatório LGPD — RoPA, RIPD e Cadeia de Suboperadores

**Castro Intelligence CRM — documento de transparência para o cliente controlador**

- **Fornecedor / Operador:** CASTRO INTELLIGENCE DATA ML LTDA — CNPJ 63.609.610/0001-07, Brasil
- **Produto:** Castro Intelligence CRM — atendimento via WhatsApp Business Platform
- **Destinatário:** Empresa-cliente, na condição de **Controladora** dos dados (LGPD, Lei nº 13.709/2018)
- **Versão:** 1.0 — **Data:** 2026-05-15
- **Encarregado (DPO) da Castro Intelligence:** `[ENCARREGADO_CASTRO]` — `[contato]`

> **Propósito deste documento.** Apoiar a empresa-cliente, na qualidade de
> Controladora, a montar seu próprio Registro de Operações de Tratamento (RoPA),
> seu Relatório de Impacto (RIPD) e a cláusula de suboperadores do contrato,
> esclarecendo como a Castro Intelligence, na qualidade de **Operadora**, trata
> os dados pessoais por conta e ordem da Controladora.

---

## 1. Papéis na LGPD

```
Titular (cliente final / operador da empresa)
   │
   ▼
CONTROLADORA  ──  Empresa-cliente: define as finalidades e os meios,
   │                é dona da conta WhatsApp Business (WABA)
   ▼
OPERADORA     ──  CASTRO INTELLIGENCE DATA ML LTDA: trata os dados
   │                por conta e ordem da Controladora
   ▼
SUBOPERADORES ──  Google LLC (infraestrutura de nuvem)
                  Meta Platforms, Inc. (WhatsApp Business Platform)
```

- A **Controladora** decide quais dados coleta, com qual finalidade e qual base
  legal, e é o ponto de contato do titular.
- A **Castro Intelligence (Operadora)** fornece a plataforma e trata os dados
  **seguindo as instruções da Controladora**, com as medidas de segurança
  descritas neste documento.
- **Suboperadores** são contratados pela Castro Intelligence para sustentar a
  infraestrutura; sua atuação é restrita à prestação do serviço.

---

## 2. RoPA — Registro de Operações de Tratamento

> Operações que a Castro Intelligence executa **por conta da Controladora**. A
> definição da base legal de cada operação é atribuição da Controladora; as
> indicações abaixo refletem o desenho técnico da plataforma.

### 2.1 Agentes de tratamento

| Papel | Identificação |
|---|---|
| Controladora | `[RAZÃO SOCIAL DO CLIENTE]` — `[CNPJ]` — Encarregado: `[ENCARREGADO_CLIENTE]` |
| Operadora | CASTRO INTELLIGENCE DATA ML LTDA — CNPJ 63.609.610/0001-07 — Encarregado: `[ENCARREGADO_CASTRO]` |
| Suboperador — Infraestrutura | Google LLC (Google Cloud Platform + Firebase) |
| Suboperador — Mensageria | Meta Platforms, Inc. (WhatsApp Business Platform / Graph API) |
| Suboperador — Comunicação interna (opcional) | Google Workspace / Google Chat — apenas se habilitado para a Controladora |

### 2.2 Categorias de titulares e de dados

| Titulares | Categorias de dados pessoais |
|---|---|
| Clientes finais / leads | Telefone, nome (de perfil ou informado), foto de perfil, conteúdo das mensagens, anexos, localização (quando enviada pelo titular), notas e qualificação de atendimento |
| Operadores / atendentes da empresa | Nome, e-mail, identificador de autenticação, registro de acesso (data/hora e IP) |
| Dados sensíveis (se aplicável ao segmento da Controladora, ex.: clínica) | Conteúdo de natureza sensível eventualmente trazido pelo titular na conversa — tratado sob condições reforçadas (item 4) |

### 2.3 Operações de tratamento

| # | Operação | Finalidade | Base legal aplicável | Retenção | Suboperador envolvido |
|---|---|---|---|---|---|
| 1 | Recepção de mensagens recebidas | Registrar e exibir a conversa iniciada pelo titular para atendimento | Execução de contrato / procedimentos preliminares (art. 7º V) | Definida pela Controladora (ver item 5) | Meta (origem), Google (armazenamento) |
| 2 | Envio de respostas | Responder o titular dentro do atendimento | Execução de contrato (art. 7º V) | Idem | Meta (entrega) |
| 3 | Gestão e qualificação de contatos (CRM) | Organizar, qualificar e direcionar o atendimento | Legítimo interesse da Controladora (art. 7º IX), com teste de proporcionalidade da Controladora | Idem | Google |
| 4 | Anexos e localização | Armazenar arquivos e localização trocados na conversa | Execução de contrato (art. 7º V) | Idem | Google |
| 5 | Transcrição de áudio (opcional) | Converter áudio recebido em texto para o atendente | Execução de contrato (art. 7º V) | Mesmo ciclo da mensagem | **Nenhum** — processada na própria infraestrutura no Brasil |
| 6 | Conexão do número WhatsApp (onboarding) | Vincular a conta WhatsApp da Controladora à plataforma | Execução de contrato (art. 7º V) | Enquanto o canal estiver ativo | Meta |
| 7 | Autenticação dos operadores | Autenticar e autorizar o acesso à plataforma | Execução de contrato de trabalho/serviço (art. 7º V); segurança (art. 7º IX) | Enquanto houver vínculo de acesso | Google (Firebase Auth) |
| 8 | Registro de auditoria | Demonstrar quem realizou cada ação (responsabilização) | Cumprimento de obrigação / legítimo interesse (art. 7º II / IX) | Conforme política de retenção acordada | Google |

---

## 3. RIPD — Relatório de Impacto à Proteção de Dados (visão de controles)

### 3.1 Descrição e proporcionalidade

A plataforma recebe, armazena e permite responder conversas de WhatsApp
**iniciadas pelo próprio titular** com a empresa, acrescentando uma camada de
CRM (qualificação, atribuição e transferência entre atendentes). A coleta é
proporcional à finalidade de atendimento: o dado essencial (telefone e conteúdo
da conversa) é intrínseco ao canal WhatsApp escolhido pelo titular.

### 3.2 Medidas de segurança implementadas

| Domínio | Controle |
|---|---|
| Residência dos dados | Banco de dados e aplicação hospedados no **Brasil** (`southamerica-east1`) |
| Isolamento entre clientes | Arquitetura **multi-tenant com isolamento estrutural** por subcoleções dedicadas a cada cliente |
| Integridade do canal | Webhooks da Meta validados por **assinatura criptográfica HMAC-SHA256** antes do processamento |
| Autenticação | **Firebase Auth** com controle de acesso por e-mail/domínio autorizado e perfis (administrador, supervisor, operador) |
| Controle de acesso | Visibilidade de conversas restrita por **atribuição e perfil** do operador |
| Rastreabilidade | **Registro de auditoria** das ações (com identificação do autor, ação e IP) |
| Confidencialidade em logs | **Mecanismo de mascaramento de dados pessoais** (telefone/nome) aplicado em pontos sensíveis de log, com expansão contínua de cobertura |
| Criptografia | Criptografia **em trânsito** (HTTPS/TLS) e **em repouso** (nativa da nuvem) |
| Rastreabilidade reforçada (coex) | Distinção entre **titular do número** e **operador que respondeu**, preservando a auditoria mesmo em atendimento por equipe |
| Reversibilidade | Arquivamento de contatos preservando histórico para fins de auditoria |

### 3.3 Riscos relevantes e responsabilidades da Controladora

Alguns pontos de atenção, próprios do modelo de atendimento por **equipe**
(quando vários atendentes operam um mesmo número), dependem de instrumentos que
**cabem à Controladora**, por ser ela quem define a relação com o titular e com
seus colaboradores:

| Ponto de atenção | Responsabilidade da Controladora |
|---|---|
| O titular pode interagir com um número e ser atendido por mais de um operador da equipe ao longo do tempo | Declarar na **Política de Privacidade** que o atendimento é prestado por **equipe autorizada** da empresa, e que o histórico pode ser acessado por outros operadores autorizados |
| Quando o número de atendimento está em aparelho/linha de um colaborador | Tratar **contratualmente** o número como ferramenta de trabalho, com devolução/encerramento de acesso no desligamento |
| Definição de base legal e captura de consentimento quando aplicável | Definir a base legal de cada finalidade e, quando for o caso, capturar e registrar o consentimento do titular |
| Atendimento a pedidos de titulares (art. 18) | Ser o ponto de contato do titular; a Castro Intelligence apoia tecnicamente o atendimento dessas solicitações mediante requisição da Controladora |

A Castro Intelligence apoia tecnicamente todas essas frentes (ex.: mensagem de
sistema visível ao titular na troca de atendente; relatório de "quem fez o quê"
sobre um titular mediante solicitação) e mantém um **plano de evolução
contínua** de privacidade e segurança alinhado à diretriz interna de
conformidade LGPD do produto.

---

## 4. Tratamento de dados sensíveis (segmentos como clínicas)

Quando a Controladora atua em segmento que possa envolver **dados sensíveis**
(ex.: saúde), o tratamento ocorre sob condições reforçadas, e a Castro
Intelligence deve ser **previamente informada** para habilitar os controles
adicionais aplicáveis (criptografia reforçada, registro de acesso e política de
retenção específica). O uso de base legal para dado sensível (art. 11 da LGPD —
consentimento específico e destacado ou tutela da saúde) é definido pela
Controladora.

---

## 5. Retenção e direitos do titular

- **Retenção:** o período de retenção é **definido pela Controladora** conforme
  sua finalidade e obrigações legais; a Castro Intelligence o implementa
  tecnicamente. Recomenda-se formalizá-lo no contrato/DPA.
- **Direitos do titular (art. 18):** confirmação, acesso, correção,
  anonimização, portabilidade, eliminação e informação sobre compartilhamento.
  O titular exerce esses direitos junto à **Controladora**; a Castro
  Intelligence atende às instruções da Controladora para operacionalizá-los
  sobre os dados sob seu tratamento.

---

## 6. Cadeia de suboperadores e fluxo de dados

### 6.1 Suboperadores

| Suboperador | Serviço prestado | Localização do tratamento |
|---|---|---|
| **Google LLC** | Banco de dados, autenticação, armazenamento de anexos, hospedagem da aplicação, logs | Dados primários e aplicação no **Brasil** (`southamerica-east1`); serviços de identidade e gestão de segredos operados globalmente pela Google |
| **Meta Platforms, Inc.** | Transporte das mensagens via WhatsApp Business Platform (Graph API) | Estados Unidos |
| **Google Workspace / Chat** (opcional) | Comunicação interna entre operadores | Somente se habilitado para a Controladora |

A Castro Intelligence é **Tech Provider verificado pela Meta**. A conta WhatsApp
Business (WABA) é da **Controladora**, que mantém relação direta de cobrança com
a Meta.

### 6.2 Transferência internacional (art. 33 LGPD)

| Dado | Suboperador | País | Observação |
|---|---|---|---|
| Conteúdo das mensagens (envio/recebimento) | Meta | EUA | Inerente ao uso do WhatsApp escolhido pelo titular; amparada por instrumentos contratuais entre os agentes e a Meta |
| Identidade de autenticação do operador | Google | Serviço global | Amparada por instrumentos contratuais com a Google |
| Banco de dados, aplicação e logs | Google | **Brasil** | Sem transferência internacional |

> A formalização das garantias de transferência internacional (cláusulas
> contratuais / DPA) com Meta e Google integra os instrumentos contratuais
> entre as partes e deve constar do contrato entre a Controladora e a Castro
> Intelligence.

### 6.3 Fluxo de dados (visão funcional)

**Recebimento (titular → empresa):**

```
Titular no WhatsApp → Meta (EUA) → [webhook validado por assinatura] →
Plataforma no Brasil → roteamento para o cliente correto →
Banco de dados no Brasil → atendente vê a conversa
```

**Resposta (empresa → titular):**

```
Atendente autenticado → Plataforma no Brasil (verifica permissão e janela de
24h do WhatsApp) → Meta (EUA) → Titular no WhatsApp
(resposta registrada e auditada no Brasil)
```

**Transferência de atendimento:**

```
Atendente A transfere → Plataforma valida autorização →
conversa reatribuída ao Atendente B + mensagem de sistema +
registro de auditoria
```

**Transcrição de áudio (opcional):**

```
Áudio recebido → transcrição executada na própria infraestrutura no Brasil →
texto disponível ao atendente (nenhum dado enviado a terceiros para essa
finalidade)
```

---

## 7. Contato

Para questões de privacidade e proteção de dados relativas à plataforma
Castro Intelligence CRM:

- **Encarregado (DPO) — Castro Intelligence:** `[ENCARREGADO_CASTRO]` —
  `[e-mail / canal de contato]`
- Solicitações de titulares devem ser direcionadas primariamente à
  **Controladora** (`[ENCARREGADO_CLIENTE]`), que aciona a Castro Intelligence
  quando o atendimento depender de ação técnica sobre os dados.

---

### Cobertura deste documento

- [x] **RoPA** — item 2 (agentes, titulares, categorias de dados, operações)
- [x] **RIPD** — item 3 (descrição, proporcionalidade, controles, riscos e responsabilidades)
- [x] **Mapa de suboperadores e fluxo de dados** — item 6 (Google, Meta; transferência internacional; fluxos funcionais)

*Campos entre colchetes (`[...]`) devem ser preenchidos no fechamento contratual
entre a Controladora e a Castro Intelligence.*
