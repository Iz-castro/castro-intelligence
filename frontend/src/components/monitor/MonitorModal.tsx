// Monitor de atendimento (backend: monitor_service.py, rotas /api/admin/monitor/*).
//
// Porte da tela do painel local do Izael (painel.html, 13/10/2026) para dentro
// do CRM: mesmas secoes e na mesma ordem (fila de espera com alarme,
// indicadores, volume, atendimentos, tempo de resposta, equipamentos, origem,
// exportacao da auditoria), mesmas cores da Hub Loc e Chart.js — carregado SO
// quando o Monitor abre (import dinamico, fora do bundle principal). No fim,
// o conteudo do dashboard antigo (agregado diario, avaliacoes, CSV).
//
// Custo: a fila consulta a cada 30s SO com o Monitor aberto (cache de 20s no
// backend, dezenas de docs); as metricas so carregam ao abrir, ao trocar o
// periodo e no "Atualizar" (cache de 10 min no backend).

import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent, type ReactNode } from "react";
import type { Chart, ChartConfiguration } from "chart.js";
import { useCrm } from "../../context/CrmContext";
import { getJson } from "../../api";
import { errorText } from "../../utils/errors";
import { playBeep } from "../../utils/audio";

// ---------------------------------------------------------------------------
// Tipos (espelham o payload de monitor_service.py)
// ---------------------------------------------------------------------------

type Alerta = {
  chave: string;
  contato: number;
  fila: string;
  minutos: number;
  desde: string;
  handoff_em: string;
  responsavel: string | null;
  protocolo: string | null;
  mensagens_apos_fila: number;
  previa: string;
};

type Fila = {
  dentro_do_expediente: boolean;
  expediente: string;
  limite_min: number;
  agora: string;
  alertas: Alerta[];
};

type OrigemResumo = {
  rotulo: string;
  confianca: string;
  protocolos: number;
  na_fila: number;
  com_humano: number;
  primeira_resposta_mediana_min: number | null;
};

type Origem = {
  versao_regra: string;
  total: number;
  fora_da_janela: number;
  continuacoes: number;
  resumo: Record<string, OrigemResumo>;
  por_dia: Record<string, Record<string, number>>;
  por_canal: Record<string, Record<string, number>>;
  indeterminadas_recorrentes: { texto: string; protocolos: number }[];
};

type Dados = {
  total_atendimentos: number;
  total_mensagens: number;
  atendimentos_por_operador: Record<string, number>;
  resposta_mediana_min: Record<string, number>;
  resposta_media_min: Record<string, number>;
  primeira_resposta_mediana_min: Record<string, number>;
  volume_por_dia: Record<string, number>;
  entrada_por_dia: Record<string, number>;
  volume_por_canal: Record<string, number>;
  equipamentos: { termo: string; ocorrencias: number; conversas: number }[];
  origem: Origem | null;
};

type Metricas = {
  dias: number;
  truncado: boolean;
  dados: Dados;
  mensagens_lidas: number;
  extraido_em: string;
  rotulo: string;
  origem_ativa: boolean;
  exportar_auditoria: boolean;
};

// ---------------------------------------------------------------------------
// Cores (Hub Loc) e Chart.js sob demanda
// ---------------------------------------------------------------------------

const COR_CLARO = { azul: "#10327E", vermelho: "#FF4230", neutro: "#7A8497" };
const COR_ESCURO = { azul: "#6E95F5", vermelho: "#FF6B5C", neutro: "#9AA3B5" };

type Paleta = typeof COR_CLARO;

function corOrigem(p: Paleta, chave: string) {
  return ({ site: p.azul, meta: p.vermelho, indeterminada: p.neutro } as Record<string, string>)[chave] || p.neutro;
}

type ChartLib = typeof import("chart.js");
let chartLib: Promise<ChartLib> | null = null;

function carregarChart(): Promise<ChartLib> {
  if (!chartLib) {
    chartLib = import("chart.js").then((m) => {
      m.Chart.register(...m.registerables);
      return m;
    });
  }
  return chartLib;
}

function corDoTema(variavel: string, padrao: string) {
  const v = getComputedStyle(document.documentElement).getPropertyValue(variavel).trim();
  return v || padrao;
}

