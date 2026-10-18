// Matriz LOCAL de rules e Auth; qualquer host/projeto externo aborta no boot.
import assert from "node:assert/strict";
import { createHash, randomBytes } from "node:crypto";
import { readFileSync } from "node:fs";
import { initializeTestEnvironment, assertFails, assertSucceeds } from "@firebase/rules-unit-testing";
import { initializeApp as initializeClient, deleteApp as deleteClient } from "firebase/app";
import {
  initializeAuth, inMemoryPersistence, connectAuthEmulator, signInWithCustomToken,
  updateProfile, updatePassword, updateEmail, deleteUser, signInWithEmailAndPassword,
} from "firebase/auth";
import {
  doc, collection, getDoc, getDocFromServer, getDocs, setDoc, updateDoc, deleteDoc, query, where,
  orderBy, limit, Timestamp, onSnapshot, connectFirestoreEmulator, initializeFirestore,
  memoryLocalCache, terminate, setLogLevel,
} from "firebase/firestore";
import { initializeApp as initializeAdmin, deleteApp as deleteAdmin } from "firebase-admin/app";
import { getAuth as adminAuth } from "firebase-admin/auth";

const PROJECT = "demo-impersonate";
assert.equal(process.env.GCLOUD_PROJECT, PROJECT);
assert.equal(process.env.GOOGLE_CLOUD_PROJECT, PROJECT);
assert.equal(process.env.FIREBASE_AUTH_EMULATOR_HOST, "127.0.0.1:9099");
assert.equal(process.env.FIRESTORE_EMULATOR_HOST, "127.0.0.1:8080");
assert.equal(process.env.GOOGLE_APPLICATION_CREDENTIALS, undefined);
setLogLevel("silent");
const env = await initializeTestEnvironment({
  projectId: PROJECT,
  firestore: { host: "127.0.0.1", port: 8080, rules: readFileSync(new URL("../../firestore.rules", import.meta.url), "utf8") },
});
const admin = initializeAdmin({ projectId: PROJECT }, "impersonate-local-admin");
const authAdmin = adminAuth(admin);
const PREFIXES = ["castro_crm", "castro_crm_staging"];
const TID = "tenant-sim";
const TARGET = "uid-target-sim";
const SUPERVISOR = "uid-supervisor-sim";
const ACTOR = "uid-admin-sim";
let checks = 0;
const normalBackupObservations = [];
const apps = [];
function check(value, message) { assert.ok(value, message); checks++; console.log(`OK ${message}`); }
async function allow(label, promise) { await assertSucceeds(promise); checks++; console.log(`OK ${label}`); }
async function deny(label, promise) { await assertFails(promise); checks++; console.log(`OK ${label}`); }
const base = (prefix, tenant = TID) => `${prefix}_tenants/${tenant}`;
const seconds = () => Math.floor(Date.now() / 1000);
const stamp = (value) => Timestamp.fromMillis(value * 1000);
const profile = (role = "operador") => ({
  uid: role === "supervisor" ? SUPERVISOR : TARGET,
  user_id: role === "supervisor" ? 3 : 2, role, is_active: 1,
  perfil_acesso_id: role === "supervisor" ? "perfil_sup_custom" : "perfil_op_custom",
});
const normalClaims = (role = "operador") => ({
  email: "operador@hubloc.com.br", tenant_id: TID, role,
  perfil_acesso_id: profile(role).perfil_acesso_id, auth_time: seconds(),
});
function fixture(prefix, options = {}) {
  const sid = options.sid || randomBytes(16).toString("hex");
  const uid = `imp_ro_${createHash("sha256").update(prefix).digest("hex").slice(0, 8)}_${sid}`;
  const role = options.role || "operador";
  const target = role === "supervisor" ? SUPERVISOR : TARGET;
  const issued = options.issued ?? seconds();
  const ttl = options.ttl ?? 1800;
  const claims = {
    imp: true, imp_sid: sid, imp_target_uid: target, imp_by: 1, imp_by_uid: ACTOR,
    imp_env: prefix, tenant_id: TID, role, perfil_acesso_id: profile(role).perfil_acesso_id,
    imp_exp: issued + ttl, auth_time: options.authTime ?? issued, ...options.claims,
  };
  const record = {
    sid, auth_uid: uid, target_uid: target, target_user_id: profile(role).user_id,
    admin_uid: ACTOR, admin_user_id: 1, tenant_id: TID, environment: prefix,
    role_at_start: role, perfil_acesso_id_at_start: profile(role).perfil_acesso_id,
    ttl_seconds: ttl, created_at: stamp(issued), expires_at: stamp(issued + ttl),
    cleanup_after: stamp(issued + 7200), status: "active", ...options.record,
  };
  return { uid, sid, target, claims, record, prefix };
}
async function seed(path, data) {
  await env.withSecurityRulesDisabled((context) => setDoc(doc(context.firestore(), path), data));
}
async function remove(path) {
  await env.withSecurityRulesDisabled((context) => deleteDoc(doc(context.firestore(), path)));
}
async function seedSession(session) {
  await seed(`${base(session.prefix)}/impersonation_sessions/${session.sid}`, session.record);
}
function dbFor(session) { return env.authenticatedContext(session.uid, session.claims).firestore(); }
async function initialData() {
  for (const prefix of PREFIXES) {
    const root = base(prefix);
    await seed(root, { name: "Tenant Sim" });
    await seed(`${root}/operator_profiles/${TARGET}`, profile());
    await seed(`${root}/operator_profiles/${SUPERVISOR}`, profile("supervisor"));
    await seed(`${root}/operator_profiles/${ACTOR}`, { ...profile(), user_id: 1, role: "admin", perfil_acesso_id: "perfil_admin" });
    await seed(`${root}/operator_profiles/uid-other-sim`, { ...profile(), user_id: 4 });
    for (const [name, owner, backup] of [["mine", TARGET, false], ["other", "uid-other-sim", false], ["pool", "", false], ["null", null, false], ["backup", TARGET, true], ["backup-pool", "", true], ["backup-null", null, true]]) {
      for (const kind of ["wa_contacts", "wa_conversations"]) await seed(`${root}/${kind}/${name}`, {
        assigned_to_uid: owner, is_backup: backup, is_archived: 0, last_message_at: name,
      });
    }
    for (const kind of ["departments", "perfis_acesso", "system_settings", "health_status", "gc_conversations", "gc_messages", "messages", "media_assets", "wa_transfer_log", "audit_log", "audit_metrics", "users", "user_settings", "bot_states", "unknown_collection", "wa_message_status", "internal_unread", "operator_assume_counters", "_meta"])
      await seed(`${root}/${kind}/sample`, { value: "sim" });
    await seed(`${root}/media_assets/sample/chunks/part`, { value: "sim" });
    await seed(`${root}/wa_messages/regular`, { is_backup: false, content: "sim" });
    await seed(`${root}/wa_messages/backup`, { is_backup: true, content: "sim" });
    await seed(`${prefix}_wa_contacts/flat`, { assigned_to_uid: TARGET });
    await seed(`${base(prefix, "other-tenant")}/departments/sample`, { value: "sim" });
  }
  await seed(`castro_crm_operator_profiles/${TARGET}`, { ...profile(), user_id: 2 });
  await seed("castro_crm_super_admins/uid-admin-sim", { is_active: true });
  await seed("castro_crm_audit_logs_system/sample", { action: "sim" });
}

