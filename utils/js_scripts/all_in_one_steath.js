(function (config) {

  /********************************************************************
   * 0. Основная функция, которую будем запускать и в окне, и в воркерах
   ********************************************************************/
  function STEALTH_FUNC(cfg) {
    'use strict';
    // ensure cfg and debug default
    cfg = cfg || {};
    if (cfg.debug === undefined) cfg.debug = false;
    const DEBUG = !!cfg.debug;
    if (DEBUG){
        console.log('starting steath', { cfg: cfg });
    }
    const navCfg = cfg.navigator || {};
    const tzCfg = cfg.timezone || {};
    const chCfg = cfg.uaClientHints || {};
    const webglCfg = cfg.webgl || {};
    const canvasCfg = cfg.canvas || { noiseAmplitude: 0.0003, noiseChance: 0.005 };
    const audioCfg = cfg.audio || { noiseAmplitude: 0.0002, step: 100 };

    /********************************************************************
     * utils — локальные утилиты для toString, Proxy и getter'ов
     ********************************************************************/
    const utils = {
      cache: {
        ready: false
      },

      // Log errors in a centralized place when DEBUG is enabled.
      logError(err, context) {
        try {
          this.preload();
        } catch (e) { if (DEBUG) try { console.error('StealthError (internal preload):', e); } catch (_) { } }
        const cleaned = this.cleanErrorStack(err) || err || {};
        const entry = {
          time: (new Date()).toISOString(),
          context: context || 'unknown',
          message: (err && err.message) || String(err),
          stack: cleaned && cleaned.stack || (err && err.stack) || null
        };

        try {
          const g = typeof globalThis !== 'undefined' ? globalThis : window || self || {};
          if (!g.__stealthErrorLogs) g.__stealthErrorLogs = [];
          g.__stealthErrorLogs.push(entry);
        } catch (e) { if (DEBUG) try { console.error('StealthError (internal logs push):', e); } catch (_) { } }

        if (DEBUG) {
          try {
            console.error('StealthError:', entry.context, entry.message);
            if (entry.stack) console.error(entry.stack);
          } catch (_) { }
        }
      },

      preload() {
        if (this.cache.ready) return;
        this.cache.Reflect = {
          get: Reflect.get.bind(Reflect),
          set: Reflect.set.bind(Reflect),
          apply: Reflect.apply.bind(Reflect)
        };
        this.cache.nativeToString = Function.prototype.toString;
        // строка вида "function toString() { [native code] }"
        this.cache.nativeStringSample = this.cache.nativeToString.call(Function.prototype.toString);
        this.cache.ready = true;
      },

      makeNativeStr(name = 'toString') {
        this.preload();
        // Делаем что-то вроде "function get vendor() { [native code] }"
        return this.cache.nativeStringSample
          .replace('toString', name)
          .replace('Function', 'function');
      },


      patchFnToString(fn, name) {
        const nativeStr = this.makeNativeStr(name || fn.name || 'anonymous');

        try {
          // Патчим toString
          Object.defineProperty(fn, 'toString', {
            value: function () { return nativeStr; },
            configurable: false,
            writable: false,
            enumerable: false
          });

          // Патчим name — ВАЖНО: это ДОЛЖНА быть СТРОКА
          Object.defineProperty(fn, 'name', {
            value: name || fn.name || "",
            configurable: false,
            writable: false,
            enumerable: false
          });

        } catch (e) {
          if (DEBUG) utils.logError(e, 'patchFnToString');
        }
      }
      ,

      cleanErrorStack(err) {
        if (!err || !err.stack) return err;
        const filtered = err.stack
          .split('\n')
          .filter(line => !/at (Proxy|Reflect|Object\.newHandler|Object\.apply|Object\.get)/.test(line))
          .join('\n');
        err.stack = filtered;
        return err;
      },

      proxyWithCleanErrors(handler) {
        const wrapped = {};
        for (const key of Object.getOwnPropertyNames(handler)) {
          const orig = handler[key];
          wrapped[key] = function (...args) {
            try {
              return orig.apply(this, args);
            } catch (e) {
              throw utils.cleanErrorStack(e);
            }
          };
        }
        return wrapped;
      },

      defineGetter(obj, prop, getterFn, nameHint) {
        const g = function () { return getterFn.call(this); };
        this.patchFnToString(g, `get ${nameHint || prop}`);
        Object.defineProperty(obj, prop, {
          get: g,
          configurable: false,
          enumerable: false
        });
      },




      defineValue(obj, prop, value) {
        Object.defineProperty(obj, prop, {
          value,
          configurable: false,
          writable: false,
          enumerable: false
        });
      },

      overrideDescriptorValue: (function () {
        // ====== внутреннее состояние ======
        const rules = [];      // { obj, key }
        let patched = false;

        // Сохраняем оригиналы (будут доступны везде)
        const origGetOwnPropertyDescriptor = Object.getOwnPropertyDescriptor;
        const origGetPrototypeOf = Object.getPrototypeOf;
        const origGetOwnPropertyNames = Object.getOwnPropertyNames;
        const origGetOwnPropertySymbols = Object.getOwnPropertySymbols;

        // ====== проверка: надо ли подменять это свойство ======
        function shouldSpoof(obj, key) {
          // линейный поиск, но правило обычно мало
          for (const r of rules) {
            if (r.obj === obj && r.key === key) return true;
          }
          return false;
        }

        // ====== выполняем патч один раз ======
        function applyPatch() {
          if (patched) return;
          patched = true;

          // -----------------------------
          // Patch: getOwnPropertyDescriptor
          // -----------------------------
          Object.getOwnPropertyDescriptor = function (obj, key) {
            const desc = origGetOwnPropertyDescriptor(obj, key);
            if (!desc) return desc;

            if (shouldSpoof(obj, key)) {
  // Если это accessor property (есть get/set) → НЕ используем value!
  if (typeof desc.get === 'function' || typeof desc.set === 'function') {
    return {
      get() { return undefined; },
      set() { },
      enumerable: desc.enumerable,
      configurable: desc.configurable
    };
  }

  // Если это data property → сохраняем структуру полностью
  return {
    value: undefined,
    writable: desc.writable,
    enumerable: desc.enumerable,
    configurable: desc.configurable
  };
}


            return desc;
          };

          // -----------------------------
          // Patch: getOwnPropertyNames
          // -----------------------------
          Object.getOwnPropertyNames = function (obj) {
            const list = origGetOwnPropertyNames(obj);

            // фильтруем ключи, которые должны быть скрыты
            return list.filter(k => !shouldSpoof(obj, k));
          };

          // -----------------------------
          // Patch: getOwnPropertySymbols (обычно не трогаем)
          // -----------------------------
          Object.getOwnPropertySymbols = function (obj) {
            const list = origGetOwnPropertySymbols(obj);
            return list; // символы редко нужно скрывать
          };

          // -----------------------------
          // Patch: getPrototypeOf (просто прокидываем оригинал)
          // -----------------------------
          Object.getPrototypeOf = function (obj) {
            return origGetPrototypeOf(obj);
          };
        }

        // ====== возвращаем пользовательскую функцию ======
        return function overrideDescriptorValue(obj, key) {
          rules.push({ obj, key });
          applyPatch();
        };
      })(),

      safeDefineNavGetter() {
        // Flexible signature:
        // safeDefineNavGetter(prop, getter, nameHint)
        // safeDefineNavGetter(targetObj, prop, getter, nameHint)
        const args = Array.prototype.slice.call(arguments);
        let target, prop, getter, nameHint;

        if (args.length === 0) return;

        if (typeof args[0] === 'object' && args[0] !== null && typeof args[1] === 'string') {
          target = args[0];
          prop = args[1];
          getter = args[2];
          nameHint = args[3];
        } else {
          prop = args[0];
          getter = args[1];
          nameHint = args[2];
          // prefer prototype of navigator if available, otherwise navigator itself
          if (typeof navigator !== 'undefined') {
            target = Object.getPrototypeOf(navigator) || navigator;
          } else {
            // nothing to define on
            return;
          }
        }

        try {
          const gfn = function () { return getter.call(this); };
          this.patchFnToString(gfn, `get ${nameHint || prop}`);

          Object.defineProperty(target, prop, {
            get: gfn,
            configurable: true,
            enumerable: true
          });

          // После определения геттера, скрываем само значение от Object.getOwnPropertyDescriptor
          this.overrideDescriptorValue(target, prop);
        } catch (e) { if (DEBUG) this.logError(e, `safeDefineNavGetter:${prop}`); }
      }

    };


    utils.preload();

    // Install global error handlers to capture uncaught errors and promise rejections
    try {
      const g = typeof globalThis !== 'undefined' ? globalThis : (typeof window !== 'undefined' ? window : self);
      if (g && typeof g.addEventListener === 'function') {
        try {
          g.addEventListener('error', (ev) => {
            try { utils.logError(ev.error || ev, 'global.error'); } catch (_) { }
          });
        } catch (_) { }

        try {
          g.addEventListener('unhandledrejection', (ev) => {
            try { utils.logError(ev.reason || ev, 'global.unhandledrejection'); } catch (_) { }
          });
        } catch (_) { }
      }

      // window.onerror fallback (only in page context)
      if (typeof window !== 'undefined') {
        try {
          const origOnError = window.onerror;
          window.onerror = function (msg, src, line, col, err) {
            try { utils.logError(err || msg, `window.onerror ${src}:${line}:${col}`); } catch (_) { }
            if (typeof origOnError === 'function') return origOnError.apply(this, arguments);
            return false;
          };
        } catch (_) { }
      }
    } catch (e) { if (DEBUG) try { console.error('Stealth: install global handlers failed', e); } catch (_) { } }

    /********************************************************************
     * 1. navigator.* базовые
     ********************************************************************/
    // Use Proxy to intercept all navigator property accesses and descriptor queries
    /********************************************************************
 * 1. navigator.* базовые — ПОЛНОСТЬЮ ПЕРЕПИСАННЫЙ РАБОЧИЙ БЛОК
 ********************************************************************/
    if (typeof navigator !== 'undefined') {
      const navProto = Object.getPrototypeOf(navigator);

      const navProps = {
        vendor: navCfg.vendor ?? (navigator.vendor || 'Google Inc.'),
        platform: navCfg.platform ?? (navigator.platform || 'Win32'),
        deviceMemory: navCfg.deviceMemory ?? chCfg.deviceMemory ?? (navigator.deviceMemory || 8),
        hardwareConcurrency: navCfg.hardwareConcurrency ?? (navigator.hardwareConcurrency || 8),
        maxTouchPoints: navCfg.maxTouchPoints ?? (navigator.maxTouchPoints || 0),
        languages: navCfg.languages ?? (navigator.languages || ['en-US', 'en']),
        language: navCfg.language ?? (navCfg.languages?.[0] ?? navigator.language ?? 'en-US'),
        webdriver: false,
        userAgent: navCfg.userAgent ?? (navigator.userAgent)
      };

      // На navigator НЕЛЬЗЯ ставить Proxy — Chrome не даст
      // И НЕЛЬЗЯ переопределять navigator целиком — configurable:false
      // Единственный рабочий вариант: ПЕРЕКРЫТЬ ПРОТОТИП Navigator.prototype

      Object.entries(navProps).forEach(([prop, value]) => {

        // webdriver — data-property, а не accessor
        if (prop === "webdriver") {
          try {
            utils.safeDefineNavGetter(navProto, prop, () => value, prop);
          } catch (e) { if (DEBUG) utils.logError(e, `navProp:${prop}`); }
        }

        // Все остальные свойства — обычные геттеры
        try {
          utils.safeDefineNavGetter(navProto, prop, () => value, prop);
        } catch (e) { if (DEBUG) utils.logError(e, `navPropDefine:${prop}`); }
      });
    }


    /********************************************************************
     * 2. navigator.userAgentData (UA Client Hints)
     ********************************************************************/
    (function () {
      const brands = chCfg.brands || [
        { brand: 'Google Chrome', version: '133' },
        { brand: 'Chromium', version: '133' },
        { brand: 'Not=A?Brand', version: '24' }
      ];
      const fullList = chCfg.fullVersionList || [
        { brand: 'Google Chrome', version: '133.0.6943.98' },
        { brand: 'Chromium', version: '133.0.6943.98' },
        { brand: 'Not=A?Brand', version: '24.0.0.0' }
      ];

      const uaData = {
        brands,
        fullVersionList: fullList,
        mobile: chCfg.mobile ?? false,
        platform: chCfg.platform ?? 'Windows',
        platformVersion: chCfg.platformVersion ?? '15.0.0',
        architecture: chCfg.architecture ?? 'x86',
        bitness: chCfg.bitness ?? '64',
        model: chCfg.model ?? '',
        uaFullVersion: chCfg.uaFullVersion ?? '133.0.6943.98',

        getHighEntropyValues(hints) {
          const result = {};
          (hints || []).forEach(h => {
            if (h in uaData) result[h] = uaData[h];
          });
          return Promise.resolve(result);
        },

        toJSON() {
          return {
            brands: this.brands,
            fullVersionList: this.fullVersionList,
            mobile: this.mobile,
            platform: this.platform,
            platformVersion: this.platformVersion,
            architecture: this.architecture,
            bitness: this.bitness,
            model: this.model,
            uaFullVersion: this.uaFullVersion
          };
        }
      };

      utils.patchFnToString(uaData.getHighEntropyValues, 'getHighEntropyValues');
      utils.patchFnToString(uaData.toJSON, 'toJSON');

      // Define userAgentData via navigator proxy or fallback
      if (typeof navigator !== 'undefined') {
        const navProto = Object.getPrototypeOf(navigator);
        utils.safeDefineNavGetter(navProto, 'userAgentData', () => uaData, 'userAgentData');
      }
    })();



    /********************************************************************
     * 3. Timezone spoof — только getTimezoneOffset + resolvedOptions
     ********************************************************************/
    (function () {
      const tzId = tzCfg.id || "Europe/Moscow";
      const desired = tzCfg.offsetMinutes ?? -180;   // -180 = Москва

      const OrigDate = Date;
      const origGetTimezoneOffset = OrigDate.prototype.getTimezoneOffset;
      const OrigParse = OrigDate.parse;
      const OrigResolved = Intl.DateTimeFormat.prototype.resolvedOptions;

      // --- getTimezoneOffset: сохраняем поведение this/null ---
      function patchedGetTimezoneOffset(...args) {
        // Если this не Date - ведём себя как оригинал (чтобы были те же TypeError при null/undefined)
        if (!(this instanceof OrigDate)) {
          return origGetTimezoneOffset.apply(this, args);
        }
        const real = origGetTimezoneOffset.call(this);
        const delta = desired - real;
        return real + delta;
      }
      utils.patchFnToString(patchedGetTimezoneOffset, "getTimezoneOffset");

      Object.defineProperty(OrigDate.prototype, "getTimezoneOffset", {
        value: patchedGetTimezoneOffset,
        writable: true,        // как у нативного
        configurable: true,
        enumerable: false
      });

      // --- Date.parse: мягкий сдвиг только для "чистых дат" ---
      const MDY = /^\d{2}\/\d{2}\/\d{4}$/;
      const YMD = /^\d{4}-\d{2}-\d{2}$/;
      const shouldShift = s => typeof s === "string" && (MDY.test(s) || YMD.test(s));

      Date.parse = function (str) {
        if (!shouldShift(str)) return OrigParse(str);
        const ts = OrigParse(str);
        if (isNaN(ts)) return ts;
        const realOffset = new OrigDate(ts).getTimezoneOffset();
        const shiftMinutes = desired - realOffset;
        return ts + shiftMinutes * 60000;
      };
      utils.patchFnToString(Date.parse, "parse");

      // --- Intl.DateTimeFormat.prototype.resolvedOptions: через bound-функцию без prototype ---


      const rawResolved = function (...args) {

        let o;

        try {
          // Если this нормальный — вызываем как есть
          o = OrigResolved.apply(this, args);
        } catch (e) {
          // Если this = null / undefined / не DTF-объект —
          // создаём временный валидный объект
          try {
            const dtf = new Intl.DateTimeFormat();
            o = OrigResolved.call(dtf);
          } catch (e2) {
            // Если даже это почему-то не удалось — возвращаем минимальный объект
            o = {};
          }
        }

        // Теперь точно есть объект
        o.timeZone = tzId;
        return o;
      };


      // bound-функции НЕ имеют собственного .prototype
      const wrappedResolved = rawResolved.bind(null);
      utils.patchFnToString(wrappedResolved, "resolvedOptions");

      Intl.DateTimeFormat.prototype.resolvedOptions = wrappedResolved;
    })();





    /********************************************************************
     * 4. Canvas / OffscreenCanvas: DISABLED due to detection
     ********************************************************************/
    // Canvas noise disabled


    /********************************************************************
     * 5. Audio fingerprint noise: DISABLED due to detection
     ********************************************************************/
    // Audio noise disabled


    /********************************************************************
     * 6. WebGL vendor/renderer spoof (37445 / 37446) — без accessor-магии
     ********************************************************************/
    (function () {
      const g = globalThis;

      const vendor = webglCfg.vendor || 'Intel Inc.';
      const renderer = webglCfg.renderer || 'Intel(R) Iris(R) Xe Graphics';

      const targets = [
        typeof g.WebGLRenderingContext !== "undefined" ? g.WebGLRenderingContext : null,
        typeof g.WebGL2RenderingContext !== "undefined" ? g.WebGL2RenderingContext : null
      ];

      targets.forEach(Ctx => {
        if (!Ctx || !Ctx.prototype || !Ctx.prototype.getParameter) return;

        const orig = Ctx.prototype.getParameter;

        function wrappedGetParameter(p) {
          if (p === 37445) return vendor;
          if (p === 37446) return renderer;
          return orig.call(this, p);
        }

        utils.patchFnToString(wrappedGetParameter, "getParameter");

        try {
          Object.defineProperty(Ctx.prototype, "getParameter", {
            value: wrappedGetParameter,
            writable: true,
            configurable: true,
            enumerable: false
          });
        } catch (e) {
          if (DEBUG) utils.logError(e, 'WebGL.defineProperty');
          // fallback, если defineProperty вдруг не сработает
          Ctx.prototype.getParameter = wrappedGetParameter;
        }
      });
    })();


    /********************************************************************
     * 7. navigator.permissions.query — notifications
     ********************************************************************/
    (function () {
      if (typeof navigator === 'undefined' || !navigator.permissions || !navigator.permissions.query) return;

      try {
        const orig = navigator.permissions.query;

        navigator.permissions.query = function (parameters) {
          // Avoid recursion: check if this is a notifications query
          if (parameters && parameters.name === 'notifications') {
            const permission = typeof Notification !== 'undefined' ? Notification.permission : 'default';
            return Promise.resolve({ state: permission });
          }
          // For all other queries, use original
          return orig.call(this, parameters);
        };

        utils.patchFnToString(navigator.permissions.query, 'query');
      } catch (e) { if (DEBUG) utils.logError(e, 'permissions.query.patch'); }
    })();


    /********************************************************************
     * 8. HTMLMediaElement.canPlayType — реалистичные ответы
     ********************************************************************/
    (function () {
      const g = globalThis;

      // Нет HTMLMediaElement → просто выходим (например, в worker)
      if (typeof g.HTMLMediaElement === "undefined" ||
        !g.HTMLMediaElement.prototype ||
        !g.HTMLMediaElement.prototype.canPlayType) {
        return;
      }

      const orig = g.HTMLMediaElement.prototype.canPlayType;

      const parseInput = (arg) => {
        const [mime, codecStr] = arg.trim().split(';');
        let codecs = [];
        if (codecStr && codecStr.includes('codecs="')) {
          codecs = codecStr
            .trim()
            .replace('codecs="', '')
            .replace('"', '')
            .split(',')
            .map(x => x.trim())
            .filter(Boolean);
        }
        return { mime, codecs };
      };

      const handler = {
        apply(target, thisArg, args) {
          if (!args || !args.length) {
            return utils.cache.Reflect.apply(target, thisArg, args);
          }
          const { mime, codecs } = parseInput(args[0]);

          if (mime === 'video/mp4' && codecs.includes('avc1.42E01E')) {
            return 'probably';
          }
          if (mime === 'audio/x-m4a' && !codecs.length) {
            return 'maybe';
          }
          if (mime === 'audio/aac' && !codecs.length) {
            return 'probably';
          }

          return utils.cache.Reflect.apply(target, thisArg, args);
        }
      };

      g.HTMLMediaElement.prototype.canPlayType =
        new Proxy(orig, utils.proxyWithCleanErrors(handler));

      utils.patchFnToString(
        g.HTMLMediaElement.prototype.canPlayType,
        'canPlayType'
      );
    })();


    /********************************************************************
     * 9. window.chrome.* (runtime, csi, loadTimes) — минимальный, но реалистичный
     ********************************************************************/
    (function () {
      const g = globalThis;   // окно или воркер

      // chrome API имеет смысл только в window
      if (typeof window === "undefined") return;

      // -------------------------
      // chrome object
      // -------------------------
      if (typeof g.chrome !== "object" || g.chrome === null) {
        utils.defineValue(g, "chrome", {});
      }

      const chrome = g.chrome;

      // -------------------------
      // chrome.runtime
      if (!chrome.runtime) {
        chrome.runtime = {
          get id() { return undefined; },
          connect() {
            return {
              postMessage() { },
              onMessage: { addListener() { }, removeListener() { }, hasListener() { return false; } },
              disconnect() { }
            };
          },
          sendMessage() { },
          onMessage: {
            addListener() { }, removeListener() { }, hasListener() { return false; }
          },
          onConnect: {
            addListener() { }, removeListener() { }, hasListener() { return false; }
          }
        };

        utils.patchFnToString(chrome.runtime.connect, "connect");
        utils.patchFnToString(chrome.runtime.sendMessage, "sendMessage");
      }

      // -------------------------
      // chrome.csi
      // -------------------------
      if (!chrome.csi && g.performance && performance.timing) {
        chrome.csi = function () {
          const t = performance.timing;
          return {
            onloadT: t.loadEventEnd,
            pageT: Date.now() - t.navigationStart,
            startE: t.navigationStart,
            tran: 15
          };
        };

        utils.patchFnToString(chrome.csi, "csi");
      }

      // -------------------------
      // chrome.loadTimes
      // -------------------------
      if (!chrome.loadTimes && g.performance && performance.timing) {
        chrome.loadTimes = function () {
          const t = performance.timing;
          return {
            requestTime: t.navigationStart / 1000,
            startLoadTime: t.navigationStart / 1000,
            commitLoadTime: t.responseStart / 1000,
            finishDocumentLoadTime: t.domContentLoadedEventEnd / 1000,
            finishLoadTime: t.loadEventEnd / 1000,
            firstPaintTime: (performance.getEntriesByType?.("paint")?.[0]?.startTime || t.loadEventEnd) / 1000,
            navigationType: "Other",
            wasFetchedViaSpdy: true,
            connectionInfo: "h2",
            npnNegotiatedProtocol: "h2",
            wasNpnNegotiated: true,
            wasAlternateProtocolAvailable: false
          };
        };

        utils.patchFnToString(chrome.loadTimes, "loadTimes");
      }
    })();



    /********************************************************************
     * 10. screen.* фиксы для headless — БЕЗ Proxy
     ********************************************************************/
    (function () {
      if (typeof window === "undefined" || typeof screen === "undefined") return;

      try {
        const screenProto = Object.getPrototypeOf(screen);
        if (!screenProto) return;

        const base = {
          width: 1920,
          height: 1080,
          availWidth: 1920,
          availHeight: 1080 - 80,
          colorDepth: 24,
          pixelDepth: 24
        };

        function defineScreenGetter(prop, compute) {
          try {
             utils.safeDefineNavGetter(screenProto, prop, compute, prop);
          } catch (e) { if (DEBUG) utils.logError(e, `screen.define:${prop}`); }
        }

        defineScreenGetter("width", () => window.innerWidth || base.width);
        defineScreenGetter("height", () => window.innerHeight || base.height);
        defineScreenGetter("availWidth", () => window.innerWidth || base.availWidth);
        defineScreenGetter("availHeight", () => {
          const h = window.innerHeight || base.height;
          return Math.max(0, h - 80);
        });
        defineScreenGetter("colorDepth", () => base.colorDepth);
        defineScreenGetter("pixelDepth", () => base.pixelDepth);
      } catch (e) { if (DEBUG) utils.logError(e, 'screen.block'); }
    })();


    /********************************************************************
     * 11. window.frameElement — null в топ-фрейме
     ********************************************************************/
    (function () {
      if (typeof window === "undefined") return;
      try {
        if (window.top === window) {
          Object.defineProperty(window, 'frameElement', {
            get() { return null; },
            configurable: false
          });
        }
      } catch (e) { if (DEBUG) utils.logError(e, 'frameElement.patch'); }
    })();


    /********************************************************************
     * 12. Патчирование Worker + nested Worker (Chrome/Safari/Firefox)
     ********************************************************************/
    (function () {

      function wrapWorkerCode(input, opts) {
        const stealthInit = `(${STEALTH_FUNC.toString()})(${JSON.stringify(cfg)});`;
        const isModule = opts && opts.type === 'module';

        // HTTP/HTTPS URL — загружаем как внешний скрипт с инъекцией stealth
        if (typeof input === 'string' && /^https?:/.test(input)) {
          if (isModule) {
            return `${stealthInit}\nimport(${JSON.stringify(input)});`;
          }
          return `${stealthInit}\nimportScripts(${JSON.stringify(input)});`;
        }

        // Blob объект — преобразуем в blob URL, читаем содержимое и обёртываем
        try {
          if (typeof Blob !== 'undefined' && input instanceof Blob) {
            // Синхронно читать Blob нельзя, но мы можем просто загрузить его через importScripts
            const blobURL = URL.createObjectURL(input);
            if (isModule) {
              return `${stealthInit}\nimport(${JSON.stringify(blobURL)});`;
            }
            return `${stealthInit}\nimportScripts(${JSON.stringify(blobURL)});`;
          }
        } catch (e) { if (DEBUG) utils.logError(e, 'wrapWorkerCode.blobDetect'); }

        // Blob URL (string, начинается с blob:) — тоже обёртываем через importScripts
        if (typeof input === 'string' && /^blob:/.test(input)) {
          if (isModule) {
            return `${stealthInit}\nimport(${JSON.stringify(input)});`;
          }
          return `${stealthInit}\nimportScripts(${JSON.stringify(input)});`;
        }

        // URL объект -> string
        try {
          if (typeof URL !== 'undefined' && input && input.constructor && input.constructor.name === 'URL') {
            const urlStr = input.toString();
            if (isModule) {
              return `${stealthInit}\nimport(${JSON.stringify(urlStr)});`;
            }
            return `${stealthInit}\nimportScripts(${JSON.stringify(urlStr)});`;
          }
        } catch (e) { if (DEBUG) utils.logError(e, 'wrapWorkerCode.urlObj'); }

        // Иначе это сырой код строка — обёртываем напрямую
        return `${stealthInit}\n${String(input)}`;
      }

      function patchWorkerConstructor(WorkerConstructor, isSharedWorker = false) {
        if (!WorkerConstructor) return;

        const OriginalWorker = WorkerConstructor;
        const replacementConstructor = function (input, opts) {
          try {
            const wrappedCode = wrapWorkerCode(input, opts);
            const blob = new Blob([wrappedCode], { type: 'application/javascript' });
            const blobURL = URL.createObjectURL(blob);

            const newOpts = Object.assign({}, opts || {});
            return new OriginalWorker(blobURL, newOpts);
          } catch (e) {
            if (DEBUG) utils.logError(e, 'patchWorkerConstructor.create');
            // fallback to original behavior
            return new OriginalWorker(input, opts);
          }
        };

        // Copy static methods and properties
        try {
          Object.setPrototypeOf(replacementConstructor, OriginalWorker);
          replacementConstructor.prototype = OriginalWorker.prototype;
        } catch (e) { if (DEBUG) utils.logError(e, 'patchWorkerConstructor.copyProto'); }

        return replacementConstructor;
      }

      function patchWorkerGlobals(globalObj) {
        if (!globalObj) return;

        // Patch dedicated Worker
        if (globalObj.Worker) {
          globalObj.Worker = patchWorkerConstructor(globalObj.Worker);
        }

        // Patch SharedWorker
        if (globalObj.SharedWorker) {
          globalObj.SharedWorker = patchWorkerConstructor(globalObj.SharedWorker, true);
        }
      }

      // Patch in top-level window (if available) and in worker global scope (self)
      try { if (typeof window !== "undefined") patchWorkerGlobals(window); } catch (e) { if (DEBUG) utils.logError(e, 'patchWorkerGlobals.window'); }
      try { if (typeof self !== "undefined") patchWorkerGlobals(self); } catch (e) { if (DEBUG) utils.logError(e, 'patchWorkerGlobals.self'); }

      // Also patch all existing frames (iframes)
      try {
        if (typeof window !== "undefined" && window.frames) {

          const patchFrames = () => {
            for (let i = 0; i < window.frames.length; i++) {
              try {
                const frame = window.frames[i];
                if (frame && frame.Worker) {
                  patchWorkerGlobals(frame);
                }
              } catch (e) {
                if (DEBUG) utils.logError(e, `patchFrames.inner:${i}`);
              }
            }
          };

          // Patch existing frames
          patchFrames();

          // Re-patch when new frames appear
          const OrigMutationObserver = window.MutationObserver;
          if (OrigMutationObserver) {

            const observeTarget = document.documentElement || document;

            const observer = new OrigMutationObserver(() => {
              patchFrames();
            });

            observer.observe(observeTarget, {
              childList: true,
              subtree: true
            });
          }
        }
      } catch (e) {
        if (DEBUG) utils.logError(e, 'patchFrames.outer');
      }




    })();
    if (DEBUG){
    console.log('Steath succes');
    }
  };   // <-- конец STEALTH_FUNC


  /********************************************************************
   * Запуск в окне
   ********************************************************************/
  try {
    STEALTH_FUNC(config);

  } catch (e) {
    try {
      const g = typeof globalThis !== 'undefined' ? globalThis : (typeof window !== 'undefined' ? window : self);
      if (g && g.__stealthErrorLogs && Array.isArray(g.__stealthErrorLogs)) {
        g.__stealthErrorLogs.push({ time: (new Date()).toISOString(), context: 'init', message: e && e.message, stack: e && e.stack });
      }
    } catch (_) { }
    if (config.debug ){
    console.error('Failed to initialize stealth:', e);
    }
  }

})(/*CONFIG_INJECTION*/);
//# sourceURL=all_in_one_stealth.js