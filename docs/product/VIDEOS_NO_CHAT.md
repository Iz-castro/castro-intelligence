# Videos no chat

Implementado localmente em 13/11/2026; sem deploy nesta alteracao.

- Videos recebidos e enviados podem ser reproduzidos no balao, com controles e som.
- O player usa `preload="none"`: abrir uma conversa nao inicia downloads dos videos.
- **Ampliar video** pausa o player do balao e abre a visualizacao maior.
- **Baixar video** continua disponivel. Se o navegador nao conseguir reproduzir o formato,
  a interface mostra uma mensagem e mantem essa alternativa.
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
streaming rodam no threadpool, fora do event loop.

Respostas usam `Cache-Control: private, no-store`. As URLs e o modelo de acesso
permanecem os anteriores: a pendencia conhecida de midia acessivel sem login continua
aberta. Nao ha redirecionamento para bucket publico nem geracao de URLs assinadas.

## Validacao

- Backend: `tools/sim_media_streaming.py`, com dados sinteticos, armazenamento fake e
  rede externa bloqueada; cobre HTTP, compatibilidade e concorrencia.
- Frontend: `npm ci` e `npm run build` dentro de `frontend/`.
- Navegador: Chrome local com video sintetico; verificados ausencia de download antes do
  play, resposta 206, reproducao e avanco, ampliacao/fechamento, layout em 375 px e erro
  de reproducao mantendo o download. Sem acesso a conversas ou arquivos de clientes.
- Checagem manual recomendada antes de liberar: video recebido e enviado, play/pausa,
  volume, avancar/retroceder, ampliar/fechar e fallback de arquivo indisponivel; confirmar
  em Safari/iPhone com os formatos usados pela operacao.
