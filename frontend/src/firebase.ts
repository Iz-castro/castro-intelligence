import { initializeApp, type FirebaseApp } from "firebase/app";
import { browserLocalPersistence, getAuth, GoogleAuthProvider, initializeAuth, inMemoryPersistence, setPersistence, signInWithCustomToken, type Auth } from "firebase/auth";
import { getDoc, getDocs, getFirestore, initializeFirestore, onSnapshot, persistentLocalCache, persistentMultipleTabManager, terminate, type DocumentReference, type DocumentSnapshot, type Firestore, type FirestoreError, type Query, type QuerySnapshot } from "firebase/firestore";

import type { FirebaseWebConfig } from "./types";

export type FirebaseBundle = {
  app: FirebaseApp;
  auth: Auth;
  db: Firestore | null;
  provider: GoogleAuthProvider;
  impersonationTab: boolean;
  impersonationExpiresAt?: string;
  impersonationAuthUid?: string;
  impersonationSessionId?: string;
  impersonationEnvironment?: string;
  impersonationTargetUid?: string;
  impersonationTenantId?: string;
};

let bundle: FirebaseBundle | null = null;
let initialization: Promise<FirebaseBundle> | null = null;
const TAB_MARKER = "crm_impersonation_tab";
const fragment = new URLSearchParams(window.location.hash.slice(1));
let customToken = fragment.get("imp");
const hasTokenFragment = fragment.has("imp");
let markedTab = false;
let markerAvailable = true;
try {
  markedTab = window.sessionStorage.getItem(TAB_MARKER) === "1";
  if (hasTokenFragment) window.sessionStorage.setItem(TAB_MARKER, "1");
} catch { markerAvailable = false; }
export const impersonationTab = hasTokenFragment || markedTab;
let impersonationStopped = impersonationTab && !hasTokenFragment;
const listeners = new Set<() => void>();
const stopObservers = new Set<(message: string) => void>();
if (hasTokenFragment) {
  // Somente o marcador nao secreto persiste; token e dados ficam na memoria.
  window.history.replaceState(null, "", window.location.pathname + window.location.search);
  fragment.delete("imp");
}

export function onImpersonationStopped(observer: (message: string) => void) {
  stopObservers.add(observer);
  return () => { stopObservers.delete(observer); };
}

export function stopImpersonationReading(message = "A sessão de visualização foi encerrada.") {
  if (!impersonationTab || impersonationStopped) return;
  impersonationStopped = true;
  for (const stop of Array.from(listeners)) stop();
  listeners.clear();
  for (const observer of Array.from(stopObservers)) observer(message);
}

export function isFirebaseSessionActive(auth: Auth | null) {
  if (!impersonationTab || !auth) return true;
  if (impersonationStopped) return false;
  const expiry = Date.parse(bundle?.impersonationExpiresAt || "");
  if (!bundle || bundle.auth !== auth || !auth.currentUser || auth.currentUser.uid !== bundle.impersonationAuthUid || !Number.isFinite(expiry) || Date.now() >= expiry) {
    stopImpersonationReading("A sessão de visualização expirou ou ficou inválida.");
    return false;
  }
  return true;
}

export function assertFirebaseSessionActive(auth: Auth | null) {
  if (!isFirebaseSessionActive(auth)) throw new Error("A sessão de visualização foi encerrada.");
}

function trackListener(auth: Auth, unsubscribe: () => void) {
  if (!impersonationTab) return unsubscribe;
  const stop = () => { listeners.delete(stop); unsubscribe(); };
  if (isFirebaseSessionActive(auth)) listeners.add(stop);
  else stop();
  return stop;
}

export function trackImpersonationTask(cleanup: () => void) {
  if (!impersonationTab) return () => {};
  const stop = () => { listeners.delete(stop); cleanup(); };
  if (impersonationStopped) stop();
  else listeners.add(stop);
  return () => { listeners.delete(stop); };
}

function snapshotError(auth: Auth, onError: ((error: FirestoreError) => void) | undefined, error: FirestoreError) {
  if (!isFirebaseSessionActive(auth)) return;
  // Perda da thread para outro dono deve seguir o watcher normal do alvo.
  onError?.(error);
}

export function watchSessionQuery<T>(auth: Auth, reference: Query<T>, onNext: (snapshot: QuerySnapshot<T>) => void, onError?: (error: FirestoreError) => void, options?: { includeMetadataChanges?: boolean }) {
  if (impersonationTab) throw new Error("A visualização usa somente leituras pelo servidor.");
  if (!isFirebaseSessionActive(auth)) return () => {};
  // options.includeMetadataChanges: o caller que distingue cache x servidor
  // (gate de "carregando") precisa ouvir a confirmacao do servidor mesmo quando
  // os docs nao mudam — sem isso um resultado vazio do cache nunca "amadurece".
  return trackListener(auth, onSnapshot(reference, options ?? {}, (snapshot) => {
    if (isFirebaseSessionActive(auth)) onNext(snapshot);
  }, (error) => snapshotError(auth, onError, error)));
}

