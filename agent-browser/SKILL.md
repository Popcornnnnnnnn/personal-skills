---
disable-model-invocation: true
name: agent-browser
description: "Choose direct reading or BrowserOS neo for authorized web tasks, preserving login, focus and task-tab boundaries. Neo is the author's browser preference; an explicit user choice takes priority."
---

# Agent Browser

This skill owns browser selection, login handling, focus, and fallback. Research and UI skills should refer here instead of maintaining competing rules.

## Routing

1. Prefer task-appropriate connectors, APIs, direct search, HTTP or CLI reading when they can complete the authorized task. Use a browser when page interaction, authenticated rendered content or visual verification is necessary.
2. An explicit user browser choice wins for browser work. Otherwise use BrowserOS neo. A CLI or extension that drives browser pages is a browser operation. This does not change the system's default browser.
3. For Neo, read and follow the separately installed `browseros-neo` skill for its MCP interface and session handling. This skill owns selection, login boundaries, focus, and fallback; `browseros-neo` owns the concrete Neo workflow. For an explicitly chosen alternative, use its documented control interface and preserve its existing profile.
4. Public-fetch failure does not prove an authenticated page is inaccessible. Check Neo's available connection and the required site's access before asking for manually supplied content. Do not assume Neo shares the daily browser's login state or copy cookies, credentials, or profile data into it.
5. Report Neo connection or access failures precisely; do not silently switch to the daily browser, an in-app browser, an isolated browser, or a fresh profile. Continue independent direct-reading work where useful.

## Focus and tabs

- Prefer Neo's browser tools without activating windows or switching foreground tabs when equally effective. A requested browser or desktop task permits necessary page operations, window changes, and focus; do not claim that every Neo action is guaranteed to avoid focus changes.
- Treat background/no-focus operation as a hard constraint only when requested for the current task. If the required step cannot satisfy it, report that step as blocked and continue independent work.
- Preserve existing tabs and unrelated user work. Record the tabs and group created for this task. After saving needed results, close task-created tabs by default when the task ends; a source link alone is sufficient for later reference and does not require leaving a page open.
- Keep a task-created tab only for a concrete remaining need: an explicitly requested preview or retention, a pending human handoff, ongoing work, or unsaved input that would be lost. State the reason when keeping one. Possible future usefulness alone is not a reason to retain it.
- At completion, list tabs again, match the recorded task pages or group, close the eligible pages through the documented browser tools, and verify they are gone. After reconnecting, recover the task group by its recorded id and task name rather than trusting stale page ids or current ownership labels. Close a whole group only after checking every page belongs to this task and none requires retention. Do not sweep unrelated groups, other agents' work, or pre-existing user tabs.

## Login and autofill

- Reuse an existing authenticated session first. For a user-authorized destination, try the browser's normal login flow and existing password-manager autofill before requesting user intervention.
- Autofill means using the browser or password manager's normal controls to supply an existing credential to its intended site. Do not reveal, copy, export, or log passwords; do not read filled password values, cookies, local storage, profile databases, or session databases.
- Confirm the destination is the intended site before login. If the destination or account is not authorized or is ambiguous, resolve that first; do not choose an unrelated account or website merely to test autofill.
- If Touch ID, a device passcode, an unavailable credential, human verification, a tool-policy restriction, or a new permission blocks login, state the exact requirement and request the minimum intervention. In Neo, follow its documented `request_human_help` / `await_human_help` handoff and waiting rules. Do not bypass authentication or expand access. Stop the blocked step and continue independent work when the tool's handoff rules permit; resume when completion is verified.
- Verify successful login through the resulting site state. Already being signed in proves session reuse, not password autofill. A filled form alone does not prove successful login.
- Login does not authorize posting, purchasing, messaging, account changes, or other external writes. Follow the user's action scope and the tool's confirmation rules.

## Shopping searches

Use the separately configured `shop-search` workflow for JD and Taobao/Tmall queries. Browser operations retain the routing and credential boundaries above. Do not revive old browser bridges or install a backend to hide an unavailable route.

## Local owner context

If `~/.config/personal-skills/profiles/agent-browser/SKILL.md` exists, read it once for this task's private destinations, environment and established constraints. Keep that profile local. Verify changing facts live; a saved profile does not grant new access or authorize an unrelated action. Without a configured profile, resolve the required inputs from the current request and authorized tools; never invent the author's account or destination.
