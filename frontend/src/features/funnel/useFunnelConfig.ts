import { useCallback, useEffect, useState } from "react";
import type { Auth } from "firebase/auth";
import { loadFunnelConfig } from "./api";
import { funnelErrorMessage, isAccessLost } from "./errors";
import { catalogWithSettings } from "./settingsForm";
import type { FunnelConfig, FunnelSettings } from "./types";

// Disponibilidade do funil na UI. PURA: nada do funil faz request quando
// e falso (Ver como, flag global, tenant sem funil, perfil sem ver_funil).
// Vale para o quadro, o cartao da etapa, o drawer e as rotas que exigem
// ver_funil.
export function funnelAvailable(input: { readOnly: boolean; featureFunnel?: boolean | null; funnelEnabled: boolean; canView: boolean }): boolean {
  return !input.readOnly && input.featureFunnel === true && input.funnelEnabled === true && input.canView === true;
}

// Disponibilidade do CATALOGO (GET /config): desfechos do "Encerrar
// atendimento" e o que depende dele (gate do menu, chip e filtro com
// etapas, cartao Qualificacao escondido). Decisao do PO: quem fecha
// atendimento recebe o catalogo mesmo sem ver_funil (o backend aceita o
// /config com ver_funil OU fechar_atendimento_manual). PURA, como acima.
export function funnelCatalogAvailable(input: { readOnly: boolean; featureFunnel?: boolean | null; funnelEnabled: boolean; canView: boolean; canClose: boolean }): boolean {
  return funnelAvailable({ ...input, canView: input.canView === true || input.canClose === true });
}

// 1 GET /config por sessao: cache de UM slot, chaveado pela identidade e
// pelos toggles que mudam as capacidades (uid, cargo, permissoes). Trocar de
// usuario ou de perfil troca a chave e descarta o anterior; erro nao fica
// em cache (proxima montagem tenta de novo).
type Slot = { key: string; promise: Promise<FunnelConfig>; value: FunnelConfig | null };
let slot: Slot | null = null;
// Consumidores montados (cartao, quadro, barra lateral, encerramento): a
// invalidacao (textos salvos na aba "Etapas", "Tentar novamente") faz TODOS
// buscarem de novo, com um GET so (mesma chave = mesmo slot novo). Um GET
// que da certo tambem avisa quem usa a MESMA chave: consumidor que ficou em
// erro (ex.: 503 no boot) pega o valor do cache, sem GET novo e sem
// recarregar a pagina. `key` undefined = todos (invalidacao).
const listeners = new Set<(key?: string) => void>();

function notifyListeners(key?: string): void {
  for (const listener of [...listeners]) listener(key);
}
// Textos que ESTA sessao acabou de salvar na aba "Etapas" (resposta do PUT),
// valendo sobre o /config enquanto ele vier com overrides_version menor (o
// backend tem cache de 30 s por instancia). Some quando o /config alcanca a
// versao, ao trocar de identidade ou quando o funil fica indisponivel.
let savedTexts: { key: string; settings: FunnelSettings } | null = null;
const overlaid = new WeakMap<FunnelConfig, { settings: FunnelSettings; result: FunnelConfig }>();

export function resetFunnelConfigCache(): void {
  slot = null;
  savedTexts = null;
}

// `saved` = resposta do PUT /settings (textos novos ja valem na tela, mesmo
// que o proximo /config venha de uma instancia com o cache antigo).
export function invalidateFunnelConfig(saved?: FunnelSettings | null): void {
  if (saved && slot) savedTexts = { key: slot.key, settings: saved };
  slot = null;
  notifyListeners();
}

function overrideVersion(config: FunnelConfig): number {
  const value = config?.catalog?.overrides_version;
  return Number.isInteger(value) ? Number(value) : 0;
}

// Identidade estavel (WeakMap): o mesmo config com os mesmos textos devolve
// o MESMO objeto, sem disparar efeitos/memos dos consumidores a cada render.
export function withSavedTexts(config: FunnelConfig | null, key: string): FunnelConfig | null {
  const pending = savedTexts;
  if (!config || !pending || pending.key !== key || !config.catalog) return config;
  const cached = overlaid.get(config);
  if (cached && cached.settings === pending.settings) return cached.result;
  const catalog = catalogWithSettings(config.catalog, pending.settings);
  const result = catalog === config.catalog ? config : { ...config, catalog };
  overlaid.set(config, { settings: pending.settings, result });
  return result;
}

function cachedConfig(auth: Auth, key: string): Slot {
  if (slot?.key === key) return slot;
  const entry: Slot = { key, promise: loadFunnelConfig(auth), value: null };
  slot = entry;
  entry.promise.then((value) => {
    // O servidor alcancou os textos salvos: o overlay nao e mais preciso.
    if (savedTexts && savedTexts.key === key && overrideVersion(value) >= savedTexts.settings.version) savedTexts = null;
    if (slot !== entry) return;
    entry.value = value;
    // Recupera quem ficou em erro com esta chave (o slot agora tem valor).
    notifyListeners(key);
  }, () => { if (slot === entry) slot = null; });
  return entry;
}

export type FunnelConfigState = { config: FunnelConfig | null; error: string; accessLost: boolean; loading: boolean; reload: () => void };

export function useFunnelConfig(auth: Auth | null | undefined, available: boolean, accessKey: string): FunnelConfigState {
  const [state, setState] = useState<{ key: string; config: FunnelConfig | null; error: string; accessLost: boolean }>({ key: "", config: null, error: "", accessLost: false });
  const [nonce, setNonce] = useState(0);
  const reload = useCallback(() => invalidateFunnelConfig(), []);

  useEffect(() => {
    const listener = (key?: string) => { if (key === undefined || key === accessKey) setNonce((value) => value + 1); };
    listeners.add(listener);
    return () => { listeners.delete(listener); };
  }, [accessKey]);

  // Ficar indisponivel (Ver como, flag, tenant, perfil) descarta o cache.
  // Efeito proprio: o aviso de um GET bem-sucedido (nonce) nunca descarta.
  useEffect(() => {
    if (!available) { slot = null; savedTexts = null; }
  }, [available]);

  useEffect(() => {
    if (!auth || !available) { setState({ key: "", config: null, error: "", accessLost: false }); return; }
    const entry = cachedConfig(auth, accessKey);
    if (entry.value) { setState({ key: accessKey, config: entry.value, error: "", accessLost: false }); return; }
    let cancelled = false;
    // Recarga (invalidacao) mantem o catalogo anterior na tela ate o novo chegar.
    setState((current) => current.key === accessKey && current.config ? current : { key: accessKey, config: null, error: "", accessLost: false });
    entry.promise.then((config) => {
      if (!cancelled) setState({ key: accessKey, config, error: "", accessLost: false });
    }, (reason) => {
      if (!cancelled) setState({ key: accessKey, config: null, error: funnelErrorMessage(reason), accessLost: isAccessLost(reason) });
    });
    return () => { cancelled = true; };
  }, [auth, available, accessKey, nonce]);

  const current = state.key === accessKey && available ? state : null;
  return {
    config: withSavedTexts(current?.config || null, accessKey),
    error: current?.error || "",
    accessLost: Boolean(current?.accessLost),
    loading: available && Boolean(auth) && !current?.config && !current?.error,
    reload,
  };
}
