// ==UserScript==
// @name         Stripe UPI QR Code Extractor
// @namespace    https://github.com/anomalyco/opencode
// @version      2.1
// @description  从 Stripe Checkout 页面提取 UPI QR 码, 转为可点击的 upi:// 链接, 支持自动复制
// @author       opencode
// @match        https://pay.openai.com/c/pay/*
// @match        https://checkout.stripe.com/c/pay/*
// @match        https://js.stripe.com/v3/checkout-inner-origin-frame*
// @grant        GM_addStyle
// @grant        GM_setClipboard
// @grant        GM_xmlhttpRequest
// @run-at       document-start
// @require      https://cdn.jsdelivr.net/npm/jsqr@1.4.0/dist/jsQR.js
// ==/UserScript==

(function () {
  'use strict';

  // ===================== 工具函数 =====================

  function isUPIData(str) {
    return str && (str.startsWith('upi://') || /^[a-zA-Z0-9._-]+@[a-zA-Z0-9]{2,}/.test(str));
  }

  function isInStripeIframe() {
    return window.location.href.indexOf('checkout-inner-origin-frame') !== -1;
  }

  // ===================== QR 解码 =====================

  function decodeQRFromCanvas(canvas) {
    try {
      var ctx = canvas.getContext('2d');
      if (!ctx) return null;
      var w = canvas.width, h = canvas.height;
      if (w < 50 || h < 50) return null;
      var imageData = ctx.getImageData(0, 0, w, h);
      var result = window.jsQR(imageData.data, w, h);
      return result && result.data ? result.data : null;
    } catch (e) {
      return null;
    }
  }

  function decodeQRFromImg(img) {
    try {
      var c = document.createElement('canvas');
      c.width = img.naturalWidth || img.width;
      c.height = img.naturalHeight || img.height;
      if (c.width < 50 || c.height < 50) return null;
      var ctx = c.getContext('2d');
      if (!ctx) return null;
      ctx.drawImage(img, 0, 0);
      return decodeQRFromCanvas(c);
    } catch (e) {
      return null;
    }
  }

  function scanPage() {
    var results = [];
    document.querySelectorAll('canvas').forEach(function (el) {
      var d = decodeQRFromCanvas(el);
      if (d && isUPIData(d)) results.push({ data: d, el: el });
    });
    document.querySelectorAll('img').forEach(function (el) {
      var d = decodeQRFromImg(el);
      if (d && isUPIData(d)) results.push({ data: d, el: el });
    });
    return results;
  }

  // ===================== 网络拦截 =====================

  var foundUPI = null;

  function hookFetch() {
    var orig = window.fetch;
    window.fetch = function (url, opts) {
      var reqUrl = typeof url === 'string' ? url : (url && url.url ? url.url : '');
      return orig.apply(this, arguments).then(function (resp) {
        if (/api\.stripe\.com|merchant-ui-api\.stripe\.com/.test(reqUrl)) {
          var clone = resp.clone();
          clone.text().then(function (body) {
            parseResponseBody(body, reqUrl);
          }).catch(function () { });
        }
        return resp;
      });
    };
  }

  function hookXHR() {
    var open = XMLHttpRequest.prototype.open;
    var send = XMLHttpRequest.prototype.send;
    XMLHttpRequest.prototype.open = function (method, url) {
      this.__upi_url = url;
      return open.apply(this, arguments);
    };
    XMLHttpRequest.prototype.send = function () {
      var xhr = this;
      var cb = xhr.onreadystatechange;
      xhr.onreadystatechange = function () {
        if (xhr.readyState === 4 && xhr.responseText) {
          var u = xhr.__upi_url || xhr.responseURL || '';
          if (/api\.stripe\.com|merchant-ui-api\.stripe\.com/.test(u)) {
            parseResponseBody(xhr.responseText, u);
          }
        }
        if (cb) cb.apply(xhr, arguments);
      };
      return send.apply(this, arguments);
    };
  }

  function parseResponseBody(text, url) {
    if (foundUPI || !text) return;

    var match = text.match(/upi:\/\/[^\s"'<\\]+/);
    if (match) { emit(match[0], 'API: ' + url); return; }

    try {
      var upi = findUPIInJSON(JSON.parse(text));
      if (upi) { emit(upi, 'API: ' + url); return; }
    } catch (e) { }

    match = text.match(/["']vpa["']\s*[:=]\s*["']([^"']+)["']/);
    if (match && /@/.test(match[1])) {
      emit('upi://pay?pa=' + match[1], 'API(VPA): ' + url);
    }
  }

  function findUPIInJSON(obj, depth) {
    if (!obj || typeof obj !== 'object' || depth > 15) return null;
    if (depth === undefined) depth = 0;
    for (var k in obj) {
      var v = obj[k];
      if (typeof v === 'string') {
        if (v.startsWith('upi://')) return v;
        if (/^[\w.-]+@[\w]{2,}$/.test(v) && k === 'vpa') return 'upi://pay?pa=' + v;
      }
      if (typeof v === 'object') {
        var r = findUPIInJSON(v, depth + 1);
        if (r) return r;
      }
    }
    return null;
  }

  function emit(upiUrl, source) {
    foundUPI = upiUrl;
    console.log('[UPI Extractor] FOUND:', upiUrl, '|', source);
    showPanel(upiUrl);
    GM_setClipboard(upiUrl, 'text');
    showToast('UPI link copied!');
  }

  // ===================== UI 面板 =====================

  var panel;

  function showPanel(upiUrl) {
    if (!panel) {
      panel = document.createElement('div');
      panel.id = '__upi_panel';
      panel.innerHTML =
        '<div id="__upi_hd"><span>UPI Payment Link</span><b id="__upi_cl">&times;</b></div>' +
        '<div id="__upi_bd"></div>' +
        '<div id="__upi_ft"><button id="__upi_cp">Copy Link</button><button id="__upi_rs">Re-scan</button></div>';
      document.body.appendChild(panel);
      document.getElementById('__upi_cl').onclick = function () { panel.style.display = 'none'; };
      document.getElementById('__upi_rs').onclick = function () { foundUPI = null; doScan(); };
      document.getElementById('__upi_cp').onclick = function () {
        var a = panel.querySelector('.__upi_lnk');
        if (a) GM_setClipboard(a.href, 'text');
        showToast('Copied!');
      };
    }
    document.getElementById('__upi_bd').innerHTML =
      '<a class="__upi_lnk" href="' + upiUrl + '" target="_blank">' + upiUrl + '</a>' +
      '<div class="__upi_hint">Click to open UPI app &middot; Auto-copied to clipboard</div>';
    panel.style.display = 'block';
  }

  var toastEl;
  function showToast(msg) {
    if (!toastEl) {
      toastEl = document.createElement('div');
      toastEl.id = '__upi_toast';
      document.body.appendChild(toastEl);
    }
    toastEl.textContent = msg;
    toastEl.style.display = 'block';
    toastEl.style.opacity = '1';
    clearTimeout(toastEl.__t);
    toastEl.__t = setTimeout(function () { toastEl.style.opacity = '0'; }, 1800);
    toastEl.__t = setTimeout(function () { toastEl.style.display = 'none'; }, 2200);
  }

  // ===================== DOM 观察 =====================

  var scanTimer;

  function doScan() {
    clearTimeout(scanTimer);
    scanTimer = setTimeout(function () {
      scanPage().forEach(function (r) { emit(r.data, 'DOM'); });

      if (!foundUPI) {
        var txt = (document.body || document.documentElement).innerText || '';
        var m = txt.match(/upi:\/\/[^\s]+/);
        if (m) emit(m[0], 'page text');
      }
    }, 600);
  }

  function observeDOM() {
    new MutationObserver(function () { doScan(); }).observe(
      document.body || document.documentElement,
      { childList: true, subtree: true, attributes: true, attributeFilter: ['src', 'style'] }
    );
  }

  // ===================== CSS =====================

  function injectCSS() {
    GM_addStyle(
      '#__upi_panel{position:fixed;bottom:16px;right:16px;width:380px;max-width:94vw;' +
      'background:#1a1f36;border:1px solid #444;border-radius:12px;box-shadow:0 8px 28px rgba(0,0,0,.55);' +
      'z-index:2147483647;font:13px system-ui,sans-serif;color:#ddd;display:none}' +
      '#__upi_hd{display:flex;justify-content:space-between;align-items:center;padding:10px 14px;' +
      'border-bottom:1px solid #333;font-weight:600;color:#6ee7b7}' +
      '#__upi_cl{font-size:20px;cursor:pointer;color:#888;padding:0 4px}#__upi_cl:hover{color:#fff}' +
      '#__upi_bd{padding:14px}' +
      '.__upi_lnk{display:block;color:#63b3ff;text-decoration:none;font:13px monospace;' +
      'padding:10px;background:#0d1117;border-radius:6px;border:1px solid #30363d;margin-bottom:8px;word-break:break-all}' +
      '.__upi_lnk:hover{border-color:#58a6ff}' +
      '.__upi_hint{font-size:11px;color:#777;margin-top:4px}' +
      '#__upi_ft{display:flex;gap:8px;padding:0 14px 12px}' +
      '#__upi_ft button{flex:1;padding:7px;border:1px solid #555;border-radius:6px;' +
      'background:#2a2f45;color:#ddd;cursor:pointer;font-size:12px}' +
      '#__upi_ft button:hover{background:#3a3f55}' +
      '#__upi_toast{position:fixed;bottom:100px;left:50%;transform:translateX(-50%);' +
      'background:#333;color:#fff;padding:8px 20px;border-radius:6px;font-size:12px;' +
      'z-index:2147483648;display:none;transition:opacity .3s}' +
      (isInStripeIframe() ? '#__upi_panel{top:10px;bottom:auto}' : '')
    );
  }

  // ===================== 初始化 =====================

  function init() {
    if (!/\/c\/pay\//.test(window.location.pathname) && !/checkout/.test(window.location.hostname) &&
      !isInStripeIframe()) return;

    console.log('[UPI Extractor] init:', window.location.href);
    injectCSS();
    hookFetch();
    hookXHR();
    observeDOM();
    setTimeout(doScan, 1500);
    setTimeout(doScan, 4000);
  }

  init();
})();
