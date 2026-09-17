# Guia rápido — Nova agenda de contatos (botão +)

> **Para distribuição quando o picker novo for ativado no tenant** (feature
> flag). Material de treinamento das operadoras — 1 página, linguagem de
> usuário. Versão 1 (picker v2.1).

---

## O que mudou

- A agenda **abre na hora**, mesmo com milhares de contatos: ela mostra os
  contatos em **ordem alfabética** (quem tem nome primeiro, telefones sem
  nome por último), de 50 em 50 — role e toque em **"Ver mais"** para
  carregar a próxima página.
- A **busca agora procura na agenda INTEIRA**, sempre — não importa se o
  contato é antigo ou nunca conversou: se ele existe, a busca acha.

## Como buscar

Digite na caixa de busca e aguarde um instante (ou aperte Enter):

**Por NOME** — digite o **começo** do nome ou do sobrenome (mínimo 2 letras):

| Você digita | Encontra |
|---|---|
| `jo` | João Silva |
| `sil` ou `silva` | João Silva |
| `jo sil` | João Silva (as duas palavras juntas) |

Acentos e maiúsculas não importam: `joao` acha `João`.

**Por TELEFONE** — digite (mínimo 4 números; pode colar com máscara,
`(31) 98344-0484` funciona):

| Você digita | O que a busca entende |
|---|---|
| `31983440484` ou `+55 31 98344-0484` | número completo |
| `98344` ou `8344` | começo do número (sem DDD) |
| `0484` | **final** do número |

## Regra de bolso pra decorar

> **Nome busca pelo COMEÇO (do nome ou do sobrenome). Telefone busca pelo
> número completo, pelo começo ou pelo FINAL.**

## O que a busca NÃO faz (de propósito)

- **Pedaço do MEIO de uma palavra**: `ilv` não acha "Silva" (use `sil`).
- **Erro de digitação**: `silvaa` não acha "Silva" — confira a grafia.
- Se aparecer **"Muitos resultados. Digite mais caracteres."**, refine: mais
  letras do nome ou mais dígitos do telefone.

## Dicas

- O resultado mostra o **responsável** e o canal do contato — útil pra
  distinguir dois "João".
- Contato que nunca conversou (só agenda) aparece na busca e no fim da
  lista alfabética — tocar nele abre a conversa normalmente.
- Cada operadora continua vendo **só os próprios contatos + a fila** — a
  busca respeita exatamente as mesmas regras de sempre.

*Dúvidas ou algo estranho na busca: avise o supervisor com um print.*
