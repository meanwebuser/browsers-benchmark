const fs = require("node:fs");
const path = require("node:path");
const readline = require("node:readline");

// Keep MITM disabled by default to avoid socket-setup failures in constrained hosts.
if (process.env.UBK_MITM_DISABLE === undefined) {
  process.env.UBK_MITM_DISABLE = "true";
}

const Hero = require("@ulixee/hero");
const UlixeeServer = require("@ulixee/server").default;

let hero = null;
let heroServer = null;
let initScripts = [];
let commandQueue = Promise.resolve();

function writeResponse(id, ok, result = null, error = null) {
  const payload = { id, ok };
  if (ok) {
    payload.result = result ?? {};
  } else {
    payload.error = error ?? "unknown error";
  }
  process.stdout.write(`${JSON.stringify(payload)}\n`);
}

function toPlainHeaders(headers) {
  if (!headers || typeof headers !== "object") return {};
  const out = {};
  for (const [k, v] of Object.entries(headers)) out[String(k)] = String(v);
  return out;
}

function buildUpstreamProxyUrl(proxy) {
  if (!proxy || typeof proxy !== "object") return null;
  if (proxy.url) return String(proxy.url);

  const protocol = proxy.protocol ? String(proxy.protocol) : "";
  const host = proxy.host ? String(proxy.host) : "";
  const port = proxy.port ? String(proxy.port) : "";
  if (!protocol || !host || !port) return null;

  const username = proxy.username ? encodeURIComponent(String(proxy.username)) : "";
  const password = proxy.password ? encodeURIComponent(String(proxy.password)) : "";
  const auth = username && password ? `${username}:${password}@` : "";
  return `${protocol}://${auth}${host}:${port}`;
}

async function handleStart(payload) {
  await handleStop();

  const viewport = payload.viewport || {};
  const options = {
    showChrome: !payload.headless,
    viewport: {
      width: Number(viewport.width || 1366),
      height: Number(viewport.height || 768),
    },
  };

  if (payload.userAgent) options.userAgent = payload.userAgent;
  const upstreamProxyUrl = buildUpstreamProxyUrl(payload.proxy);
  if (upstreamProxyUrl) options.upstreamProxyUrl = upstreamProxyUrl;
  initScripts = Array.isArray(payload.initScripts)
    ? payload.initScripts.filter(x => typeof x === "string" && x.trim().length > 0)
    : [];

  // Avoid global host auto-routing to a stale/fixed port shared by other processes.
  heroServer = new UlixeeServer();
  await heroServer.listen({ port: 0 }, false);
  options.connectionToCore = { host: await heroServer.address };

  hero = new Hero(options);
  // In current Hero alpha builds, activeTab is not immediately ready after constructor.
  await hero.tabs;
  await applyInitScripts();
  return { started: true };
}

async function applyInitScripts() {
  if (!hero || !initScripts.length) return;
  for (const source of initScripts) {
    try {
      await hero.getJsValue(`(() => {\n${source}\n; return true;\n})()`);
    } catch (err) {
      process.stderr.write(`[hero-worker] init script failed: ${err && err.message ? err.message : String(err)}\n`);
    }
  }
}

async function handleNavigate(payload) {
  if (!hero) throw new Error("Hero is not started");
  const started = Date.now();
  const timeoutMs = Number(payload.timeoutMs || 90000);
  const resource = await hero.goto(payload.url, { timeoutMs });
  const loadTime = (Date.now() - started) / 1000;
  const statusCode = resource?.response?.statusCode ?? 0;
  const headers = toPlainHeaders(resource?.response?.headers);
  await applyInitScripts();

  return {
    url: (await hero.url) || payload.url,
    load_time: loadTime,
    success: statusCode > 0 ? statusCode < 400 : true,
    headers,
  };
}

