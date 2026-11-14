# Videos no chat

Implementado em 13/11/2026 (PR #7, mergeado no develop com os ajustes da revisao); sem deploy.

- Videos recebidos e enviados podem ser reproduzidos no balao, com controles e som.
- O player usa `preload="none"`: abrir uma conversa nao inicia downloads dos videos.
- A caixa do balao comeca em 16:9 e, no play, assume a proporcao real do video. Video
  gravado em pe ocupa ~202x360 px em vez de 101x180.
- **Ampliar video** pausa o player do balao e abre a visualizacao maior no mesmo ponto
  do video. O foco vai para "Fechar" e volta ao botao quando a janela fecha.
- So um video ou audio com som toca por vez em qualquer conversa; GIFs (mudos, em loop)
  ficam fora disso.
- **Baixar video** continua disponivel e mostra o nome do arquivo quando ele existe.
- Erros: antes dos metadados o navegador reporta "formato nao suportado" tambem para 404,
  503 e queda de rede. Por isso o player consulta a rota com HEAD antes de escolher o aviso.
  Arquivo que nao existe mais mostra "nao esta mais disponivel" (sem download); falha de
  rede ou do servidor mostra **Tentar novamente**; formato que o navegador nao reproduz
  mostra o aviso e mantem o download.
- GIFs preservam o comportamento anterior (reproducao automatica, repeticao e sem som).

## Entrega da midia

A mesma rota `/media/{subdir}/{filename}` aceita GET e HEAD. O GET suporta um intervalo
de bytes, incluindo intervalos abertos e sufixos, com 206 e `Content-Range`.
Intervalos invalidos ou fora do arquivo retornam 416. Unidades desconhecidas e multiplos
intervalos sao ignorados (200 completo); HEAD ignora Range. Sem validador de If-Range,
uma requisicao com esse cabecalho recebe a representacao completa.

No GCS, a rota consulta metadados e baixa somente o intervalo solicitado, em blocos de
ate 1 MiB, fixando a geracao do objeto para nao misturar versoes. Disco local tambem usa
leitura por blocos. O armazenamento legado no Firestore ainda pode precisar reconstruir
e descompactar o arquivo inteiro antes de recorta-lo. A rota sincrona e a iteracao de
streaming rodam no threadpool, fora do event loop. O pool HTTP do cliente do GCS foi
ampliado para 32 conexoes (o padrao de 10 descartava conexoes a cada rajada).

Erros: objeto inexistente (ou nome que o GCS recusa com 400) responde 404 sem aviso no log
(caso normal, por exemplo midia antiga); bucket inexistente gera um unico aviso por
processo. Falha do storage responde 503 com `Retry-After`; antes os dois casos viravam 404.
O pool ampliado nao e montado quando o cliente usa mTLS. O primeiro bloco e lido antes de o status sair, para que uma falha ali
vire 404/503 limpo e nao uma resposta 200 vazia. Falha no meio do envio ainda corta a
conexao (o navegador pede o intervalo de novo). Nomes iniciados por ponto sao recusados:
`..` passava pelo `basename` e o fallback local servia o diretorio pai.

Respostas usam `Cache-Control: private, no-store`. As URLs e o modelo de acesso
permanecem os anteriores: a pendencia conhecida de midia acessivel sem login continua
aberta. Nao ha redirecionamento para bucket publico nem geracao de URLs assinadas.

## Validacao

- Backend: `tools/sim_media_streaming.py` (13 testes), com dados sinteticos, armazenamento
  fake e rede externa bloqueada. Cobre HTTP, compatibilidade, concorrencia, falha no 1o
  bloco, 503, nomes com ponto, mime/extensao e pool do GCS.
- Frontend: `npm ci` e `npm run build` dentro de `frontend/`.
- Navegador (PR original): Chrome local com video sintetico. Verificados: nenhum download
  antes do play, resposta 206, reproducao e avanco, ampliacao/fechamento, layout em 375 px
  e erro de reproducao mantendo o download. Sem acesso a conversas ou arquivos de clientes.
- Checagem manual recomendada antes de liberar: video recebido e enviado (em pe e
  deitado), play/pausa, volume, avancar/retroceder, ampliar/fechar e fallback de arquivo
  indisponivel. Confirmar em Safari/iPhone com os formatos usados pela operacao.
