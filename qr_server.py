"""
ChatGPT Plus UPI QR 码 Web 工具
启动: python qr_server.py
访问: http://127.0.0.1:7791
"""

import json
import base64
import random
import time
import re
import threading
import os
import sys
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

try:
    from curl_cffi import requests as curl_requests
except Exception:
    curl_requests = None

try:
    from playwright.sync_api import sync_playwright
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False

import urllib.parse
import urllib.request
import urllib.error

HOST = "127.0.0.1"
PORT = 7791
CHECKOUT_API = "https://chatgpt.com/backend-api/payments/checkout"
WORK_DIR = Path(__file__).parent

COUNTRY_CURRENCY = {
    "AT": "EUR", "AU": "AUD", "BE": "EUR", "BR": "BRL", "CA": "CAD", "CH": "CHF",
    "CZ": "CZK", "DE": "EUR", "DK": "DKK", "ES": "EUR", "FI": "EUR", "FR": "EUR",
    "GB": "GBP", "HK": "HKD", "ID": "IDR", "IE": "EUR", "IN": "INR", "IT": "EUR",
    "JP": "JPY", "KR": "KRW", "MX": "MXN", "MY": "MYR", "NL": "EUR", "NO": "NOK",
    "NZ": "NZD", "PH": "PHP", "PL": "PLN", "PT": "EUR", "SE": "SEK", "SG": "SGD",
    "TH": "THB", "TW": "TWD", "US": "USD", "VN": "VND",
}
COUNTRY_TIMEZONE = {
    "AT": "Europe/Vienna", "AU": "Australia/Sydney", "BE": "Europe/Brussels",
    "BR": "America/Sao_Paulo", "CA": "America/Toronto", "CH": "Europe/Zurich",
    "CZ": "Europe/Prague", "DE": "Europe/Berlin", "DK": "Europe/Copenhagen",
    "ES": "Europe/Madrid", "FI": "Europe/Helsinki", "FR": "Europe/Paris",
    "GB": "Europe/London", "HK": "Asia/Hong_Kong", "ID": "Asia/Jakarta",
    "IE": "Europe/Dublin", "IN": "Asia/Kolkata", "IT": "Europe/Rome",
    "JP": "Asia/Tokyo", "KR": "Asia/Seoul", "MX": "America/Mexico_City",
    "MY": "Asia/Kuala_Lumpur", "NL": "Europe/Amsterdam", "NO": "Europe/Oslo",
    "NZ": "Pacific/Auckland", "PH": "Asia/Manila", "PL": "Europe/Warsaw",
    "PT": "Europe/Lisbon", "SE": "Europe/Stockholm", "SG": "Asia/Singapore",
    "TH": "Asia/Bangkok", "TW": "Asia/Taipei", "US": "America/New_York",
    "VN": "Asia/Ho_Chi_Minh",
}
COUNTRY_LABELS = [
    ("IN", "印度 IN"), ("US", "美国 US"), ("JP", "日本 JP"), ("NL", "荷兰 NL"),
    ("DE", "德国 DE"), ("FR", "法国 FR"), ("GB", "英国 GB"), ("ID", "印尼 ID"),
    ("BR", "巴西 BR"), ("CA", "加拿大 CA"), ("AU", "澳大利亚 AU"), ("KR", "韩国 KR"),
    ("SG", "新加坡 SG"), ("HK", "香港 HK"), ("TW", "台湾 TW"), ("VN", "越南 VN"),
    ("MX", "墨西哥 MX"), ("TH", "泰国 TH"), ("MY", "马来 MY"), ("PH", "菲律宾 PH"),
    ("CH", "瑞士 CH"), ("SE", "瑞典 SE"), ("NO", "挪威 NO"), ("DK", "丹麦 DK"),
    ("PL", "波兰 PL"), ("CZ", "捷克 CZ"), ("AT", "奥地利 AT"), ("BE", "比利时 BE"),
    ("FI", "芬兰 FI"), ("IE", "爱尔兰 IE"), ("IT", "意大利 IT"), ("PT", "葡萄牙 PT"),
    ("ES", "西班牙 ES"), ("NZ", "新西兰 NZ"),
]


def billing_preset(country: str) -> dict:
    country = (country or "IN").upper()
    return {
        "country": country,
        "currency": COUNTRY_CURRENCY.get(country, "USD"),
        "timezone": COUNTRY_TIMEZONE.get(country, "America/New_York"),
    }


# =============================================================================
# PersonPool (from get_qr_code.py)
# =============================================================================

