# -*- coding: utf-8 -*-
"""Configura o funil comercial de UM tenant: tenants/{tid}.settings.funnel.

Mesmo doc (e mesmo cache de 60 s) de settings.ai; o super-admin nao edita
settings, entao este script e o caminho de operacao (ADR 0015). Sem config
habilitada o funil fica desligado no tenant (rotas /api/funnel 404 e entrada
automatica inerte), mesmo com FEATURE_FUNNEL=true no Cloud Run.

O que grava: a SUBARVORE inteira, com
tenant_doc_ref(tid).update({"settings.funnel": cfg}): substitui o mapa em vez
de fazer merge profundo (o merge deixaria para tras rotulo, limiar ou etapa
inativa removidos). Chaves que este script nao conhece sao preservadas.
version +1 a cada gravacao, enabled_at so no 1o --enable, updated_at sempre.
Escrita com precondicao de update_time: doc do tenant alterado depois da
leitura (outra gravacao em paralelo) = nada gravado, exit 1; rode de novo.

Recusas (exit 2, nada gravado):
  - template desconhecido ou invalido (funnel_catalog.validate_template);
  - etapa/motivo que nao existe no template; new/unclassified nunca inativas;
    rotulo vazio de verdade, com mais de 40 caracteres ou com quebra de linha;
  - --inactive-stage de etapa estrutural do template: KPI de conversao
    (kpis.booked_stage/won_stage, ex.: scheduled) ou destino de automacao
    (ex.: in_service, para onde o handoff da Val e a 1a resposta humana
    movem). Inativa, a conversao some do painel ou a automacao para em
    silencio;
  - --inactive-stage de etapa que ainda tem contatos (count() por etapa),
    salvo --allow-inactive-with-contacts (a coluna inativa continua no quadro
    enquanto tiver contatos);
  - --stale em etapa sem limiar por dias (o de tarefa nao tem dias);
  - troca de template que deixaria contato em etapa inexistente no novo.

Dry-run por padrao (escrita TRAVADA no cliente antes da 1a leitura): mostra o
diff e o catalogo resultante. --yes grava. --show so mostra a config atual,
os textos da clinica, o catalogo resolvido e quantos contatos ha em cada
etapa.

Textos da clinica: rotulos e textos explicativos que a clinica edita na tela
"Etapas" (doc tenant-scoped system_settings/funnel; decisao do PO de 28/10)
ficam POR CIMA dos rotulos de settings.funnel. Este script so le esse doc: o
--show e o catalogo do dry-run mostram o que a equipe ve, e --stage-label/
--reason-label avisam quando a clinica ja renomeou a mesma chave. Tambem
avisa quando settings.funnel cita etapa/motivo que nao existe no template (o
runtime ignora; ex.: chaves de uma versao anterior do template).

Rotulo vazio (--stage-label k=) volta ao rotulo do template; --stale k=off
desliga o selo "parado" da etapa; --stale k=default volta ao limiar do
template. O cache de tenants atualiza em ate 60 s nas instancias do Cloud Run
(sem deploy). Saida sem PII (so configuracao e contagens).

Exige FIRESTORE_PROJECT_ID e FIRESTORE_COLLECTION_PREFIX explicitos (no
ambiente ou no .env), antes de qualquer leitura: staging e prod compartilham
o projeto e so o prefixo os separa; o padrao do config e o de PRODUCAO.

Uso (PowerShell, raiz do repo):
  $env:FIRESTORE_PROJECT_ID = "project-4a851bf9-f475-418c-800"
  $env:FIRESTORE_COLLECTION_PREFIX = "castro_crm"     # ou castro_crm_staging
  ./.venv/Scripts/python.exe -m scripts.set_tenant_funnel --tenant varizemed-test --show
  ./.venv/Scripts/python.exe -m scripts.set_tenant_funnel --tenant varizemed-test --enable --template clinic_v1
  ./.venv/Scripts/python.exe -m scripts.set_tenant_funnel --tenant varizemed-test --enable --template clinic_v1 --yes
  ./.venv/Scripts/python.exe -m scripts.set_tenant_funnel --tenant varizemed --stage-label "new=Novo lead" --stale in_service=3 --yes
  ./.venv/Scripts/python.exe -m scripts.set_tenant_funnel --tenant varizemed --disable --yes   # kill-switch do tenant

Exit 0 ok / 1 erro de gravacao / 2 recusado (nada gravado).
"""
import argparse
import copy
import json
import os
import re
import sys
import traceback
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import funnel_catalog as fc  # noqa: E402  (modulo puro: nenhum Firestore no import)

