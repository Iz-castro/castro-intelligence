// Executa somente emuladores locais, com projeto demo e sem credenciais.
import { spawn } from "node:child_process";
import { copyFileSync, existsSync, mkdirSync, readdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = dirname(fileURLToPath(import.meta.url));
const env = { ...process.env };
for (const key of ["GOOGLE_APPLICATION_CREDENTIALS", "FIREBASE_TOKEN", "FIREBASE_CONFIG", "CLOUDSDK_AUTH_CREDENTIAL_FILE_OVERRIDE", "DEBUG", "NODE_DEBUG"])
  delete env[key];
Object.assign(env, {
  GCLOUD_PROJECT: "demo-impersonate", GOOGLE_CLOUD_PROJECT: "demo-impersonate",
  FIREBASE_AUTH_EMULATOR_HOST: "127.0.0.1:9099", FIRESTORE_EMULATOR_HOST: "127.0.0.1:8080",
  FIREBASE_EMULATORS_PATH: join(root, ".cache", "emulators"),
  XDG_CONFIG_HOME: join(root, ".cache", "config"),
  FIREBASE_CLI_DISABLE_MOTD: "1", FIREBASE_CLI_DISABLE_UPDATE_CHECK: "true", CI: "true",
  NO_UPDATE_NOTIFIER: "1",
});
// O preload vale tambem para o processo dos testes: so loopback e o JAR
// publico exato podem usar HTTP. MOTD/telemetria nao consultam servicos reais.
env.NODE_OPTIONS = `--require="${join(root, "offline.cjs").replaceAll("\\", "/")}"`;
const javaRoot = join(root, ".runtime", "jre21");
if (existsSync(javaRoot)) {
  const directory = readdirSync(javaRoot).find((name) => existsSync(join(javaRoot, name, "bin", "java.exe")));
  if (directory) {
    env.JAVA_HOME = join(javaRoot, directory);
    env.PATH = join(env.JAVA_HOME, "bin") + ";" + env.PATH;
  }
}
mkdirSync(env.FIREBASE_EMULATORS_PATH, { recursive: true });
for (const file of ["firestore.rules", "firestore.indexes.json"])
  copyFileSync(join(root, "..", "..", file), join(root, ".cache", file));
const child = spawn(process.execPath, [
  join(root, "node_modules", "firebase-tools", "lib", "bin", "firebase.js"),
  "emulators:exec", "--project", "demo-impersonate", "--only", "auth,firestore",
  "--config", join(root, "firebase.json"), "node test.mjs",
], { cwd: root, env, stdio: "inherit", windowsHide: true });
child.on("error", (error) => { console.error(error.message); process.exitCode = 1; });
child.on("exit", (code) => { process.exitCode = code ?? 1; });
