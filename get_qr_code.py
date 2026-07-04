"""
ChatGPT Plus UPI 全自动支付脚本
- 虚拟人物信息池，随机填充账单
- 参考 server.py 反欺诈实现调用 ChatGPT API 创建 checkout 长链
- Playwright 浏览器自动化完成 Stripe 支付 → 提取 UPI QR 码

依赖:
    pip install requests playwright curl_cffi
    playwright install chromium

用法:
    python get_qr_code.py
"""

import argparse
import json
import base64
import uuid
import random
import time
import os
import re
import sys
import urllib.parse
from typing import Optional, Dict, Any, Tuple
from pathlib import Path

import requests

try:
    from curl_cffi import requests as curl_requests
except Exception:
    curl_requests = None

try:
    from playwright.sync_api import sync_playwright, Page, Route
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False
    Page = "Page"   # type: ignore[assignment,misc]
    Route = "Route" # type: ignore[assignment,misc]


CHECKOUT_API = "https://chatgpt.com/backend-api/payments/checkout"
AUTH_SESSION_API = "https://chatgpt.com/api/auth/session"
PLAN_TYPE_MAP = {"plus": "chatgptplusplan", "team": "chatgptteamplan", "go": "chatgptgoplan"}
PROXY_REGION_CHECK_ATTEMPTS = 2
PROXY_PROBE_ENDPOINTS = ("https://ipwho.is/", "https://ipapi.co/json/", "https://api.myip.com")

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
REGION_LOCALE = {
    "DE": ("de-DE", "de"), "ES": ("es-ES", "es"), "FR": ("fr-FR", "fr"),
    "ID": ("id-ID", "id"), "IT": ("it-IT", "it"), "JP": ("ja-JP", "ja"),
    "KR": ("ko-KR", "ko"), "BR": ("pt-BR", "pt-BR"), "CN": ("zh-CN", "zh-CN"),
    "TW": ("zh-TW", "zh-TW"), "HK": ("zh-TW", "zh-TW"),
    "US": ("en-US", "en"), "GB": ("en-GB", "en"), "NL": ("nl-NL", "nl"),
    "IN": ("en-IN", "en"), "VN": ("vi-VN", "vi"),
}

# Payment-method → required provider exit region
PROVIDER_REGION_MAP = {
    "upi": "IN", "gopay": "ID", "ideal": "NL", "paypal": "US",
    "card": "US", "hosted": "",
}

# Parallel/sequential proxy strategy matrix: (label, checkout, provider, approve)
PROXY_STRATEGIES = (
    ("US→US", "US", "US", ""),
    ("JP→US", "JP", "US", ""),
    ("JP→JP", "JP", "same", ""),
    ("US→JP", "US", "JP", ""),
    ("JP→US→JP", "JP", "US", "JP"),
)

MATRIX_STRATEGIES = tuple(
    (f"{c}->{p}->{a}", c, p, a)
    for c in ("US", "JP")
    for p in ("US", "JP")
    for a in ("US", "JP")
)


def billing_preset(country: str) -> dict:
    country = (country or "IN").upper()
    return {
        "country": country,
        "currency": COUNTRY_CURRENCY.get(country, "USD"),
        "timezone": COUNTRY_TIMEZONE.get(country, "America/New_York"),
        "locale": REGION_LOCALE.get(country, ("en-US", "en"))[0],
    }