_TENANT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
_KEY_RE = re.compile(r"^[a-z][a-z0-9_]{1,39}$")
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")
STALE_OFF = "off"
STALE_DEFAULT = "default"
STALE_MAX_DAYS = 365
# Mudam a cada gravacao; nao contam como "mudanca" no diff de conteudo.
_BOOKKEEPING = ("version", "enabled_at", "updated_at")
_AUSENTE = object()


class Recusa(Exception):
    """Pedido invalido ou inseguro: nada e gravado (exit 2)."""


def _agora():
    return datetime.now(timezone.utc)


def trava_escrita():
    """Dry-run/--show: cliente Firestore so-leitura NESTE processo, antes da
    1a leitura. Inclui o commit interno das transacoes (_commit, que e o que
    o @firestore.transactional chama na 2.x; travar so commit() nao basta)."""
    from google.cloud.firestore_v1 import batch, collection, document, transaction

    def _bloqueado(*_a, **_k):
        raise RuntimeError("dry-run: escrita no Firestore bloqueada")

    alvos = [
        (document.DocumentReference, ("set", "update", "delete", "create")),
        (collection.CollectionReference, ("add",)),
        (batch.WriteBatch, ("set", "update", "delete", "create", "commit")),
        (transaction.Transaction, ("set", "update", "delete", "create", "commit", "_commit")),
    ]
    try:
        from google.cloud.firestore_v1 import bulk_writer
        alvos.append((bulk_writer.BulkWriter, ("set", "update", "delete", "create")))
    except ImportError:  # pragma: no cover - versao sem BulkWriter
        pass
    for cls, nomes in alvos:
        for nome in nomes:
            if hasattr(cls, nome):
                setattr(cls, nome, _bloqueado)


def _stdout_seguro():
    # Rotulo com acento/simbolo nunca derruba o script em console cp1252.
    for fluxo in (sys.stdout, sys.stderr):
        reconfigure = getattr(fluxo, "reconfigure", None)
        if reconfigure:
            try:
                reconfigure(errors="replace")
            except Exception:  # noqa: BLE001
                pass


def _ambiente():
    """(projeto, prefixo) que o cliente vai usar, ou None com erro claro.
    Os dois precisam vir explicitos do ambiente; o .env conta, porque o
    config o carrega no import (antes da checagem). Staging e prod
    compartilham o projeto e so o prefixo os separa: o padrao do config e
    o prefixo de PRODUCAO, entao nao serve de fallback."""
    import config
    projeto = str(getattr(config, "FIRESTORE_PROJECT_ID", "") or "").strip()
    if not projeto:
        print("ERRO: defina FIRESTORE_PROJECT_ID (e FIRESTORE_COLLECTION_PREFIX) no ambiente. "
              "Sem ele o cliente cairia no projeto padrao do gcloud, que aponta para o projeto "
              "ERRADO. Nada foi lido nem gravado.", file=sys.stderr)
        return None
    if "FIRESTORE_COLLECTION_PREFIX" not in os.environ:
        print("ERRO: defina FIRESTORE_COLLECTION_PREFIX no ambiente (castro_crm = producao, "
              "castro_crm_staging = staging). Sem ele o config cai no prefixo de PRODUCAO, e "
              "staging e prod compartilham o projeto. Nada foi lido nem gravado.", file=sys.stderr)
        return None
    return projeto, str(getattr(config, "FIRESTORE_COLLECTION_PREFIX", "") or "")


def _onde(exc):
    """arquivo:linha do erro, sem a mensagem (pode carregar valores)."""
    quadros = traceback.extract_tb(exc.__traceback__)
    if not quadros:
        return "?"
    ultimo = quadros[-1]
    return "%s:%s" % (Path(ultimo.filename).name, ultimo.lineno)


def _iso(valor):
    if isinstance(valor, (datetime, date)):
        return valor.isoformat()
    return str(valor)


def _fmt(valor):
    if valor is _AUSENTE:
        return "(ausente)"
    if isinstance(valor, datetime):
        return valor.isoformat()
    return json.dumps(valor, ensure_ascii=False, sort_keys=True, default=_iso)


