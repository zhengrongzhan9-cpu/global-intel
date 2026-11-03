import worker from "../src/index.js";
import assert from "node:assert/strict";

let captured = null;

globalThis.fetch = async (url, options) => {
  captured = { url: String(url), options };
  return new Response(null, { status: 204 });
};

const env = { GITHUB_TOKEN: "test-token", GITHUB_REPO: "owner/repo" };

async function run(cron) {
  captured = null;
  let pending;
  const ctx = { waitUntil: (p) => { pending = p; } };
  await worker.scheduled({ cron }, env, ctx);
  await pending;
  return captured;
}

const morning = await run("20 0 * * *");
assert.equal(
  morning.url,
  "https://api.github.com/repos/owner/repo/actions/workflows/intel.yml/dispatches"
);
assert.equal(JSON.parse(morning.options.body).inputs.mode, "morning");
assert.equal(morning.options.headers.Authorization, "Bearer test-token");

const evening = await run("20 12 * * *");
assert.equal(JSON.parse(evening.options.body).inputs.mode, "evening");

const hourly = await run("7 1-11,13-23 * * *");
assert.equal(JSON.parse(hourly.options.body).inputs.mode, "hourly");

const unknown = await run("0 0 * * *");
assert.equal(JSON.parse(unknown.options.body).inputs.mode, "hourly");

// 鉴权：无 key 时必须 401
const unauthorized = await worker.fetch(new Request("https://x/trigger?mode=hourly"), { TRIGGER_KEY: "k" });
assert.equal(unauthorized.status, 401);

console.log("worker tests passed");