class PersonPool:
    """虚拟印度人物信息池"""

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
        {"city": "Mumbai",       "state": "Maharashtra", "pin": "400001"},
        {"city": "Pune",         "state": "Maharashtra", "pin": "411001"},
        {"city": "Nagpur",       "state": "Maharashtra", "pin": "440001"},
        {"city": "Thane",        "state": "Maharashtra", "pin": "400601"},
        {"city": "Nashik",       "state": "Maharashtra", "pin": "422001"},
        {"city": "Delhi",        "state": "Delhi",        "pin": "110001"},
        {"city": "New Delhi",    "state": "Delhi",        "pin": "110002"},
        {"city": "Bengaluru",    "state": "Karnataka",    "pin": "560001"},
        {"city": "Mysuru",       "state": "Karnataka",    "pin": "570001"},
        {"city": "Mangalore",    "state": "Karnataka",    "pin": "575001"},
        {"city": "Hyderabad",    "state": "Telangana",    "pin": "500001"},
        {"city": "Warangal",     "state": "Telangana",    "pin": "506002"},
        {"city": "Chennai",      "state": "Tamil Nadu",   "pin": "600001"},
        {"city": "Coimbatore",   "state": "Tamil Nadu",   "pin": "641001"},
        {"city": "Madurai",      "state": "Tamil Nadu",   "pin": "625001"},
        {"city": "Kolkata",      "state": "West Bengal",  "pin": "700001"},
        {"city": "Howrah",       "state": "West Bengal",  "pin": "711101"},
        {"city": "Ahmedabad",    "state": "Gujarat",      "pin": "380001"},
        {"city": "Surat",        "state": "Gujarat",      "pin": "395001"},
        {"city": "Vadodara",     "state": "Gujarat",      "pin": "390001"},
        {"city": "Jaipur",       "state": "Rajasthan",    "pin": "302001"},
        {"city": "Jodhpur",      "state": "Rajasthan",    "pin": "342001"},
        {"city": "Udaipur",      "state": "Rajasthan",    "pin": "313001"},
        {"city": "Lucknow",      "state": "Uttar Pradesh","pin": "226001"},
        {"city": "Kanpur",       "state": "Uttar Pradesh","pin": "208001"},
        {"city": "Agra",         "state": "Uttar Pradesh","pin": "282001"},
        {"city": "Noida",        "state": "Uttar Pradesh","pin": "201301"},
        {"city": "Patna",        "state": "Bihar",        "pin": "800001"},
        {"city": "Gaya",         "state": "Bihar",        "pin": "823001"},
        {"city": "Bhopal",       "state": "Madhya Pradesh","pin": "462001"},
        {"city": "Indore",       "state": "Madhya Pradesh","pin": "452001"},
        {"city": "Gwalior",      "state": "Madhya Pradesh","pin": "474001"},
        {"city": "Chandigarh",   "state": "Chandigarh",   "pin": "160001"},
        {"city": "Bhubaneswar",  "state": "Odisha",       "pin": "751001"},
        {"city": "Guwahati",     "state": "Assam",        "pin": "781001"},
        {"city": "Kochi",        "state": "Kerala",       "pin": "682001"},
        {"city": "Thiruvananthapuram", "state": "Kerala", "pin": "695001"},
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
        base = f"{first.lower()}{last.lower()}"
        tag = self.rng.randint(100, 9999)
        domain = self.rng.choice(self.DOMAINS)
        email = f"{base}{tag}@{domain}"

        return {
            "name": name,
            "email": email,
            "country": "IN",
            "city": city["city"],
            "state": city["state"][:2].upper(),
            "postal_code": city["pin"],
            "line1": f"H.No {house}, {street}",
        }