class PersonPool:
    FIRST_NAMES = [
        "Aarav", "Vihaan", "Arjun", "Sai", "Reyansh", "Ayaan", "Ananya",
        "Diya", "Sneha", "Priya", "Neha", "Kavya", "Ishita", "Riya",
        "Aditya", "Rohan", "Vikram", "Raj", "Amit", "Suresh", "Deepak",
        "Sunita", "Meena", "Lakshmi", "Pooja", "Radha", "Shweta",
        "Rajesh", "Nikhil", "Manish", "Rahul", "Vivek", "Anil",
        "Karthik", "Varun", "Anjali", "Nandini", "Pallavi", "Tanya",
        "Arun", "Prakash", "Ganesh", "Dinesh", "Mahesh", "Sanjay",
    ]
    LAST_NAMES = [
        "Sharma", "Patel", "Singh", "Kumar", "Verma", "Gupta", "Shah",
        "Reddy", "Nair", "Menon", "Joshi", "Desai", "Mehta", "Das",
        "Bose", "Sen", "Chopra", "Kapoor", "Malhotra", "Agarwal",
        "Yadav", "Jain", "Pandey", "Mishra", "Tiwari", "Dubey",
        "Rao", "Naidu", "Pillai", "Iyer", "Choudhury", "Banerjee",
    ]
    CITIES = [
        {"city": "Mumbai",       "state": "Maharashtra",      "pin": "400001"},
        {"city": "Pune",         "state": "Maharashtra",      "pin": "411001"},
        {"city": "Nagpur",       "state": "Maharashtra",      "pin": "440001"},
        {"city": "Delhi",        "state": "Delhi",            "pin": "110001"},
        {"city": "Bengaluru",    "state": "Karnataka",        "pin": "560001"},
        {"city": "Mysuru",       "state": "Karnataka",        "pin": "570001"},
        {"city": "Hyderabad",    "state": "Telangana",        "pin": "500001"},
        {"city": "Chennai",      "state": "Tamil Nadu",       "pin": "600001"},
        {"city": "Coimbatore",   "state": "Tamil Nadu",       "pin": "641001"},
        {"city": "Kolkata",      "state": "West Bengal",      "pin": "700001"},
        {"city": "Ahmedabad",    "state": "Gujarat",          "pin": "380001"},
        {"city": "Surat",        "state": "Gujarat",          "pin": "395001"},
        {"city": "Jaipur",       "state": "Rajasthan",        "pin": "302001"},
        {"city": "Udaipur",      "state": "Rajasthan",        "pin": "313001"},
        {"city": "Lucknow",      "state": "Uttar Pradesh",    "pin": "226001"},
        {"city": "Kanpur",       "state": "Uttar Pradesh",    "pin": "208001"},
        {"city": "Noida",        "state": "Uttar Pradesh",    "pin": "201301"},
        {"city": "Patna",        "state": "Bihar",            "pin": "800001"},
        {"city": "Bhopal",       "state": "Madhya Pradesh",   "pin": "462001"},
        {"city": "Indore",       "state": "Madhya Pradesh",   "pin": "452001"},
        {"city": "Chandigarh",   "state": "Chandigarh",       "pin": "160001"},
        {"city": "Bhubaneswar",  "state": "Odisha",           "pin": "751001"},
        {"city": "Guwahati",     "state": "Assam",            "pin": "781001"},
        {"city": "Kochi",        "state": "Kerala",           "pin": "682001"},
        {"city": "Thane",        "state": "Maharashtra",      "pin": "400601"},
        {"city": "Nashik",       "state": "Maharashtra",      "pin": "422001"},
        {"city": "Vadodara",     "state": "Gujarat",          "pin": "390001"},
        {"city": "Jodhpur",      "state": "Rajasthan",        "pin": "342001"},
        {"city": "Agra",         "state": "Uttar Pradesh",    "pin": "282001"},
        {"city": "Gwalior",      "state": "Madhya Pradesh",   "pin": "474001"},
    ]
    STREETS = [
        "MG Road", "Park Street", "Station Road", "Main Bazaar",
        "Link Road", "Ring Road", "Civil Lines", "Rajpath",
        "College Road", "Hospital Road", "Temple Road", "Market Road",
        "Gandhi Nagar", "Nehru Colony", "Shivaji Nagar", "Patel Nagar",
    ]
    DOMAINS = ["gmail.com", "yahoo.com", "outlook.com", "hotmail.com", "proton.me"]

    def __init__(self, seed: int = None):
        self.rng = random.Random(seed or int(time.time() * 1000))

    def generate(self) -> dict:
        city = self.rng.choice(self.CITIES)
        first = self.rng.choice(self.FIRST_NAMES)
        last = self.rng.choice(self.LAST_NAMES)
        house = str(self.rng.randint(1, 299))
        street = self.rng.choice(self.STREETS)
        name = f"{first} {last}"
        tag = self.rng.randint(100, 9999)
        domain = self.rng.choice(self.DOMAINS)
        email = f"{first.lower()}{last.lower()}{tag}@{domain}"
        return {
            "name": name, "email": email,
            "country": "IN", "city": city["city"],
            "state": city["state"][:2].upper(),
            "postal_code": city["pin"],
            "line1": f"H.No {house}, {street}",
        }


# =============================================================================
# Checkout API (from server.py)
# =============================================================================

