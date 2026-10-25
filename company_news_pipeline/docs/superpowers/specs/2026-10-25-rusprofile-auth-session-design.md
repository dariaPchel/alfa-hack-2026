# Rusprofile authenticated session design

## Intent
Allow the Rusprofile parser to reuse the user's authenticated browser session for search and profile-page retrieval without storing the account password in source code.

## Goals
- Provide a small interactive Playwright script that opens a visible Chromium window and lets the user log in manually.
- Save Playwright storage state to a local file excluded from Git.
- Load that state in the parser for both `/search-advanced` and `/id/{id}` requests.
- Return a clear error when the state file is missing or the session has expired.

## Non-goals
- Do not automate password entry or bypass CAPTCHA/MFA.
- Do not print or commit cookies, storage state, or credentials.

## Approaches
- **Selected: interactive browser login + Playwright storage state.** Fits the existing Playwright search flow and preserves the browser cookies needed by both pages.
- Manual cookie copying into environment variables would be fragile and would require maintaining browser-specific cookie data.
- Hard-coded credentials or cookies in source would expose the account and would not be reliably refreshable.

## Constraints and implementation notes
- Add an ignore rule for the local storage-state file because the project currently has no root `.gitignore`.
- Keep the password out of the script and repository. User completes login in the browser and confirms when ready to save state.
- Use the saved state through a Playwright browser context for search and profile retrieval; retain BeautifulSoup extraction into JSON.
