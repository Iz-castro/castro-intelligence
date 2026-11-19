import { useEffect, useRef, useState } from "react";
import { getJson, putJson } from "../../api";
import { useCrm } from "../../context/CrmContext";
import { WaText } from "../chat/WaText";
import { READ_ONLY_TOOLTIP } from "../Impersonation";

type Settings = {
  bot_reminder_enabled: boolean;
  bot_reminder_text_1: string;
  bot_reminder_text_2: string;
  bot_reminder_text_3: string;
  bot_reminder_lgpd_text_1: string;
  bot_reminder_lgpd_text_2: string;
  bot_reminder_lgpd_text_3: string;
  bot_reminder_minutes_1: number;
  bot_reminder_minutes_2: number;
  bot_reminder_closing_minutes: number;
};
type Payload = { settings: Settings; version: string; simulation: boolean };
// Serie B: depois do aceite da LGPD (aceita [Nome]; o ultimo sai com os botoes
// Continuar conversa / Encerrar conversa). Serie A: sem resposta ao aviso da LGPD
// (sai com os botoes Sim/Nao do aviso, sem nome). Mesmos horarios nas duas.
// Sem rodape de PARAR LEMBRETES desde 19/11 (o comando segue valendo).
const NAME_TOKEN = /[[{]\s*nome\s*[\]}]/i; // [Nome] ou {Nome}, como no backend
const NAME_EXAMPLE = "Maria";
const CLOSING_BUTTONS = ["Continuar conversa", "Encerrar conversa"];
const acceptedKeys = ["bot_reminder_text_1", "bot_reminder_text_2", "bot_reminder_text_3"] as const;
const noticeKeys = ["bot_reminder_lgpd_text_1", "bot_reminder_lgpd_text_2", "bot_reminder_lgpd_text_3"] as const;
type TextKey = typeof acceptedKeys[number] | typeof noticeKeys[number];
const textKeys: readonly TextKey[] = [...acceptedKeys, ...noticeKeys];

function duration(minutes: number) {
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  return hours ? `${hours} h${rest ? ` ${rest} min` : ""}` : `${rest} min`;
}