class ChatGPTCheckout:
    """ChatGPT API checkout 长链构造 (参考 server.py)"""

    @staticmethod
    def _request_headers(token: str) -> dict:
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

    @staticmethod
    def _do_request(method, url, proxy, **kwargs):
        if curl_requests is not None:
            req_kwargs = {"impersonate": "chrome136", "timeout": 30}
            req_kwargs.update(kwargs)
            if proxy:
                req_kwargs["proxies"] = {"http": proxy, "https": proxy}
            return getattr(curl_requests, method)(url, **req_kwargs)
        else:
            req_kwargs = {"timeout": 30}
            req_kwargs.update(kwargs)
            if proxy:
                req_kwargs["proxies"] = {"http": proxy, "https": proxy}
            return getattr(requests, method)(url, **req_kwargs)

    @classmethod
    def refresh_access_token(cls, session_token: str, proxy: str = "") -> Optional[str]:
        """用 sessionToken (cookie) 刷新获取新的 accessToken。
        调用 GET /api/auth/session，返回 accessToken 或 None。"""
        if not session_token:
            return None
        try:
            resp = cls._do_request(
                "get", AUTH_SESSION_API, proxy,
                headers={
                    "Accept": "application/json",
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/136.0.0.0 Safari/537.36"
                    ),
                },
                cookies={"__Secure-next-auth.session-token": session_token},
            )
            if resp.status_code != 200:
                print(f"[!] /api/auth/session 返回 {resp.status_code}")
                return None
            data = resp.json() if callable(resp.json) else json.loads(resp.text)
            token = data.get("accessToken") or ""
            if token:
                email = data.get("user", {}).get("email", "")
                print(f"[OK] Token 刷新成功 ({email})")
            return token or None
        except Exception as exc:
            print(f"[!] Token 刷新异常: {exc}")
            return None

    @classmethod
    def create(cls, token: str, proxy: str = "", plan: str = "plus",
               billing_region: str = "IN", session_token: str = "",
               currency_override: str = "") -> dict:
        billing = billing_preset(billing_region)
        currency = (currency_override or billing["currency"]).upper()
        payload = {
            "plan_name": PLAN_TYPE_MAP.get(plan, "chatgptplusplan"),
            "billing_details": {"country": billing["country"], "currency": currency},
            "checkout_ui_mode": "hosted",
            "cancel_url": "https://chatgpt.com/#pricing",
        }

        cookies = None
        if session_token:
            cookies = {"__Secure-next-auth.session-token": session_token}

        resp = cls._do_request(
            "post", CHECKOUT_API, proxy,
            json=payload,
            headers=cls._request_headers(token),
            cookies=cookies,
        )

        if resp.status_code != 200:
            text = resp.text[:800]
            if "_cf_chl_opt" in text.lower() or "cf-chl" in text.lower():
                raise RuntimeError(
                    "被 Cloudflare 拦截。请安装 curl_cffi:\n"
                    "  pip install curl_cffi"
                )
            raise RuntimeError(f"ChatGPT API 返回 {resp.status_code}: {text}")

        try:
            data = resp.json() if callable(resp.json) else json.loads(resp.text)
        except Exception:
            data = json.loads(resp.text)
        return cls._enrich(data)

    @staticmethod
    def _enrich(data: dict) -> dict:
        session_id = data.get("checkout_session_id") or data.get("session_id") or ""
        publishable_key = data.get("publishable_key") or ""
        if session_id:
            url = f"https://pay.openai.com/c/pay/{session_id}"
            client_secret = data.get("client_secret") or ""
            if client_secret and "_secret_" in client_secret:
                hash_data = client_secret.split("_secret_", 1)[1]
                if hash_data:
                    url += f"#{hash_data}"
            data["url"] = url
        return data

    @staticmethod
    def stripe_init(session_id: str, publishable_key: str, proxy: str = "",
                    timezone: str = "Asia/Kolkata",
                    locale: str = "en-US") -> Optional[str]:
        """Step 2: POST https://api.stripe.com/v1/payment_pages/{cs_id}/init
        Returns stripe_hosted_url (the REAL working hosted checkout URL)."""
        if not session_id or not publishable_key:
            return None
        init_url = f"https://api.stripe.com/v1/payment_pages/{session_id}/init"
        form_data = {
            "key": publishable_key,
            "browser_locale": locale,
            "browser_timezone": timezone,
            "_stripe_version": "2025-06-30.basil",
        }
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": "https://js.stripe.com",
            "Referer": "https://js.stripe.com/",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/136.0.0.0 Safari/537.36"
            ),
        }
        try:
            if curl_requests is not None and proxy:
                resp = curl_requests.post(
                    init_url, data=form_data, headers=headers,
                    impersonate="chrome136",
                    proxies={"http": proxy, "https": proxy},
                    timeout=20,
                )
            elif curl_requests is not None:
                resp = curl_requests.post(
                    init_url, data=form_data, headers=headers,
                    impersonate="chrome136", timeout=20,
                )
            else:
                resp = requests.post(init_url, data=form_data, headers=headers, timeout=20)
            if resp.status_code != 200:
                print(f"[!] Stripe init 返回 {resp.status_code}: {resp.text[:200]}")
                return None
            data = resp.json() if callable(resp.json) else json.loads(resp.text)
            hosted = data.get("stripe_hosted_url") or data.get("hosted_url") or ""
            if not hosted:
                for k, v in data.items():
                    if isinstance(v, str) and ("checkout.stripe.com" in v or "pay.openai.com" in v):
                        hosted = v
                        break
            return hosted if hosted else None
        except Exception as exc:
            print(f"[!] Stripe init 异常: {exc}")
            return None

    @staticmethod
    def to_openai_pay_url(url: str) -> str:
        """Step 3: checkout.stripe.com -> pay.openai.com"""
        if url.startswith("https://checkout.stripe.com"):
            return "https://pay.openai.com" + url[len("https://checkout.stripe.com"):]
        return url