def _tenant(valor):
    if not _TENANT_RE.match(valor or ""):
        raise argparse.ArgumentTypeError("tenant invalido: use letras, numeros, '_' ou '-'")
    return valor


def _pares(valores, opcao):
    """['chave=valor', ...] -> [(chave, valor)] na ordem; chave validada."""
    pares = []
    for bruto in valores or []:
        if "=" not in bruto:
            raise Recusa("%s espera CHAVE=VALOR" % opcao)
        chave, valor = bruto.split("=", 1)
        chave = chave.strip()
        if not _KEY_RE.match(chave):
            raise Recusa("%s: chave invalida %r" % (opcao, chave))
        pares.append((chave, valor))
    return pares


def _dias(valor, opcao, chave):
    """'off' -> 0 (desliga), 'default' -> None (volta ao template), N -> int."""
    texto = str(valor).strip().lower()
    if texto == STALE_OFF:
        return 0
    if texto == STALE_DEFAULT:
        return None
    try:
        dias = int(texto)
    except ValueError:
        dias = -1
    if not 1 <= dias <= STALE_MAX_DAYS:
        raise Recusa("%s %s: use dias (1..%d), off ou default" % (opcao, chave, STALE_MAX_DAYS))
    return dias


def _tipos_de_canal():
    from channel_service import CHANNEL_TYPE_COEXISTENCE, CHANNEL_TYPE_STANDARD
    return (CHANNEL_TYPE_STANDARD, CHANNEL_TYPE_COEXISTENCE)


def etapas_estruturais(template):
    """{etapa: [papel]} das etapas que o template usa POR CHAVE: KPI de
    conversao (kpis) e destino de automacao (automations[*].to)."""
    papeis = {}
    for slot, chave in sorted((template.get("kpis") or {}).items()):
        if chave:
            papeis.setdefault(chave, []).append("kpi %s" % slot)
    for evento, regra in sorted((template.get("automations") or {}).items()):
        destino = (regra or {}).get("to") if isinstance(regra, dict) else None
        if destino:
            papeis.setdefault(destino, []).append("destino da automacao %s" % evento)
    return papeis


def chaves_fora_do_template(cfg):
    """Entradas de settings.funnel que citam etapa/motivo inexistente no
    template (o runtime ignora), ex.: chaves de uma versao anterior."""
    cfg = cfg if isinstance(cfg, dict) else {}
    template = fc.TEMPLATES.get(cfg.get("template"))
    if not template:
        return []
    etapas = {s["key"] for s in template["stages"]}
    motivos = {r["key"] for r in template["reasons"]}
    achadas = []
    for campo, conhecidas in (("stage_labels", etapas), ("stale_days", etapas), ("reason_labels", motivos)):
        valor = cfg.get(campo)
        if isinstance(valor, dict):
            achadas += ["%s.%s" % (campo, k) for k in sorted(valor, key=str) if k not in conhecidas]
    for campo, conhecidas in (("inactive_stages", etapas), ("inactive_reasons", motivos)):
        valor = cfg.get(campo)
        if isinstance(valor, (list, tuple)):
            achadas += ["%s[%s]" % (campo, k) for k in valor if isinstance(k, str) and k not in conhecidas]
    return achadas


def avisar_chaves_fora_do_template(cfg):
    achadas = chaves_fora_do_template(cfg)
    if achadas:
        print("ATENCAO: settings.funnel cita chave(s) fora do template %s (o runtime ignora): %s"
              % (cfg.get("template"), ", ".join(achadas)))


def ler_textos_da_clinica(tenant_id):
    """Doc tenant-scoped system_settings/funnel (tela "Etapas": rotulos e
    textos que a clinica edita sem deploy) ou {}. So leitura: este script
    nunca grava nele."""
    from firestore_common import tenant_document
    snap = tenant_document(tenant_id, "system_settings", "funnel").get()
    dados = snap.to_dict() if snap.exists else None
    return dados if isinstance(dados, dict) else {}


def _mudancas_de_conteudo(args):
    return any((args.template, args.stage_label, args.reason_label, args.inactive_stage,
                args.active_stage, args.stale, args.intake_channel_types is not None))


def _ha_mudanca(args):
    return bool(args.enable or args.disable or _mudancas_de_conteudo(args))


def _so_desligar(args):
    # Kill-switch: --disable sozinho nunca depende do template estar valido.
    return bool(args.disable and not _mudancas_de_conteudo(args))