function Grafico({ config, altura = 260 }: { config: ChartConfiguration; altura?: number }) {
  const ref = useRef<HTMLCanvasElement | null>(null);
  useEffect(() => {
    let grafico: Chart | null = null;
    let cancelado = false;
    void carregarChart().then(({ Chart: ChartCtor }) => {
      if (cancelado || !ref.current) return;
      ChartCtor.defaults.font.family = '"Space Grotesk", system-ui, sans-serif';
      ChartCtor.defaults.color = corDoTema("--muted", "#7d6958");
      ChartCtor.defaults.plugins.legend.labels.boxWidth = 12;
      ChartCtor.defaults.plugins.legend.labels.boxHeight = 12;
      ChartCtor.defaults.maintainAspectRatio = false;
      grafico = new ChartCtor(ref.current, config);
    });
    return () => {
      cancelado = true;
      grafico?.destroy();
    };
  }, [config]);
  return (
    <div className="monitor-grafico" style={{ height: altura }}>
      <canvas ref={ref} />
    </div>
  );
}

type Serie = { nome: string; valores: number[]; cor: string };

function eixos(horizontal: boolean, empilhado: boolean) {
  const grade = corDoTema("--border", "rgba(0,0,0,0.1)");
  const valor = { beginAtZero: true, stacked: empilhado, grid: { color: grade }, border: { display: false }, ticks: { precision: 0 } };
  const categoria = { stacked: empilhado, grid: { display: false } };
  return horizontal ? { x: valor, y: categoria } : { x: categoria, y: valor };
}

function barras(rotulos: string[], series: Serie[], opts: { horizontal?: boolean; empilhado?: boolean; unidade?: string } = {}): ChartConfiguration {
  const { horizontal = false, empilhado = false, unidade = "" } = opts;
  return {
    type: "bar",
    data: {
      labels: rotulos,
      datasets: series.map((s) => ({
        label: s.nome, data: s.valores, backgroundColor: s.cor,
        borderRadius: empilhado ? 0 : 4, maxBarThickness: 28,
      })),
    },
    options: {
      indexAxis: horizontal ? "y" : "x",
      scales: eixos(horizontal, empilhado),
      plugins: {
        legend: { display: series.length > 1, position: "top", align: "start" },
        tooltip: { callbacks: { label: (c) => `${c.dataset.label}: ${c.formattedValue}${unidade}` } },
      },
    },
  };
}

function linhas(rotulos: string[], series: Serie[]): ChartConfiguration {
  return {
    type: "line",
    data: {
      labels: rotulos,
      datasets: series.map((s) => ({
        label: s.nome, data: s.valores, borderColor: s.cor, backgroundColor: s.cor,
        borderWidth: 2, pointRadius: 3, pointHoverRadius: 5, tension: 0.25,
      })),
    },
    options: {
      scales: eixos(false, false),
      interaction: { mode: "index", intersect: false },
      plugins: { legend: { position: "top", align: "start" } },
    },
  };
}

// ---------------------------------------------------------------------------
// Utilitarios
// ---------------------------------------------------------------------------

/** "2026-10-01" -> "01/10" */
function rotuloDia(iso: string) {
  const [, m, d] = iso.split("-");
  return d && m ? `${d}/${m}` : iso;
}

function pct(a: number, b: number) {
  return b ? `${Math.round((100 * a) / b)}%` : "–";
}

function hojeIso(deslocamentoDias = 0) {
  const d = new Date(Date.now() + deslocamentoDias * 864e5);
  return new Date(d.getTime() - d.getTimezoneOffset() * 6e4).toISOString().slice(0, 10);
}

function bipeDuplo() {
  playBeep({ type: "square", freq: 880, gain: 0.18, duration: 0.42, steps: [{ freq: 660, at: 0.22 }] });
}

// ---------------------------------------------------------------------------
// Componente
// ---------------------------------------------------------------------------