class StripeBrowserAutomator:
    """Playwright 浏览器自动化: 打开 Stripe 支付页 → 选择 UPI → 填账单 → 确认 → 提取 QR"""

    def __init__(self, headless: bool = True, timeout: float = 60):
        if not HAS_PLAYWRIGHT:
            raise ImportError("需要安装 playwright: pip install playwright && playwright install chromium")
        self.headless = headless
        self.timeout = timeout * 1000

    def run(self, pay_url: str, person: dict) -> Tuple[Optional[bytes], dict]:
        qr_bytes = None
        captured = {}

        with sync_playwright() as p:
            launch_kwargs = {
                "headless": self.headless,
                "args": ["--disable-blink-features=AutomationControlled"],
            }
            chrome_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
            import os as _os
            if _os.path.exists(chrome_path):
                launch_kwargs["executable_path"] = chrome_path
            try:
                browser = p.chromium.launch(**launch_kwargs)
            except Exception:
                browser = p.chromium.launch(
                    headless=self.headless,
                    args=["--disable-blink-features=AutomationControlled"],
                )
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/136.0.0.0 Safari/537.36"
                ),
                locale="en-IN",
            )
            page = context.new_page()

            self._setup_network_intercept(page, captured)

            page.goto(pay_url, wait_until="domcontentloaded", timeout=self.timeout)

            self._fill_email(page, person["email"])
            self._dismiss_apple_pay(page)
            self._select_upi(page)

            self._fill_name(page, person["name"])
            page.wait_for_timeout(800)

            self._fill_address(page, person)
            page.wait_for_timeout(500)

            self._click_confirm(page)

            self._wait_for_qr_or_timeout(page)

            qr_intercepted = captured.get("qr_code")
            if qr_intercepted:
                qr_bytes = qr_intercepted

            if qr_bytes is None:
                qr_bytes = self._extract_qr_from_dom(page)

            browser.close()

        return qr_bytes, captured

    def _setup_network_intercept(self, page: Page, captured: dict):
        def handle_route(route: Route):
            url = route.request.url
            if "api.stripe.com/v1/payment_pages" in url and "/confirm" in url:
                response = route.fetch()
                try:
                    body = response.json()
                    pi = body.get("payment_intent", {})
                    na = pi.get("next_action", {})
                    upi = na.get("upi", {})
                    qr_data_url = upi.get("qr_code", "")
                    if qr_data_url:
                        captured["qr_code"] = StripeBrowserAutomator._dec(qr_data_url)
                    captured["confirm_response"] = body
                    captured["pi_id"] = pi.get("id")
                    captured["pi_status"] = pi.get("status")
                except Exception:
                    pass
                route.fulfill(response=response)
            else:
                route.continue_()

        page.route("**/*", handle_route)

    def _fill_email(self, page: Page, email: str):
        try:
            sel = 'input[autocomplete="email"], input[name="email"], input[type="email"]'
            el = page.wait_for_selector(sel, timeout=15000)
            if el:
                el.click()
                el.fill("")
                el.type(email, delay=50)
        except Exception:
            pass

    def _dismiss_apple_pay(self, page: Page):
        try:
            buttons = page.query_selector_all("button, [role=button]")
            for btn in buttons:
                text = (btn.inner_text() or "").lower()
                if "not now" in text or "skip" in text:
                    btn.click()
                    page.wait_for_timeout(500)
                    break
        except Exception:
            pass

    def _select_upi(self, page: Page):
        page.wait_for_timeout(2000)

        selectors = [
            'button[aria-label*="UPI"]',
            'button[aria-label*="upi"]',
            'div[data-testid*="upi"]',
            'input[value="upi"]',
            'label:has-text("UPI")',
            'button:has-text("UPI")',
            'div[data-payment-method="upi"]',
            'img[alt*="UPI"]',
        ]
        for sel in selectors:
            try:
                el = page.query_selector(sel)
                if el and el.is_visible():
                    el.click()
                    page.wait_for_timeout(1500)
                    return
            except Exception:
                continue

        try:
            elements = page.query_selector_all(
                '[data-testid*="payment"], [class*="Payment"], [class*="payment"]'
            )
            for el in elements:
                try:
                    text = (el.inner_text() or "").lower()
                    if "upi" in text:
                        el.click()
                        page.wait_for_timeout(1500)
                        return
                except Exception:
                    continue
        except Exception:
            pass

        try:
            page.keyboard.press("Tab")
            page.wait_for_timeout(300)
            page.keyboard.press("Tab")
            page.wait_for_timeout(300)
            page.keyboard.press("ArrowDown")
            page.wait_for_timeout(300)
            for _ in range(10):
                active = page.evaluate("() => document.activeElement?.textContent?.toLowerCase() || ''")
                if "upi" in active:
                    page.keyboard.press("Enter")
                    page.wait_for_timeout(1500)
                    return
                page.keyboard.press("ArrowDown")
                page.wait_for_timeout(200)
        except Exception:
            pass

    def _fill_name(self, page: Page, name: str):
        try:
            sel = 'input[autocomplete="name"], input[name="name"], input[placeholder*="Name"], input[placeholder*="name"]'
            el = page.query_selector(sel)
            if el and el.is_visible():
                el.click()
                el.fill("")
                el.type(name, delay=40)
        except Exception:
            pass

    def _fill_address(self, page: Page, person: dict):
        field_map = {
            "line1":       'input[autocomplete="address-line1"], input[name="address-line1"], input[placeholder*="Address"]',
            "city":        'input[autocomplete="address-level2"], input[name="city"], input[placeholder*="City"]',
            "state":       'input[autocomplete="address-level1"], input[name="state"], input[placeholder*="State"]',
            "postal_code": 'input[autocomplete="postal-code"], input[name="postal-code"], input[placeholder*="ZIP"], input[placeholder*="Postal"]',
        }

        # Try country first
        try:
            country_sel = 'select[autocomplete="country"], select[name="country"]'
            el = page.query_selector(country_sel)
            if el:
                el.select_option("IN")
                page.wait_for_timeout(500)
        except Exception:
            pass

        for field, selector in field_map.items():
            if field not in person:
                continue
            try:
                el = page.query_selector(selector)
                if el and el.is_visible():
                    el.click()
                    el.fill("")
                    el.type(str(person[field]), delay=30)
            except Exception:
                pass

    def _click_confirm(self, page: Page):
        page.wait_for_timeout(1000)
        confirm_selectors = [
            'button[type="submit"]',
            'button:has-text("Pay")',
            'button:has-text("Subscribe")',
            'button:has-text("Confirm")',
            'button:has-text("pay")',
            'button:has-text("continue")',
            'button[data-testid*="confirm"]',
            'div[role="button"]:has-text("Pay")',
        ]
        for sel in confirm_selectors:
            try:
                el = page.query_selector(sel)
                if el and el.is_visible() and el.is_enabled():
                    el.click()
                    return
            except Exception:
                continue
        try:
            page.evaluate("""() => {
                const btns = document.querySelectorAll('button');
                for (const b of btns) {
                    const t = b.textContent.toLowerCase();
                    if ((t.includes('pay') || t.includes('confirm') || t.includes('subscribe')) && b.offsetParent) {
                        b.click();
                        return;
                    }
                }
            }""")
        except Exception:
            pass

    def _wait_for_qr_or_timeout(self, page: Page, timeout: float = 40):
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                has_qr = page.evaluate("""() => {
                    const imgs = document.querySelectorAll('img[src^="data:image/png;base64,"]');
                    for (const img of imgs) if (img.src.length > 200) return true;
                    return false;
                }""")
                if has_qr:
                    return
            except Exception:
                pass
            time.sleep(0.8)

    def _extract_qr_from_dom(self, page: Page) -> Optional[bytes]:
        try:
            b64 = page.evaluate("""() => {
                const imgs = document.querySelectorAll('img[src^="data:image/png;base64,"]');
                for (const img of imgs) if (img.src.length > 200) return img.src;
                return null;
            }""")
            if b64:
                return self._dec(b64)
        except Exception:
            pass
        return None

    @staticmethod
    def _dec(data_url: str) -> bytes:
        b64 = data_url.split(",", 1)[1]
        return base64.b64decode(b64)