def validar_sintaxe(args):
    """Checagens que nao dependem do tenant (antes de qualquer leitura)."""
    if args.show and (_ha_mudanca(args) or args.yes):
        raise Recusa("--show so mostra; nao combine com opcoes de mudanca nem com --yes")
    if not args.show and not _ha_mudanca(args):
        raise Recusa("nada a fazer: use --show ou alguma opcao de mudanca (ver --help)")
    _pares(args.stage_label, "--stage-label")
    _pares(args.reason_label, "--reason-label")
    for chave in list(args.inactive_stage) + list(args.active_stage):
        if not _KEY_RE.match(chave or ""):
            raise Recusa("etapa invalida %r" % chave)
    ambas = sorted(set(args.inactive_stage) & set(args.active_stage))
    if ambas:
        raise Recusa("etapa em --inactive-stage e --active-stage ao mesmo tempo: %s" % ", ".join(ambas))
    for chave, valor in _pares(args.stale, "--stale"):
        _dias(valor, "--stale", chave)
    if args.intake_channel_types is not None:
        tipos = [t.strip() for t in args.intake_channel_types.split(",") if t.strip()]
        if not tipos:
            raise Recusa("--intake-channel-types vazio (o padrao do runtime e standard)")


def montar_config(atual, args):
    """Nova settings.funnel (sem version/updated_at/enabled_at) a partir da
    atual e dos argumentos. Puro: nenhuma leitura. Levanta Recusa."""
    atual = atual if isinstance(atual, dict) else {}
    cfg = copy.deepcopy(atual)
    nome = args.template or atual.get("template")
    if _so_desligar(args) and nome not in fc.TEMPLATES:
        # Template ausente/desconhecido ja e funil desligado no runtime; o
        # kill-switch so registra enabled=false, sem validar o resto.
        cfg["enabled"] = False
        return cfg
    if not nome:
        raise Recusa("tenant sem settings.funnel.template: informe --template (%s)"
                     % ", ".join(sorted(fc.TEMPLATES)))
    template = fc.TEMPLATES.get(nome)
    if template is None:
        raise Recusa("template %r nao existe neste codigo; informe --template (%s)"
                     % (nome, ", ".join(sorted(fc.TEMPLATES))))
    erros = fc.validate_template(nome, template)
    if erros:
        raise Recusa("template invalido: " + "; ".join(erros))
    cfg["template"] = nome
    etapas = {s["key"]: s for s in template["stages"]}
    motivos = {r["key"]: r for r in template["reasons"]}

    if args.enable:
        cfg["enabled"] = True
    elif args.disable:
        cfg["enabled"] = False
    else:
        cfg["enabled"] = atual.get("enabled") is True

    for campo, opcao, conhecidos, pares in (
            ("stage_labels", "--stage-label", etapas, args.stage_label),
            ("reason_labels", "--reason-label", motivos, args.reason_label)):
        mapa = dict(cfg[campo]) if isinstance(cfg.get(campo), dict) else {}
        for chave, valor in _pares(pares, opcao):
            if chave not in conhecidos:
                raise Recusa("%s: %r nao existe no template %s" % (opcao, chave, nome))
            valor = valor.strip()
            if not valor or valor == conhecidos[chave]["label"]:
                mapa.pop(chave, None)  # volta ao rotulo do template
                continue
            if len(valor) > fc.LABEL_MAX or _CONTROL_RE.search(valor):
                raise Recusa("%s %s: rotulo com ate %d caracteres e sem quebra de linha"
                             % (opcao, chave, fc.LABEL_MAX))
            mapa[chave] = valor
        if mapa or campo in atual:
            cfg[campo] = mapa

    inativas = {k for k in (cfg.get("inactive_stages") or []) if isinstance(k, str)}
    estruturais = etapas_estruturais(template)
    for chave in args.inactive_stage or []:
        if chave not in etapas:
            raise Recusa("--inactive-stage: %r nao existe no template %s" % (chave, nome))
        if chave in (fc.ENTRY_STAGE, fc.TRIAGE_STAGE):
            raise Recusa("--inactive-stage: %s e etapa reservada (entrada/triagem) e nunca fica inativa" % chave)
        if chave in estruturais:
            # Inativa, a conversao some do painel ou a automacao para em
            # silencio (auto_transition exige o destino ativo).
            raise Recusa("--inactive-stage: %s e etapa estrutural do template %s (%s) e nunca fica inativa"
                         % (chave, nome, ", ".join(estruturais[chave])))
        inativas.add(chave)
    for chave in args.active_stage or []:
        if chave not in etapas:
            raise Recusa("--active-stage: %r nao existe no template %s" % (chave, nome))
        inativas.discard(chave)
    if inativas or "inactive_stages" in atual:
        cfg["inactive_stages"] = sorted(inativas)

    limiares = dict(cfg["stale_days"]) if isinstance(cfg.get("stale_days"), dict) else {}
    for chave, valor in _pares(args.stale, "--stale"):
        etapa = etapas.get(chave)
        if etapa is None:
            raise Recusa("--stale: %r nao existe no template %s" % (chave, nome))
        regra = etapa.get("stale") or {}
        if regra.get("kind") not in (fc.STALE_PATIENT_SILENCE, fc.STALE_TIME_IN_STAGE):
            raise Recusa("--stale: a etapa %s nao tem limiar por dias no template" % chave)
        dias = _dias(valor, "--stale", chave)
        if dias is None:
            limiares.pop(chave, None)
        else:
            limiares[chave] = dias
    if limiares or "stale_days" in atual:
        cfg["stale_days"] = limiares

    if args.intake_channel_types is not None:
        conhecidos = _tipos_de_canal()
        tipos = []
        for tipo in (t.strip() for t in args.intake_channel_types.split(",")):
            if not tipo:
                continue
            if tipo not in conhecidos:
                raise Recusa("--intake-channel-types: tipo %r desconhecido (%s)" % (tipo, ", ".join(conhecidos)))
            if tipo not in tipos:
                tipos.append(tipo)
        cfg["intake_channel_types"] = tipos
    return cfg