export function watchSessionDocument<T>(auth: Auth, reference: DocumentReference<T>, onNext: (snapshot: DocumentSnapshot<T>) => void, onError?: (error: FirestoreError) => void) {
  if (impersonationTab) throw new Error("A visualização usa somente leituras pelo servidor.");
  if (!isFirebaseSessionActive(auth)) return () => {};
  return trackListener(auth, onSnapshot(reference, (snapshot) => {
    if (isFirebaseSessionActive(auth)) onNext(snapshot);
  }, (error) => snapshotError(auth, onError, error)));
}

export async function getSessionDocs<T>(auth: Auth, reference: Query<T>) {
  if (impersonationTab) throw new Error("A visualização usa somente leituras pelo servidor.");
  assertFirebaseSessionActive(auth);
  const snapshot = await getDocs(reference);
  assertFirebaseSessionActive(auth);
  return snapshot;
}

export async function getSessionDoc<T>(auth: Auth, reference: DocumentReference<T>) {
  if (impersonationTab) throw new Error("A visualização usa somente leituras pelo servidor.");
  assertFirebaseSessionActive(auth);
  const snapshot = await getDoc(reference);
  assertFirebaseSessionActive(auth);
  return snapshot;
}

export async function disposeImpersonationFirebase(current: FirebaseBundle) {
  if (!current.impersonationTab) return;
  stopImpersonationReading();
  await Promise.allSettled([current.auth.signOut(), current.db ? terminate(current.db) : Promise.resolve()]);
  if (bundle === current) bundle = null;
  initialization = null;
}

export async function initializeFirebaseBundle(config: FirebaseWebConfig, environment = ""): Promise<FirebaseBundle> {
  if (bundle) return bundle;
  if (initialization) return initialization;
  initialization = createFirebaseBundle(config, environment);
  return initialization;
}

async function createFirebaseBundle(config: FirebaseWebConfig, environment: string): Promise<FirebaseBundle> {
  const app = initializeApp({
    apiKey: config.apiKey, authDomain: config.authDomain, projectId: config.projectId,
    storageBucket: config.storageBucket, appId: config.appId,
    messagingSenderId: config.messagingSenderId || undefined, measurementId: config.measurementId || undefined,
  });
  const auth = impersonationTab ? initializeAuth(app, { persistence: inMemoryPersistence }) : getAuth(app);
  if (!impersonationTab) await setPersistence(auth, browserLocalPersistence);
  const provider = new GoogleAuthProvider();
  provider.setCustomParameters({ prompt: "select_account" });
  let db: Firestore | null = null;
  if (!impersonationTab) {
    try {
      db = initializeFirestore(app, { localCache: persistentLocalCache({ tabManager: persistentMultipleTabManager() }) });
    } catch { db = getFirestore(app); }
  }
  const initialized: FirebaseBundle = { app, auth, db, provider, impersonationTab };
  if (impersonationTab && hasTokenFragment) {
    const token = customToken;
    customToken = null;
    try {
      if (!token || !markerAvailable || !environment) throw new Error();
      const credential = await signInWithCustomToken(auth, token);
      const result = await credential.user.getIdTokenResult();
      const claims = result.claims;
      const expires = Number(claims.imp_exp);
      const authTime = Number(claims.auth_time);
      const now = Date.now() / 1000;
      const sid = String(claims.imp_sid || "");
      const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(environment));
      const envHash = Array.from(new Uint8Array(digest)).map((part) => part.toString(16).padStart(2, "0")).join("").slice(0, 8);
      const authUid = `imp_ro_${envHash}_${sid}`;
      const targetUid = String(claims.imp_target_uid || "");
      if (claims.imp !== true || claims.imp_env !== environment || !/^[a-f0-9]{32}$/.test(sid)
        || typeof claims.imp_exp !== "number" || typeof claims.auth_time !== "number"
        || credential.user.uid !== authUid || typeof claims.imp_target_uid !== "string" || !targetUid || targetUid.startsWith("imp_ro_") || targetUid === authUid
        || typeof claims.tenant_id !== "string" || !claims.tenant_id || claims.role === "admin"
        || typeof claims.role !== "string" || typeof claims.perfil_acesso_id !== "string" || !claims.perfil_acesso_id
        || !Number.isFinite(expires) || !Number.isFinite(authTime) || expires <= now || expires > now + 3600
        || authTime <= 0 || authTime > now + 60 || now - authTime > 3660) throw new Error();
      initialized.impersonationExpiresAt = new Date(expires * 1000).toISOString();
      initialized.impersonationAuthUid = authUid;
      initialized.impersonationSessionId = sid;
      initialized.impersonationEnvironment = environment;
      initialized.impersonationTargetUid = targetUid;
      initialized.impersonationTenantId = claims.tenant_id;
    } catch {
      await Promise.allSettled([auth.signOut(), db ? terminate(db) : Promise.resolve()]);
      impersonationStopped = true;
      throw new Error("Não foi possível iniciar a visualização. Gere um novo acesso.");
    }
  }
  bundle = initialized;
  return bundle;
}