def parse_account_json(raw: str) -> dict:
    raw = raw.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    m = re.search(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", raw)
    if m:
        return {"accessToken": m.group(0)}
    raise ValueError("无法解析账户 JSON 或 JWT token")


def _load_token_file(path: str) -> str:
    """从 session JSON 文件中提取 accessToken"""
    with open(path, "r", encoding="utf-8-sig") as f:
        raw = f.read()
    account = parse_account_json(raw)
    token = account.get("accessToken") or account.get("access_token") or ""
    if not token:
        raise ValueError(f"文件 {path} 中未找到 accessToken")
    return token, account


def _build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="ChatGPT Plus UPI 全自动支付脚本",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  python get_qr_code.py --token-from-file session.json\n"
            "  python get_qr_code.py --token eyJhbGciOi...\n"
            "  python get_qr_code.py --token-from-file session.json --plan team\n"
            '  $env:ACCOUNT_JSON="session.json"; python get_qr_code.py\n'
        ),
    )
    g = p.add_mutually_exclusive_group()
    g.add_argument("--token-from-file", "-f", metavar="PATH",
                   help="从 session JSON 文件读取 accessToken 和 sessionToken")
    g.add_argument("--token", "-t", metavar="JWT",
                   help="直接传入 accessToken 字符串")
    p.add_argument("--plan", choices=["plus", "team", "go"], default="plus",
                   help="订阅计划 (默认: plus)")
    p.add_argument("--billing", default="IN",
                   help="账单地区国家代码 (如 IN/US/JP/NL/DE/GB/ID 等, 默认: IN)")
    p.add_argument("--currency", default="",
                   help="覆盖币种 (如 USD/INR/EUR/JPY, 默认按地区自动选择)")
    p.add_argument("--proxy", default="",
                   help="HTTP(S) 代理地址，如 http://127.0.0.1:7890")
    p.add_argument("--no-refresh", action="store_true",
                   help="跳过 sessionToken 刷新，直接用 accessToken")
    p.add_argument("--headless", action="store_true", default=False,
                   help="无头模式运行浏览器 (默认: 有头，可观察)")
    p.add_argument("--no-browser", action="store_true",
                   help="仅创建 checkout session，不启动浏览器 (只输出支付链接)")
    p.add_argument("--out", default="upi_qr.png",
                   help="QR 码图片输出路径 (默认: upi_qr.png)")
    p.add_argument("--reuse", action="store_true", default=True,
                   help="复用已缓存的 checkout session (默认开启)")
    p.add_argument("--no-reuse", dest="reuse", action="store_false",
                   help="不使用缓存，强制重新创建 checkout session")
    return p