def _versao(cfg):
    valor = (cfg or {}).get("version")
    return valor if isinstance(valor, int) and not isinstance(valor, bool) else 0


def com_contabilidade(atual, novo, agora):
    """version +1, updated_at agora, enabled_at so no 1o enable."""
    final = dict(novo)
    final["version"] = _versao(atual) + 1
    final["updated_at"] = agora
    if atual.get("enabled_at"):
        final["enabled_at"] = atual["enabled_at"]
    elif final.get("enabled") is True:
        final["enabled_at"] = agora
    return final


def _nucleo(cfg):
    return {k: v for k, v in (cfg or {}).items() if k not in _BOOKKEEPING}


def diff(atual, novo):
    """Linhas 'caminho: antes -> depois' (mapas abertos um nivel)."""
    linhas = []
    for chave in sorted(set(atual) | set(novo)):
        antes, depois = atual.get(chave, _AUSENTE), novo.get(chave, _AUSENTE)
        if isinstance(antes, dict) and isinstance(depois, dict):
            for sub in sorted(set(antes) | set(depois)):
                a, d = antes.get(sub, _AUSENTE), depois.get(sub, _AUSENTE)
                if a != d:
                    linhas.append("%s.%s: %s -> %s" % (chave, sub, _fmt(a), _fmt(d)))
        elif antes != depois:
            linhas.append("%s: %s -> %s" % (chave, _fmt(antes), _fmt(depois)))
    return linhas


def _contar(tenant_id, operador, valor):
    """count() de contatos por crm_stage (indice de campo unico)."""
    from google.cloud.firestore_v1.base_query import FieldFilter
    from firestore_common import tenant_collection
    consulta = tenant_collection(tenant_id, "wa_contacts").where(
        filter=FieldFilter(fc.F_STAGE, operador, valor))
    resultado = consulta.count(alias="n").get()
    return int(resultado[0][0].value)


