# Rusprofile Authenticated Session Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement the plan task-by-task.

**Goal:** Let the Rusprofile parser reuse a manually authenticated Playwright session for search and `/id/{id}` profile retrieval without putting credentials or cookies in source.

**Architecture:** A small visible-browser helper opens Rusprofile, waits for the user to finish login, and writes Playwright storage state under `Auto_audit/.local/`. The parser loads that state into one browser context, uses it to search and open the chosen profile page, then transfers the context cookies to its existing `requests.Session` for profile subrequests.

**Tech Stack:** Python, Playwright, BeautifulSoup, requests.

**Spec:** `company_news_pipeline/docs/superpowers/specs/2026-10-25-rusprofile-auth-session-design.md`

## Global Constraints

- Never embed, print, or commit the supplied password or session-cookie values.
- Save state at `Auto_audit/.local/rusprofile_storage_state.json` and exclude it from Git.
- Keep the existing `parse_rusprofile(query)` interface and profile JSON shape.
- Use the same authenticated browser context for search and the `/id/{id}` page.
- Do not automate password entry or CAPTCHA/MFA.

## Review Focus

- Missing storage state: return a clear instruction to run the login helper.
- Expired or rejected state: report the site's rejection and direct the user to refresh the saved session.
- Search returns no profile ID: return a clear no-results error without requesting `/id/None`.
- Browser launch or navigation failure: close the browser and return a useful error.
- Session data: ensure the state file is ignored and no cookie values are logged or returned.

---

### Task 1: Add interactive session saver

**Files:**
- Create: `Auto_audit/save_rusprofile_session.py`
- Create: `Auto_audit/.gitignore`
- Modify: `Auto_audit/README.md`

**Interface:** Running `python Auto_audit/save_rusprofile_session.py` opens a visible Chromium window at Rusprofile. The user completes login manually and presses Enter in the terminal; the helper writes storage state to `Auto_audit/.local/rusprofile_storage_state.json` and reports only the path and completion status.

- [ ] Add the helper using Playwright's `browser.new_context()` and `context.storage_state(path=...)`; do not request or read the password in Python.
- [ ] Create the local state directory and ignore only the generated storage-state path.
- [ ] Document the command and the manual login/confirmation flow in the README.
- [ ] Verify the helper and touched Python files compile with `python -m py_compile`.

### Task 2: Reuse saved session in the parser

**Files:**
- Modify: `Auto_audit/PARSING/rusprofile.py`

**Interface:** `parse_rusprofile(query: str) -> Dict[str, Any]` continues returning its existing JSON-serializable result, with `id` and `profile_page` populated from the profile at `https://www.rusprofile.ru/id/{id}`.

- [ ] Resolve the state file relative to the project directory and return a clear error if it does not exist.
- [ ] Create a browser context from the saved state; use it for `/search-advanced?query=...` and the selected `/id/{id}` profile page.
- [ ] Preserve the numeric ID extracted from the search result and fetch the canonical URL `/id/{id}`.
- [ ] Copy cookies from that browser context into the existing requests session for the parser's profile subrequests; never log or include cookie values in the return data.
- [ ] Report rejected/expired session state clearly and close the browser/context on every exit path.
- [ ] Verify syntax with `python -m py_compile Auto_audit/PARSING/rusprofile.py`.

### Task 3: Review end-to-end instructions

**Files:**
- Modify: `Auto_audit/README.md`

- [ ] Confirm the README explains the one-time manual login, local state path, and how to refresh an expired session.
- [ ] Confirm the documented parser request still searches, extracts an ID, and returns the profile JSON.
