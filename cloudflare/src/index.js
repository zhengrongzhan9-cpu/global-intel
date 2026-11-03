// Cloudflare Worker: 用 Cron Triggers 调 GitHub workflow_dispatch 触发 intel.yml
// 密钥只从 env 读取，绝不写死或打印。

const CRON_MODES = {
  "20 0 * * *": "morning", // 08:20 KL
  "20 12 * * *": "evening", // 20:20 KL
  "7 1-11,13-23 * * *": "hourly", // 每小时 :07 KL，避开 08/20 点
};

const DEFAULT_REPO = "zhengrongzhan9-cpu/global-intel";
const WORKFLOW_FILE = "intel.yml";

function json(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json; charset=utf-8" },
  });
}

async function dispatch(env, mode) {
  const token = env.GITHUB_TOKEN;
  if (!token) throw new Error("GITHUB_TOKEN is not configured");
  const repo = env.GITHUB_REPO || DEFAULT_REPO;
  const url = `https://api.github.com/repos/${repo}/actions/workflows/${WORKFLOW_FILE}/dispatches`;
  const resp = await fetch(url, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
      "User-Agent": "global-intel-cron",
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ ref: "main", inputs: { mode } }),
  });
  if (resp.status !== 204) {
    const text = await resp.text();
    throw new Error(`dispatch ${mode} failed: HTTP ${resp.status} ${text.slice(0, 200)}`);
  }
  console.log(JSON.stringify({ event: "dispatch", mode, repo, status: 204 }));
  return true;
}

export default {
  async scheduled(event, env, ctx) {
    const mode = CRON_MODES[event.cron] || "hourly";
    ctx.waitUntil(
      dispatch(env, mode).catch((err) => {
        console.error(JSON.stringify({ event: "dispatch_failed", mode, error: String(err) }));
      })
    );
  },

  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === "/health") {
      return json({ ok: true, worker: "global-intel-cron", crons: CRON_MODES });
    }
    // 受保护的测试入口：需要 TRIGGER_KEY，避免公网任意触发
    if (url.pathname === "/trigger") {
      const provided = request.headers.get("X-Trigger-Key") || "";
      if (!env.TRIGGER_KEY || provided !== env.TRIGGER_KEY) {
        return json({ ok: false, error: "unauthorized" }, 401);
      }
      const mode = url.searchParams.get("mode") || "hourly";
      if (!["hourly", "morning", "evening"].includes(mode)) {
        return json({ ok: false, error: "bad mode" }, 400);
      }
      try {
        await dispatch(env, mode);
        return json({ ok: true, mode });
      } catch (err) {
        return json({ ok: false, error: String(err) }, 502);
      }
    }
    return json({ ok: true, worker: "global-intel-cron" });
  },
};