def imprimir_catalogo(catalogo, ligado, textos=False):
    """Catalogo resolvido. `textos` = imprime tambem o texto explicativo de
    cada etapa (--show)."""
    print("\n=== catalogo resolvido: %s (%s), %s ===" % (
        catalogo["template"], catalogo["template_label"],
        "HABILITADO no tenant" if ligado else "DESLIGADO no tenant"))
    for etapa in catalogo["stages"]:
        regra = etapa.get("stale") or {}
        if regra.get("kind") == fc.STALE_TASK:
            parado = "parado: pela tarefa"
        elif regra.get("days"):
            parado = "parado: %s %s dia(s)" % (regra["kind"], regra["days"])
        else:
            parado = "parado: -"
        marcas = []
        if etapa.get("close_outcome"):
            marcas.append("desfecho do Encerrar")
        if etapa.get("legacy_qualification"):
            marcas.append("legado=%s" % etapa["legacy_qualification"])
        if etapa.get("visibility_permission"):
            marcas.append("so com %s" % etapa["visibility_permission"])
        print("  %3s %-18s %-30s %-9s %-8s %s%s" % (
            etapa["order"], etapa["key"], etapa["label"], etapa["kind"],
            "ativa" if etapa["active"] else "INATIVA", parado,
            " | " + ", ".join(marcas) if marcas else ""))
        if textos and etapa.get("description"):
            print("        %s" % etapa["description"])
    motivos = ["%s=%s%s" % (r["key"], r["label"], "" if r["active"] else " (inativo)")
               for r in catalogo["reasons"]]
    print("  motivos: " + "; ".join(motivos))
    automacoes = catalogo.get("automations") or {}
    if automacoes:
        print("  automacoes: " + "; ".join(
            "%s: %s -> %s" % (evento, ", ".join(regra.get("from") or []), regra.get("to"))
            for evento, regra in sorted(automacoes.items())))
    if catalogo.get("kpis"):
        print("  kpis: " + ", ".join("%s=%s" % par for par in sorted(catalogo["kpis"].items())))
    print("  entrada automatica (tipos de canal): " + ", ".join(catalogo["intake_channel_types"]))


def mostrar_textos_da_clinica(nome, textos):
    """Bloco do --show com os textos da tela Etapas (so leitura)."""
    print("\n=== textos da clinica (tela Etapas; system_settings/funnel) ===")
    mapas = {campo: textos.get(campo) for campo in ("stage_labels", "stage_descriptions", "reason_labels")
             if textos.get(campo)}
    if not mapas:
        print("  (nenhum: valem os rotulos de settings.funnel e os textos do template)")
        return
    print("  versao %s" % textos.get("version"))
    print(json.dumps(mapas, indent=2, ensure_ascii=False, sort_keys=True, default=_iso))
    try:
        fc.validate_overrides(nome, {campo: (textos.get(campo) if isinstance(textos.get(campo), dict) else {})
                                     for campo in ("stage_labels", "stage_descriptions", "reason_labels")})
    except fc.FunnelRuleError as exc:
        print("ATENCAO: textos da clinica fora da validacao (o runtime usa o padrao onde nao servem): %s"
              % exc.message)


def mostrar(tenant_id, atual):
    print("\n=== settings.funnel atual ===")
    if atual:
        print(json.dumps(atual, indent=2, ensure_ascii=False, sort_keys=True, default=_iso))
    else:
        print("  (ausente: funil desligado no tenant)")
    nome = atual.get("template")
    if nome not in fc.TEMPLATES:
        if nome:
            print("ATENCAO: template %r nao existe neste codigo (o runtime trata como desligado)." % nome)
        return
    avisar_chaves_fora_do_template(atual)
    textos = ler_textos_da_clinica(tenant_id)
    mostrar_textos_da_clinica(nome, textos)
    catalogo = fc.resolve_funnel(dict(atual, enabled=True), textos)
    if not catalogo:
        print("ATENCAO: settings.funnel nao resolve um catalogo (o runtime trata como desligado).")
        return
    imprimir_catalogo(catalogo, atual.get("enabled") is True, textos=True)
    print("\n=== contatos por etapa (count) ===")
    soma = 0
    for etapa in catalogo["stages"]:
        n = _contar(tenant_id, "==", etapa["key"])
        soma += n
        print("  %-18s %7d%s" % (etapa["key"], n, "" if etapa["active"] else "  (inativa)"))
    total = _contar(tenant_id, ">", "")
    print("  %-18s %7d" % ("com etapa (total)", total))
    if total > soma:
        print("  ATENCAO: %d contato(s) com etapa fora do template." % (total - soma))


def checar_inativas(tenant_id, atual, novo, permitir):
    novas = sorted(set(novo.get("inactive_stages") or []) - set(atual.get("inactive_stages") or []))
    bloqueadas = []
    for chave in novas:
        n = _contar(tenant_id, "==", chave)
        if n and not permitir:
            bloqueadas.append("%s=%d" % (chave, n))
        elif n:
            print("ATENCAO: etapa %s fica inativa com %d contato(s); a coluna segue no quadro enquanto "
                  "tiver contatos e ninguem consegue mover para ela." % (chave, n))
    if bloqueadas:
        raise Recusa("etapa(s) com contatos: %s. Mova os contatos antes ou use "
                     "--allow-inactive-with-contacts." % ", ".join(bloqueadas))