async function rulesMatrix() {
  console.log("MATRIZ: Ver como sem acesso direto; grants normais preservados");
  for (const prefix of PREFIXES) {
    const root = base(prefix);
    for (const role of ["operador", "supervisor"]) {
      const s = fixture(prefix, { role }); await seedSession(s);
      const db = dbFor(s);
      const paths = [root, `${root}/operator_profiles/${s.target}`, `${root}/operator_profiles/${ACTOR}`,
        ...["wa_contacts", "wa_conversations"].flatMap((kind) => ["mine", "pool", "null", "other", "backup", "backup-pool", "backup-null"].map((id) => `${root}/${kind}/${id}`)),
        ...["departments", "perfis_acesso", "system_settings", "health_status", "gc_conversations", "gc_messages", "messages", "media_assets", "wa_transfer_log", "audit_log", "audit_metrics", "users", "user_settings", "bot_states", "unknown_collection", "wa_message_status", "internal_unread", "operator_assume_counters", "_meta"].map((kind) => `${root}/${kind}/sample`),
        `${root}/media_assets/sample/chunks/part`, `${root}/wa_messages/regular`, `${root}/wa_messages/backup`,
        `${root}/impersonation_sessions/${s.sid}`, `${root}/impersonation_sessions/${s.sid}/nested/sample`,
        `${base(prefix, "other-tenant")}/departments/sample`,
        ...["operator_profiles", "users", "departments", "channels", "wa_contacts", "wa_conversations", "wa_messages", "wa_message_status", "wa_transfer_log", "bot_states", "system_settings", "user_settings", "audit_log", "audit_metrics", "operator_assume_counters", "media_assets", "gc_conversations", "gc_messages", "messages", "internal_unread", "_meta"].map((kind) => `${prefix}_${kind}/sample`),
        `${prefix}_media_assets/sample/chunks/part`, "castro_crm_super_admins/uid-admin-sim", `castro_crm_super_admins/${s.uid}`, "castro_crm_audit_logs_system/sample"];
      for (const path of paths) {
        await deny(`${role}: read direto negado ${path}`, getDocFromServer(doc(db, path)));
        await deny(`${role}: write direto negado ${path}`, setDoc(doc(db, path), { value: "nao gravar" }));
      }
      await deny(`${prefix}/${role}: query global negada`, getDocs(collection(db, `${root}/wa_conversations`)));
      await deny(`${prefix}/${role}: query UID/backup explicito negada`, getDocs(query(collection(db, `${root}/wa_conversations`), where("assigned_to_uid", "==", s.target), where("is_backup", "==", false), orderBy("last_message_at", "desc"), limit(50))));
      await deny(`${prefix}/${role}: update negado`, updateDoc(doc(db, `${root}/wa_contacts/mine`), { notes: "nao gravar" }));
      await deny(`${prefix}/${role}: delete negado`, deleteDoc(doc(db, `${root}/wa_contacts/mine`)));
      const otherPrefix = prefix === PREFIXES[0] ? PREFIXES[1] : PREFIXES[0];
      await deny(`${prefix}/${role}: outro ambiente negado`, getDocFromServer(doc(db, `${base(otherPrefix)}/departments/sample`)));
    }
    const session = fixture(prefix); await seedSession(session);
    const normal = env.authenticatedContext(TARGET, normalClaims()).firestore();
    await allow(`${prefix}: sessao normal ainda le proprio`, getDoc(doc(normal, `${root}/wa_contacts/mine`)));
    await allow(`${prefix}: normal ainda le pool`, getDoc(doc(normal, `${root}/wa_contacts/pool`)));
    await allow(`${prefix}: normal ainda le perfil proprio`, getDoc(doc(normal, `${root}/operator_profiles/${TARGET}`)));
    await allow(`${prefix}: normal ainda le departamentos`, getDoc(doc(normal, `${root}/departments/sample`)));
    await deny(`${prefix}: normal nao le registry`, getDoc(doc(normal, `${root}/impersonation_sessions/${session.sid}`)));
    await deny(`${prefix}: normal nao escreve registry`, setDoc(doc(normal, `${root}/impersonation_sessions/${session.sid}`), session.record));
    await deny(`${prefix}: normal nao le descendente registry`, getDoc(doc(normal, `${root}/impersonation_sessions/${session.sid}/nested/sample`)));
    await deny(`${prefix}: normal nao escreve descendente registry`, setDoc(doc(normal, `${root}/impersonation_sessions/${session.sid}/nested/sample`), { value: "nao" }));
    if (prefix === "castro_crm_staging") await allow("staging: escrita normal antiga preservada", setDoc(doc(normal, `${root}/wa_contacts/normal-write`), { assigned_to_uid: TARGET }));
    else {
      await deny("prod: escrita normal continua negada", setDoc(doc(normal, `${root}/wa_contacts/normal-write`), { assigned_to_uid: TARGET }));
      await deny("prod: get normal de colega continua negado", getDoc(doc(normal, `${root}/wa_contacts/other`)));
      await deny("prod: get normal de backup continua negado", getDoc(doc(normal, `${root}/wa_contacts/backup`)));
    }
    for (const [label, uid, claims] of [["reservado sem imp", session.uid, normalClaims()], ["UID real com imp antigo", TARGET, { ...normalClaims(), ...session.claims }], ["imp malformado", TARGET, { ...normalClaims(), imp: "true" }]]) {
      const blocked = env.authenticatedContext(uid, claims).firestore();
      await deny(`${prefix}: ${label} nao le`, getDoc(doc(blocked, `${root}/departments/sample`)));
      await deny(`${prefix}: ${label} nao escreve`, setDoc(doc(blocked, `${root}/wa_contacts/escape`), { value: "nao" }));
      await deny(`${prefix}: ${label} nao herda flat`, getDoc(doc(blocked, `${prefix}_wa_contacts/flat`)));
    }
    const normalFalse = env.authenticatedContext(TARGET, { ...normalClaims(), imp: false }).firestore();
    await allow(`${prefix}: imp false nao altera grant normal`, getDoc(doc(normalFalse, `${root}/departments/sample`)));
    const normalSup = env.authenticatedContext(SUPERVISOR, normalClaims("supervisor")).firestore();
    await allow(`${prefix}: supervisor normal consulta global`, getDocs(collection(normalSup, `${root}/wa_conversations`)));
    await allow(`${prefix}: supervisor normal le backup`, getDoc(doc(normalSup, `${root}/wa_messages/backup`)));
  }
  const platform = env.authenticatedContext(ACTOR, { super_admin: true }).firestore();
  await allow("super_admin normal preserva plataforma sem email", getDoc(doc(platform, "castro_crm_audit_logs_system/sample")));
  const self = env.authenticatedContext(ACTOR).firestore();
  await allow("normal preserva self em super_admins sem email", getDoc(doc(self, `castro_crm_super_admins/${ACTOR}`)));
}

