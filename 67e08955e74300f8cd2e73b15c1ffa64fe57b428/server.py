from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import base64
import json
import re
import secrets
import urllib.error
import urllib.parse
import urllib.request


HOST = "127.0.0.1"
PORT = 7790
CHECKOUT_URL = "https://chatgpt.com/backend-api/payments/checkout"
IP_CHECK_URLS = (
    "http://iprust.io/ip.json",
    "https://ipwho.is/",
    "https://api.myip.com/",
    "https://ipinfo.io/json",
)

try:
    from curl_cffi import requests as curl_requests
except Exception:
    curl_requests = None


INDEX_HTML = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>本地支付长链生成器</title>
  <style>
    :root { color-scheme: light; font-family: -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif; }
    body { margin:0; background:#f5f5f7; color:#111; }
    .wrap { max-width:820px; margin:34px auto; padding:0 16px; }
    .card { background:#fff; border:1px solid #ddd; border-radius:22px; padding:22px; box-shadow:0 18px 50px rgba(0,0,0,.07); }
    h1 { margin:0 0 8px; font-size:24px; }
    p, li { color:#666; line-height:1.65; }
    label { display:block; margin:18px 0 8px; font-weight:600; }
    textarea, input, select { width:100%; box-sizing:border-box; border:1px solid #ccc; border-radius:14px; padding:12px; font:inherit; background:#fff; }
    textarea { min-height:150px; resize:vertical; font-family:ui-monospace,SFMono-Regular,Consolas,monospace; font-size:12px; line-height:1.55; }
    .grid { display:grid; grid-template-columns: repeat(2, minmax(0,1fr)); gap:12px; }
    .row { display:flex; gap:10px; align-items:center; flex-wrap:wrap; }
    button, .btn { border:0; border-radius:14px; background:#111; color:#fff; padding:13px 18px; font-weight:700; cursor:pointer; text-decoration:none; display:inline-flex; align-items:center; }
    button.secondary { background:#e9e9ec; color:#111; }
    button:disabled { opacity:.55; cursor:not-allowed; }
    .muted { color:#777; font-size:13px; }
    .warn { border:1px solid #ead7a4; background:#fff8e5; border-radius:14px; padding:12px; color:#6b4a00; }
    .ok { border:1px solid #b8dbc0; background:#f0fff3; border-radius:14px; padding:12px; color:#0f5f22; display:none; }
    .err { border:1px solid #f0b6b6; background:#fff0f0; border-radius:14px; padding:12px; color:#a40000; white-space:pre-wrap; display:none; }
    .result { margin-top:16px; border:1px solid #d8d8d8; background:#fafafa; border-radius:16px; padding:14px; display:none; }
    .linkbox { margin:10px 0; padding:12px; background:#fff; border:1px solid #ddd; border-radius:12px; overflow:hidden; }
    .link-card { margin:14px 0 8px; padding:16px 20px; background:#fff; border:1px solid #ddd; border-radius:18px; display:flex; align-items:center; justify-content:space-between; gap:14px; }
    .link-main { min-width:0; flex:1; }
    .link-label { color:#777; font-size:13px; margin-bottom:5px; }
    .link-text { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; font-size:16px; color:#111; }
    .link-open-icon { color:#111; text-decoration:none; font-size:22px; line-height:1; padding:4px 8px; }
    .link-actions { display:flex; gap:10px; margin:10px 0 16px; }
    .link-actions button { background:#fff; color:#111; border:1px solid #ddd; padding:10px 18px; border-radius:14px; box-shadow:none; }
    .link-actions button:hover { background:#f7f7f7; }
    .linkbox a { display:block; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; color:#0645ad; }
    pre { overflow:auto; background:#fff; border:1px solid #ddd; border-radius:12px; padding:12px; font-size:12px; }
    details { margin-top:16px; }
    summary { cursor:pointer; color:#333; font-weight:700; }
    @media (max-width:700px){ .grid { grid-template-columns:1fr; } }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="card">
      <h1>本地支付长链生成器</h1>
      <div class="muted">版本：地区下拉 + 币种自动跟随</div>
      <p>粘贴 ChatGPT accessToken 后，本机后端会创建新的 hosted checkout 支付会话，返回 pay.openai.com 长链。</p>
      <div class="warn">隐私说明：本工具不在服务端保存 token、代理、优惠码或生成结果；代理仅保存在用户自己的浏览器 localStorage；服务端请求日志已关闭。</div>

      <div class="row" style="justify-content:space-between;align-items:center;margin-top:18px;margin-bottom:8px">
        <label style="margin:0">Access Token 或 session JSON</label>
        <button id="copySessionUrl" class="secondary" type="button" style="padding:8px 12px;border-radius:10px">复制 Session 地址</button>
      </div>
      <textarea id="token" placeholder="可粘贴 accessToken，或 https://chatgpt.com/api/auth/session 返回的整段 JSON"></textarea>
      <div id="tokenHint" class="muted">暂未识别 token。</div>

      <div class="grid">
        <div>
          <label>方案</label>
          <select id="plan">
            <option value="plus">ChatGPT Plus</option>
            <option value="team">ChatGPT Team</option>
          </select>
        </div>
        <div>
          <label>支付页模式</label>
          <select id="mode">
            <option value="hosted" selected>hosted：pay.openai.com 长链</option>
            <option value="custom">custom：chatgpt.com/checkout 链接</option>
            <option value="redirect">redirect</option>
          </select>
        </div>
        <div>
          <label>地区</label>
          <select id="country">
            <option value="JP">日本 JP</option>
            <option value="US">美国 US</option>
            <option value="ID">印度尼西亚 ID</option>
            <option value="DE" selected>德国 DE</option>
            <option value="FR">法国 FR</option>
            <option value="GB">英国 GB</option>
            <option value="CA">加拿大 CA</option>
            <option value="AU">澳大利亚 AU</option>
            <option value="KR">韩国 KR</option>
            <option value="SG">新加坡 SG</option>
            <option value="HK">中国香港 HK</option>
            <option value="TW">中国台湾 TW</option>
            <option value="IN">印度 IN</option>
            <option value="BR">巴西 BR</option>
            <option value="MX">墨西哥 MX</option>
            <option value="TH">泰国 TH</option>
            <option value="MY">马来西亚 MY</option>
            <option value="PH">菲律宾 PH</option>
            <option value="VN">越南 VN</option>
            <option value="AE">阿联酋 AE</option>
            <option value="CH">瑞士 CH</option>
            <option value="SE">瑞典 SE</option>
            <option value="NO">挪威 NO</option>
            <option value="DK">丹麦 DK</option>
            <option value="PL">波兰 PL</option>
            <option value="CZ">捷克 CZ</option>
          </select>
          <div class="muted">选择地区后，币种会自动切换。</div>
        </div>
        <div>
          <label>币种</label>
          <input id="currency" value="EUR" maxlength="3" readonly />
          <div class="muted">币种跟随地区自动填充。</div>
        </div>
      </div>

      <label>出口代理（可选）</label>
      <input id="proxy" placeholder="例如：http://127.0.0.1:7890 或 socks5h://user:pass@host:port" />
      <div class="muted">填写后，创建 checkout 的请求会经该代理出口发出；检测时会优先使用 iprust.io，并自动尝试 socks5h / socks5 / http。</div>
      <div class="row" style="margin-top:10px">
        <button id="checkProxy" class="secondary" type="button">检测代理</button>
        <button id="saveProxy" class="secondary" type="button">保存代理</button>
        <button id="clearProxy" class="secondary" type="button">清除保存</button>
      </div>
      <div id="proxyStatus" class="muted" style="margin-top:8px">代理未检测。</div>

      <div id="teamFields" style="display:none">
        <div class="grid">
          <div>
            <label>Team 工作区名称</label>
            <input id="workspace" value="linux-do" />
          </div>
          <div>
            <label>席位数</label>
            <input id="seats" value="2" type="number" min="2" />
          </div>
        </div>
        <label>Team 优惠码 / 优惠链接</label>
        <input id="promoCode" value="STRIPEATLASGPT4BIZ050126" placeholder="可填 STRIPEATLASGPT4BIZ050126，或粘贴 https://chatgpt.com/?promoCode=..." />
        <div class="muted">选择 Team 时会使用 promo_code，并把 cancel_url 设置为对应 promoCode 链接。</div>
      </div>

      <label class="row">
        <input id="promo" type="checkbox" checked style="width:auto" />
        <span>使用优惠参数（Plus 使用 plus-1-month-free；Team 使用上方优惠码）</span>
      </label>

      <div class="row" style="margin-top:18px">
        <button id="go">生成支付长链</button>
        <button id="copy" class="secondary" disabled>复制链接</button>
        <button id="open" class="secondary" disabled>打开链接</button>
      </div>

      <div id="ok" class="ok"></div>
      <div id="error" class="err"></div>

      <div id="result" class="result">
        <strong>生成结果</strong>
        <div id="links"></div>
        <details>
          <summary>查看原始返回</summary>
          <pre id="raw"></pre>
        </details>
      </div>
    </div>
  </div>

  <script>
    const $ = (id) => document.getElementById(id);
    const PROXY_STORAGE_KEY = 'local_payurl_saved_proxy_v1';
    const COUNTRY_CURRENCY = {
      JP: 'JPY',
      US: 'USD',
      ID: 'IDR',
      DE: 'EUR',
      FR: 'EUR',
      GB: 'GBP',
      CA: 'CAD',
      AU: 'AUD',
      KR: 'KRW',
      SG: 'SGD',
      HK: 'HKD',
      TW: 'TWD',
      IN: 'INR',
      BR: 'BRL',
      MX: 'MXN',
      TH: 'THB',
      MY: 'MYR',
      PH: 'PHP',
      VN: 'VND',
      AE: 'AED',
      CH: 'CHF',
      SE: 'SEK',
      NO: 'NOK',
      DK: 'DKK',
      PL: 'PLN',
      CZ: 'CZK',
    };
    let currentLink = '';

    function extractToken(text) {
      text = String(text || '').trim();
      if (/^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$/.test(text)) return text;
      try {
        const j = JSON.parse(text);
        return j.accessToken || j.access_token || j.token || j?.data?.accessToken || '';
      } catch (_) {}
      const m = text.match(/eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+/);
      return m ? m[0] : '';
    }

    function decodeJwtPayload(token) {
      try {
        const part = token.split('.')[1];
        const json = atob(part.replace(/-/g, '+').replace(/_/g, '/'));
        return JSON.parse(decodeURIComponent(Array.from(json).map(c => '%' + c.charCodeAt(0).toString(16).padStart(2, '0')).join('')));
      } catch (_) {
        return {};
      }
    }

    function updateTokenHint() {
      const token = extractToken($('token').value);
      if (!token) {
        $('tokenHint').textContent = '暂未识别 token。';
        return;
      }
      const payload = decodeJwtPayload(token);
      const email = payload.email || payload['https://api.openai.com/profile']?.email || '';
      $('tokenHint').textContent = email ? `已识别 token，可能关联邮箱：${email}` : '已识别 token。';
    }

    function setError(msg) {
      $('error').style.display = msg ? 'block' : 'none';
      $('error').textContent = msg || '';
    }

    function setOk(msg) {
      $('ok').style.display = msg ? 'block' : 'none';
      $('ok').textContent = msg || '';
    }

    function setProxyStatus(msg) {
      $('proxyStatus').textContent = msg || '代理未检测。';
    }

    function updateCurrencyForCountry() {
      const country = $('country').value.trim().toUpperCase();
      $('currency').value = COUNTRY_CURRENCY[country] || 'USD';
    }

    function extractPromoCode(value) {
      const text = String(value || '').trim();
      if (!text) return '';
      try {
        const url = new URL(text);
        return (url.searchParams.get('promoCode') || url.searchParams.get('promocode') || '').trim();
      } catch (_) {}
      const match = text.match(/promoCode=([^&#\s]+)/i);
      return decodeURIComponent(match?.[1] || text).trim();
    }

    function updatePlanFields() {
      const isTeam = $('plan').value === 'team';
      $('teamFields').style.display = isTeam ? 'block' : 'none';
    }

    function loadSavedProxy() {
      try {
        const saved = localStorage.getItem(PROXY_STORAGE_KEY) || '';
        if (saved) {
          $('proxy').value = saved;
          setProxyStatus('已载入保存的代理。');
        }
      } catch (_) {}
    }

    function saveProxy(showMessage = true) {
      const proxy = $('proxy').value.trim();
      try {
        if (proxy) {
          localStorage.setItem(PROXY_STORAGE_KEY, proxy);
          if (showMessage) setProxyStatus('代理已保存。');
        } else {
          localStorage.removeItem(PROXY_STORAGE_KEY);
          if (showMessage) setProxyStatus('代理已清空。');
        }
      } catch (_) {
        setError('保存失败：浏览器不允许写入本地存储。');
      }
    }

    function escapeHtml(s) {
      return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
    }

    function linkLabel(key) {
      const labels = {
        url: 'Stripe/外部支付链接',
        stripe_hosted_url: 'Stripe/外部支付链接',
        checkout_url: 'ChatGPT 支付短链',
        chatgpt_checkout_url: 'ChatGPT 支付短链',
        openai_payurl: 'OpenAI 站内长链',
      };
      return labels[key] || key;
    }

    function setResult(payload) {
      const links = [];
      for (const key of ['url', 'stripe_hosted_url', 'checkout_url', 'chatgpt_checkout_url']) {
        if (payload[key]) links.push([key, payload[key]]);
      }
      currentLink = links.length ? links[0][1] : '';
      $('copy').disabled = !currentLink;
      $('open').disabled = !currentLink;
      $('links').innerHTML = links.length
        ? links.map(([k, v], index) => `
          <div class="link-card">
            <div class="link-main">
              <div class="link-label">${escapeHtml(linkLabel(k))}</div>
              <div class="link-text">${escapeHtml(v)}</div>
            </div>
            <a class="link-open-icon" href="${escapeHtml(v)}" target="_blank" rel="noopener noreferrer" title="打开链接">↗</a>
          </div>
          <div class="link-actions">
            <button class="result-copy-btn" type="button" data-link-index="${index}">复制链接</button>
            <button class="result-open-btn" type="button" data-link-index="${index}">打开链接</button>
          </div>
        `).join('')
        : '<p class="muted">返回中没有可识别链接，请看原始返回。</p>';
      $('raw').textContent = JSON.stringify(payload, null, 2);
      $('result').style.display = 'block';
      document.querySelectorAll('.result-copy-btn').forEach((button) => {
        button.addEventListener('click', async () => {
          const item = links[Number(button.dataset.linkIndex || 0)];
          if (!item?.[1]) return;
          try {
            await navigator.clipboard.writeText(item[1]);
            button.textContent = '已复制';
            setTimeout(() => { button.textContent = '复制链接'; }, 1400);
          } catch (_) {
            button.textContent = '复制失败';
            setTimeout(() => { button.textContent = '复制链接'; }, 1400);
          }
        });
      });
      document.querySelectorAll('.result-open-btn').forEach((button) => {
        button.addEventListener('click', () => {
          const item = links[Number(button.dataset.linkIndex || 0)];
          if (item?.[1]) window.open(item[1], '_blank', 'noopener,noreferrer');
        });
      });
      if (payload.proxy_used && payload.proxy_used !== $('proxy').value.trim()) {
        $('proxy').value = payload.proxy_used;
        saveProxy(false);
      }
      if (currentLink) setOk('已生成支付长链。PayPal 邮箱自动填写取决于该会话绑定的 ChatGPT 账号。');
    }

    $('token').addEventListener('input', updateTokenHint);
    $('copySessionUrl').addEventListener('click', async () => {
      const url = 'https://chatgpt.com/api/auth/session';
      try {
        await navigator.clipboard.writeText(url);
        $('copySessionUrl').textContent = '已复制';
        setTimeout(() => { $('copySessionUrl').textContent = '复制 Session 地址'; }, 1400);
      } catch (_) {
        $('copySessionUrl').textContent = '复制失败';
        setTimeout(() => { $('copySessionUrl').textContent = '复制 Session 地址'; }, 1400);
      }
    });
    $('country').addEventListener('change', updateCurrencyForCountry);
    $('proxy').addEventListener('change', saveProxy);
    $('plan').addEventListener('change', updatePlanFields);

    $('saveProxy').addEventListener('click', saveProxy);

    $('clearProxy').addEventListener('click', () => {
      $('proxy').value = '';
      try {
        localStorage.removeItem(PROXY_STORAGE_KEY);
      } catch (_) {}
      setProxyStatus('已清除保存的代理。');
    });

    $('checkProxy').addEventListener('click', async () => {
      setError('');
      const proxy = $('proxy').value.trim();
      $('checkProxy').disabled = true;
      $('checkProxy').textContent = '检测中...';
      setProxyStatus('正在检测出口 IP...');
      try {
        const r = await fetch('/api/proxy-check', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({proxy})
        });
        const data = await r.json();
        if (!r.ok || data.error) throw new Error(data.error || data.message || '检测失败');
        if (data.proxy_used && data.proxy_used !== proxy) {
          $('proxy').value = data.proxy_used;
        }
        const location = [data.country_code, data.country, data.region, data.city].filter(Boolean).join(' / ');
        const isp = data.isp ? `，ISP：${data.isp}` : '';
        const used = data.proxy_used ? `，可用格式：${data.proxy_used.split('://')[0]}://` : '';
        const mode = proxy ? '代理出口' : '直连出口';
        setProxyStatus(`${mode}：${data.ip || '未知 IP'}${location ? '，位置：' + location : ''}${isp}${used}`);
        if (proxy) saveProxy(false);
      } catch (e) {
        setProxyStatus('代理检测失败。');
        setError(e.message || String(e));
      } finally {
        $('checkProxy').disabled = false;
        $('checkProxy').textContent = '检测代理';
      }
    });

    $('go').addEventListener('click', async () => {
      setError('');
      setOk('');
      $('result').style.display = 'none';
      currentLink = '';
      $('copy').disabled = true;
      $('open').disabled = true;

      const token = extractToken($('token').value);
      if (!token) {
        setError('没有识别到 accessToken。');
        return;
      }

      const body = {
        token,
        plan: $('plan').value,
        checkout_ui_mode: $('mode').value,
        country: $('country').value.trim().toUpperCase(),
        currency: $('currency').value.trim().toUpperCase(),
        proxy: $('proxy').value.trim(),
        use_promo: $('promo').checked,
        promo_code: extractPromoCode($('promoCode').value),
        workspace_name: $('workspace').value.trim(),
        seat_quantity: Number($('seats').value || 2),
      };

      $('go').disabled = true;
      $('go').textContent = '请求中...';
      try {
        const r = await fetch('/api/checkout', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify(body)
        });
        const data = await r.json();
        if (!r.ok || data.error) throw new Error(data.error || data.message || '请求失败');
        setResult(data);
      } catch (e) {
        setError(e.message || String(e));
      } finally {
        $('go').disabled = false;
        $('go').textContent = '生成支付长链';
      }
    });

    $('copy').addEventListener('click', async () => {
      if (!currentLink) return;
      try {
        await navigator.clipboard.writeText(currentLink);
        setOk('链接已复制。');
      } catch (_) {
        setError('复制失败，请手动复制链接。');
      }
    });

    $('open').addEventListener('click', () => {
      if (currentLink) window.open(currentLink, '_blank', 'noopener,noreferrer');
    });

    loadSavedProxy();
    updatePlanFields();
    updateCurrencyForCountry();
    updateTokenHint();
  </script>
</body>
</html>"""


def _read_json(handler):
    length = int(handler.headers.get("content-length") or "0")
    raw = handler.rfile.read(length).decode("utf-8", errors="replace")
    return json.loads(raw or "{}")


def _extract_token(value):
    text = str(value or "").strip()
    if re.fullmatch(r"[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", text):
        return text
    match = re.search(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", text)
    return match.group(0) if match else ""


def _extract_promo_code(value):
    text = str(value or "").strip()
    if not text:
        return ""
    match = re.search(r"[?&]promoCode=([^&#\s]+)", text, re.I)
    if match:
        return urllib.parse.unquote(match.group(1)).strip()
    return text


def _checkout_payload(body):
    plan = body.get("plan") or "plus"
    mode = body.get("checkout_ui_mode") or "hosted"
    country = (body.get("country") or "DE").upper()
    currency = (body.get("currency") or "EUR").upper()
    use_promo = bool(body.get("use_promo", True))
    promo_code = _extract_promo_code(body.get("promo_code"))

    payload = {
        "plan_name": "chatgptteamplan" if plan == "team" else "chatgptplusplan",
        "billing_details": {
            "country": country,
            "currency": currency,
        },
        "checkout_ui_mode": mode,
    }

    if plan == "team" and use_promo and promo_code:
        payload["cancel_url"] = f"https://chatgpt.com/?promoCode={urllib.parse.quote(promo_code)}"
        payload["promo_code"] = promo_code
    else:
        payload["cancel_url"] = "https://chatgpt.com/#pricing"

    if use_promo and plan != "team":
        payload["promo_campaign"] = {
            "promo_campaign_id": "plus-1-month-free",
            "is_coupon_from_query_param": True,
        }

    if plan == "team":
        workspace_name = body.get("workspace_name") or "linux-do"
        try:
            seat_quantity = max(2, int(body.get("seat_quantity") or 2))
        except (TypeError, ValueError):
            seat_quantity = 2
        payload["team_plan_data"] = {
            "workspace_name": workspace_name,
            "price_interval": "month",
            "seat_quantity": seat_quantity,
        }

    return payload


def _request_headers(token):
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Origin": "https://chatgpt.com",
        "Referer": "https://chatgpt.com/",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/136.0.0.0 Safari/537.36"
        ),
    }


def _normalize_proxy(value):
    proxy = str(value or "").strip()
    if not proxy:
        return ""
    if "://" not in proxy:
        proxy = "http://" + proxy
    if not re.match(r"^(https?|socks4a?|socks5h?)://", proxy, re.I):
        raise ValueError("代理格式不支持，请使用 http://、https://、socks5:// 或 socks5h://")
    return proxy


def _proxy_candidates(value):
    proxy = _normalize_proxy(value)
    if not proxy:
        return [""]

    match = re.match(r"^([a-z0-9+.-]+)://(.+)$", proxy, re.I)
    if not match:
        return [proxy]

    first_scheme = match.group(1).lower()
    rest = match.group(2)
    schemes = [first_scheme]
    for scheme in ("socks5h", "socks5", "http", "https"):
        if scheme not in schemes:
            schemes.append(scheme)
    return [f"{scheme}://{rest}" for scheme in schemes]


def _call_checkout(token, payload, proxy=""):
    if curl_requests is not None:
        return _call_checkout_curl_cffi(token, payload, proxy)
    return _call_checkout_urllib(token, payload, proxy)


def _call_checkout_curl_cffi(token, payload, proxy=""):
    last_error = ""
    for candidate in _proxy_candidates(proxy):
        try:
            proxies = {"http": candidate, "https": candidate} if candidate else None
            response = curl_requests.post(
                CHECKOUT_URL,
                json=payload,
                headers=_request_headers(token),
                impersonate="chrome136",
                proxies=proxies,
                timeout=30,
            )
            text = response.text
            if _looks_like_cloudflare_challenge(text):
                last_error = "请求仍被 Cloudflare 拦截。请确认 run.bat 使用的是带 curl_cffi 的 Python 环境。"
                continue
            data = _parse_response_json(text)
            if isinstance(data, dict) and candidate:
                data["proxy_used"] = candidate
            return response.status_code, data
        except Exception as exc:
            last_error = str(exc)
            continue
    return 502, {"error": last_error or "请求失败"}


def _call_checkout_urllib(token, payload, proxy=""):
    candidates = _proxy_candidates(proxy)
    last_error = ""
    for candidate in candidates:
        if candidate.lower().startswith(("socks4://", "socks4a://", "socks5://", "socks5h://")):
            last_error = "当前 Python 环境不支持 urllib 使用 socks 代理，请用 run.bat 启动 curl_cffi 环境。"
            continue
        opener = None
        if candidate:
            opener = urllib.request.build_opener(
                urllib.request.ProxyHandler({"http": candidate, "https": candidate})
            )
        req = urllib.request.Request(
            CHECKOUT_URL,
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
            headers=_request_headers(token),
        )
        try:
            open_func = opener.open if opener else urllib.request.urlopen
            with open_func(req, timeout=30) as resp:
                text = resp.read().decode("utf-8", errors="replace")
                data = _parse_response_json(text)
                if isinstance(data, dict) and candidate:
                    data["proxy_used"] = candidate
                return resp.status, data
        except urllib.error.HTTPError as exc:
            text = exc.read().decode("utf-8", errors="replace")
            if _looks_like_cloudflare_challenge(text):
                last_error = "当前 Python 环境缺少 curl_cffi，普通请求被 Cloudflare 拦截。请用 run.bat 启动，或安装 curl_cffi。"
                continue
            data = _parse_response_json(text)
            if isinstance(data, dict) and candidate:
                data["proxy_used"] = candidate
            return exc.code, data
        except urllib.error.URLError as exc:
            last_error = str(exc.reason)
    return 502, {"error": last_error or "请求失败"}


def _check_proxy_ip(proxy=""):
    if curl_requests is not None:
        return _check_proxy_ip_curl_cffi(proxy)
    return _check_proxy_ip_urllib(proxy)


def _check_proxy_ip_curl_cffi(proxy=""):
    last_error = ""
    for candidate in _proxy_candidates(proxy):
        proxies = {"http": candidate, "https": candidate} if candidate else None
        for url in IP_CHECK_URLS:
            try:
                response = curl_requests.get(
                    url,
                    headers={
                        "Accept": "application/json",
                        "User-Agent": (
                            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                            "AppleWebKit/537.36 (KHTML, like Gecko) "
                            "Chrome/136.0.0.0 Safari/537.36"
                        ),
                    },
                    impersonate="chrome136",
                    proxies=proxies,
                    timeout=15,
                )
                if response.status_code >= 400:
                    last_error = f"{url} returned {response.status_code}"
                    continue
                data = _normalize_ip_check_response(_parse_response_json(response.text))
                if isinstance(data, dict) and candidate:
                    data["proxy_used"] = candidate
                return 200, data
            except Exception as exc:
                last_error = str(exc)
    return 502, {"error": last_error or "代理检测失败"}


def _check_proxy_ip_urllib(proxy=""):
    last_error = ""
    for candidate in _proxy_candidates(proxy):
        if candidate.lower().startswith(("socks4://", "socks4a://", "socks5://", "socks5h://")):
            last_error = "当前 Python 环境不支持 urllib 检测 socks 代理，请用 run.bat 启动 curl_cffi 环境。"
            continue
        opener = None
        if candidate:
            opener = urllib.request.build_opener(
                urllib.request.ProxyHandler({"http": candidate, "https": candidate})
            )
        for url in IP_CHECK_URLS:
            req = urllib.request.Request(
                url,
                headers={
                    "Accept": "application/json",
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/136.0.0.0 Safari/537.36"
                    ),
                },
            )
            try:
                open_func = opener.open if opener else urllib.request.urlopen
                with open_func(req, timeout=15) as resp:
                    text = resp.read().decode("utf-8", errors="replace")
                    data = _normalize_ip_check_response(_parse_response_json(text))
                    if isinstance(data, dict) and candidate:
                        data["proxy_used"] = candidate
                    return 200, data
            except Exception as exc:
                last_error = str(exc)
    return 502, {"error": last_error or "代理检测失败"}


def _normalize_ip_check_response(data):
    if not isinstance(data, dict):
        return {"error": "IP 检测服务返回异常"}

    connection = data.get("connection") if isinstance(data.get("connection"), dict) else {}
    loc = data.get("loc") or ""
    region = data.get("region") or data.get("region_name") or ""
    city = data.get("city") or ""

    return {
        "ip": data.get("ip") or data.get("query") or "",
        "country": data.get("country_long") or data.get("country") or data.get("country_name") or "",
        "country_code": data.get("country_short") or data.get("country_code") or data.get("cc") or data.get("countryCode") or "",
        "region": region,
        "city": city,
        "timezone": data.get("timezone") or "",
        "isp": connection.get("isp") or data.get("org") or data.get("isp") or "",
        "loc": loc,
    }


def _parse_response_json(text):
    try:
        return json.loads(text or "{}")
    except json.JSONDecodeError:
        return {"error": text or "返回不是 JSON"}


def _looks_like_cloudflare_challenge(text):
    lowered = (text or "").lower()
    return (
        "_cf_chl_opt" in lowered
        or "enable javascript and cookies to continue" in lowered
        or "cf-chl" in lowered
    )


def _enrich_links(data):
    if not isinstance(data, dict):
        return data
    session_id = data.get("checkout_session_id")
    processor = data.get("processor_entity")
    if session_id and processor and not data.get("chatgpt_checkout_url"):
        data["chatgpt_checkout_url"] = f"https://chatgpt.com/checkout/{processor}/{session_id}"
    for key in ("url", "stripe_hosted_url", "checkout_url"):
        value = data.get(key)
        if isinstance(value, str) and value.startswith("https://pay.openai.com/"):
            data["openai_payurl"] = value
            break
    return data


class Handler(BaseHTTPRequestHandler):
    def do_HEAD(self):
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            content = INDEX_HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            return
        self.send_response(404)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            self._send(200, INDEX_HTML.encode("utf-8"), "text/html; charset=utf-8")
            return
        self._send_json(404, {"error": "not found"})

    def do_POST(self):
        if self.path == "/api/proxy-check":
            try:
                body = _read_json(self)
                proxy = _normalize_proxy(body.get("proxy"))
                status, data = _check_proxy_ip(proxy)
                self._send_json(status, data)
            except Exception as exc:
                self._send_json(500, {"error": str(exc)})
            return

        if self.path != "/api/checkout":
            self._send_json(404, {"error": "not found"})
            return
        try:
            body = _read_json(self)
            token = _extract_token(body.get("token"))
            if not token:
                self._send_json(400, {"error": "没有识别到 accessToken"})
                return
            payload = _checkout_payload(body)
            proxy = _normalize_proxy(body.get("proxy"))
            status, data = _call_checkout(token, payload, proxy)
            data = _enrich_links(data)
            self._send_json(status, data)
        except Exception as exc:
            self._send_json(500, {"error": str(exc)})

    def _send_json(self, status, payload):
        self._send(status, json.dumps(payload, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def _send(self, status, content, content_type):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, fmt, *args):
        return


if __name__ == "__main__":
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    engine = "curl_cffi" if curl_requests is not None else "urllib"
    print(f"Local Pay URL Generator: http://{HOST}:{PORT}/")
    print(f"Request engine: {engine}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