export function BotRemindersSettings() {
  const { bundle, readOnly, can } = useCrm();
  const [open, setOpen] = useState(false);
  const [loaded, setLoaded] = useState<Payload | null>(null);
  const [draft, setDraft] = useState<Settings | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const trigger = useRef<HTMLButtonElement>(null);
  const panel = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open || !bundle) return;
    const abort = new AbortController();
    setLoaded(null);
    setDraft(null);
    setError("");
    setNotice("");
    getJson<Payload>(bundle.auth, "/api/settings/bot-reminders", { signal: abort.signal })
      .then((result) => { if (!abort.signal.aborted) { setLoaded(result); setDraft(result.settings); } })
      .catch((reason: unknown) => { if (!abort.signal.aborted) setError(reason instanceof Error ? reason.message : "Não foi possível carregar os lembretes."); });
    panel.current?.focus();
    return () => abort.abort();
  }, [open, bundle]);

  function close() {
    if (busy) return;
    setOpen(false);
    trigger.current?.focus();
  }

  async function save() {
    if (!bundle || !draft || !loaded || readOnly || busy) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const result = await putJson<Payload>(bundle.auth, "/api/settings/bot-reminders", { settings: draft, version: loaded.version });
      setLoaded(result);
      setDraft(result.settings);
      setNotice("Lembretes salvos.");
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "Não foi possível salvar os lembretes.");
    } finally { setBusy(false); }
  }

  if (!can("gerenciar_config_sistema")) return null;
  const timings = draft ? [duration(draft.bot_reminder_minutes_1), duration(draft.bot_reminder_minutes_2), duration(draft.bot_reminder_closing_minutes)] : [];
  const dirty = !!draft && !!loaded && JSON.stringify(draft) !== JSON.stringify(loaded.settings);
  const empty = !!draft?.bot_reminder_enabled && textKeys.every((key) => !draft[key].trim());
  const nameInNotice = !!draft && noticeKeys.some((key) => NAME_TOKEN.test(draft[key]));
  const buttons = (labels: string[]) => <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 8 }}>{labels.map((label) => <span key={label} className="chip">{label}</span>)}</div>;
  const group = (d: Settings, keys: readonly TextKey[], notice: boolean) => keys.map((key, index) => <div className="settings-block" key={key} style={{ marginTop: "1rem" }}>
    <label htmlFor={key} style={{ display: "block", fontWeight: 600 }}>{index === 0 ? "Primeiro" : index === 1 ? "Segundo" : "Último"} lembrete · {timings[index]}</label>
    <p className="sub" style={{ fontSize: "0.8rem" }}>{index < 2 ? (notice ? "Depois do aviso da política de privacidade." : "Depois da resposta do assistente.") : "Depois da última mensagem do cliente, antes de terminar a janela de 24 horas."}</p>
    <textarea id={key} rows={4} maxLength={1000} value={d[key]} disabled={readOnly || busy} title={readOnly ? READ_ONLY_TOOLTIP : undefined}
      placeholder="Escreva a mensagem que será enviada ao cliente." style={{ width: "100%", resize: "vertical" }}
      onChange={(event) => setDraft({ ...d, [key]: event.target.value })} />
    <p className="sub" style={{ fontSize: "0.75rem" }}>{d[key].length}/1.000 caracteres · Campo vazio desativa esta etapa.</p>
    {d[key].trim() && <details><summary>Ver como fica no WhatsApp</summary><div className="settings-block" style={{ whiteSpace: "pre-wrap", padding: 12 }}>
      {notice
        ? <><WaText text={d[key]} />{buttons(["Sim", "Não"])}</>
        : <><WaText text={d[key].replace(new RegExp(NAME_TOKEN.source, "gi"), NAME_EXAMPLE)} />{index === 2 && buttons(CLOSING_BUTTONS)}</>}
      {!notice && NAME_TOKEN.test(d[key]) && <p className="sub" style={{ fontSize: "0.75rem", margin: "0.5rem 0 0" }}>Exemplo com o nome “{NAME_EXAMPLE}”. Sem nome cadastrado, o trecho com [Nome] é retirado.</p>}
    </div></details>}
  </div>);

  return <div className="settings-section" style={{ marginTop: "1.2rem" }}>
    <h3>Lembretes automáticos</h3>
    <p className="sub">Mensagens para quem parou de responder ao assistente virtual.</p>
    <button ref={trigger} type="button" className="ghost" onClick={() => setOpen(true)}>Configurar lembretes automáticos</button>
    {open && <div className="lightbox" role="dialog" aria-modal="true" aria-labelledby="reminder-title"
      onClick={(event) => { event.stopPropagation(); close(); }}
      onKeyDown={(event) => {
        event.stopPropagation();
        if (event.key === "Escape") close();
        if (event.key === "Tab") {
          const elements = panel.current?.querySelectorAll<HTMLElement>("button:not(:disabled), input:not(:disabled), textarea:not(:disabled), summary");
          if (!elements?.length) return;
          const first = elements[0], last = elements[elements.length - 1];
          if (event.shiftKey && (document.activeElement === first || document.activeElement === panel.current)) { event.preventDefault(); last.focus(); }
          else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
        }
      }}>
      <div ref={panel} tabIndex={-1} className="settings-modal" style={{ maxWidth: 640, width: "min(640px, 94vw)", maxHeight: "90vh", overflowY: "auto" }} onClick={(event) => event.stopPropagation()}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12 }}>
          <h2 id="reminder-title">Lembretes automáticos</h2>
          <button type="button" className="ghost" onClick={close} disabled={busy} aria-label="Fechar lembretes">Fechar</button>
        </div>
        <p className="sub">O assistente pode enviar até três lembretes enquanto espera uma resposta, em duas situações: depois do aceite da política de privacidade e quando o cliente não respondeu ao aviso da política. Uma mensagem nova cancela a sequência anterior. Despedidas, transferência para a equipe e envio do link de agendamento interrompem os lembretes.</p>
        <p className="sub">Os envios acontecem aproximadamente nos intervalos indicados, inclusive à noite e nos fins de semana, dentro da janela de atendimento do WhatsApp.</p>
        {error && <div className="alert" role="alert">{error}</div>}
        {notice && <p role="status">{notice}</p>}
        {!draft && !error && <p role="status">Carregando configuração…</p>}
        {draft && <>
          {loaded?.simulation && <p className="alert" role="status">Modo simulação: os lembretes são registrados para avaliação, sem enviar mensagens aos clientes.</p>}
          <label className="settings-toggle" style={{ margin: "1rem 0" }}>
            <input type="checkbox" checked={draft.bot_reminder_enabled} disabled={readOnly || busy} title={readOnly ? READ_ONLY_TOOLTIP : undefined}
              onChange={(event) => setDraft({ ...draft, bot_reminder_enabled: event.target.checked })} />
            <span>Ativar lembretes automáticos</span>
          </label>
          <h3 style={{ marginTop: "1.2rem" }}>Depois do aceite da política de privacidade</h3>
          <p className="sub">O cliente aceitou a política e parou de responder ao assistente. Escreva [Nome] onde quiser o primeiro nome do cliente. O último lembrete sai com os botões Continuar conversa e Encerrar conversa: Continuar devolve a conversa ao assistente; Encerrar encerra o atendimento, envia o protocolo e impede reabrir a conversa (em lote ou pela equipe) até o cliente escrever de novo.</p>
          {group(draft, acceptedKeys, false)}
          <h3 style={{ marginTop: "1.6rem" }}>Sem resposta ao aviso da política de privacidade</h3>
          <p className="sub">O cliente recebeu o aviso e não respondeu. Os lembretes saem com os botões Sim e Não do aviso: um toque em Sim registra o aceite. Quem recusou não recebe. Não use nome ([Nome]) nem dados do cliente, porque ele ainda não aceitou a política.</p>
          {group(draft, noticeKeys, true)}
          <p className="sub" style={{ fontSize: "0.8rem", marginTop: "1rem" }}>As mensagens não trazem instrução de parada. Se o cliente enviar PARAR LEMBRETES, deixa de recebê-los até enviar ATIVAR LEMBRETES.</p>
          <details style={{ margin: "1rem 0" }}><summary>Ajustar intervalos</summary>
            {(["bot_reminder_minutes_1", "bot_reminder_minutes_2"] as const).map((key, index) => <label key={key} style={{ display: "block", marginTop: 12 }}>
              {index === 0 ? "Primeiro" : "Segundo"} lembrete, em minutos após a resposta: <input type="number" min={10} step={1} value={draft[key]} disabled={readOnly || busy} style={{ width: 90 }} onChange={(event) => setDraft({ ...draft, [key]: Number(event.target.value) })} />
            </label>)}
            <label style={{ display: "block", marginTop: 12 }}>Último lembrete, minutos antes das 24 horas: <input type="number" min={15} step={1} value={1440 - draft.bot_reminder_closing_minutes} disabled={readOnly || busy} style={{ width: 90 }} onChange={(event) => setDraft({ ...draft, bot_reminder_closing_minutes: 1440 - Number(event.target.value) })} /></label>
            <p className="sub">Mínimo de 10 minutos para o primeiro e 60 minutos entre as etapas. O último precisa de pelo menos 15 minutos de antecedência. Os intervalos valem para as duas situações.</p>
          </details>
          {empty && <p role="alert">Preencha pelo menos uma mensagem antes de ativar.</p>}
          {nameInNotice && <p role="alert">Retire o [Nome] dos lembretes do aviso de privacidade: o cliente ainda não aceitou a política.</p>}
          <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 20 }}>
            <button type="button" className="ghost" onClick={close} disabled={busy}>Cancelar</button>
            <button type="button" className="primary" onClick={save} disabled={readOnly || busy || !dirty || empty || nameInNotice} title={readOnly ? READ_ONLY_TOOLTIP : undefined}>{busy ? "Salvando…" : "Salvar lembretes"}</button>
          </div>
        </>}
      </div>
    </div>}
  </div>;
}
