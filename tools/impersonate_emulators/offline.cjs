// Preload do harness LOCAL: bloqueia APIs externas e desativa MOTD do CLI.
const http = require("node:http");
const https = require("node:https");
const artifacts = require("firebase-tools/lib/emulator/downloadableEmulatorInfo.json");
const allowedArtifact = new URL(artifacts.firestore.remoteUrl);
function inspect(input) {
  let host;
  let path;
  if (typeof input === "string" || input instanceof URL) {
    const url = new URL(input);
    host = url.hostname; path = url.pathname;
  } else {
    host = input.hostname || input.host || "localhost";
    host = host.replace(/:\d+$/, "");
    path = (input.path || "/").split("?")[0];
  }
  if (["localhost", "127.0.0.1", "[::1]", "::1"].includes(host)) return;
  if (host === allowedArtifact.hostname && path === allowedArtifact.pathname) return;
  throw new Error("Harness local bloqueou rede externa: " + host);
}
for (const module of [http, https]) {
  for (const method of ["request", "get"]) {
    const original = module[method];
    module[method] = function (input, ...rest) {
      inspect(input);
      return original.call(this, input, ...rest);
    };
  }
}
const motdPath = require.resolve("firebase-tools/lib/fetchMOTD");
require.cache[motdPath] = { id: motdPath, filename: motdPath, loaded: true, exports: { fetchMOTD() {} } };