def _create_checkout(token: str, proxy: str = "", country: str = "IN",
                     currency: str = "", session_token: str = "") -> dict:
    preset = billing_preset(country)
    billing_country = preset["country"]
    billing_currency = (currency or preset["currency"]).upper()
    payload = {
        "plan_name": "chatgptplusplan",
        "billing_details": {"country": billing_country, "currency": billing_currency},
        "checkout_ui_mode": "hosted",
        "cancel_url": "https://chatgpt.com/#pricing",
    }
    headers = {
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
    cookies = {"__Secure-next-auth.session-token": session_token} if session_token else None

    if curl_requests is not None:
        proxies = {"http": proxy, "https": proxy} if proxy else None
        resp = curl_requests.post(CHECKOUT_API, json=payload, headers=headers,
                                  impersonate="chrome136", proxies=proxies,
                                  cookies=cookies, timeout=30)
        status = resp.status_code
        text = resp.text
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            data = {"error": text}
    else:
        try:
            req_headers = dict(headers)
            if cookies:
                req_headers["Cookie"] = "; ".join(f"{k}={v}" for k, v in cookies.items())
            req = urllib.request.Request(CHECKOUT_API, data=json.dumps(payload).encode("utf-8"),
                                         headers=req_headers, method="POST")
            with urllib.request.urlopen(req, timeout=15) as resp:
                status = resp.getcode()
                text = resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            status = exc.code
            text = exc.read().decode("utf-8", errors="replace")
        except urllib.error.URLError as exc:
            raise RuntimeError(
                f"无法连接 ChatGPT API ({exc.reason})。"
                "请安装 curl_cffi 以绕过 Cloudflare: pip install curl_cffi"
            )
        except Exception as exc:
            raise RuntimeError(f"请求失败: {exc}")
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            data = {"error": text}

    if status != 200:
        if "_cf_chl_opt" in (text or "").lower() or "cf-chl" in (text or "").lower():
            raise RuntimeError("被 Cloudflare 拦截，请安装 curl_cffi")
        raise RuntimeError(f"ChatGPT API {status}: {text[:600]}")

    sid = data.get("checkout_session_id") or data.get("id")
    if sid and not data.get("url"):
        data["url"] = f"https://pay.openai.com/c/pay/{sid}"
    return data


# =============================================================================
# Playwright QR Extraction
# =============================================================================

def _extract_qr_via_browser(pay_url: str, person: dict) -> bytes:
    return _extract_qr_via_browser_sse(pay_url, person, lambda *a: None, lambda s, m: (_ for _ in ()).throw(RuntimeError(m)))


def _extract_qr_via_browser_sse(pay_url: str, person: dict,
                                 prog, err) -> bytes:
    if not HAS_PLAYWRIGHT:
        raise ImportError("playwright 未安装")

    captured = {"qr": None}

    with sync_playwright() as p:
        prog("browser", "启动浏览器...")
        browser = p.chromium.launch(
            headless=True,
            channel="chrome",
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )
        ctx = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/136.0.0.0 Safari/537.36"
            ),
            locale="en-IN",
        )
        page = ctx.new_page()

        def on_route(route):
            url = route.request.url
            if "api.stripe.com/v1/payment_pages" in url and "/confirm" in url:
                resp = route.fetch()
                try:
                    body = resp.json()
                    pi = body.get("payment_intent", {})
                    na = pi.get("next_action", {})
                    upi = na.get("upi", {})
                    qr = upi.get("qr_code", "")
                    if qr:
                        captured["qr"] = base64.b64decode(qr.split(",", 1)[1])
                except Exception:
                    pass
                route.fulfill(response=resp)
            else:
                route.continue_()

        page.route("**/*", on_route)
        prog("browser", "打开支付页面...")
        page.goto(pay_url, wait_until="load", timeout=60000)
        page.wait_for_timeout(5000)

        # Check for error page
        body_text = (page.evaluate("() => document.body.innerText") or "").lower()
        if "something went wrong" in body_text or "could not be found" in body_text:
            prog("browser", "支付页面加载完成，但返回错误")
            browser.close()
            raise RuntimeError("Stripe 返回错误：支付会话无效或已过期，请重新获取链接")

        prog("fill", "填写邮箱...")
        try:
            el = page.query_selector('input[autocomplete="email"], input[name="email"]')
            if el and el.is_visible():
                el.click(); el.fill(""); el.type(person["email"], delay=40)
        except Exception:
            pass

        page.wait_for_timeout(1500)
        prog("fill", "选择 UPI 支付方式...")
        for sel in [
            'button[aria-label*="UPI"]', 'button:has-text("UPI")',
            'label:has-text("UPI")', 'img[alt*="UPI"]',
        ]:
            try:
                el = page.query_selector(sel)
                if el and el.is_visible():
                    el.click()
                    page.wait_for_timeout(2000)
                    break
            except Exception:
                continue

        prog("fill", "填写姓名与地址...")
        try:
            el = page.query_selector(
                'input[autocomplete="name"], input[name="name"], input[placeholder*="Name"]')
            if el and el.is_visible():
                el.click(); el.fill(""); el.type(person["name"], delay=40)
        except Exception:
            pass
        page.wait_for_timeout(600)

        for field, sels in [
            ("line1",       'input[autocomplete="address-line1"], input[name="address-line1"]'),
            ("city",        'input[autocomplete="address-level2"], input[name="city"]'),
            ("state",       'input[autocomplete="address-level1"], input[name="state"]'),
            ("postal_code", 'input[autocomplete="postal-code"], input[name="postal-code"]'),
        ]:
            try:
                el = page.query_selector(sels)
                if el and el.is_visible() and field in person:
                    el.click(); el.fill(""); el.type(str(person[field]), delay=30)
            except Exception:
                pass

        page.wait_for_timeout(500)
        prog("qr", "确认支付...")
        for sel in [
            'button[type="submit"]', 'button:has-text("Pay")',
            'button:has-text("Subscribe")', 'button:has-text("Confirm")',
        ]:
            try:
                el = page.query_selector(sel)
                if el and el.is_visible() and el.is_enabled():
                    el.click()
                    break
            except Exception:
                continue

        prog("qr", "等待 QR 码...")
        deadline = time.time() + 30
        while time.time() < deadline:
            if captured["qr"]:
                break
            try:
                b64 = page.evaluate("""() => {
                    const imgs = document.querySelectorAll('img[src^="data:image/png;base64,"]');
                    for (const img of imgs) if (img.src.length > 200) return img.src;
                    return null;
                }""")
                if b64:
                    captured["qr"] = base64.b64decode(b64.split(",", 1)[1])
                    break
            except Exception:
                pass
            time.sleep(0.8)

        browser.close()

    if captured["qr"] is None:
        raise RuntimeError("未能提取 QR 码，请确认支付页面流程是否正常。")
    return captured["qr"]