def checar_troca_de_template(tenant_id, atual, novo):
    antigo = atual.get("template")
    if not antigo or antigo == novo["template"]:
        return
    chaves = [s["key"] for s in fc.TEMPLATES[novo["template"]]["stages"]]
    total = _contar(tenant_id, ">", "")
    soma = sum(_contar(tenant_id, "==", chave) for chave in chaves)
    if total > soma:
        raise Recusa("troca de template %s -> %s: %d contato(s) ficariam em etapa que nao existe no "
                     "novo template" % (antigo, novo["template"], total - soma))
    print("troca de template %s -> %s: nenhum contato fica em etapa inexistente." % (antigo, novo["template"]))


def gravar(tenant_id, snapshot, final, agora):
    from google.api_core import exceptions as gex
    from firestore_common import get_firestore_client, tenant_doc_ref
    ref = tenant_doc_ref(tenant_id)
    opcao = get_firestore_client().write_option(last_update_time=snapshot.update_time)
    try:
        # Caminho "settings.funnel": substitui a subarvore inteira (nao e
        # merge profundo); o resto de settings (ai, branding) fica intacto.
        ref.update({"settings.funnel": final, "updated_at": agora}, option=opcao)
    except gex.FailedPrecondition:
        print("\nERRO: o doc do tenant mudou depois da leitura (gravacao em paralelo). "
              "Nada gravado; rode de novo.")
        return 1
    gravado = ((ref.get().to_dict() or {}).get("settings") or {}).get("funnel") or {}
    print("\nGravado: settings.funnel versao %s (%s). O cache de tenants atualiza em ate 60 s "
          "nas instancias do Cloud Run." % (
              gravado.get("version"), "habilitado" if gravado.get("enabled") is True else "desligado"))
    return 0


def executar(args):
    from firestore_common import tenant_doc_ref
    agora = _agora()
    snapshot = tenant_doc_ref(args.tenant).get()
    if not snapshot.exists:
        raise Recusa("tenant %r nao existe neste projeto/prefixo" % args.tenant)
    doc = snapshot.to_dict() or {}
    settings = doc.get("settings")
    if settings is not None and not isinstance(settings, dict):
        raise Recusa("settings do tenant nao e um mapa; corrija o doc antes")
    atual = (settings or {}).get("funnel")
    if atual is not None and not isinstance(atual, dict):
        raise Recusa("settings.funnel nao e um mapa; corrija o doc antes")
    atual = atual or {}
    if args.show:
        mostrar(args.tenant, atual)
        return 0
    if _so_desligar(args) and not atual:
        print("\nsettings.funnel ausente: o funil ja esta desligado no tenant. Nada a gravar.")
        return 0

    novo = montar_config(atual, args)
    checar_inativas(args.tenant, atual, novo, args.allow_inactive_with_contacts)
    checar_troca_de_template(args.tenant, atual, novo)
    if _nucleo(novo) == _nucleo(atual):
        print("\nSem mudancas em settings.funnel (versao %s). Nada a gravar." % _versao(atual))
        return 0
    final = com_contabilidade(atual, novo, agora)
    print("\n=== diff de settings.funnel ===")
    for linha in diff(atual, final):
        print("  " + linha)
    # Kill-switch (--disable sozinho) nao depende de nenhuma leitura extra.
    textos = {} if _so_desligar(args) else ler_textos_da_clinica(args.tenant)
    for campo, opcao, pares in (("stage_labels", "--stage-label", args.stage_label),
                                ("reason_labels", "--reason-label", args.reason_label)):
        da_clinica = textos.get(campo) if isinstance(textos.get(campo), dict) else {}
        sombreadas = sorted({chave for chave, _valor in _pares(pares, opcao)} & set(da_clinica))
        if sombreadas:
            print("ATENCAO: %s: a clinica ja renomeou %s na tela Etapas; o rotulo de settings.funnel "
                  "fica por baixo (a tela prevalece)." % (opcao, ", ".join(sombreadas)))
    avisar_chaves_fora_do_template(final)
    catalogo = fc.resolve_funnel(dict(final, enabled=True), textos)
    if catalogo:
        imprimir_catalogo(catalogo, final.get("enabled") is True)
    elif final.get("enabled") is True:
        raise Recusa("a config resultante nao resolve um catalogo (bug de validacao)")
    else:
        print("\n(catalogo nao resolvido: template ausente ou desconhecido; funil desligado)")
    if final.get("enabled") is True and atual.get("enabled") is not True:
        print("\nLembrete: o funil so aparece com FEATURE_FUNNEL=true no Cloud Run e indices READY. "
              "A entrada automatica liga junto; a migracao dos contatos antigos e "
              "scripts.classify_funnel_stage (dry-run primeiro).")
    if final.get("enabled") is not True and atual.get("enabled") is True:
        print("\nLembrete: desligar nao apaga etapas nem historico; rotas 404 e entrada "
              "automatica param em ate 60 s.")
    if not args.yes:
        print("\nDRY-RUN: nada gravado. Adicione --yes para aplicar.")
        return 0
    return gravar(args.tenant, snapshot, final, agora)