def main():
    parser = _build_argparser()
    args = parser.parse_args()

    # ================================================
    # 1. 获取 token (优先级: CLI > 环境变量 > 自动检测)
    # ================================================
    token = ""
    account: dict = {}

    if args.token:
        token = args.token
        print("[*] 使用命令行传入的 token")
    elif args.token_from_file:
        token, account = _load_token_file(args.token_from_file)
        print(f"[*] 从文件加载 token: {args.token_from_file}")
    else:
        account_path = os.environ.get("ACCOUNT_JSON", "")
        if not account_path:
            candidates = [
                f for f in Path(".").iterdir()
                if f.suffix == ".json"
                and f.stem != "__checkout_session"
                and not f.name.startswith(".")
            ]
            if candidates:
                account_path = str(candidates[0])
                print(f"[*] 自动检测到账户文件: {account_path}")
            else:
                parser.print_help()
                print("\n[!] 未提供 token。请使用 --token-from-file 或 --token，"
                      "或设置 ACCOUNT_JSON 环境变量，或将 session JSON 放到当前目录。")
                sys.exit(1)
        token, account = _load_token_file(account_path)

    if not token:
        print("[!] 未找到 accessToken")
        sys.exit(1)

    user_name = account.get("user", {}).get("name", "")
    user_email = account.get("user", {}).get("email", "")
    plan_type = account.get("account", {}).get("planType", "")
    session_token = account.get("sessionToken") or account.get("session_token") or ""
    if user_name or user_email:
        print(f"[*] 账户: {user_name or '(unknown)'} <{user_email or '(no email)'}>  当前计划: {plan_type or '?'}")

    proxy = args.proxy or os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY") or ""

    # ================================================
    # 1b. 用 sessionToken 刷新获取新的 accessToken (避免 401)
    # ================================================
    if session_token and not args.no_refresh:
        print("[*] 用 sessionToken 刷新 accessToken...")
        new_token = ChatGPTCheckout.refresh_access_token(session_token, proxy)
        if new_token:
            token = new_token
        else:
            print("[!] 刷新失败，使用原始 accessToken 继续...")
    elif not session_token:
        print("[*] 无 sessionToken，直接使用 accessToken (可能遇到 401)")

    # ================================================
    # 2. 生成虚拟人物 + 创建 checkout session
    # ================================================
    pool = PersonPool()
    person = pool.generate()
    print(f"[*] 虚拟身份: {person['name']}, {person['city']}, {person['state']}")

    saved_session = Path("__checkout_session.json")

    sess = None
    if args.reuse and saved_session.exists():
        print("[*] 复用已缓存的 checkout session...")
        try:
            sess = json.loads(saved_session.read_text(encoding="utf-8"))
        except Exception:
            sess = None

    if sess:
        hosted_url = sess.get("hosted_long_url", "")
        if not hosted_url or "cs_live_" not in hosted_url:
            print("[!] 缓存的 session 无效，重新创建...")
            sess = None

    if sess is None:
        print(f"[*] 调用 ChatGPT API 创建 checkout session (plan={args.plan}, billing={args.billing}, currency={args.currency or 'auto'})...")
        try:
            sess = ChatGPTCheckout.create(
                token, proxy, plan=args.plan,
                billing_region=args.billing,
                currency_override=args.currency,
                session_token=session_token,
            )
        except Exception as exc:
            print(f"[!] 创建 checkout session 失败: {exc}")
            sys.exit(1)
        saved_session.write_text(json.dumps(sess, indent=2), encoding="utf-8")

    session_id = sess.get("checkout_session_id") or sess.get("session_id") or ""
    publishable_key = sess.get("publishable_key") or ""
    short_url = sess.get("url", "")
    print(f"[*] Session ID: {session_id}")
    if short_url:
        print(f"[*] 短链 (fallback): {short_url}")

    # Step 2: Stripe init → 拿真正的 hosted_url (长链, 400字符 hash)
    pay_url = short_url
    if session_id and publishable_key:
        billing = billing_preset(args.billing)
        print("[*] 调用 Stripe init 获取 hosted checkout URL...")
        hosted = ChatGPTCheckout.stripe_init(
            session_id, publishable_key, proxy,
            timezone=billing["timezone"],
            locale=billing["locale"],
        )
        if hosted:
            long_url = ChatGPTCheckout.to_openai_pay_url(hosted)
            hash_len = len(hosted.split("#", 1)[1]) if "#" in hosted else 0
            print(f"[OK] hosted 长链 (hash={hash_len}字符): {long_url}")
            pay_url = long_url
            sess["hosted_long_url"] = long_url
            saved_session.write_text(json.dumps(sess, indent=2), encoding="utf-8")
        else:
            print("[!] Stripe init 失败，使用短链 fallback")
    else:
        print("[!] 缺少 session_id 或 publishable_key，使用短链 fallback")

    # --no-browser: 只输出链接，不启动浏览器
    if args.no_browser:
        print("\n[✓] 仅输出模式，不启动浏览器。")
        print(f"    支付链接: {pay_url}")
        result = {
            "url": pay_url,
            "session_id": session_id,
            "session": sess,
        }
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return

    # ================================================
    # 3. Playwright 浏览器自动化 → 获取 QR
    # ================================================
    if not pay_url or "cs_live_" not in pay_url:
        print("[!] 未能获取到有效的支付链接")
        sys.exit(1)

    if not HAS_PLAYWRIGHT:
        print("[!] 未安装 playwright，无法自动提取 QR 码。")
        print("    请手动打开支付链接完成支付:")
        print(f"    {pay_url}")
        print("    安装: pip install playwright && playwright install chromium")
        sys.exit(0)

    print(f"[*] 启动浏览器 (headless={args.headless})，打开支付页面...")
    automator = StripeBrowserAutomator(headless=args.headless, timeout=90)

    qr_bytes, captured = automator.run(pay_url, person)

    if qr_bytes:
        with open(args.out, "wb") as f:
            f.write(qr_bytes)
        print(f"\n[OK] QR 码已保存: {args.out} ({len(qr_bytes)} bytes)")
        print("[OK] 请用 UPI 应用扫描完成支付。")
    else:
        print("\n[!] 未能提取到 QR 码")
        if captured:
            print(f"    payment_intent.status: {captured.get('pi_status', '?')}")
            print(f"    payment_intent.id:     {captured.get('pi_id', '?')}")
        print("[!] 请检查浏览器窗口，手动完成支付流程。")
        print(f"    支付链接: {pay_url}")


if __name__ == "__main__":
    main()
