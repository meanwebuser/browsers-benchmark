(function (config) {
  'use strict';

  /************************************************************************************************
   * STEALTH ENGINE v2.0 - Comprehensive Browser Fingerprint Spoofing
   * 
   * Features:
   * - Navigator properties spoofing
   * - User-Agent Client Hints (UAData)
   * - Timezone manipulation
   * - WebGL vendor/renderer spoofing
   * - Canvas fingerprint noise
   * - Audio fingerprint noise
   * - Screen properties
   * - Chrome API emulation
   * - Worker injection
   * - Plugin/MimeType spoofing
   * - WebRTC leak prevention
   * - Font detection protection
   * - Performance API normalization
   * - Battery API spoofing
   * - Iframe handling
   ************************************************************************************************/

  const STEALTH_FUNC = (function initStealthEngine(cfg) {
    cfg = cfg || {};
    
    // Configuration with defaults
    const DEBUG = !!cfg.debug;
    const browserPlatform = String(cfg.platform || 'chrome').toLowerCase();
    const isChrome = browserPlatform === 'chrome';
    const navCfg = cfg.navigator || {};
    const tzCfg = cfg.timezone || {};
    const chCfg = cfg.uaClientHints || {};
    const webglCfg = cfg.webgl || {};
    const canvasCfg = cfg.canvas || {};
    const audioCfg = cfg.audio || {};
    const screenCfg = cfg.screen || {};
    const pluginCfg = cfg.plugins || {};
    const webrtcCfg = cfg.webrtc || {};
    const perfCfg = cfg.performance || {};

    // Default configurations
    const CANVAS_DEFAULTS = {
      enabled: true,
      noiseAmplitude: 0.0001,
      noiseMode: 'random', // 'random', 'consistent'
      seed: null
    };
    const canvasConfig = { ...CANVAS_DEFAULTS, ...canvasCfg };

    const AUDIO_DEFAULTS = {
      enabled: true,
      noiseAmplitude: 0.0001,
      noiseType: 'gaussian' // 'gaussian', 'uniform'
    };
    const audioConfig = { ...AUDIO_DEFAULTS, ...audioCfg };

    const WEBRTC_DEFAULTS = {
      enabled: true,
      mode: 'disabled' // 'disabled', 'proxy', 'native'
    };
    const webrtcConfig = { ...WEBRTC_DEFAULTS, ...webrtcCfg };

    /************************************************************************************************
     * UTILITY LAYER
     ************************************************************************************************/
    const Utils = {
      cache: { ready: false },
      errorLog: [],
      maxLogSize: 100,

      // Initialize cached references to native functions
      preload() {
        if (this.cache.ready) return;

        this.cache = {
          ready: true,
          Reflect: {
            get: Reflect.get.bind(Reflect),
            set: Reflect.set.bind(Reflect),
            apply: Reflect.apply.bind(Reflect),
            ownKeys: Reflect.ownKeys.bind(Reflect),
            getOwnPropertyDescriptor: Reflect.getOwnPropertyDescriptor.bind(Reflect),
            has: Reflect.has.bind(Reflect)
          },
          nativeToString: Function.prototype.toString,
          nativeDefineProperty: Object.defineProperty,
          nativeGetOwnPropertyDescriptor: Object.getOwnPropertyDescriptor,
          nativeGetPrototypeOf: Object.getPrototypeOf,
          nativeSetPrototypeOf: Object.setPrototypeOf,
          nativeCreate: Object.create,
          nativeKeys: Object.keys,
          nativeFreeze: Object.freeze,
          nativeProxy: Proxy,
          // Store native prototype references
          nativeDate: Date,
          nativeArray: Array,
          nativeObject: Object,
          nativeFunction: Function
        };

        // Generate native function string template
        this.cache.nativeStringTemplate = this.cache.nativeToString.call(Function.prototype.toString);
      },

      // Centralized error logging
      logError(err, context = 'unknown', severity = 'error') {
        const entry = {
          timestamp: Date.now(),
          iso: new Date().toISOString(),
          context,
          severity,
          message: err?.message || String(err),
          stack: this.sanitizeStack(err?.stack)
        };

        this.errorLog.push(entry);
        if (this.errorLog.length > this.maxLogSize) {
          this.errorLog.shift();
        }

        // Store globally for debugging
        try {
          const g = this.getGlobal();
          if (!g.__stealthErrorLog) g.__stealthErrorLog = [];
          g.__stealthErrorLog.push(entry);
        } catch (_) {}

        if (DEBUG) {
          console[severity === 'warning' ? 'warn' : 'error'](
            `[Stealth:${context}]`, entry.message
          );
        }
      },

      // Sanitize stack traces to remove stealth internals
      sanitizeStack(stack) {
        if (!stack) return null;
        return stack
          .split('\n')
          .filter(line => !/STEALTH_FUNC|stealth|Utils|Proxy|Reflect/i.test(line))
          .join('\n');
      },

      // Get global object safely
      getGlobal() {
        if (typeof globalThis !== 'undefined') return globalThis;
        if (typeof window !== 'undefined') return window;
        if (typeof self !== 'undefined') return self;
        return (new Function('return this'))();
      },

      // Generate native-looking function string
      makeNativeString(name = 'toString') {
        this.preload();
        return this.cache.nativeStringTemplate
          .replace('toString', name)
          .replace('Function', 'function');
      },

      // Patch function to appear native
      patchNative(fn, name = fn?.name || 'anonymous') {
        if (typeof fn !== 'function') return fn;
        
        const nativeStr = this.makeNativeString(name);
        
        try {
          this.cache.nativeDefineProperty.call(Object, fn, 'toString', {
            value: function toString() { return nativeStr; },
            configurable: true,
            writable: true,
            enumerable: false
          });

          this.cache.nativeDefineProperty.call(Object, fn, 'name', {
            value: name,
            configurable: true,
            writable: false,
            enumerable: false
          });
        } catch (e) {
          if (DEBUG) this.logError(e, 'patchNative');
        }

        return fn;
      },

      // Create a proxy with clean error handling
      createCleanProxy(target, handler) {
        const wrappedHandler = {};
        
        for (const trap of Object.keys(handler)) {
          const orig = handler[trap];
          wrappedHandler[trap] = (...args) => {
            try {
              const result = orig.apply(null, args);
              return result;
            } catch (e) {
              if (e?.stack) {
                e.stack = this.sanitizeStack(e.stack);
              }
              throw e;
            }
          };
        }

        return new this.cache.nativeProxy(target, wrappedHandler);
      },

      // Deep clone an object
      deepClone(obj) {
        if (obj === null || typeof obj !== 'object') return obj;
        if (obj instanceof Date) return new Date(obj.getTime());
        if (obj instanceof Array) return obj.map(item => this.deepClone(item));
        if (obj instanceof Object) {
          const copy = {};
          for (const key of Object.keys(obj)) {
            copy[key] = this.deepClone(obj[key]);
          }
          return copy;
        }
        return obj;
      },

      // Generate deterministic noise from seed
      seededRandom(seed) {
        const x = Math.sin(seed++) * 10000;
        return x - Math.floor(x);
      },

      // Gaussian random number (Box-Muller transform)
      gaussianRandom(mean = 0, std = 1) {
        const u1 = Math.random();
        const u2 = Math.random();
        const z0 = Math.sqrt(-2 * Math.log(u1)) * Math.cos(2 * Math.PI * u2);
        return z0 * std + mean;
      },

      // Define a getter property that looks native
      defineNativeGetter(obj, prop, getter, options = {}) {
        this.preload();
        
        const opts = {
          configurable: true,
          enumerable: true,
          ...options
        };

        const getterFn = typeof getter === 'function' ? getter : () => getter;
        this.patchNative(getterFn, `get ${prop}`);

        try {
          this.cache.nativeDefineProperty.call(Object, obj, prop, {
            get: getterFn,
            configurable: opts.configurable,
            enumerable: opts.enumerable
          });
          return true;
        } catch (e) {
          if (DEBUG) this.logError(e, `defineNativeGetter:${prop}`);
          return false;
        }
      },

      // Define a value property that looks native
      defineNativeValue(obj, prop, value, options = {}) {
        this.preload();
        
        const opts = {
          configurable: true,
          writable: true,
          enumerable: true,
          ...options
        };

        try {
          this.cache.nativeDefineProperty.call(Object, obj, prop, {
            value,
            configurable: opts.configurable,
            writable: opts.writable,
            enumerable: opts.enumerable
          });
          return true;
        } catch (e) {
          if (DEBUG) this.logError(e, `defineNativeValue:${prop}`);
          return false;
        }
      },

      // Override property descriptor to hide spoofing
      descriptorOverrides: [],
      
      overrideDescriptor(obj, key, fakeDesc) {
        this.descriptorOverrides.push({ obj, key, fakeDesc });
        this.applyDescriptorPatch();
      },

      applyDescriptorPatch() {
        if (this.cache.descriptorPatched) return;
        this.cache.descriptorPatched = true;

        const origGetOwnPropertyDescriptor = Object.getOwnPropertyDescriptor;
        const self = this;

        Object.getOwnPropertyDescriptor = function(obj, key) {
          const override = self.descriptorOverrides.find(
            o => o.obj === obj && o.key === key
          );
          
          if (override) {
            return override.fakeDesc;
          }
          
          return origGetOwnPropertyDescriptor.call(this, obj, key);
        };

        this.patchNative(Object.getOwnPropertyDescriptor, 'getOwnPropertyDescriptor');
      }
    };

    Utils.preload();

    /************************************************************************************************
     * NAVIGATOR SPOOFING
     ************************************************************************************************/
    const NavigatorSpoof = {
      // Default navigator values
      defaults: {
        vendor: 'Google Inc.',
        vendorSub: '',
        productSub: '20030107',
        platform: 'Win32',
        appName: 'Netscape',
        appVersion: '5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36',
        userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36',
        product: 'Gecko',
        language: 'en-US',
        languages: ['en-US', 'en'],
        deviceMemory: 8,
        hardwareConcurrency: 8,
        maxTouchPoints: 0,
        cookiesEnabled: true,
        doNotTrack: null,
        pdfViewerEnabled: true,
        webdriver: false,
        ink: undefined,
        persisted: false,
        onLine: true,
        globalPrivacyControl: undefined,
        clipboard: undefined,
        credentials: undefined,
        keyboard: undefined,
        locks: undefined,
        mediaDevices: undefined,
        mediaSession: undefined,
        permissions: undefined,
        presentation: undefined,
        serial: undefined,
        storage: undefined,
        virtualKeyboard: undefined,
        wakeLock: undefined,
        windowControlsOverlay: undefined
      },

      apply() {
        if (typeof navigator === 'undefined') return;

        const navProto = Utils.cache.nativeGetPrototypeOf.call(Object, navigator);
        if (!navProto) return;

        // Merge config with defaults
        const values = { ...this.defaults, ...navCfg };

        // Ensure language/languages consistency
        if (navCfg.languages && !navCfg.language) {
          values.language = navCfg.languages[0];
        }
        if (navCfg.language && !navCfg.languages) {
          values.languages = [navCfg.language, navCfg.language.split('-')[0]];
        }

        // Define all navigator properties
        const props = {
          // Accessor properties
          vendor: { type: 'getter', value: () => values.vendor },
          vendorSub: { type: 'getter', value: () => values.vendorSub },
          productSub: { type: 'getter', value: () => values.productSub },
          platform: { type: 'getter', value: () => values.platform },
          appName: { type: 'getter', value: () => values.appName },
          appVersion: { type: 'getter', value: () => values.appVersion },
          userAgent: { type: 'getter', value: () => values.userAgent },
          product: { type: 'getter', value: () => values.product },
          language: { type: 'getter', value: () => values.language },
          languages: { 
            type: 'getter', 
            value: () => values.languages.slice() // Return new array each time
          },
          deviceMemory: { type: 'getter', value: () => values.deviceMemory },
          hardwareConcurrency: { type: 'getter', value: () => values.hardwareConcurrency },
          maxTouchPoints: { type: 'getter', value: () => values.maxTouchPoints },
          cookieEnabled: { type: 'getter', value: () => values.cookiesEnabled },
          doNotTrack: { type: 'getter', value: () => values.doNotTrack },
          pdfViewerEnabled: { type: 'getter', value: () => values.pdfViewerEnabled },
          webdriver: { type: 'getter', value: () => values.webdriver },
          ink: { type: 'getter', value: () => values.ink },
          onLine: { type: 'getter', value: () => values.onLine },
          globalPrivacyControl: { type: 'getter', value: () => values.globalPrivacyControl }
        };

        for (const [prop, config] of Object.entries(props)) {
          try {
            if (config.type === 'getter') {
              Utils.defineNativeGetter(navProto, prop, config.value);
            }
          } catch (e) {
            if (DEBUG) Utils.logError(e, `NavigatorSpoof:${prop}`);
          }
        }

        // Apply additional patches
        this.patchPermissions();
        this.patchConnection();
      },

      // Patch permissions API
      patchPermissions() {
        if (!navigator.permissions) return;

        const origQuery = navigator.permissions.query.bind(navigator.permissions);
        const self = this;

        const queryCache = new Map();

        navigator.permissions.query = function(parameters) {
          const key = JSON.stringify(parameters);
          
          // Check cache first
          if (queryCache.has(key)) {
            return Promise.resolve(queryCache.get(key));
          }

          // Handle specific permissions
          if (parameters?.name === 'notifications') {
            const result = { 
              state: typeof Notification !== 'undefined' ? Notification.permission : 'prompt',
              onchange: null
            };
            Utils.patchNative(result, 'PermissionStatus');
            queryCache.set(key, result);
            return Promise.resolve(result);
          }

          if (parameters?.name === 'geolocation') {
            const result = { state: 'prompt', onchange: null };
            queryCache.set(key, result);
            return Promise.resolve(result);
          }

          return origQuery(parameters).catch(() => {
            const result = { state: 'prompt', onchange: null };
            return result;
          });
        };

        Utils.patchNative(navigator.permissions.query, 'query');
      },

      // Patch network connection info
      patchConnection() {
        if (!navigator.connection) return;

        const connDefaults = {
          effectiveType: '4g',
          downlink: 10,
          rtt: 50,
          saveData: false,
          downlinkMax: Infinity,
          type: 'unknown'
        };

        const connProto = Utils.cache.nativeGetPrototypeOf.call(Object, navigator.connection);
        if (!connProto) return;

        for (const [prop, value] of Object.entries(connDefaults)) {
          Utils.defineNativeGetter(connProto, prop, () => value);
        }
      }
    };

    /************************************************************************************************
     * USER-AGENT CLIENT HINTS SPOOFING
     ************************************************************************************************/
    const ClientHintsSpoof = {
      apply() {
        if (!isChrome) return;
        if (typeof navigator === 'undefined') return;

        const brands = chCfg.brands || [
          { brand: 'Google Chrome', version: '133' },
          { brand: 'Chromium', version: '133' },
          { brand: 'Not=A?Brand', version: '24' }
        ];

        const fullVersionList = chCfg.fullVersionList || [
          { brand: 'Google Chrome', version: '133.0.6943.98' },
          { brand: 'Chromium', version: '133.0.6943.98' },
          { brand: 'Not=A?Brand', version: '24.0.0.0' }
        ];

        const uaData = {
          brands: brands,
          mobile: chCfg.mobile ?? false,
          platform: chCfg.platform ?? 'Windows',
          getHighEntropyValues: function(hints) {
            const result = {};
            const fullData = {
              brands: brands,
              fullVersionList: fullVersionList,
              mobile: chCfg.mobile ?? false,
              platform: chCfg.platform ?? 'Windows',
              platformVersion: chCfg.platformVersion ?? '15.0.0',
              architecture: chCfg.architecture ?? 'x86',
              bitness: chCfg.bitness ?? '64',
              model: chCfg.model ?? '',
              uaFullVersion: chCfg.uaFullVersion ?? '133.0.6943.98',
              wow64: chCfg.wow64 ?? false,
              formFactor: chCfg.formFactor ?? ['Desktop'],
              formFactors: chCfg.formFactors ?? ['Desktop']
            };

            if (Array.isArray(hints)) {
              for (const hint of hints) {
                if (hint in fullData) {
                  result[hint] = fullData[hint];
                }
              }
            }

            return Promise.resolve(result);
          },
          toJSON: function() {
            return {
              brands: this.brands,
              mobile: this.mobile,
              platform: this.platform
            };
          }
        };

        Utils.patchNative(uaData.getHighEntropyValues, 'getHighEntropyValues');
        Utils.patchNative(uaData.toJSON, 'toJSON');

        // Freeze to prevent modification
        Utils.cache.nativeFreeze.call(Object, uaData);

        const navProto = Utils.cache.nativeGetPrototypeOf.call(Object, navigator);
        Utils.defineNativeGetter(navProto, 'userAgentData', () => uaData);
      }
    };

    /************************************************************************************************
     * TIMEZONE SPOOFING
     ************************************************************************************************/
    const TimezoneSpoof = {
      apply() {
        const tzId = tzCfg.id || 'Europe/Moscow';
        const desiredOffset = tzCfg.offsetMinutes ?? -180;

        const OrigDate = Date;
        const origGetTimezoneOffset = OrigDate.prototype.getTimezoneOffset;
        const origParse = OrigDate.parse;
        const origNow = OrigDate.now;
        const origToString = OrigDate.prototype.toString;
        const origToTimeString = OrigDate.prototype.toTimeString;

        // Patch getTimezoneOffset
        const patchedGetTimezoneOffset = function getTimezoneOffset() {
          if (!(this instanceof OrigDate)) {
            return origGetTimezoneOffset.apply(this, arguments);
          }
          const realOffset = origGetTimezoneOffset.call(this);
          return realOffset + (desiredOffset - realOffset);
        };

        Utils.patchNative(patchedGetTimezoneOffset, 'getTimezoneOffset');
        Utils.defineNativeValue(OrigDate.prototype, 'getTimezoneOffset', patchedGetTimezoneOffset);

        // Patch Date.parse for date-only strings
        const dateOnlyPatterns = [
          /^\d{4}-\d{2}-\d{2}$/,
          /^\d{2}\/\d{2}\/\d{4}$/,
          /^\d{4}\/\d{2}\/\d{2}$/,
          /^\d{2}-\d{2}-\d{4}$/
        ];

        const isDateOnlyString = (str) => {
          return typeof str === 'string' && dateOnlyPatterns.some(p => p.test(str.trim()));
        };

        OrigDate.parse = function parse(dateStr) {
          const result = origParse(dateStr);
          if (isNaN(result) || !isDateOnlyString(dateStr)) {
            return result;
          }
          
          const tempDate = new OrigDate(result);
          const realOffset = origGetTimezoneOffset.call(tempDate);
          const shiftMs = (desiredOffset - realOffset) * 60000;
          
          return result + shiftMs;
        };

        Utils.patchNative(OrigDate.parse, 'parse');

        // Patch toTimeString to show spoofed timezone
        const patchedToTimeString = function toTimeString() {
          const result = origToTimeString.call(this);
          // Replace timezone abbreviation with consistent value
          return result.replace(/\s*\([^)]+\)$/, ` (${tzId})`);
        };

        Utils.patchNative(patchedToTimeString, 'toTimeString');
        Utils.defineNativeValue(OrigDate.prototype, 'toTimeString', patchedToTimeString);

        // Patch Intl.DateTimeFormat
        this.patchIntlDateTimeFormat(tzId);
      },

      patchIntlDateTimeFormat(tzId) {
        const origResolvedOptions = Intl.DateTimeFormat.prototype.resolvedOptions;
        
        const patchedResolvedOptions = function resolvedOptions() {
          let result;
          try {
            result = origResolvedOptions.call(this);
          } catch (e) {
            result = origResolvedOptions.call(new Intl.DateTimeFormat());
          }
          
          result.timeZone = tzId;
          result.timeZoneName = result.timeZoneName || 'long';
          
          return result;
        };

        Utils.patchNative(patchedResolvedOptions, 'resolvedOptions');
        Utils.defineNativeValue(
          Intl.DateTimeFormat.prototype, 
          'resolvedOptions', 
          patchedResolvedOptions
        );

        // Patch Intl.DateTimeFormat constructor to use spoofed timezone
        const OrigDateTimeFormat = Intl.DateTimeFormat;
        Intl.DateTimeFormat = function DateTimeFormat(locales, options) {
          if (options && typeof options === 'object') {
            options = { ...options };
          } else if (!options) {
            options = {};
          }
          
          // Don't override if explicitly set
          if (!options.timeZone) {
            options.timeZone = tzId;
          }
          
          return new OrigDateTimeFormat(locales, options);
        };

        Intl.DateTimeFormat.prototype = OrigDateTimeFormat.prototype;
        Intl.DateTimeFormat.supportedLocalesOf = OrigDateTimeFormat.supportedLocalesOf;
        Utils.patchNative(Intl.DateTimeFormat, 'DateTimeFormat');
      }
    };

    /************************************************************************************************
     * WEBGL SPOOFING
     ************************************************************************************************/
    const WebGLSpoof = {
      apply() {
        const vendor = webglCfg.vendor || 'Intel Inc.';
        const renderer = webglCfg.renderer || 'Intel(R) Iris(R) Xe Graphics';
        const unmaskedVendor = webglCfg.unmaskedVendor || vendor;
        const unmaskedRenderer = webglCfg.unmaskedRenderer || renderer;

        const contexts = [
          typeof WebGLRenderingContext !== 'undefined' ? WebGLRenderingContext : null,
          typeof WebGL2RenderingContext !== 'undefined' ? WebGL2RenderingContext : null
        ].filter(Boolean);

        for (const Ctx of contexts) {
          if (!Ctx?.prototype?.getParameter) continue;

          const origGetParameter = Ctx.prototype.getParameter;
          const self = this;

          const patchedGetParameter = function getParameter(pname) {
            // UNMASKED_VENDOR_WEBGL
            if (pname === 37445) return vendor;
            // UNMASKED_RENDERER_WEBGL
            if (pname === 37446) return renderer;
            // VERSION
            if (pname === 0x1F02) {
              const orig = origGetParameter.call(this, pname);
              // Make sure version string is consistent with renderer
              return orig;
            }
            // SHADING_LANGUAGE_VERSION
            if (pname === 0x8B8C) {
              return 'WebGL GLSL ES 3.00';
            }
            // MAX_TEXTURE_SIZE - normalize across devices
            if (pname === 0x0D33) {
              const orig = origGetParameter.call(this, pname);
              return Math.min(orig, 16384);
            }
            // MAX_RENDERBUFFER_SIZE
            if (pname === 0x84E8) {
              const orig = origGetParameter.call(this, pname);
              return Math.min(orig, 16384);
            }

            return origGetParameter.call(this, pname);
          };

          Utils.patchNative(patchedGetParameter, 'getParameter');
          Utils.defineNativeValue(Ctx.prototype, 'getParameter', patchedGetParameter);

          // Also patch getExtension to hide debug renderer info
          const origGetExtension = Ctx.prototype.getExtension;
          const patchedGetExtension = function getExtension(name) {
            const ext = origGetExtension.call(this, name);
            
            if (name === 'WEBGL_debug_renderer_info' && ext) {
              // Return a modified extension object
              return {
                UNMASKED_VENDOR_WEBGL: 37445,
                UNMASKED_RENDERER_WEBGL: 37446
              };
            }
            
            return ext;
          };

          Utils.patchNative(patchedGetExtension, 'getExtension');
          Utils.defineNativeValue(Ctx.prototype, 'getExtension', patchedGetExtension);
        }

        // Patch getSupportedExtensions to be consistent
        for (const Ctx of contexts) {
          if (!Ctx?.prototype?.getSupportedExtensions) continue;

          const origGetSupportedExtensions = Ctx.prototype.getSupportedExtensions;
          const patchedGetSupportedExtensions = function getSupportedExtensions() {
            const exts = origGetSupportedExtensions.call(this) || [];
            // Ensure WEBGL_debug_renderer_info is in the list
            if (!exts.includes('WEBGL_debug_renderer_info')) {
              exts.push('WEBGL_debug_renderer_info');
            }
            return exts;
          };

          Utils.patchNative(patchedGetSupportedExtensions, 'getSupportedExtensions');
          Utils.defineNativeValue(Ctx.prototype, 'getSupportedExtensions', patchedGetSupportedExtensions);
        }
      }
    };

    /************************************************************************************************
     * CANVAS FINGERPRINT NOISE
     ************************************************************************************************/
    const CanvasSpoof = {
      noiseSeed: null,

      apply() {
        if (!canvasConfig.enabled) return;

        this.noiseSeed = canvasConfig.seed || Date.now();

        const contexts = ['2d', 'webgl', 'webgl2', 'bitmaprenderer'];

        // Patch HTMLCanvasElement.getContext
        const origGetContext = HTMLCanvasElement.prototype.getContext;
        const self = this;

        HTMLCanvasElement.prototype.getContext = function getContext(type, options) {
          const ctx = origGetContext.call(this, type, options);
          
          if (!ctx) return ctx;

          if (type === '2d') {
            self.patch2DContext(ctx);
          } else if (type === 'webgl' || type === 'webgl2') {
            self.patchWebGLContext(ctx);
          }

          return ctx;
        };

        Utils.patchNative(HTMLCanvasElement.prototype.getContext, 'getContext');

        // Patch toDataURL
        const origToDataURL = HTMLCanvasElement.prototype.toDataURL;
        HTMLCanvasElement.prototype.toDataURL = function toDataURL(type, quality) {
          // Add noise before extraction
          const ctx = origGetContext.call(this, '2d');
          if (ctx) {
            self.addCanvasNoise(this, ctx);
          }
          return origToDataURL.call(this, type, quality);
        };
        Utils.patchNative(HTMLCanvasElement.prototype.toDataURL, 'toDataURL');

        // Patch toBlob
        const origToBlob = HTMLCanvasElement.prototype.toBlob;
        HTMLCanvasElement.prototype.toBlob = function toBlob(callback, type, quality) {
          const ctx = origGetContext.call(this, '2d');
          if (ctx) {
            self.addCanvasNoise(this, ctx);
          }
          return origToBlob.call(this, callback, type, quality);
        };
        Utils.patchNative(HTMLCanvasElement.prototype.toBlob, 'toBlob');

        // Patch OffscreenCanvas if available
        if (typeof OffscreenCanvas !== 'undefined') {
          this.patchOffscreenCanvas();
        }
      },

      patch2DContext(ctx) {
        const origGetImageData = ctx.getImageData.bind(ctx);
        const origFillText = ctx.fillText.bind(ctx);
        const origStrokeText = ctx.strokeText.bind(ctx);
        const self = this;

        // Patch getImageData
        ctx.getImageData = function getImageData(x, y, w, h) {
          const data = origGetImageData(x, y, w, h);
          self.addPixelNoise(data.data);
          return data;
        };
        Utils.patchNative(ctx.getImageData, 'getImageData');
      },

      patchWebGLContext(gl) {
        const origReadPixels = gl.readPixels.bind(gl);
        const self = this;

        gl.readPixels = function readPixels(x, y, width, height, format, type, pixels) {
          origReadPixels(x, y, width, height, format, type, pixels);
          if (pixels instanceof ArrayBuffer || ArrayBuffer.isView(pixels)) {
            self.addPixelNoise(new Uint8Array(pixels));
          }
        };
        Utils.patchNative(gl.readPixels, 'readPixels');
      },

      addPixelNoise(data) {
        const amplitude = canvasConfig.noiseAmplitude;
        
        for (let i = 0; i < data.length; i += 4) {
          // Skip fully transparent pixels
          if (data[i + 3] === 0) continue;

          // Add subtle noise to RGB channels
          for (let c = 0; c < 3; c++) {
            const noise = (Math.random() - 0.5) * amplitude * 255;
            data[i + c] = Math.max(0, Math.min(255, data[i + c] + noise));
          }
        }
      },

      addCanvasNoise(canvas, ctx) {
        // Add invisible noise to canvas
        const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
        this.addPixelNoise(imageData.data);
        ctx.putImageData(imageData, 0, 0);
      },

      patchOffscreenCanvas() {
        const origGetContext = OffscreenCanvas.prototype.getContext;
        const self = this;

        OffscreenCanvas.prototype.getContext = function getContext(type, options) {
          const ctx = origGetContext.call(this, type, options);
          if (!ctx) return ctx;

          if (type === '2d') {
            self.patch2DContext(ctx);
          } else if (type === 'webgl' || type === 'webgl2') {
            self.patchWebGLContext(ctx);
          }

          return ctx;
        };

        Utils.patchNative(OffscreenCanvas.prototype.getContext, 'getContext');
      }
    };

    /************************************************************************************************
     * AUDIO FINGERPRINT NOISE
     ************************************************************************************************/
    const AudioSpoof = {
      apply() {
        if (!audioConfig.enabled) return;

        if (typeof AudioContext === 'undefined' && typeof webkitAudioContext === 'undefined') {
          return;
        }

        const OrigAudioContext = AudioContext || webkitAudioContext;
        const origCreateAnalyser = OrigAudioContext.prototype.createAnalyser;
        const origCreateOscillator = OrigAudioContext.prototype.createOscillator;
        const self = this;

        // Patch createAnalyser
        OrigAudioContext.prototype.createAnalyser = function createAnalyser() {
          const analyser = origCreateAnalyser.call(this);
          self.patchAnalyser(analyser);
          return analyser;
        };
        Utils.patchNative(OrigAudioContext.prototype.createAnalyser, 'createAnalyser');

        // Patch createOscillator
        OrigAudioContext.prototype.createOscillator = function createOscillator() {
          const oscillator = origCreateOscillator.call(this);
          return oscillator;
        };
        Utils.patchNative(OrigAudioContext.prototype.createOscillator, 'createOscillator');

        // Patch OfflineAudioContext
        if (typeof OfflineAudioContext !== 'undefined') {
          const OrigOfflineAudioContext = OfflineAudioContext;
          const origStartRendering = OrigOfflineAudioContext.prototype.startRendering;

          OrigOfflineAudioContext.prototype.startRendering = function startRendering() {
            const promise = origStartRendering.call(this);
            return promise.then(buffer => {
              self.addAudioNoise(buffer);
              return buffer;
            });
          };

          Utils.patchNative(OrigOfflineAudioContext.prototype.startRendering, 'startRendering');
        }
      },

      patchAnalyser(analyser) {
        const origGetFloatFrequencyData = analyser.getFloatFrequencyData.bind(analyser);
        const origGetByteFrequencyData = analyser.getByteFrequencyData.bind(analyser);
        const origGetFloatTimeDomainData = analyser.getFloatTimeDomainData.bind(analyser);
        const origGetByteTimeDomainData = analyser.getByteTimeDomainData.bind(analyser);
        const self = this;

        analyser.getFloatFrequencyData = function getFloatFrequencyData(array) {
          origGetFloatFrequencyData(array);
          self.addArrayNoise(array);
        };
        Utils.patchNative(analyser.getFloatFrequencyData, 'getFloatFrequencyData');

        analyser.getByteFrequencyData = function getByteFrequencyData(array) {
          origGetByteFrequencyData(array);
          self.addArrayNoise(array, 255);
        };
        Utils.patchNative(analyser.getByteFrequencyData, 'getByteFrequencyData');

        analyser.getFloatTimeDomainData = function getFloatTimeDomainData(array) {
          origGetFloatTimeDomainData(array);
          self.addArrayNoise(array);
        };
        Utils.patchNative(analyser.getFloatTimeDomainData, 'getFloatTimeDomainData');

        analyser.getByteTimeDomainData = function getByteTimeDomainData(array) {
          origGetByteTimeDomainData(array);
          self.addArrayNoise(array, 255);
        };
        Utils.patchNative(analyser.getByteTimeDomainData, 'getByteTimeDomainData');
      },

      addArrayNoise(array, maxValue = 1) {
        const amplitude = audioConfig.noiseAmplitude;
        for (let i = 0; i < array.length; i++) {
          const noise = Utils.gaussianRandom(0, amplitude * maxValue);
          array[i] = Math.max(0, Math.min(maxValue, array[i] + noise));
        }
      },

      addAudioNoise(buffer) {
        for (let channel = 0; channel < buffer.numberOfChannels; channel++) {
          const data = buffer.getChannelData(channel);
          this.addArrayNoise(data);
        }
      }
    };

    /************************************************************************************************
     * PLUGIN & MIMETYPE SPOOFING
     ************************************************************************************************/
    const PluginSpoof = {
      apply() {
        if (typeof navigator === 'undefined') return;

        const plugins = pluginCfg.plugins || [
          {
            name: 'PDF Viewer',
            description: 'Portable Document Format',
            filename: 'internal-pdf-viewer',
            mimeTypes: ['application/pdf']
          }
        ];

        const mimeTypes = pluginCfg.mimeTypes || [
          {
            type: 'application/pdf',
            suffixes: 'pdf',
            description: 'Portable Document Format',
            enabledPlugin: 'PDF Viewer'
          }
        ];

        // Create Plugin objects
        const pluginArray = this.createPluginArray(plugins, mimeTypes);
        const mimeTypeArray = this.createMimeTypeArray(mimeTypes, pluginArray);

        const navProto = Utils.cache.nativeGetPrototypeOf.call(Object, navigator);

        Utils.defineNativeGetter(navProto, 'plugins', () => pluginArray);
        Utils.defineNativeGetter(navProto, 'mimeTypes', () => mimeTypeArray);
      },

      createPluginArray(plugins, mimeTypes) {
        const arr = [];

        for (let i = 0; i < plugins.length; i++) {
          const p = plugins[i];
          const plugin = this.createPlugin(p, i, mimeTypes);
          arr.push(plugin);
          arr[p.name] = plugin;
        }

        // Add array-like properties
        arr.length = plugins.length;
        arr.item = function item(index) {
          return this[index] || null;
        };
        arr.namedItem = function namedItem(name) {
          return this[name] || null;
        };
        arr.refresh = function refresh() {
          // No-op
        };

        Utils.patchNative(arr.item, 'item');
        Utils.patchNative(arr.namedItem, 'namedItem');
        Utils.patchNative(arr.refresh, 'refresh');

        return arr;
      },

      createPlugin(pluginData, index, mimeTypes) {
        const plugin = {
          name: pluginData.name,
          description: pluginData.description,
          filename: pluginData.filename,
          length: pluginData.mimeTypes?.length || 0
        };

        // Add mimeType references
        if (pluginData.mimeTypes) {
          for (let i = 0; i < pluginData.mimeTypes.length; i++) {
            const mt = mimeTypes.find(m => m.type === pluginData.mimeTypes[i]);
            if (mt) {
              plugin[i] = mt;
              plugin[mt.type] = mt;
            }
          }
        }

        plugin.item = function item(i) {
          return this[i] || null;
        };
        plugin.namedItem = function namedItem(name) {
          return this[name] || null;
        };

        Utils.patchNative(plugin.item, 'item');
        Utils.patchNative(plugin.namedItem, 'namedItem');

        return plugin;
      },

      createMimeTypeArray(mimeTypes, pluginArray) {
        const arr = [];

        for (let i = 0; i < mimeTypes.length; i++) {
          const mt = mimeTypes[i];
          const mimeType = {
            type: mt.type,
            suffixes: mt.suffixes,
            description: mt.description,
            enabledPlugin: pluginArray[mt.enabledPlugin] || null
          };
          arr.push(mimeType);
          arr[mt.type] = mimeType;
        }

        arr.length = mimeTypes.length;
        arr.item = function item(index) {
          return this[index] || null;
        };
        arr.namedItem = function namedItem(name) {
          return this[name] || null;
        };

        Utils.patchNative(arr.item, 'item');
        Utils.patchNative(arr.namedItem, 'namedItem');

        return arr;
      }
    };

    /************************************************************************************************
     * WEBRTC LEAK PROTECTION
     ************************************************************************************************/
    const WebRTCSpoof = {
      apply() {
        if (!webrtcConfig.enabled) return;

        if (typeof RTCPeerConnection === 'undefined') return;

        const OrigRTCPeerConnection = RTCPeerConnection;
        const self = this;

        if (webrtcConfig.mode === 'disabled') {
          // Completely disable WebRTC
          window.RTCPeerConnection = function RTCPeerConnection() {
            throw new TypeError('Illegal constructor');
          };
          Utils.patchNative(window.RTCPeerConnection, 'RTCPeerConnection');
          
          // Also disable related APIs
          if (typeof RTCSessionDescription !== 'undefined') {
            window.RTCSessionDescription = undefined;
          }
          if (typeof RTCIceCandidate !== 'undefined') {
            window.RTCIceCandidate = undefined;
          }
        } else if (webrtcConfig.mode === 'proxy') {
          // Use proxy mode - only allow configured ICE servers
          window.RTCPeerConnection = function(config, constraints) {
            const filteredConfig = self.filterIceConfig(config);
            return new OrigRTCPeerConnection(filteredConfig, constraints);
          };

          window.RTCPeerConnection.prototype = OrigRTCPeerConnection.prototype;
          Utils.patchNative(window.RTCPeerConnection, 'RTCPeerConnection');
        }
      },

      filterIceConfig(config) {
        if (!config) return {};
        
        const filtered = { ...config };
        
        // Remove any STUN/TURN servers that could leak IP
        if (filtered.iceServers) {
          filtered.iceServers = filtered.iceServers.filter(server => {
            // Only allow configured proxy servers
            return false;
          });
        }

        // Set to relay-only mode if possible
        filtered.iceTransportPolicy = 'relay';

        return filtered;
      }
    };

    /************************************************************************************************
     * SCREEN SPOOFING
     ************************************************************************************************/
    const ScreenSpoof = {
      apply() {
        if (typeof window === 'undefined' || typeof screen === 'undefined') return;

        const defaults = {
          width: 1920,
          height: 1080,
          availWidth: 1920,
          availHeight: 1000,
          colorDepth: 24,
          pixelDepth: 24,
          devicePixelRatio: 1
        };

        const config = { ...defaults, ...screenCfg };

        const screenProto = Utils.cache.nativeGetPrototypeOf.call(Object, screen);
        if (!screenProto) return;

        Utils.defineNativeGetter(screenProto, 'width', () => config.width);
        Utils.defineNativeGetter(screenProto, 'height', () => config.height);
        Utils.defineNativeGetter(screenProto, 'availWidth', () => config.availWidth);
        Utils.defineNativeGetter(screenProto, 'availHeight', () => config.availHeight);
        Utils.defineNativeGetter(screenProto, 'colorDepth', () => config.colorDepth);
        Utils.defineNativeGetter(screenProto, 'pixelDepth', () => config.pixelDepth);

        // Patch devicePixelRatio
        Utils.defineNativeGetter(window, 'devicePixelRatio', () => config.devicePixelRatio);

        // Patch matchMedia for screen queries
        const origMatchMedia = window.matchMedia.bind(window);
        window.matchMedia = function matchMedia(query) {
          const result = origMatchMedia(query);
          
          // Intercept screen-related queries
          if (query.includes('device-pixel-ratio')) {
            Object.defineProperty(result, 'matches', {
              get: () => {
                const ratio = parseFloat(query.match(/device-pixel-ratio:\s*([\d.]+)/)?.[1] || 1);
                return config.devicePixelRatio === ratio;
              }
            });
          }

          return result;
        };
        Utils.patchNative(window.matchMedia, 'matchMedia');
      }
    };

    /************************************************************************************************
     * CHROME API EMULATION
     ************************************************************************************************/
    const ChromeSpoof = {
      apply() {
        if (!isChrome) return;
        if (typeof window === 'undefined') return;

        const g = Utils.getGlobal();

        // Create chrome object if not present
        if (typeof g.chrome === 'undefined' || g.chrome === null) {
          Utils.defineNativeValue(g, 'chrome', {}, { configurable: true });
        }

        const chrome = g.chrome;

        // chrome.runtime
        if (!chrome.runtime) {
          chrome.runtime = {
            id: undefined,
            connect: function connect(extensionId, connectInfo) {
              return {
                postMessage: function postMessage() {},
                onMessage: {
                  addListener: function addListener() {},
                  removeListener: function removeListener() {},
                  hasListener: function hasListener() { return false; }
                },
                onDisconnect: {
                  addListener: function addListener() {},
                  removeListener: function removeListener() {},
                  hasListener: function hasListener() { return false; }
                },
                disconnect: function disconnect() {}
              };
            },
            sendMessage: function sendMessage() {},
            onMessage: {
              addListener: function addListener() {},
              removeListener: function removeListener() {},
              hasListener: function hasListener() { return false; }
            },
            onConnect: {
              addListener: function addListener() {},
              removeListener: function removeListener() {},
              hasListener: function hasListener() { return false; }
            }
          };

          Utils.patchNative(chrome.runtime.connect, 'connect');
          Utils.patchNative(chrome.runtime.sendMessage, 'sendMessage');
        }

        // chrome.csi
        if (!chrome.csi && typeof performance !== 'undefined' && performance.timing) {
          chrome.csi = function csi() {
            const t = performance.timing;
            return {
              onloadT: t.loadEventEnd || 0,
              pageT: Date.now() - (t.navigationStart || Date.now()),
              startE: t.navigationStart || 0,
              tran: 15
            };
          };
          Utils.patchNative(chrome.csi, 'csi');
        }

        // chrome.loadTimes
        if (!chrome.loadTimes && typeof performance !== 'undefined' && performance.timing) {
          chrome.loadTimes = function loadTimes() {
            const t = performance.timing;
            return {
              requestTime: (t.navigationStart || 0) / 1000,
              startLoadTime: (t.navigationStart || 0) / 1000,
              commitLoadTime: (t.responseStart || 0) / 1000,
              finishDocumentLoadTime: (t.domContentLoadedEventEnd || 0) / 1000,
              finishLoadTime: (t.loadEventEnd || 0) / 1000,
              firstPaintTime: 0,
              firstPaintAfterLoadTime: 0,
              navigationType: 'Other',
              wasFetchedViaSpdy: true,
              wasNpnNegotiated: true,
              npnNegotiatedProtocol: 'h2',
              wasAlternateProtocolAvailable: false,
              connectionInfo: 'h2'
            };
          };
          Utils.patchNative(chrome.loadTimes, 'loadTimes');
        }

        // chrome.app
        if (!chrome.app) {
          chrome.app = {
            isInstalled: false,
            InstallState: { DISABLED: 0, INSTALLED: 1, NOT_INSTALLED: 2 },
            RunningState: { CANNOT_RUN: 0, READY_TO_RUN: 1, RUNNING: 2 },
            getDetails: function getDetails() { return null; },
            getIsInstalled: function getIsInstalled() { return false; },
            runningState: function runningState() { return 'cannot_run'; }
          };
          Utils.patchNative(chrome.app.getDetails, 'getDetails');
          Utils.patchNative(chrome.app.getIsInstalled, 'getIsInstalled');
          Utils.patchNative(chrome.app.runningState, 'runningState');
        }
      }
    };

    /************************************************************************************************
     * IFRAME & FRAME ELEMENT
     ************************************************************************************************/
    const FrameSpoof = {
      apply() {
        if (typeof window === 'undefined') return;

        // Set frameElement to null in top-level frames
        if (window.top === window) {
          try {
            Utils.defineNativeGetter(window, 'frameElement', () => null, { configurable: true });
          } catch (e) {
            if (DEBUG) Utils.logError(e, 'FrameSpoof.frameElement');
          }
        }

        // Patch length property to return consistent values
        if (typeof window.length !== 'undefined') {
          Utils.defineNativeGetter(window, 'length', () => window.frames?.length || 0);
        }
      }
    };

    /************************************************************************************************
     * MEDIA ELEMENT SPOOFING
     ************************************************************************************************/
    const MediaSpoof = {
      apply() {
        if (typeof HTMLMediaElement === 'undefined') return;

        const origCanPlayType = HTMLMediaElement.prototype.canPlayType;

        const knownTypes = {
          // Video codecs
          'video/mp4; codecs="avc1.42E01E"': 'probably',
          'video/mp4; codecs="avc1.42E01E, mp4a.40.2"': 'probably',
          'video/mp4; codecs="avc1.4D401E"': 'probably',
          'video/mp4; codecs="avc1.64001E"': 'probably',
          'video/webm; codecs="vp8"': 'probably',
          'video/webm; codecs="vp9"': 'probably',
          'video/webm; codecs="vp8, vorbis"': 'probably',
          'video/webm; codecs="vp9, opus"': 'probably',
          
          // Audio codecs
          'audio/mp4; codecs="mp4a.40.2"': 'probably',
          'audio/mp4; codecs="mp4a.40.5"': 'probably',
          'audio/mpeg': 'probably',
          'audio/mpegurl': 'maybe',
          'audio/x-m4a': 'maybe',
          'audio/aac': 'probably',
          'audio/ogg; codecs="vorbis"': 'probably',
          'audio/ogg; codecs="opus"': 'probably',
          'audio/wav': 'probably',
          'audio/webm; codecs="vorbis"': 'probably',
          'audio/webm; codecs="opus"': 'probably'
        };

        HTMLMediaElement.prototype.canPlayType = function canPlayType(type) {
          if (!type) return '';

          const normalized = type.trim().toLowerCase();
          
          // Check known types
          for (const [pattern, result] of Object.entries(knownTypes)) {
            if (normalized === pattern.toLowerCase() || 
                normalized.includes(pattern.split(';')[0].toLowerCase())) {
              return result;
            }
          }

          // Fallback to original
          return origCanPlayType.call(this, type) || '';
        };

        Utils.patchNative(HTMLMediaElement.prototype.canPlayType, 'canPlayType');
      }
    };

    /************************************************************************************************
     * PERFORMANCE API NORMALIZATION
     ************************************************************************************************/
    const PerformanceSpoof = {
      apply() {
        if (typeof performance === 'undefined') return;

        // Normalize timing precision to prevent timing attacks
        const precision = perfCfg.precision || 0.1; // 100μs default
        
        const roundToPrecision = (value) => {
          return Math.round(value / precision) * precision;
        };

        // Patch performance.now
        const origNow = performance.now.bind(performance);
        performance.now = function now() {
          return roundToPrecision(origNow());
        };
        Utils.patchNative(performance.now, 'now');

        // Patch Date.now for consistency
        const origDateNow = Date.now;
        Date.now = function now() {
          return Math.round(origDateNow() / precision) * precision;
        };
        Utils.patchNative(Date.now, 'now');

        // Patch performance.timing
        const origTiming = performance.timing;
        const timingHandler = {
          get(target, prop) {
            const value = target[prop];
            if (typeof value === 'number') {
              return roundToPrecision(value);
            }
            return value;
          }
        };

        try {
          performance.timing = new Proxy(origTiming, timingHandler);
        } catch (e) {
          // Proxy might not work, ignore
        }
      }
    };

    /************************************************************************************************
     * BATTERY API SPOOFING
     ************************************************************************************************/
    const BatterySpoof = {
      apply() {
        if (typeof navigator === 'undefined') return;

        // navigator.getBattery is deprecated but still detectable
        if (navigator.getBattery) {
          const origGetBattery = navigator.getBattery.bind(navigator);
          
          navigator.getBattery = function getBattery() {
            return Promise.resolve({
              charging: true,
              chargingTime: 0,
              dischargingTime: Infinity,
              level: 1,
              onchargingchange: null,
              onchargingtimechange: null,
              ondischargingtimechange: null,
              onlevelchange: null
            });
          };

          Utils.patchNative(navigator.getBattery, 'getBattery');
        }
      }
    };

    /************************************************************************************************
     * WORKER INJECTION
     ************************************************************************************************/
    const WorkerSpoof = {
      applied: false,

      apply() {
        if (this.applied) return;
        this.applied = true;

        const self = this;

        // Patch Worker constructor
        if (typeof Worker !== 'undefined') {
          const OrigWorker = Worker;
          
          window.Worker = function Worker(scriptURL, options) {
            const wrappedCode = self.wrapWorkerCode(scriptURL, options);
            const blob = new Blob([wrappedCode], { type: 'application/javascript' });
            const blobURL = URL.createObjectURL(blob);
            
            return new OrigWorker(blobURL, options);
          };

          // Copy static properties
          window.Worker.prototype = OrigWorker.prototype;
          for (const prop of Object.getOwnPropertyNames(OrigWorker)) {
            if (prop !== 'prototype' && !(prop in window.Worker)) {
              window.Worker[prop] = OrigWorker[prop];
            }
          }

          Utils.patchNative(window.Worker, 'Worker');
        }

        // Patch SharedWorker
        if (typeof SharedWorker !== 'undefined') {
          const OrigSharedWorker = SharedWorker;
          
          window.SharedWorker = function SharedWorker(scriptURL, options) {
            const wrappedCode = self.wrapWorkerCode(scriptURL, options);
            const blob = new Blob([wrappedCode], { type: 'application/javascript' });
            const blobURL = URL.createObjectURL(blob);
            
            return new OrigSharedWorker(blobURL, options);
          };

          window.SharedWorker.prototype = OrigSharedWorker.prototype;
          Utils.patchNative(window.SharedWorker, 'SharedWorker');
        }

        // Patch ServiceWorker (for completeness)
        if (typeof ServiceWorker !== 'undefined' && navigator.serviceWorker) {
          const origRegister = navigator.serviceWorker.register.bind(navigator.serviceWorker);
          
          navigator.serviceWorker.register = function register(scriptURL, options) {
            // We can't easily wrap ServiceWorker, so just pass through
            return origRegister(scriptURL, options);
          };

          Utils.patchNative(navigator.serviceWorker.register, 'register');
        }
      },

      wrapWorkerCode(input, options) {
        const stealthInit = `(${STEALTH_FUNC.toString()})(${JSON.stringify(cfg)});`;
        const isModule = options?.type === 'module';
        
        let code = '';

        if (typeof input === 'string') {
          if (/^https?:/.test(input)) {
            // HTTP URL
            code = isModule 
              ? `${stealthInit}\nimport ${JSON.stringify(input)};`
              : `${stealthInit}\nimportScripts(${JSON.stringify(input)});`;
          } else if (/^blob:/.test(input)) {
            // Blob URL
            code = isModule
              ? `${stealthInit}\nimport ${JSON.stringify(input)};`
              : `${stealthInit}\nimportScripts(${JSON.stringify(input)});`;
          } else if (/^data:/.test(input)) {
            // Data URL - decode and wrap
            code = `${stealthInit}\n${input}`;
          } else {
            // Assume it's inline code
            code = `${stealthInit}\n${input}`;
          }
        } else if (input instanceof Blob) {
          // Blob object - we need to read it synchronously
          // For Blobs, we create a blob URL and import it
          const blobURL = URL.createObjectURL(input);
          code = isModule
            ? `${stealthInit}\nimport ${JSON.stringify(blobURL)};`
            : `${stealthInit}\nimportScripts(${JSON.stringify(blobURL)});`;
        } else if (input?.toString) {
          // URL object or other
          code = isModule
            ? `${stealthInit}\nimport ${JSON.stringify(input.toString())};`
            : `${stealthInit}\nimportScripts(${JSON.stringify(input.toString())});`;
        }

        return code;
      }
    };

    /************************************************************************************************
     * OBJECT PROTOTYPE PROTECTION
     ************************************************************************************************/
    const PrototypeProtection = {
      apply() {
        // Prevent toString detection
        const origFunctionToString = Function.prototype.toString;
        const self = this;

        Function.prototype.toString = function toString() {
          // Check if this is a spoofed function
          if (this.__stealthNative__) {
            return Utils.makeNativeString(this.__stealthNative__);
          }
          return origFunctionToString.call(this);
        };
        Utils.patchNative(Function.prototype.toString, 'toString');

        // Protect against prototype tampering detection
        this.protectNavigatorPrototype();
      },

      protectNavigatorPrototype() {
        if (typeof navigator === 'undefined') return;

        const navProto = Utils.cache.nativeGetPrototypeOf.call(Object, navigator);
        if (!navProto) return;

        // Make properties appear as native accessors
        const props = ['vendor', 'platform', 'deviceMemory', 'hardwareConcurrency',
                       'maxTouchPoints', 'languages', 'language', 'userAgent',
                       'webdriver'];
        if (isChrome) props.push('userAgentData');

        for (const prop of props) {
          Utils.overrideDescriptor(navProto, prop, {
            get: undefined,
            set: undefined,
            configurable: true,
            enumerable: true
          });
        }
      }
    };

    /************************************************************************************************
     * INITIALIZE ALL SPOOFING MODULES
     ************************************************************************************************/
    function initialize() {
      try {
        // Apply in specific order to handle dependencies
        PrototypeProtection.apply();
        NavigatorSpoof.apply();
        ClientHintsSpoof.apply();
        TimezoneSpoof.apply();
        WebGLSpoof.apply();
        CanvasSpoof.apply();
        AudioSpoof.apply();
        PluginSpoof.apply();
        WebRTCSpoof.apply();
        ScreenSpoof.apply();
        ChromeSpoof.apply();
        FrameSpoof.apply();
        MediaSpoof.apply();
        PerformanceSpoof.apply();
        BatterySpoof.apply();
        WorkerSpoof.apply();

        if (DEBUG) {
          console.log('[Stealth] Initialization complete');
        }

        return true;
      } catch (e) {
        Utils.logError(e, 'initialize');
        return false;
      }
    }

    // Run initialization
    initialize();

    // Return for potential debugging
    return {
      utils: Utils,
      config: cfg,
      errorLog: Utils.errorLog
    };

  }); // End of STEALTH_FUNC

  /************************************************************************************************
   * EXECUTE IN MAIN CONTEXT
   ************************************************************************************************/
  try {
    STEALTH_FUNC(config);
  } catch (e) {
    try {
      const g = typeof globalThis !== 'undefined' ? globalThis : 
                typeof window !== 'undefined' ? window : self;
      if (g && g.__stealthErrorLog) {
        g.__stealthErrorLog.push({
          timestamp: Date.now(),
          context: 'main:init',
          message: e?.message || String(e),
          stack: e?.stack
        });
      }
    } catch (_) {}
    
    if (config?.debug) {
      console.error('[Stealth] Initialization failed:', e);
    }
  }

})(/*CONFIG_INJECTION*/);
//# sourceURL=stealth_engine_v2.js