async function handleReload(payload) {
  if (!hero) throw new Error("Hero is not started");
  const started = Date.now();
  const timeoutMs = Number(payload.timeoutMs || 90000);
  const resource = await hero.reload({ timeoutMs });
  const loadTime = (Date.now() - started) / 1000;
  const statusCode = resource?.response?.statusCode ?? 0;
  const headers = toPlainHeaders(resource?.response?.headers);
  await applyInitScripts();
  return {
    url: (await hero.url) || "",
    load_time: loadTime,
    success: statusCode > 0 ? statusCode < 400 : true,
    headers,
  };
}

async function handleLocator(payload) {
  if (!hero) throw new Error("Hero is not started");
  const selector = String(payload.selector || "");
  const element = await hero.document.querySelector(selector);
  if (!element) return { found: false, html: "" };

  let html = "";
  try {
    html = (await element.textContent) || "";
  } catch (err) {
    // no-op
  }
  if (!html) {
    try {
      html = (await element.innerHTML) || "";
    } catch (err) {
      // no-op
    }
  }
  return { found: true, html: String(html || "").slice(0, 20000) };
}

async function handleGetPageContent() {
  if (!hero) throw new Error("Hero is not started");
  const text = await hero.getJsValue(
    "(document.documentElement && (document.documentElement.innerText || document.documentElement.textContent)) || ''",
  );
  return { content: String(text || "").slice(0, 300000) };
}

async function handleExecuteJs(payload) {
  if (!hero) throw new Error("Hero is not started");
  const script = String(payload.script || "");
  const expression = `(() => {\n${script}\n})()`;
  const value = await hero.getJsValue(expression);
  return { value: value === undefined ? null : value };
}

async function handleScreenshot(payload) {
  if (!hero) throw new Error("Hero is not started");
  const targetPath = String(payload.path || "");
  if (!targetPath) throw new Error("Path is required for screenshot");
  fs.mkdirSync(path.dirname(targetPath), { recursive: true });
  const image = await hero.takeScreenshot();
  fs.writeFileSync(targetPath, image);
  return { saved: true };
}

async function handleStop() {
  if (hero || heroServer) {
    try {
      if (hero) await hero.close();
    } finally {
      hero = null;
      if (heroServer) await heroServer.close();
      heroServer = null;
    }
  }
  return { stopped: true };
}

async function dispatch(command, payload) {
  switch (command) {
    case "start":
      return await handleStart(payload);
    case "navigate":
      return await handleNavigate(payload);
    case "reload":
      return await handleReload(payload);
    case "locator":
      return await handleLocator(payload);
    case "get_page_content":
      return await handleGetPageContent();
    case "execute_js":
      return await handleExecuteJs(payload);
    case "screenshot":
      return await handleScreenshot(payload);
    case "stop":
      return await handleStop();
    default:
      throw new Error(`Unknown command: ${command}`);
  }
}

process.on("uncaughtException", err => {
  process.stderr.write(`[hero-worker] uncaughtException: ${err.stack || err.message}\n`);
});

process.on("unhandledRejection", err => {
  process.stderr.write(`[hero-worker] unhandledRejection: ${err && err.stack ? err.stack : String(err)}\n`);
});

const rl = readline.createInterface({
  input: process.stdin,
  crlfDelay: Infinity,
});

rl.on("line", line => {
  commandQueue = commandQueue
    .then(async () => {
      let req;
      try {
        req = JSON.parse(line);
      } catch (err) {
        writeResponse(-1, false, null, `Invalid JSON: ${err.message}`);
        return;
      }

      const id = Number(req.id);
      const command = String(req.command || "");
      const payload = req.payload && typeof req.payload === "object" ? req.payload : {};

      try {
        const result = await dispatch(command, payload);
        writeResponse(id, true, result, null);
      } catch (err) {
        writeResponse(id, false, null, err && err.message ? err.message : String(err));
      }
    })
    .catch(err => {
      process.stderr.write(`[hero-worker] queue error: ${err && err.stack ? err.stack : String(err)}\n`);
    });
});

rl.on("close", async () => {
  try {
    if (hero || heroServer) await handleStop();
  } catch (err) {
    process.stderr.write(`[hero-worker] close error: ${err && err.stack ? err.stack : String(err)}\n`);
  } finally {
    process.exit(0);
  }
});