async function invalidContracts() {
  console.log("MATRIZ: contratos, prazos e plataforma");
  const prefix = PREFIXES[0];
  const cases = [
    ["registry ausente", {}, false],
    ["auth_uid divergente", { record: { auth_uid: "imp_ro_outro" } }],
    ["target divergente", { record: { target_uid: "uid-outro" } }],
    ["tenant divergente", { record: { tenant_id: "other-tenant" } }],
    ["ambiente divergente", { record: { environment: "castro_crm_staging" } }],
    ["SID divergente", { record: { sid: "b".repeat(32) } }],
    ["ator divergente", { record: { admin_uid: "outro-admin" } }],
    ["role registro divergente", { record: { role_at_start: "admin" } }],
    ["perfil registro divergente", { record: { perfil_acesso_id_at_start: "perfil_admin" } }],
    ["TTL menor que minimo", { ttl: 299 }],
    ["TTL maior que maximo", { ttl: 3601 }],
    ["imp_exp expirado", { issued: seconds() - 1900 }],
    ["claim prazo divergente", { claims: { imp_exp: seconds() + 3000 } }],
    ["auth_time antigo", { authTime: seconds() - 2000 }],
    ["auth_time futuro", { authTime: seconds() + 90 }],
    ["claim sid ausente", { claims: { imp_sid: "" } }],
    ["claim alvo reservado", { claims: { imp_target_uid: "imp_ro_escape" } }],
    ["claim ambiente ausente", { claims: { imp_env: "" } }],
    ["claim role admin", { claims: { role: "admin" } }],
    ["claim super_admin", { claims: { super_admin: true } }],
  ];
  for (const [label, options, persist = true] of cases) {
    const s = fixture(prefix, options);
    if (persist) await seedSession(s);
    await deny(label, getDoc(doc(dbFor(s), `${base(prefix)}/departments/sample`)));
  }
  const s = fixture(prefix);
  await seedSession(s);
  for (const path of ["castro_crm_super_admins/uid-admin-sim", `castro_crm_super_admins/${s.uid}`, "castro_crm_audit_logs_system/sample"])
    await deny(`preview nao acessa plataforma ${path}`, getDoc(doc(dbFor(s), path)));
  const platformEscape = env.authenticatedContext(s.uid, { ...normalClaims(), super_admin: true }).firestore();
  await deny("reservado com super_admin nao herda plataforma", getDoc(doc(platformEscape, "castro_crm_audit_logs_system/sample")));
}

