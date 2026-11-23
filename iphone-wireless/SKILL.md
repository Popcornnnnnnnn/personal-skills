---
name: iphone-wireless
description: "Default workflow for wireless real-iPhone automation using WebDriverAgent over Wi-Fi, local Appium, and wdio-mcp. Use for physical iPhone tasks unless the user explicitly asks for USB iphone_use or its live sidebar preview."
---

# iPhone Wireless

Operate a physical iPhone over Wi-Fi using Appium + `wdio-mcp` backed by an on-demand WebDriverAgent (`xcodebuild test-without-building`) runner managed by `~/.local/bin/iphone-wireless`.

## Default routing

- Use this wireless `wdio-mcp` workflow by default for physical iPhone tasks.
- Switch to USB-only `iphone_use` only when the user explicitly requests `iphone_use`, a wired USB workflow, or the `iphone_use` live sidebar preview.

## Preflight

1. Read `~/.config/personal-skills/profiles/iphone-wireless/SKILL.md` once at the start of the task if it exists for this Mac's device settings and local preferences.
2. Run `~/.local/bin/iphone-wireless start` (or `~/.local/bin/iphone-wireless status` for a read-only check):
   - Reuses a healthy Wi-Fi WDA + Appium pair immediately when already running.
   - Otherwise cold-starts WDA over Wi-Fi, detects the current LAN WDA URL dynamically, and starts Appium (`127.0.0.1:4723`) with `--default-capabilities` preconfigured (`appium:webDriverAgentUrl`, `appium:skipLogCapture: true`, zero idle/animation wait).
3. Copy the returned `session_args` object directly for `start_session`.

## `wdio-mcp` workflow

1. **Start session (flat args only):**
   Call `wdio-mcp` tool `start_session` with ONLY the flat primitive fields from `session_args`:
   - `platform`: `"ios"`
   - `deviceName`: from `session_args`
   - `platformVersion`: from `session_args`
   - `udid`: from `session_args`
   - `noReset`: `true`
   - `autoAcceptAlerts`: `false`
   - **Do NOT pass nested `capabilities` or `appiumConfig` objects** when invoking `wdio-mcp` through lazy MCP wrappers that stringify nested records (Appium `--default-capabilities` already supplies them).
   - **Never pass `"appium:usePreinstalledWDA": true` together with `"appium:webDriverAgentUrl"`** without a matching `updatedWDABundleId` — `appium-xcuitest-driver` runs `cleanupApps` first and will uninstall a custom-bundle WDA runner from the iPhone.
2. **Observe and act:**
   - Call `snapshot` to read the accessibility tree and element refs (`[ref=eN]`).
   - Act using refs (`click_element`, `set_value`, `perform_actions`, `scroll`, or `enable_tools` for mobile-specific tools like `tap_element`, `swipe`, `list_apps`, `get_app_state`, `hide_keyboard`).
   - Call `get_screenshot` whenever visual verification is needed or the accessibility tree is missing/ambiguous.
3. **Close cleanly:**
   - Call `close_session` with `{"detach": false}` when finished so the Appium session ends cleanly while WDA stays ready for the next task.

## Security and human boundaries

- Always keep `autoAcceptAlerts: false` so system or app permission prompts on a daily phone are never accepted automatically.
- Hand off to the user whenever device unlock, passcode, Face ID / Touch ID, passwords, or payment confirmation is required.
- WDA listens on the local Wi-Fi network without built-in authentication. Only run `iphone-wireless start` on trusted private networks, and run `~/.local/bin/iphone-wireless stop` when finished on shared networks or when requested.