# =============================================================================
# Account JSON Parser
# =============================================================================

def parse_account(raw: str) -> dict:
    raw = raw.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    m = re.search(r'eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+', raw)
    if m:
        return {"accessToken": m.group(0)}
    raise ValueError("无法解析账户信息")


def extract_info(account: dict) -> tuple:
    token = account.get("accessToken") or account.get("access_token") or ""
    user = account.get("user", {})
    name = user.get("name", "")
    email = user.get("email", "")
    return token, name, email


# =============================================================================
# HTML
# =============================================================================

HTML = r"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width,initial-scale=1" />
<title>ChatGPT Plus UPI QR 码生成器</title>
<style>
:root {
  color-scheme: dark;
  font-family: -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;
  --bg: #0d1117; --card: #161b22; --border: #30363d;
  --text: #c9d1d9; --muted: #8b949e; --accent: #58a6ff;
  --green: #3fb950; --red: #f85149; --orange: #d29922;
}
body { margin:0; background:var(--bg); color:var(--text); min-height:100vh; }
.wrap { max-width:700px; margin:0 auto; padding:24px 16px; }
.card { background:var(--card); border:1px solid var(--border); border-radius:12px;
  padding:24px; box-shadow:0 4px 24px rgba(0,0,0,.3); }
h1 { margin:0 0 4px; font-size:22px; display:flex; align-items:center; gap:8px; }
h1 svg { width:24px; height:24px; }
.subtitle { color:var(--muted); font-size:13px; margin:0 0 20px; }
label { display:block; margin:18px 0 6px; font-weight:600; font-size:13px; }
textarea { width:100%; box-sizing:border-box; border:1px solid var(--border);
  border-radius:8px; padding:12px; font:13px/1.5 ui-monospace,SFMono-Regular,Consolas,monospace;
  background:#0d1117; color:var(--text); min-height:160px; resize:vertical; }
textarea:focus { outline:none; border-color:var(--accent); box-shadow:0 0 0 2px rgba(88,166,255,.15); }
.row { display:flex; gap:10px; align-items:center; margin-top:16px; flex-wrap:wrap; }
button, .btn { display:inline-flex; align-items:center; gap:6px;
  border:1px solid var(--border); border-radius:8px; padding:10px 20px;
  font-weight:600; font-size:13px; cursor:pointer; transition:.15s; }
.btn-primary { background:var(--accent); color:#fff; border-color:var(--accent); }
.btn-primary:hover { background:#4090e0; }
.btn-primary:disabled { opacity:.45; cursor:not-allowed; }
.btn-outline { background:transparent; color:var(--text); }
.btn-outline:hover { background:#21262d; }
.steps { margin:16px 0 6px; }
.step { display:flex; align-items:flex-start; gap:12px; padding:10px 0;
  border-bottom:1px solid var(--border); font-size:13px; opacity:.45; transition:opacity .3s; }
.step:last-child { border-bottom:none; }
.step-icon { width:22px; height:22px; border-radius:50%; flex-shrink:0; margin-top:0;
  display:flex; align-items:center; justify-content:center;
  border:2px solid var(--border); color:var(--muted); font-size:11px; font-weight:700;
  transition:all .3s; }
.step-pending .step-icon { background:#21262d; }
.step-running  { opacity:1; }
.step-running  .step-icon { background:var(--orange); border-color:var(--orange); color:#fff; animation:pulse 1.2s infinite; }
.step-done     { opacity:1; }
.step-done     .step-icon { background:var(--green); border-color:var(--green); color:#fff; }
.step-error    { opacity:1; }
.step-error    .step-icon { background:var(--red); border-color:var(--red); color:#fff; }
.step-content { flex:1; padding-top:1px; }
.step-label { font-weight:600; }
.step-detail { color:var(--muted); font-size:11px; margin-top:2px; }
.step-time { color:var(--muted); font-size:10px; font-weight:400; }
.result { margin-top:20px; display:none; }
.result-card { background:var(--card); border:1px solid var(--border); border-radius:12px;
  padding:24px; text-align:center; }
.result-card img { max-width:260px; border-radius:8px; border:4px solid #fff; }
.result-card .qr-label { font-size:13px; color:var(--muted); margin:12px 0 6px; }
.result-card .person-info { font-size:12px; color:var(--muted); margin-top:10px; }
.toast { position:fixed; top:16px; left:50%; transform:translateX(-50%);
  padding:10px 20px; border-radius:8px; font-size:13px; font-weight:600;
  z-index:999; display:none; }
.toast-error { background:#490202; color:#f85149; border:1px solid #f85149; }
@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.4} }
.accordion { margin-top:16px; }
.accordion summary { color:var(--muted); font-size:12px; cursor:pointer; }
.accordion pre { background:#0d1117; border:1px solid var(--border); border-radius:8px;
  padding:12px; font-size:11px; overflow:auto; max-height:200px; color:var(--muted); }
.settings { display:flex; flex-wrap:wrap; gap:12px; margin-top:12px; }
.checkbox-row { display:flex; align-items:center; gap:6px; font-size:12px; color:var(--muted); }
.checkbox-row input { width:14px; height:14px; }
</style>
</head>
<body>
<div class="wrap">
  <div class="card">
    <h1>
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/><rect x="7" y="7" width="3" height="3"/><rect x="14" y="7" width="3" height="3"/><rect x="7" y="14" width="3" height="3"/><rect x="14" y="14" width="3" height="3"/></svg>
      UPI QR 码生成器
    </h1>
    <p class="subtitle">粘贴 ChatGPT 账户 JSON → 自动创建印度 UPI 支付 → 提取 QR 码</p>

    <label>账户 JSON / accessToken</label>
    <textarea id="jsonInput" placeholder='粘贴 https://chatgpt.com/api/auth/session 返回的 JSON，或直接粘贴 accessToken（eyJ...）'></textarea>
    <div id="accountHint" class="subtitle" style="margin-top:4px"></div>

    <div class="settings">
      <label class="checkbox-row">
        <input type="checkbox" id="reuseSession" checked />
        复用上次的 checkout session
      </label>
      <label class="checkbox-row">
        <input type="checkbox" id="manualSession" />
        手动提供支付链接 (跳过 API，直接填 cs_live_xxx)
      </label>
    </div>

    <div class="settings" id="billingGroup">
      <div style="display:flex; gap:10px; align-items:flex-end; flex-wrap:wrap;">
        <div style="flex:1; min-width:160px;">
          <label for="country" style="margin:0 0 4px;">地区 / Region</label>
          <select id="country" style="width:100%;box-sizing:border-box;border:1px solid var(--border);border-radius:8px;padding:10px;background:#0d1117;color:var(--text);font:13px inherit;"></select>
        </div>
        <div style="flex:1; min-width:120px;">
          <label for="currency" style="margin:0 0 4px;">币种 / Currency</label>
          <input id="currency" value="INR" maxlength="3" style="width:100%;box-sizing:border-box;border:1px solid var(--border);border-radius:8px;padding:10px;background:#0d1117;color:var(--text);font:13px monospace;text-transform:uppercase;" />
        </div>
      </div>
    </div>

    <div id="manualUrlGroup" style="display:none; margin-top:8px;">
      <input id="manualPayUrl" placeholder="粘贴 pay.openai.com/c/pay/cs_live_xxx 完整链接" style="width:100%;box-sizing:border-box;border:1px solid var(--border);border-radius:8px;padding:10px;font:13px monospace;background:#0d1117;color:var(--text);" />
    </div>

    <div class="row">
      <button id="goBtn" class="btn-primary">生成 QR 码</button>
      <button id="copyBtn" class="btn-outline" disabled>复制到剪贴板</button>
      <button id="downloadBtn" class="btn-outline" disabled>下载 PNG</button>
    </div>

    <div id="steps" class="steps">
      <div class="step step-pending">
        <div class="step-icon">1</div>
        <div class="step-content"><div class="step-label">等待开始</div></div>
      </div>
      <div class="step step-pending">
        <div class="step-icon">2</div>
        <div class="step-content"><div class="step-label">创建支付会话</div></div>
      </div>
      <div class="step step-pending">
        <div class="step-icon">3</div>
        <div class="step-content"><div class="step-label">启动浏览器</div></div>
      </div>
      <div class="step step-pending">
        <div class="step-icon">4</div>
        <div class="step-content"><div class="step-label">填写支付信息</div></div>
      </div>
      <div class="step step-pending">
        <div class="step-icon">5</div>
        <div class="step-content"><div class="step-label">确认支付 & 提取 QR</div></div>
      </div>
    </div>
    <div id="progressBar" style="display:none; height:3px; background:#21262d; border-radius:3px; margin:12px 0; overflow:hidden;">
      <div id="progressFill" style="height:100%; width:0%; background:var(--accent); transition: width .3s;"></div>
    </div>

    <div id="result" class="result">
      <div class="result-card">
        <div class="qr-label">请用 UPI 应用扫描以下 QR 码完成支付</div>
        <img id="qrImage" src="" alt="UPI QR Code" />
        <div class="person-info" id="personInfo"></div>
      </div>
      <details class="accordion">
        <summary>响应明细</summary>
        <pre id="responseDetail"></pre>
      </details>
    </div>
  </div>
</div>
<div id="toast" class="toast"></div>

<script>
const $ = id => document.getElementById(id);

let currentB64 = '';

const COUNTRY_CURRENCY = {
  "AT":"EUR","AU":"AUD","BE":"EUR","BR":"BRL","CA":"CAD","CH":"CHF",
  "CZ":"CZK","DE":"EUR","DK":"DKK","ES":"EUR","FI":"EUR","FR":"EUR",
  "GB":"GBP","HK":"HKD","ID":"IDR","IE":"EUR","IN":"INR","IT":"EUR",
  "JP":"JPY","KR":"KRW","MX":"MXN","MY":"MYR","NL":"EUR","NO":"NOK",
  "NZ":"NZD","PH":"PHP","PL":"PLN","PT":"EUR","SE":"SEK","SG":"SGD",
  "TH":"THB","TW":"TWD","US":"USD","VN":"VND"
};
const COUNTRY_LABELS = [
  ["IN","印度 IN"],["US","美国 US"],["JP","日本 JP"],["NL","荷兰 NL"],
  ["DE","德国 DE"],["FR","法国 FR"],["GB","英国 GB"],["ID","印尼 ID"],
  ["BR","巴西 BR"],["CA","加拿大 CA"],["AU","澳大利亚 AU"],["KR","韩国 KR"],
  ["SG","新加坡 SG"],["HK","香港 HK"],["TW","台湾 TW"],["VN","越南 VN"],
  ["MX","墨西哥 MX"],["TH","泰国 TH"],["MY","马来 MY"],["PH","菲律宾 PH"],
  ["CH","瑞士 CH"],["SE","瑞典 SE"],["NO","挪威 NO"],["DK","丹麦 DK"],
  ["PL","波兰 PL"],["CZ","捷克 CZ"],["AT","奥地利 AT"],["BE","比利时 BE"],
  ["FI","芬兰 FI"],["IE","爱尔兰 IE"],["IT","意大利 IT"],["PT","葡萄牙 PT"],
  ["ES","西班牙 ES"],["NZ","新西兰 NZ"]
];

(function initCountrySelect() {
  const sel = $('country');
  for (const [code, label] of COUNTRY_LABELS) {
    const opt = document.createElement('option');
    opt.value = code; opt.textContent = label;
    sel.appendChild(opt);
  }
  sel.value = 'IN';
  updateCurrencyForCountry();
})();

function updateCurrencyForCountry() {
  const c = $('country').value.trim().toUpperCase();
  $('currency').value = COUNTRY_CURRENCY[c] || 'USD';
}

$('country').addEventListener('change', updateCurrencyForCountry);

function updateHint() {
  let raw = $('jsonInput').value.trim();
  let h = '';
  if (!raw) { $('accountHint').textContent = ''; return; }
  try {
    let j = JSON.parse(raw);
    let u = j.user || {};
    let a = j.account || {};
    let parts = [];
    if (u.email) parts.push(u.email);
    if (u.name) parts.push(u.name);
    if (a.planType) parts.push('Plan: ' + a.planType);
    h = parts.join('  |  ');
  } catch(e) {
    if (/^eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$/.test(raw)) {
      h = '已识别 JWT accessToken';
    }
  }
  $('accountHint').textContent = h;
}

function showToast(msg, type) {
  let t = $('toast');
  t.textContent = msg;
  t.className = 'toast toast-' + (type || 'error');
  t.style.display = 'block';
  clearTimeout(t._t);
  t._t = setTimeout(() => { t.style.display = 'none'; }, 4000);
}

function setStep(idx, status, label, detail) {
  let root = $('steps');
  while (root.children.length <= idx) {
    let d = document.createElement('div'); d.className = 'step step-pending';
    d.innerHTML = '<div class="step-icon"></div><div class="step-content"><div class="step-label"></div><div class="step-detail"></div></div>';
    root.appendChild(d);
  }
  let el = root.children[idx];
  el.className = 'step step-' + status;
  el.querySelector('.step-label').textContent = label || '';
  if (detail !== undefined) el.querySelector('.step-detail').textContent = detail || '';
}

$('jsonInput').addEventListener('input', updateHint);

$('manualSession').addEventListener('change', function() {
  $('manualUrlGroup').style.display = this.checked ? 'block' : 'none';
  $('billingGroup').style.display = this.checked ? 'none' : 'flex';
  $('jsonInput').style.display = this.checked ? 'none' : '';
});

$('goBtn').addEventListener('click', async () => {
  let manualMode = $('manualSession').checked;
  $('goBtn').disabled = true;
  $('goBtn').textContent = '处理中...';
  $('result').style.display = 'none';
  $('copyBtn').disabled = true;
  $('downloadBtn').disabled = true;
  currentB64 = '';

  let payload = {
    reuse_session: $('reuseSession').checked,
    proxy: '',
    country: $('country').value.trim().toUpperCase(),
    currency: $('currency').value.trim().toUpperCase(),
  };
  if (manualMode) {
    let url = ($('manualPayUrl').value || '').trim();
    if (!url || !url.includes('cs_live_')) { showToast('请填写有效的支付链接', 'error'); resetBtn(); return; }
    payload.pay_url = url;
  } else {
    let raw = $('jsonInput').value.trim();
    if (!raw) { showToast('请先粘贴账户 JSON 或 accessToken', 'error'); resetBtn(); return; }
    payload.account_json = raw;
  }

  let allSteps = $('steps').querySelectorAll('.step');
  let steps = [];
  for (let s of allSteps) steps.push(s);
  for (let s of steps) { s.className = 'step step-pending'; s.querySelector('.step-label').textContent = s.querySelector('.step-label').textContent.split(' - ')[0].trim(); s.querySelector('.step-detail') ? s.querySelector('.step-detail').textContent = '' : null; }

  let pb = $('progressBar');
  let pf = $('progressFill');
  pb.style.display = 'block';
  pf.style.width = '0%';

  let stepIdxMap = { 'parse': 0, 'session': 1, 'browser': 2, 'fill': 3, 'qr': 4 };
  let progressMap = { 'parse': 10, 'session': 30, 'browser': 50, 'fill': 70, 'qr': 90 };

  function setProgress(step) {
    let pct = progressMap[step] || 0;
    pf.style.width = pct + '%';
    let idx = stepIdxMap[step];
    if (idx !== undefined && idx < steps.length) {
      for (let i = 0; i < idx; i++) {
        steps[i].className = 'step step-done';
      }
      steps[idx].className = 'step step-running';
    }
  }

  try {
    let resp = await fetch('/api/generate-stream', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload)
    });
    if (!resp.ok) {
      let err = await resp.json();
      throw new Error(err.error || resp.statusText);
    }
    let reader = resp.body.getReader();
    let decoder = new TextDecoder();
    let buf = '';
    let resultData = null;

    while (true) {
      let {done, value} = await reader.read();
      if (done) break;
      buf += decoder.decode(value, {stream: true});

      let lines = buf.split('\n');
      buf = lines.pop() || '';

      for (let line of lines) {
        if (line.startsWith('data: ')) {
          let data = JSON.parse(line.slice(6));
          if (data.type === 'progress') {
            setProgress(data.step);
            let idx = stepIdxMap[data.step];
            if (idx !== undefined && idx < steps.length) {
              let el = steps[idx];
              el.className = 'step step-running';
              el.querySelector('.step-label').textContent = el.querySelector('.step-label').textContent.split(' - ')[0].trim() + ' - ' + (data.msg || '');
            }
          } else if (data.type === 'done') {
            setProgress('qr');
            pf.style.width = '100%';
            for (let s of steps) s.className = 'step step-done';
            resultData = data;
          } else if (data.type === 'error') {
            let idx = stepIdxMap[data.step];
            if (idx !== undefined && idx < steps.length) {
              steps[idx].className = 'step step-error';
              steps[idx].querySelector('.step-label').textContent = steps[idx].querySelector('.step-label').textContent.split(' - ')[0].trim() + ' - 失败';
              steps[idx].querySelector('.step-detail').textContent = data.msg || '';
            }
            throw new Error(data.msg || '处理失败');
          }
        }
      }
    }

    if (resultData && resultData.qr_base64) {
      $('qrImage').src = 'data:image/png;base64,' + resultData.qr_base64;
      currentB64 = resultData.qr_base64;
      $('personInfo').textContent = '虚拟身份: ' + (resultData.person || '');
      try { $('responseDetail').textContent = JSON.stringify(resultData.detail || {}, null, 2); } catch(e) {}
      $('result').style.display = 'block';
      $('copyBtn').disabled = false;
      $('downloadBtn').disabled = false;
    }

  } catch(e) {
    if (e.name !== 'AbortError') showToast(e.message, 'error');
  } finally {
    setTimeout(() => { pb.style.display = 'none'; }, 800);
    resetBtn();
  }
});

function resetBtn() {
  $('goBtn').disabled = false;
  $('goBtn').textContent = '生成 QR 码';
}

$('copyBtn').addEventListener('click', async () => {
  if (!currentB64) return;
  try {
    let blob = await (await fetch('data:image/png;base64,' + currentB64)).blob();
    await navigator.clipboard.write([new ClipboardItem({'image/png': blob})]);
    showToast('QR 码已复制到剪贴板', '');
  } catch(e) {
    showToast('复制失败，请用下载按钮', 'error');
  }
});

$('downloadBtn').addEventListener('click', () => {
  if (!currentB64) return;
  let a = document.createElement('a');
  a.href = 'data:image/png;base64,' + currentB64;
  a.download = 'upi_qr.png';
  a.click();
});
</script>
</body>
</html>"""


# =============================================================================
# HTTP Handler
# =============================================================================

class Handler(BaseHTTPRequestHandler):

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/":
            self._send(200, HTML.encode("utf-8"), "text/html; charset=utf-8")
            return
        if path == "/api/status":
            self._send_json(200, {
                "playwright": HAS_PLAYWRIGHT,
                "curl_cffi": curl_requests is not None,
                "ready": HAS_PLAYWRIGHT and curl_requests is not None,
            })
            return
        self._send_json(404, {"error": "not found"})

    def do_POST(self):
        if self.path == "/api/generate":
            self._handle_generate(sse=False)
        elif self.path == "/api/generate-stream":
            self._handle_generate(sse=True)
        else:
            self._send_json(404, {"error": "not found"})

    def _sse_event(self, data: dict):
        payload = json.dumps(data, ensure_ascii=False)
        self.wfile.write(f"data: {payload}\n\n".encode("utf-8"))
        self.wfile.flush()

    def _handle_generate(self, sse: bool = False):
        if sse:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()

        try:
            body = self._read_body()
            raw = body.get("account_json", "")
            pay_url_manual = body.get("pay_url", "").strip()
            proxy = body.get("proxy", "")
            reuse = bool(body.get("reuse_session", True))
            country = (body.get("country") or "IN").strip().upper()
            currency = (body.get("currency") or "").strip().upper()

            def prog(step: str, msg: str = ""):
                if sse:
                    self._sse_event({"type": "progress", "step": step, "msg": msg})

            def fail(step: str, msg: str):
                if sse:
                    self._sse_event({"type": "error", "step": step, "msg": msg})
                raise RuntimeError(msg)

            prog("parse", "解析参数...")

            if not HAS_PLAYWRIGHT:
                fail("parse", "playwright 未安装")

            pool = PersonPool()
            person = pool.generate()
            person_label = f"{person['name']}, {person['city']}, {person['state']}"

            # ---- 路径 A: 手动 ----
            if pay_url_manual:
                if "cs_live_" not in pay_url_manual:
                    fail("parse", "无效的支付链接，需包含 cs_live_")
                pay_url = pay_url_manual
                if "https://" not in pay_url:
                    pay_url = f"https://pay.openai.com/c/pay/{pay_url}"
                prog("session", "使用手动提供的支付链接")
                sess = {"url": pay_url}

            # ---- 路径 B: ChatGPT API ----
            else:
                account = parse_account(raw)
                token, user_name, user_email = extract_info(account)
                session_token = account.get("sessionToken") or account.get("session_token") or ""
                if not token:
                    fail("parse", "未识别到 accessToken")
                if curl_requests is None:
                    fail("session", "curl_cffi 未安装，请使用手动链接模式")

                preset = billing_preset(country)
                prog("session", f"调用 ChatGPT API 创建支付会话 (地区={preset['country']}, 币种={currency or preset['currency']})...")
                cache_file = WORK_DIR / "__checkout_session.json"

                if reuse and cache_file.exists():
                    sess = json.loads(cache_file.read_text())
                    pay_url = sess.get("url", "")
                    if pay_url and "cs_live_" in pay_url:
                        prog("session", "复用已缓存的会话")
                    else:
                        cache_file.unlink()
                        sess = None
                else:
                    sess = None

                if sess is None:
                    sess = _create_checkout(token, proxy, country=country,
                                            currency=currency, session_token=session_token)
                    cache_file.write_text(json.dumps(sess, indent=2))
                    prog("session", "支付会话已创建")

                pay_url = sess.get("url", "")
                if not pay_url or "cs_live_" not in pay_url:
                    fail("session", "未能获取有效支付链接")

            # ---- Browser + QR ----
            qr_bytes = _extract_qr_via_browser_sse(pay_url, person, prog, fail)
            qr_b64 = base64.b64encode(qr_bytes).decode("utf-8")
            prog("qr", f"QR 码已提取 ({len(qr_bytes)} bytes)")

            result = {
                "qr_base64": qr_b64,
                "person": person_label,
                "detail": {
                    "pay_url": pay_url,
                    "person": person,
                    "session": {k: sess.get(k) for k in ["id", "checkout_session_id", "url"] if k in sess},
                },
            }

            if sse:
                self._sse_event({"type": "done", **result})
            else:
                self._send_json(200, result)

        except Exception as exc:
            err_msg = str(exc)
            if sse:
                try:
                    self._sse_event({"type": "error", "step": "general", "msg": err_msg})
                except Exception:
                    pass
            else:
                self._send_json(500, {"error": err_msg})

    def _read_body(self) -> dict:
        length = int(self.headers.get("content-length") or "0")
        raw = self.rfile.read(length).decode("utf-8", errors="replace")
        return json.loads(raw or "{}")

    def _send_json(self, status, payload):
        self._send(status, json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def _send(self, status, content, content_type):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(content)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def log_message(self, fmt, *args):
        return


# =============================================================================
# Main
# =============================================================================

if __name__ == "__main__":
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"UPI QR Generator: http://{HOST}:{PORT}/")
    print(f"Playwright: {'OK' if HAS_PLAYWRIGHT else 'MISSING (pip install playwright && playwright install chromium)'}")
    print(f"curl_cffi:  {'OK' if curl_requests else 'MISSING (pip install curl_cffi)'}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
