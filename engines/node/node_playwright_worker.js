const fs = require("node:fs");
const path = require("node:path");
const readline = require("node:readline");
const { spawnSync } = require("node:child_process");

let playwright;
try {
  playwright = require("playwright-core");
} catch (err) {
  process.stderr.write(
    "[node-playwright-worker] Missing dependency 'playwright-core'. Run: npm install\n",
  );
  process.exit(1);
}

let browser = null;
let context = null;
let page = null;
let commandQueue = Promise.resolve();

function writeResponse(id, ok, result = null, error = null) {
  const payload = { id, ok };
  if (ok) payload.result = result ?? {};
  else payload.error = error ?? "unknown error";
  process.stdout.write(`${JSON.stringify(payload)}\n`);
}

function which(binary) {
  const out = spawnSync("which", [binary], { encoding: "utf8" });
  if (out.status === 0) {
    const candidate = (out.stdout || "").trim();
    if (candidate && fs.existsSync(candidate)) return candidate;
  }
  return null;
}

function resolveSystemChromeBinary() {
  const envCandidate = process.env.CHROME_PATH || process.env.GOOGLE_CHROME_BIN;
  if (envCandidate && fs.existsSync(envCandidate)) return envCandidate;

  const knownBinaries = [
    "google-chrome",
    "google-chrome-stable",
    "chromium-browser",
    "chromium",
    "chrome",
  ];
  for (const bin of knownBinaries) {
    const resolved = which(bin);
    if (resolved) return resolved;
  }

  const home = process.env.HOME || "";
  const cacheDir = home ? path.join(home, ".cache", "ms-playwright") : "";
  if (cacheDir && fs.existsSync(cacheDir)) {
    const entries = fs.readdirSync(cacheDir, { withFileTypes: true });
    for (const entry of entries) {
      if (!entry.isDirectory()) continue;
      if (!entry.name.startsWith("chromium-")) continue;
      const linuxChrome = path.join(cacheDir, entry.name, "chrome-linux", "chrome");
      const linuxHeadlessShell = path.join(cacheDir, entry.name, "chrome-linux", "headless_shell");
      if (fs.existsSync(linuxChrome)) return linuxChrome;
      if (fs.existsSync(linuxHeadlessShell)) return linuxHeadlessShell;
    }
  }

  return null;
}

function toPlainHeaders(headers) {
  if (!headers || typeof headers !== "object") return {};
  const out = {};
  for (const [k, v] of Object.entries(headers)) out[String(k)] = String(v);
  return out;
}

async function closeBrowser() {
  if (page) {
    try {
      await page.close();
    } catch (err) {}
  }
  page = null;

  if (context) {
    try {
      await context.close();
    } catch (err) {}
  }
  context = null;

  if (browser) {
    try {
      await browser.close();
    } catch (err) {}
  }
  browser = null;
}

async function handleStart(payload) {
  await closeBrowser();

  const browserType = String(payload.browserType || "chromium");
  const launcher = playwright[browserType];
  if (!launcher) throw new Error(`Unsupported browserType: ${browserType}`);

  const launchOptions = {
    headless: Boolean(payload.headless),
  };

  const proxy = payload.proxy && typeof payload.proxy === "object" ? payload.proxy : null;
  if (proxy && proxy.protocol && proxy.host && proxy.port) {
    const proxyServer = `${proxy.protocol}://${proxy.host}:${proxy.port}`;
    launchOptions.proxy = { server: proxyServer };
    if (proxy.username && proxy.password) {
      launchOptions.proxy.username = String(proxy.username);
      launchOptions.proxy.password = String(proxy.password);
    }
  }

  if (browserType === "chromium" && payload.useSystemChrome !== false) {
    const executablePath = resolveSystemChromeBinary();
    if (!executablePath) {
      throw new Error(
        "System Chrome/Chromium binary not found. Install Chrome or set CHROME_PATH.",
      );
    }
    launchOptions.executablePath = executablePath;
  }

  browser = await launcher.launch(launchOptions);

  const viewport = payload.viewport || {};
  const contextOptions = {
    viewport: {
      width: Number(viewport.width || 1366),
      height: Number(viewport.height || 768),
    },
  };
  if (payload.userAgent) contextOptions.userAgent = String(payload.userAgent);
  context = await browser.newContext(contextOptions);

  const initScripts = Array.isArray(payload.initScripts) ? payload.initScripts : [];
  for (const source of initScripts) {
    if (!source || typeof source !== "string") continue;
    await context.addInitScript(source);
  }

  page = await context.newPage();
  const pageLoadTimeoutMs = Number(payload.pageLoadTimeoutMs || 90000);
  const actionTimeoutMs = Number(payload.actionTimeoutMs || 30000);
  page.setDefaultNavigationTimeout(pageLoadTimeoutMs);
  page.setDefaultTimeout(actionTimeoutMs);

  return { started: true };
}

