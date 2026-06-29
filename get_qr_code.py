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


CHECKOUT_API = "https://chatgpt.com/backend-api/payments/checkout"
PLAN_TYPE_MAP = {"plus": "chatgptplusplan", "team": "chatgptteamplan"}


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

    @classmethod
    def create(cls, token: str, proxy: str = "", plan: str = "plus") -> dict:
        payload = {
            "plan_name": PLAN_TYPE_MAP.get(plan, "chatgptplusplan"),
            "billing_details": {"country": "IN", "currency": "INR"},
            "checkout_ui_mode": "hosted",
            "cancel_url": "https://chatgpt.com/#pricing",
        }

        if curl_requests is not None and proxy:
            proxies = {"http": proxy, "https": proxy}
            resp = curl_requests.post(
                CHECKOUT_API, json=payload,
                headers=cls._request_headers(token),
                impersonate="chrome136",
                proxies=proxies,
                timeout=30,
            )
        elif curl_requests is not None:
            resp = curl_requests.post(
                CHECKOUT_API, json=payload,
                headers=cls._request_headers(token),
                impersonate="chrome136",
                timeout=30,
            )
        else:
            resp = requests.post(
                CHECKOUT_API, json=payload,
                headers=cls._request_headers(token),
                timeout=30,
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
        if session_id and not data.get("url"):
            data["url"] = f"https://pay.openai.com/c/pay/{session_id}"
        return data


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


def main():
    saved_session = Path("__checkout_session.json")

    # ================================================
    # 1. 加载账户 JSON
    # ================================================
    account_path = os.environ.get("ACCOUNT_JSON", "")
    if not account_path:
        candidates = [f for f in Path(".").iterdir() if f.suffix == ".json" and f.stem != "__checkout_session"]
        if candidates:
            account_path = str(candidates[0])
            print(f"[*] 自动检测到账户文件: {account_path}")
        else:
            print("用法之一: set ACCOUNT_JSON=account.json && python get_qr_code.py")
            print("或直接将 JSON 文件放到当前目录。")
            sys.exit(1)

    with open(account_path, "r", encoding="utf-8") as f:
        account = parse_account_json(f.read())

    token = account.get("accessToken") or account.get("access_token") or ""
    if not token:
        print("[!] 未找到 accessToken")
        sys.exit(1)

    user_name = account.get("user", {}).get("name", "")
    user_email = account.get("user", {}).get("email", "")
    print(f"[*] 账户: {user_name or '(unknown)'} <{user_email or '(no email)'}>")

    # ================================================
    # 2. 生成虚拟人物 + 创建 checkout session
    # ================================================
    pool = PersonPool()
    person = pool.generate()
    print(f"[*] 虚拟身份: {person['name']}, {person['city']}, {person['state']}")

    proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY") or ""

    if saved_session.exists():
        print("[*] 复用已缓存的 checkout session...")
        sess = json.loads(saved_session.read_text())
        pay_url = sess.get("url", "")
        if pay_url and "cs_live_" in pay_url:
            print(f"[*] 支付链接: {pay_url}")
        else:
            saved_session.unlink()
            sess = None
    else:
        sess = None

    if not sess:
        print("[*] 调用 ChatGPT API 创建 checkout session...")
        sess = ChatGPTCheckout.create(token, proxy)
        saved_session.write_text(json.dumps(sess, indent=2))
        pay_url = sess.get("url", "")
        print(f"[*] 支付链接: {pay_url}")

    # ================================================
    # 3. Playwright 浏览器自动化 → 获取 QR
    # ================================================
    if not pay_url or "cs_live_" not in pay_url:
        print("[!] 未能获取到有效的支付链接")
        sys.exit(1)

    print(f"[*] 启动浏览器，打开支付页面...")
    automator = StripeBrowserAutomator(headless=False, timeout=90)

    qr_bytes, captured = automator.run(pay_url, person)

    if qr_bytes:
        out = "upi_qr.png"
        with open(out, "wb") as f:
            f.write(qr_bytes)
        print(f"\n[✓] QR 码已保存: {out} ({len(qr_bytes)} bytes)")
        print("[✓] 请用 UPI 应用扫描完成支付。")
    else:
        print("\n[!] 未能提取到 QR 码")
        if captured:
            print(f"    payment_intent.status: {captured.get('pi_status', '?')}")
            print(f"    payment_intent.id:     {captured.get('pi_id', '?')}")
        print("[!] 请检查浏览器窗口，手动完成支付流程。")


if __name__ == "__main__":
    main()