export function MonitorModal({ dashboard }: { dashboard?: ReactNode }) {
  const { bundle, setShowSettings, operators, theme } = useCrm();
  const paleta = theme === "dark" ? COR_ESCURO : COR_CLARO;
  const [dias, setDias] = useState(14);
  const [metricas, setMetricas] = useState<Metricas | null>(null);
  const [carregando, setCarregando] = useState(false);
  const [erroMetricas, setErroMetricas] = useState("");
  const [fila, setFila] = useState<Fila | null>(null);
  const [erroFila, setErroFila] = useState("");
  const [somLigado, setSomLigado] = useState(false);
  const [silenciados, setSilenciados] = useState<Set<string>>(() => new Set());

  // -- fila (alarme) --
  const atualizarFila = useCallback(async () => {
    if (!bundle) return;
    try {
      setFila(await getJson<Fila>(bundle.auth, "/api/admin/monitor/fila"));
      setErroFila("");
    } catch (e) {
      setErroFila(errorText(e));
    }
  }, [bundle]);

  useEffect(() => {
    void atualizarFila();
    const id = window.setInterval(() => void atualizarFila(), 30000);
    return () => window.clearInterval(id);
  }, [atualizarFila]);

  const ativos = useMemo(
    () => (fila?.dentro_do_expediente ? fila.alertas.filter((a) => !silenciados.has(a.chave)) : []),
    [fila, silenciados],
  );

  useEffect(() => {
    if (!somLigado || ativos.length === 0) return;
    bipeDuplo();
    const id = window.setInterval(bipeDuplo, 2500);
    return () => window.clearInterval(id);
  }, [somLigado, ativos.length]);

  // -- metricas --
  const carregarMetricas = useCallback(async (refresh: boolean) => {
    if (!bundle) return;
    setCarregando(true);
    try {
      setMetricas(await getJson<Metricas>(bundle.auth, `/api/admin/monitor/metricas?dias=${dias}${refresh ? "&refresh=true" : ""}`));
      setErroMetricas("");
    } catch (e) {
      setErroMetricas(errorText(e));
    } finally {
      setCarregando(false);
    }
  }, [bundle, dias]);

  useEffect(() => { void carregarMetricas(false); }, [carregarMetricas]);

  const fechar = () => setShowSettings(false);

  return (
    <div className="lightbox" role="dialog" aria-modal="true" aria-label="Monitor de atendimento" onClick={fechar}>
      <button type="button" className="lightbox-close" onClick={fechar} aria-label="Fechar">Fechar</button>
      <div className="settings-modal monitor-modal" onClick={(e) => e.stopPropagation()}>
        <header className="monitor-cabecalho">
          <h2>Monitor de atendimento<small>{metricas?.rotulo || ""}</small></h2>
          <div className="monitor-espaco" />
          <label className="monitor-rotulo">
            Período{" "}
            <select value={dias} onChange={(e) => setDias(Number(e.target.value))}>
              <option value={7}>7 dias</option>
              <option value={14}>14 dias</option>
              <option value={30}>30 dias</option>
            </select>
          </label>
          <button type="button" className="ghost" disabled={carregando}
            onClick={() => { void carregarMetricas(true); void atualizarFila(); }}>
            {carregando ? "Atualizando…" : "Atualizar"}
          </button>
          <button type="button" className={somLigado ? "ghost" : "monitor-btn-som"}
            onClick={() => { setSomLigado(true); bipeDuplo(); }}>
            {somLigado ? "Som do alarme ligado" : "Ativar som do alarme"}
          </button>
          <span className="monitor-relogio">{fila?.agora || "--:--:--"}</span>
        </header>

        {metricas?.truncado ? (
          <div className="monitor-aviso">A consulta bateu no teto de mensagens: o período mostrado está incompleto. Reduza o período.</div>
        ) : null}
        {erroMetricas ? <div className="monitor-aviso">Falha ao ler métricas: {erroMetricas}</div> : null}

        <div className="monitor-grade">
          <FilaDeEspera fila={fila} erro={erroFila} silenciados={silenciados}
            silenciar={(chave) => setSilenciados((s) => new Set(s).add(chave))} ativos={ativos.length} />

          {metricas ? <Comercial m={metricas} paleta={paleta} /> : carregando ? <p className="sub monitor-cheio">Carregando métricas…</p> : null}

          {metricas?.exportar_auditoria ? <Auditoria operators={operators} /> : null}

          {dashboard ? (
            <section className="monitor-cartao monitor-cheio">
              <h3>Resumo diário e avaliações</h3>
              <p className="sub">Agregado diário do dashboard anterior (o mesmo que a supervisão vê).</p>
              {dashboard}
            </section>
          ) : null}
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Fila de espera
// ---------------------------------------------------------------------------

function FilaDeEspera({ fila, erro, silenciados, silenciar, ativos }: {
  fila: Fila | null; erro: string; silenciados: Set<string>; silenciar: (chave: string) => void; ativos: number;
}) {
  const limite = fila?.limite_min ?? 5;
  return (
    <section className={`monitor-cartao monitor-cheio monitor-fila${ativos > 0 ? " alerta" : ""}`} aria-live="polite">
      <h3>Fila de espera — sem resposta humana há mais de {limite} min</h3>
      <p className="sub">
        Só entra quem o bot encaminhou para a fila do Comercial depois do aceite de LGPD. O tempo conta a partir
        do encaminhamento (ou da abertura, se chegou com a loja fechada) e só para com resposta de uma pessoa, em
        qualquer número. Alarme ativo {fila?.expediente ? `de ${fila.expediente}` : "no horário comercial"}.
      </p>
      {erro ? <div className="vazio">Falha ao ler a fila: {erro}</div>
        : !fila ? <div className="vazio">Carregando…</div>
        : !fila.dentro_do_expediente ? <div className="vazio">Fora do expediente. Alarme em pausa.</div>
        : fila.alertas.length === 0 ? <div className="vazio">Ninguém esperando na fila além do limite.</div>
        : fila.alertas.map((a) => {
          const mudo = silenciados.has(a.chave);
          return (
            <div key={a.chave} className={`monitor-alerta${mudo ? " silenciado" : ""}`}>
              <div className="monitor-min">{Math.floor(a.minutos)}<small>min na fila</small></div>
              <div style={{ minWidth: 0 }}>
                <div className="monitor-meta">
                  Protocolo {a.protocolo || "–"} · Cliente {a.contato} · desde {a.desde}{a.fila ? ` · fila ${a.fila}` : ""}
                </div>
                <div>
                  {a.responsavel ? <span className="monitor-etiqueta">assumido por {a.responsavel}</span> : null}
                  {a.mensagens_apos_fila ? <span className="monitor-etiqueta quente">cliente mandou {a.mensagens_apos_fila} msg depois</span> : null}
                </div>
                {a.previa ? <div className="monitor-previa">{a.previa}</div> : null}
              </div>
              <button type="button" className="ghost" disabled={mudo} onClick={() => silenciar(a.chave)}>Silenciar</button>
            </div>
          );
        })}
    </section>
  );
}

// ---------------------------------------------------------------------------
// Indicadores, graficos e origem
// ---------------------------------------------------------------------------

function Comercial({ m, paleta }: { m: Metricas; paleta: Paleta }) {
  const d = m.dados;
  const o = d.origem;
  const tot = o ? o.total : 0;
  const naFila = o ? Object.values(o.resumo).reduce((s, r) => s + r.na_fila, 0) : 0;
  const comHumano = o ? Object.values(o.resumo).reduce((s, r) => s + r.com_humano, 0) : 0;

  const cfgVolume = useMemo(() => {
    const dias = Object.keys(d.volume_por_dia);
    return linhas(dias.map(rotuloDia), [
      { nome: "Mensagens", valores: dias.map((k) => d.volume_por_dia[k] || 0), cor: paleta.azul },
      { nome: "Do cliente", valores: dias.map((k) => d.entrada_por_dia[k] || 0), cor: paleta.vermelho },
    ]);
  }, [d, paleta]);

  const cfgAtend = useMemo(() => {
    const ops = Object.keys(d.atendimentos_por_operador);
    return barras(ops, [{ nome: "Atendimentos", valores: ops.map((k) => d.atendimentos_por_operador[k]), cor: paleta.azul }], { horizontal: true });
  }, [d, paleta]);

  const cfgTempo = useMemo(() => {
    const ops = Object.keys(d.resposta_mediana_min);
    return barras(ops, [
      { nome: "Mediana", valores: ops.map((k) => d.resposta_mediana_min[k]), cor: paleta.azul },
      { nome: "Média", valores: ops.map((k) => d.resposta_media_min[k]), cor: paleta.vermelho },
    ], { unidade: " min" });
  }, [d, paleta]);

  const cfgEquip = useMemo(() => barras(
    d.equipamentos.map((e) => e.termo),
    [{ nome: "Conversas", valores: d.equipamentos.map((e) => e.conversas), cor: paleta.azul }],
    { horizontal: true, unidade: " conversas" },
  ), [d, paleta]);

  const chavesOrigem = useMemo(
    () => (o ? Object.keys(o.resumo).filter((k) => o.resumo[k].protocolos > 0 || ["site", "meta", "indeterminada"].includes(k)) : []),
    [o],
  );

  const cfgOrigem = useMemo(() => {
    if (!o) return null;
    const diasO = Object.keys(o.por_dia);
    return barras(diasO.map(rotuloDia), chavesOrigem.map((k) => ({
      nome: o.resumo[k].rotulo, valores: diasO.map((dd) => o.por_dia[dd][k] || 0), cor: corOrigem(paleta, k),
    })), { empilhado: true, unidade: " protocolos" });
  }, [o, chavesOrigem, paleta]);

  const nota: string[] = [];
  if (o) {
    nota.push(`Regra ${o.versao_regra}.`);
    if (o.continuacoes) nota.push(`${o.continuacoes} protocolos de cliente que voltou sem marcador ficaram fora (continuação de atendimento, não lead novo).`);
    if (o.fora_da_janela) nota.push(`${o.fora_da_janela} protocolos abertos antes do período ficaram fora.`);
    nota.push("A origem do anúncio (referral da Meta) ainda não é gravada pelo CRM: por enquanto só a regra de texto.");
  }

  return (
    <>
      <div className="monitor-kpis monitor-cheio">
        {([
          [d.total_atendimentos, "conversas no período"],
          [d.total_mensagens, "mensagens"],
          [tot || "–", "protocolos novos (origem)"],
          [pct(naFila, tot), "chegaram à fila do bot"],
          [pct(comHumano, tot), "tiveram resposta humana"],
        ] as [string | number, string][]).map(([valor, rotulo]) => (
          <div key={rotulo} className="monitor-kpi"><b>{valor}</b><span>{rotulo}</span></div>
        ))}
      </div>

      <section className="monitor-cartao monitor-meio">
        <h3>Volume por dia</h3>
        <p className="sub">Mensagens trocadas e mensagens que o cliente mandou.</p>
        <Grafico config={cfgVolume} />
      </section>
      <section className="monitor-cartao monitor-meio">
        <h3>Atendimentos por atendente</h3>
        <p className="sub">Conversas em que a pessoa respondeu pelo menos uma vez.</p>
        <Grafico config={cfgAtend} />
      </section>

      <section className="monitor-cartao monitor-meio">
        <h3>Tempo de resposta por atendente</h3>
        <p className="sub">Minutos entre a mensagem do cliente e a resposta humana. A média sobe com conversa que dorme de um dia para o outro; a mediana, não.</p>
        <Grafico config={cfgTempo} />
      </section>
      {d.equipamentos.length ? (
        <section className="monitor-cartao monitor-meio">
          <h3>Equipamentos mais citados pelo cliente</h3>
          <p className="sub">Por número de conversas distintas. Sem as respostas do aceite de LGPD e sem o texto fixo dos templates de entrada.</p>
          <Grafico config={cfgEquip} altura={340} />
        </section>
      ) : null}

      {o && cfgOrigem ? (
        <section className="monitor-cartao monitor-cheio">
          <h3>Origem dos atendimentos</h3>
          <p className="sub">{o.total} protocolos no período, classificados pela primeira mensagem do cliente.</p>
          <Grafico config={cfgOrigem} />
          <div style={{ overflowX: "auto", marginTop: 14 }}>
            <table className="monitor-tabela">
              <thead>
                <tr>
                  <th>Origem</th><th>Critério</th><th className="num">Protocolos</th><th className="num">% do total</th>
                  <th className="num">Chegaram à fila</th><th className="num">Resposta humana</th><th className="num">1ª resposta (mediana)</th>
                </tr>
              </thead>
              <tbody>
                {chavesOrigem.map((k) => {
                  const r = o.resumo[k];
                  return (
                    <tr key={k}>
                      <td><span className="monitor-ponto" style={{ background: corOrigem(paleta, k) }} />{r.rotulo}</td>
                      <td>{r.confianca}</td>
                      <td className="num">{r.protocolos}</td>
                      <td className="num">{pct(r.protocolos, o.total)}</td>
                      <td className="num">{r.na_fila}</td>
                      <td className="num">{r.com_humano} ({pct(r.com_humano, r.protocolos)})</td>
                      <td className="num">{r.primeira_resposta_mediana_min == null ? "–" : `${r.primeira_resposta_mediana_min} min`}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <div className="monitor-duas-colunas">
            <div>
              <h4>Por canal de entrada</h4>
              <div style={{ overflowX: "auto" }}>
                <table className="monitor-tabela">
                  <thead><tr><th>Canal</th>{chavesOrigem.map((k) => <th key={k} className="num">{o.resumo[k].rotulo}</th>)}</tr></thead>
                  <tbody>
                    {Object.keys(o.por_canal).map((c) => (
                      <tr key={c}><td>{c}</td>{chavesOrigem.map((k) => <td key={k} className="num">{o.por_canal[c][k] || 0}</td>)}</tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
            <div>
              <h4>Aberturas sem marcador que se repetem</h4>
              <p className="sub">Candidatas a regra nova quando uma campanha usar texto próprio.</p>
              <ul className="monitor-lista">
                {o.indeterminadas_recorrentes.length
                  ? o.indeterminadas_recorrentes.map((i) => <li key={i.texto}>“{i.texto}” — {i.protocolos} protocolos</li>)
                  : <li>Nenhuma abertura repetida.</li>}
              </ul>
            </div>
          </div>
          <p className="monitor-nota">{nota.join(" ")}</p>
        </section>
      ) : null}

      <p className="monitor-nota monitor-cheio">
        Extraído em {m.extraido_em} · {m.mensagens_lidas} mensagens lidas · os números ficam guardados por 10 minutos; “Atualizar” recalcula.
      </p>
    </>
  );
}

// ---------------------------------------------------------------------------
// Auditoria por atendente (download .txt, registrado na auditoria do tenant)
// ---------------------------------------------------------------------------

function Auditoria({ operators }: { operators: { id: number; display_name?: string }[] }) {
  const { bundle } = useCrm();
  const lista = useMemo(
    () => [...operators].sort((a, b) => String(a.display_name || "").localeCompare(String(b.display_name || ""))),
    [operators],
  );
  const [op, setOp] = useState<number | "">("");
  const [inicio, setInicio] = useState(() => hojeIso(-6));
  const [fim, setFim] = useState(() => hojeIso());
  const [estado, setEstado] = useState("");
  const [baixando, setBaixando] = useState(false);

  const baixar = async (ev: FormEvent) => {
    ev.preventDefault();
    if (!bundle || op === "") return;
    setBaixando(true);
    setEstado("Gerando…");
    try {
      const token = await bundle.auth.currentUser?.getIdToken();
      const resp = await fetch(`/api/admin/monitor/auditoria?operador_id=${op}&inicio=${inicio}&fim=${fim}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!resp.ok) {
        const corpo = await resp.json().catch(() => ({}));
        throw new Error(corpo.detail || `Erro ${resp.status}`);
      }
      const nome = /filename="([^"]+)"/.exec(resp.headers.get("Content-Disposition") || "")?.[1] || "auditoria.txt";
      const url = URL.createObjectURL(await resp.blob());
      const a = document.createElement("a");
      a.href = url; a.download = nome; a.click();
      URL.revokeObjectURL(url);
      setEstado(`${resp.headers.get("X-Conversas") || "0"} conversas. Arquivo ${nome} baixado.`);
    } catch (e) {
      setEstado(errorText(e));
    } finally {
      setBaixando(false);
    }
  };

  return (
    <section className="monitor-cartao monitor-cheio">
      <h3>Exportar auditoria por atendente</h3>
      <p className="sub">
        Arquivo .txt com as conversas em que a pessoa respondeu no período, cliente anonimizado (sem nome e telefone)
        e protocolo preservado. Até 31 dias por vez. Cada exportação fica registrada na auditoria da empresa.
      </p>
      <form className="monitor-form" onSubmit={(ev) => void baixar(ev)}>
        <label>Atendente
          <select value={op} required onChange={(e) => setOp(e.target.value ? Number(e.target.value) : "")}>
            <option value="">Escolha…</option>
            {lista.map((o) => <option key={o.id} value={o.id}>{o.display_name || `operador ${o.id}`}</option>)}
          </select>
        </label>
        <label>De <input type="date" value={inicio} max={fim} required onChange={(e) => setInicio(e.target.value)} /></label>
        <label>Até <input type="date" value={fim} min={inicio} required onChange={(e) => setFim(e.target.value)} /></label>
        <button type="submit" className="primary" disabled={baixando || op === ""}>Baixar arquivo</button>
      </form>
      {estado ? <p className="monitor-nota">{estado}</p> : null}
    </section>
  );
}