async function probeFrontendShapes() {
  // A sessao temporaria nao pode executar nenhuma query direta. O comportamento
  // normal preexistente e registrado, sem corrigir seus filtros nesta tarefa.
  for (const prefix of PREFIXES) {
    const s = fixture(prefix); await seedSession(s);
    const preview = dbFor(s);
    const normal = env.authenticatedContext(TARGET, normalClaims()).firestore();
    for (const [kind, owner] of [["wa_contacts", TARGET], ["wa_contacts", ""], ["wa_contacts", null], ["wa_conversations", TARGET], ["wa_conversations", ""], ["wa_conversations", null]]) {
      const shape = (db) => query(collection(db, `${base(prefix)}/${kind}`),
        where("assigned_to_uid", "==", owner),
        ...(kind === "wa_contacts" ? [where("is_archived", "==", 0)] : []),
        orderBy("last_message_at", "desc"), limit(50));
      const label = `${prefix}/${kind}/${owner === null ? "null" : owner ? "mine" : "pool"}`;
      const result = await assertSucceeds(getDocs(shape(normal)));
      check(result.docs.some((d) => d.id === (owner === null ? "null" : owner ? "mine" : "pool")), `normal preserva query ${label}`);
      const ids = result.docs.map((d) => d.id);
      if (ids.some((id) => id.startsWith("backup"))) normalBackupObservations.push(label);
      console.log(`LIMITACAO NORMAL ${label}: ${JSON.stringify({ ids })}`);
      await deny(`preview nega query frontend ${label}`, getDocs(shape(preview)));
    }
  }
  console.log(`LIMITACAO NORMAL: ${normalBackupObservations.length} consultas preexistentes entregaram backup; preview direto sempre negado`);
}