async function handleNavigate(payload) {
  if (!page) throw new Error("Worker is not started");
  const url = String(payload.url || "");
  const timeoutMs = Number(payload.timeoutMs || 90000);
  const started = Date.now();
  const response = await page.goto(url, { waitUntil: "domcontentloaded", timeout: timeoutMs });
  const loadTime = (Date.now() - started) / 1000;
  const statusCode = response ? response.status() : 0;
  const headers = response ? toPlainHeaders(await response.allHeaders()) : {};
  return {
    url: page.url(),
    load_time: loadTime,
    success: statusCode > 0 ? statusCode < 400 : true,
    headers,
  };
}

async function handleReload(payload) {
  if (!page) throw new Error("Worker is not started");
  const timeoutMs = Number(payload.timeoutMs || 90000);
  const started = Date.now();
  const response = await page.reload({ waitUntil: "domcontentloaded", timeout: timeoutMs });
  const loadTime = (Date.now() - started) / 1000;
  const statusCode = response ? response.status() : 0;
  const headers = response ? toPlainHeaders(await response.allHeaders()) : {};
  return {
    url: page.url(),
    load_time: loadTime,
    success: statusCode > 0 ? statusCode < 400 : true,
    headers,
  };
}

async function handleLocator(payload) {
  if (!page) throw new Error("Worker is not started");
  const selector = String(payload.selector || "");
  const element = await page.$(selector);
  if (!element) return { found: false, html: "" };

  let html = await element.textContent();
  if (!html) html = await element.innerHTML();
  return { found: true, html: String(html || "").slice(0, 20000) };
}

async function handleGetPageContent() {
  if (!page) throw new Error("Worker is not started");
  return { content: String(await page.content()).slice(0, 300000) };
}

async function handleExecuteJs(payload) {
  if (!page) throw new Error("Worker is not started");
  const script = String(payload.script || "");
  const value = await page.evaluate(source => {
    // eslint-disable-next-line no-eval
    const out = eval(source);
    return out === undefined ? null : out;
  }, script);
  return { value };
}

async function handleScreenshot(payload) {
  if (!page) throw new Error("Worker is not started");
  const targetPath = String(payload.path || "");
  if (!targetPath) throw new Error("Path is required for screenshot");
  fs.mkdirSync(path.dirname(targetPath), { recursive: true });
  await page.screenshot({ path: targetPath, fullPage: true });
  return { saved: true };
}

async function handleStop() {
  await closeBrowser();
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
  process.stderr.write(
    `[node-playwright-worker] uncaughtException: ${err && err.stack ? err.stack : String(err)}\n`,
  );
});

process.on("unhandledRejection", err => {
  process.stderr.write(
    `[node-playwright-worker] unhandledRejection: ${err && err.stack ? err.stack : String(err)}\n`,
  );
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
      process.stderr.write(
        `[node-playwright-worker] queue error: ${err && err.stack ? err.stack : String(err)}\n`,
      );
    });
});

rl.on("close", async () => {
  try {
    await closeBrowser();
  } catch (err) {
    process.stderr.write(
      `[node-playwright-worker] close error: ${err && err.stack ? err.stack : String(err)}\n`,
    );
  } finally {
    process.exit(0);
  }
});
