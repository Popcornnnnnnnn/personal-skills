---
name: agent-auth
description: "Guarded authentication CLI for SMS OTP, Apple Mail OTP/magic links, desktop-to-iPhone QR login, desktop WeChat quick-login, Keychain TOTP, and SSO push screen checks under 3-tier safety guardrails. Use when automating everyday login challenges or running Incognito auth evaluations without bypassing security boundaries."
---

# Agent Auth

Use `~/.local/bin/agent-auth` together with `~/.local/bin/iphone-wireless` and `wdio-mcp` / `peekaboo` when an interactive login flow asks for an OTP, magic link, QR code, TOTP code, or push/quick-login confirmation.

## Safety Tiers & Guardrails (Mandatory)

- **Tier 1 (Everyday allowlist):** Auto-allowed (`exit 0`) in both `--mode check` and `--mode nocheck` (`bilibili.com`, `xiaohongshu.com`, `notion`, `linear`, `claude`, `cursor`, `openai`, `reddit`, `bigmodel` / `deepseek` SMS, etc.).
- **Tier 2 (Confirm / Unlisted):** Pauses (`exit 2`, `NEEDS_APPROVAL`, raw code/QR payload redacted) in default `--mode check` and issues a single-use 5-minute `--approve <token>`. Auto-allowed only when explicitly authorized with `--mode nocheck`.
- **Tier 3 (Hard block — ALWAYS `exit 3` in both `check` and `nocheck`):** Banks, financial/payment apps or QR prefixes (`wxp://`, `qr.alipay.com`), password resets, phone rebinding, account deletion, and Apple ID / `idmsa.apple.com`. **Stop immediately and hand off to the user.**
- **CAPTCHAs, screen lock & system alerts:** Never bypass CAPTCHAs, Turnstile, biometrics, or iOS passcodes (`autoAcceptAlerts: false`). Tap `Don't Allow Paste` (never `Allow Paste`) only if an app raises a benign clipboard-read prompt on launch.

## Fast Channel Recipes

### 1. SMS & Email OTP / Magic Links
Capture `AFTER=$(date +%s)` **before** clicking `Send Code`:
- **SMS (`chat.db`):** `~/.local/bin/agent-auth sms --service <site> --after "$AFTER" --wait 45`
- **Email (`Apple Mail`):** `~/.local/bin/agent-auth email --service <site> --after "$AFTER" --wait 60 --sync`

### 2. QR Strategy A (App Deep-Link / Universal Link — `bilibili.com`, `xiaohongshu.com`)
1. Inspect directly from the clean Chrome window using `--window-owner Chrome` (prefer `--window-owner Chrome --window-title "<tab title>"` instead of hardcoding Chrome-for-Testing vs Chrome):
   `~/.local/bin/agent-auth qr-inspect --window-owner Chrome --window-title "<tab title>" --service <domain> --mode check`
2. Open the allowed URL on iPhone cleanly via `~/.local/bin/iphone-wireless open-url --url "<payload>" --bundle-id com.apple.mobilesafari` (skipping intermediate browser pickers).
3. Before tapping Confirm on the phone, capture screen text and verify:
   `~/.local/bin/agent-auth qr-check-screen --service <domain> --mode check --text "<visible text>"` (`exit 0` required). If Bilibili's mobile WebView returns empty `<group>` accessibility nodes in `snapshot()`, fall back to `~/.local/bin/iphone-wireless screenshot --out /tmp/qr-confirm.png` + `qr-check-screen` + `~/.local/bin/iphone-wireless tap`.

### 3. QR Strategy B (JSON QR Payloads or Non-Deep-Link Apps — e.g. `feishu.cn`)
Use one-shot LAN transfer + fingerprint-matched album tap to beat short QR TTLs (`~65s` on Feishu):
1. Check gate first in `--mode check`:
   `~/.local/bin/agent-auth qr-inspect --window-owner Chrome --window-title "<tab title>" --service <domain> --mode check`
2. When authorized (`--mode nocheck` or `--approve <token>`), inspect & push straight to iPhone Photos:
   `~/.local/bin/agent-auth qr-serve --window-owner Chrome --window-title "<tab title>" --service <domain> --mode nocheck --push-to-photos --timeout 60`
   Record `raw_fingerprint` from the ready JSON.
3. Foreground the target app (`~/.local/bin/iphone-wireless activate --bundle-id <bundle>`) -> open Scan -> Album. **On Feishu, avoid `snapshot(full: true)` on the Messenger chat list (~15s cost against the ~65s TTL)**—go straight through `+` -> `Scan QR Code` -> `Album`.
4. When the album grid lacks accessibility nodes or stalls WDA:
   - `~/.local/bin/iphone-wireless screenshot --out /tmp/qr-album.png`
   - `~/.local/bin/agent-auth qr-inspect /tmp/qr-album.png --mode nocheck --match-fingerprint <raw_fp>` (or `--pick bottom` if exact payload differs) -> read `selected_center` (`x, y`) and `image_size_str`.
   - `~/.local/bin/iphone-wireless tap --x <x> --y <y> --from-image-size <WxH> --app com.apple.springboard`
5. Always validate the resulting mobile confirmation screen with `agent-auth qr-check-screen` (`exit 0`) before tapping Confirm.

### 4. Desktop WeChat Quick-Login (`wechat_desktop_quick`) vs Camera-Only OAuth QRs
- Prefer desktop WeChat quick-login (`微信快捷登录` inside `open.weixin.qq.com`) when available and `WeChat` is signed in on macOS. Always target desktop WeChat by bundle ID `com.tencent.xinWeChat` rather than app name `"WeChat"` so Peekaboo does not collide with `WeChatAppEx`.
- If macOS WeChat opens an `"<Site> requests access"` popup with `0` actionable AX elements (or on a secondary display), inspect text with `see(ocr: true)` + `agent-auth qr-check-screen`, then `window(action: "focus")` + `click(..., foreground: true)` on `Allow` (background clicks fail on non-AX pixel popups).
- Check DOM visibility (`offsetParent` / bounding rect) before stopping for slider/puzzle CAPTCHA text so hidden off-screen fallback markup does not cause false-positive `handoff_human` exits.
- Third-party `open.weixin.qq.com` QR codes reject mobile deep links, album scans, and long-press QR extraction on iOS (`camera-only` -> `handoff_human`).

### 5. Keychain TOTP & SSO Push
- `~/.local/bin/agent-auth totp --service <site> [--mode check|nocheck]`
- `~/.local/bin/agent-auth push-check-screen --service <site> --expected-number <N> --text "<screen text>"`