async function listenerDenied(db, path, label) {
  let received = false;
  let stop;
  let timer;
  const denied = await new Promise((resolve, reject) => {
    timer = setTimeout(() => reject(new Error(`Listener sem negacao: ${label}`)), 5000);
    stop = onSnapshot(doc(db, path), () => { received = true; }, (error) => resolve(error.code === "permission-denied"));
  }).finally(() => { clearTimeout(timer); stop?.(); });
  check(denied && !received, `${label}: listener negado sem receber snapshot`);
}

async function restDenied(idToken, path, method = "GET", body) {
  const url = `http://127.0.0.1:8080/v1/projects/${PROJECT}/databases/(default)/documents/${path}`;
  const response = await fetch(url, {
    method, headers: { Authorization: `Bearer ${idToken}`, "Content-Type": "application/json" },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
  // Nao imprimir headers, tokens ou o corpo da resposta de autenticacao.
  check(response.status === 403, `REST ${method} nega ${path}`);
  await response.arrayBuffer();
}

async function directIntegrationDenied(db, user, label) {
  const idToken = await user.getIdToken();
  for (const prefix of PREFIXES) {
    const root = base(prefix);
    for (const path of [`${root}/wa_contacts/mine`, `${root}/departments/sample`, `${root}/operator_profiles/${TARGET}`, `${prefix}_wa_contacts/flat`, `${root}/impersonation_sessions/${user.uid.split("_").at(-1)}`]) {
      await deny(`${label}: SDK nega ${path}`, getDocFromServer(doc(db, path)));
      await restDenied(idToken, path);
    }
    await restDenied(idToken, `${root}:runQuery`, "POST", { structuredQuery: {
      from: [{ collectionId: "wa_conversations" }],
      where: { fieldFilter: { field: { fieldPath: "assigned_to_uid" }, op: "EQUAL", value: { stringValue: TARGET } } },
      orderBy: [{ field: { fieldPath: "last_message_at" }, direction: "DESCENDING" }], limit: 50,
    } });
    await restDenied(idToken, `${root}/wa_contacts/mine`, "PATCH", { fields: { notes: { stringValue: "nao gravar" } } });
    await restDenied(idToken, `${root}/wa_contacts/mine`, "DELETE");
  }
  await restDenied(idToken, "castro_crm_audit_logs_system/sample");
  await restDenied(idToken, `castro_crm_super_admins/${user.uid}`);
}

async function authIntegration() {
  console.log("INTEGRACAO: Auth separado + Firestore SDK, somente emuladores");
  const targetBefore = await authAdmin.createUser({ uid: TARGET, email: "target@example.invalid", displayName: "Alvo original", password: "SenhaOriginalSim123!" });
  const s = fixture("castro_crm");
  await seedSession(s);
  const client = initializeClient({ apiKey: "demo-fake-key", projectId: PROJECT, authDomain: `${PROJECT}.firebaseapp.com` }, "preview-auth-local");
  apps.push(client);
  const auth = initializeAuth(client, { persistence: inMemoryPersistence });
  connectAuthEmulator(auth, "http://127.0.0.1:9099", { disableWarnings: true });
  const db = initializeFirestore(client, { localCache: memoryLocalCache() });
  connectFirestoreEmulator(db, "127.0.0.1", 8080);
  const claims = { ...s.claims }; delete claims.auth_time;
  const custom = await authAdmin.createCustomToken(s.uid, claims);
  const credential = await signInWithCustomToken(auth, custom);
  check(credential.user.uid === s.uid && credential.user.uid !== TARGET && credential.user.uid !== ACTOR, "Auth token autentica UID separado");
  const id = await credential.user.getIdTokenResult();
  check(id.claims.imp_target_uid === TARGET && !id.claims.email, "Auth ID token tem alvo assinado sem copiar email");
  await directIntegrationDenied(db, credential.user, "sessao ativa");
  await listenerDenied(db, `${base(s.prefix)}/departments/sample`, "sessao ativa");
  await deny("SDK integrado nao escreve", updateDoc(doc(db, `${base(s.prefix)}/wa_contacts/mine`), { notes: "bloquear" }));
  await updateProfile(credential.user, { displayName: "Apenas descartavel" });
  await updateEmail(credential.user, "preview@hubloc.com.br");
  await updatePassword(credential.user, "SenhaDescartavelSim123!");
  const original = await authAdmin.getUser(targetBefore.uid);
  check(original.displayName === targetBefore.displayName && original.email === targetBefore.email, "updateProfile/email/password temporarios preservam alvo original");
  await auth.signOut();
  const normalLogin = await signInWithEmailAndPassword(auth, "preview@hubloc.com.br", "SenhaDescartavelSim123!");
  const normalToken = await normalLogin.user.getIdTokenResult();
  check(normalLogin.user.uid === s.uid && normalToken.claims.imp !== true, "relogin password preserva UID reservado e perde claims temporarios");
  await deny("relogin sem claims nao ganha staging via email autorizado", getDoc(doc(db, `${base("castro_crm_staging")}/departments/sample`)));
  await deny("relogin sem claims nao escreve staging", setDoc(doc(db, `${base("castro_crm_staging")}/wa_contacts/escape-auth`), { value: "nao" }));
  await signInWithCustomToken(auth, custom);
  const refreshed = await auth.currentUser.getIdTokenResult(true);
  check(refreshed.claims.imp_exp === s.claims.imp_exp, "refresh real no Auth Emulator nao renova imp_exp");
  await directIntegrationDenied(db, auth.currentUser, "apos refresh");
  await seedSession({ ...s, record: { ...s.record, status: "closed" } });
  await directIntegrationDenied(db, auth.currentUser, "apos encerramento");
  await listenerDenied(db, `${base(s.prefix)}/departments/sample`, "apos encerramento");

  // O token real do Auth Emulator atravessa o prazo absoluto do registro.
  const expiry = seconds() + 4;
  const short = fixture("castro_crm", { issued: expiry - 300, ttl: 300 });
  await seedSession(short);
  const shortClaims = { ...short.claims }; delete shortClaims.auth_time;
  await signInWithCustomToken(auth, await authAdmin.createCustomToken(short.uid, shortClaims));
  check(seconds() < expiry, "token TTL curto inicia antes de vencer");
  await deny("SDK negado antes do TTL", getDocFromServer(doc(db, `${base(short.prefix)}/departments/sample`)));
  await restDenied(await auth.currentUser.getIdToken(), `${base(short.prefix)}/departments/sample`);
  await listenerDenied(db, `${base(short.prefix)}/departments/sample`, "antes do TTL");
  await new Promise((resolve) => setTimeout(resolve, Math.max(0, expiry * 1000 - Date.now() + 200)));
  await directIntegrationDenied(db, auth.currentUser, "apos TTL");
  await listenerDenied(db, `${base(short.prefix)}/departments/sample`, "apos TTL");
  await deleteUser(auth.currentUser);
  await assert.rejects(authAdmin.getUser(short.uid), { code: "auth/user-not-found" });
  await signInWithCustomToken(auth, custom);
  await deleteUser(auth.currentUser);
  await assert.rejects(authAdmin.getUser(s.uid), { code: "auth/user-not-found" });
  check((await authAdmin.getUser(targetBefore.uid)).displayName === targetBefore.displayName, "deleteUser temporario nao exclui conta original");
  const originalLogin = await signInWithEmailAndPassword(auth, "target@example.invalid", "SenhaOriginalSim123!");
  check(originalLogin.user.uid === TARGET, "senha original do alvo continua valida");
  await auth.signOut();
  await terminate(db);
}

try {
  await env.clearFirestore();
  await initialData();
  await rulesMatrix();
  await probeFrontendShapes();
  await invalidContracts();
  await authIntegration();
  console.log(`RESULTADO: ${checks} verificacoes, 0 falhas (Auth + Firestore locais)`);
} catch (error) {
  console.error("FALHOU:", error.code || error.name, error.message);
  process.exitCode = 1;
} finally {
  await env.cleanup();
  for (const app of apps) await deleteClient(app);
  await deleteAdmin(admin);
}
