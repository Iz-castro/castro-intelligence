# Task - Fix scroll vertical na coluna de contatos

## Data

12/04/2026

## Problema

Na coluna lateral de operacao do contato, passamos a usar varios cards colapsaveis para organizar melhor as acoes.

Depois dessa mudanca, em alguns estados de expandir e recolher, o scroll vertical da coluna deixava de aparecer, o que impedia acessar todo o conteudo disponivel.

## Causa raiz

O container rolavel da coluna estava usando `flex-grow: 1` com `height: 0`, mas sem `min-height: 0`.

Em layout `flex`, isso pode impedir o item de encolher corretamente dentro do painel pai e faz o navegador calcular a area rolavel de forma inconsistente, especialmente quando a altura interna muda por causa de cards colapsaveis.

## Correcao aplicada

- ajustar os containers rolaveis compartilhados para `flex: 1 1 0`
- definir `min-height: 0` no bloco rolavel
- manter `overflow-y: auto` e `scrollbar-gutter: stable`

## Arquivos impactados

- `frontend/src/styles.css`

## Resultado esperado

- o scroll vertical volta a aparecer quando o conteudo da coluna excede a altura disponivel
- expandir e recolher cards nao quebra mais a area rolavel
- o mesmo padrao de scroll continua consistente para lista de contatos, mensagens e painel de detalhes

## Criterio de aceite

- [x] abrir um contato com varios cards visiveis na coluna lateral
- [x] expandir e recolher combinacoes diferentes de cards
- [x] confirmar que a barra de scroll aparece sempre que houver conteudo excedente
- [x] confirmar que nenhum conteudo fica inacessivel no final da coluna

