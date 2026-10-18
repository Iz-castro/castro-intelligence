# Follow-up: atendimento a pedidos de privacidade

F1 acrescenta dados operacionais pessoais em `tenants/{tenant_id}/crm_tasks` e
`crm_activities`. O prefixo real é o de `FIRESTORE_COLLECTION_PREFIX`. A preferência
de contatos comerciais fica no contato existente, em `commercial_contact_block`,
com recibos na coleção existente `audit_log` (`commercial_contact_*`). Não há
cópia de conversas, planilha ou dados clínicos nessas entidades.

O arquivamento atual de contato não elimina esses dados nem conclui tarefas.
Não há rotina geral de eliminação física no CRM. Um pedido de privacidade exige
validação da identidade, finalidade e autorização pelo responsável da clínica,
inclusive quando houver dever de preservar parte dos registros. Este documento
não estabelece prazo de retenção nem autoriza excluir pacientes.

Para acesso/portabilidade autorizados, a gestão usa as consultas autenticadas e
paginadas por contato: `GET /api/followup/tasks?contact_id=ID&status=pending`
(repetir para `completed` e `cancelled`) e
`GET /api/followup/contacts/ID/activities`. Continuar com `next_cursor` até o fim;
uma página vazia com cursor não significa fim. A autorização ao contato e à
thread é revalidada em cada leitura. A preferência usa
`GET /api/followup/contacts/ID/commercial-preference`. Esses dados complementam a
exportação legada de contatos; ela não passou a incluir tarefas automaticamente.
O acesso da gestão continua dependente das permissões e da flag do módulo.

Retificação operacional normal usa a edição da tarefa e preserva a atividade
original. Para correção ou eliminação de informação pessoal indevida, o processo
administrativo autorizado precisa abranger, pelo `tenant_id` e `contact_id`
exatos: tarefas, todas as atividades (incluindo recibos `op_*`), preferência no
contato e recibos de preferência em `audit_log`. Estes últimos referenciam o
contato no campo `detail`; não presumir que possuam `contact_id` indexado.
Não basta apagar a tarefa e deixar atividades órfãs. Preservar somente a evidência
administrativa mínima legalmente exigida, sem reproduzir o conteúdo removido.
Preparar a relação exata de documentos, obter autorização específica antes de
qualquer mutação administrativa e verificar o resultado pelo mesmo recorte.

As coleções novas não têm acesso direto pelo SDK do navegador, em produção ou
staging. A API é a fonte de autorização atual. As regras de staging agora exigem
claim de tenant nas leituras e reservam escritas ao backend, incluindo usuários,
perfis e contatos: o wildcard anterior permitiria alterar a preferência e
contornar as verificações da API. As regras e índices precisam ser publicados
coordenadamente antes de habilitar F1 com dados reais, após merge na pasta
principal e autorização de deploy. Validar as regras no emulador nesse preparo;
os simuladores Python não executam o motor de regras do Firestore.