def _parser():
    p = argparse.ArgumentParser(
        prog="python -m scripts.set_tenant_funnel", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--tenant", required=True, type=_tenant, help="id do tenant (obrigatorio)")
    liga = p.add_mutually_exclusive_group()
    liga.add_argument("--enable", action="store_true", help="habilita o funil no tenant")
    liga.add_argument("--disable", action="store_true", help="desliga o funil no tenant (kill-switch)")
    p.add_argument("--template", choices=sorted(fc.TEMPLATES),
                   help="template de etapas e motivos (obrigatorio na 1a configuracao)")
    p.add_argument("--stage-label", action="append", default=[], metavar="ETAPA=ROTULO",
                   help="renomeia a etapa (vazio volta ao rotulo do template); repetivel")
    p.add_argument("--reason-label", action="append", default=[], metavar="MOTIVO=ROTULO",
                   help="renomeia o motivo (vazio volta ao rotulo do template); repetivel")
    p.add_argument("--inactive-stage", action="append", default=[], metavar="ETAPA",
                   help="desativa a etapa (recusa se tiver contatos); repetivel")
    p.add_argument("--allow-inactive-with-contacts", action="store_true",
                   help="permite desativar etapa que ainda tem contatos")
    p.add_argument("--active-stage", action="append", default=[], metavar="ETAPA",
                   help="reativa a etapa; repetivel")
    p.add_argument("--stale", action="append", default=[], metavar="ETAPA=DIAS|off|default",
                   help="limiar do selo parado em dias; off desliga; default volta ao template")
    p.add_argument("--intake-channel-types", metavar="TIPO[,TIPO]",
                   help="tipos de canal da entrada automatica (padrao do runtime: standard)")
    p.add_argument("--show", action="store_true", help="so mostra config, catalogo e contagens")
    p.add_argument("--yes", action="store_true", help="grava (padrao: dry-run)")
    return p


def main(argv=None):
    args = _parser().parse_args(argv)
    _stdout_seguro()
    try:
        validar_sintaxe(args)
    except Recusa as exc:
        print("RECUSADO: %s" % exc, file=sys.stderr)
        return 2
    ambiente = _ambiente()
    if ambiente is None:
        return 2
    projeto, prefixo = ambiente
    from firestore_common import collection_name
    if args.show:
        modo = "SO LEITURA (--show; escrita travada no cliente)"
    elif args.yes:
        modo = "GRAVACAO (--yes)"
    else:
        modo = "DRY-RUN (escrita travada no cliente)"
    print("=== set_tenant_funnel ===")
    print("projeto: %s" % projeto)
    print("prefixo: %s (doc: %s/%s)" % (prefixo or "(vazio)", collection_name("tenants"), args.tenant))
    print("tenant:  %s" % args.tenant)
    print("modo:    %s" % modo)
    if args.show or not args.yes:
        trava_escrita()
    try:
        return executar(args)
    except Recusa as exc:
        print("\nRECUSADO: %s" % exc)
        return 2
    except KeyboardInterrupt:
        print("\nABORTADO pelo operador.")
        return 2
    except Exception as exc:  # noqa: BLE001
        print("\nERRO: %s em %s." % (type(exc).__name__, _onde(exc)))
        return 1


if __name__ == "__main__":
    sys.exit(main())
