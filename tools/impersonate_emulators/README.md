# Ver como: Auth e Firestore Emulators locais

**Contrato atual aprovado:** Ver como consulta dados CRM somente pelo backend,
com polling de 15s. As rules negam toda leitura/escrita direta a tokens `imp` e
UIDs reservados, inclusive quando o registro seria valido. O historico do gate
anterior e o resultado do contrato novo ficam em [DIAGNOSTICO.md](DIAGNOSTICO.md).

Projeto fixo `demo-impersonate`, dados ficticios e hosts `127.0.0.1`. O runner aborta
antes dos testes se projeto/hosts nao forem os esperados. Nao usa ADC, login Firebase,
credenciais reais, deploy ou comandos gcloud.

Prerequisitos: Node 22 e Java 21 no PATH. Em Windows, tambem aceita JRE portatil
descompactado em `.runtime/jre21/<distribuicao>/bin/java.exe`. Dependencias, JRE,
cache dos emuladores e logs ficam ignorados neste diretorio.

```powershell
cd C:\Rafael\castro-intelligence-impersonate\tools\impersonate_emulators
npm.cmd ci --cache .cache/npm
npm.cmd test
```

Na primeira execucao, o Firebase CLI baixa o JAR publico do Firestore Emulator
para `.cache/emulators`. Os emuladores sao iniciados e encerrados pelo runner:
Auth `9099`, Firestore `8080`, hub `4400` e logging `4500`, todos em loopback.
Sem import/export persistente; cada execucao inicia com dados ficticios novos.

A matriz exercita as rules versionadas em `../../firestore.rules` com
`@firebase/rules-unit-testing`, incluindo consultas e principals normais/temporarios
nos prefixes prod/staging do emulador. O registry e carregado apenas com bypass
LOCAL das rules. Tokens temporarios de operador e supervisor nao podem ler nem
escrever em paths de tenant, flat, plataforma, registro ou wildcard staging.
UID reservado sem claims, UID real com imp e marcador imp malformado tambem sao
negados. Grants normais e registry server-only continuam sendo verificados.

Uma integracao com o Auth Emulator troca custom token por ID token, altera
perfil/email/senha da conta descartavel, tenta escapar por login password, forca
refresh e exclui a conta temporaria; a conta original e sua senha ficam intactas.
SDK e REST diretos sao negados em sessao ativa, apos refresh, encerramento e TTL.
O listener deve ser negado antes de entregar qualquer snapshot, inclusive antes
do TTL: o modo temporario nao abre stream Firestore para dados CRM.

Consultas normais do frontend continuam sendo observadas. O comportamento local
preexistente de backup nesse caminho e registrado como pendencia fora do escopo;
nao autoriza nenhuma leitura temporaria nem aprova regras/publicacao de producao.
O prazo e a exclusao de backups no transporte HTTP precisam dos gates do backend;
este harness nao simula ou substitui esses gates.

Emuladores nao comprovam IAM de assinatura ADC, configuracao/publicacao de rules,
quotas ou propagacao de producao. Esses pontos continuam no roteiro humano.
