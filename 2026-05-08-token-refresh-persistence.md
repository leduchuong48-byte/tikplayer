# Token Refresh Persistence Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make AList token refresh durable across restarts by persisting token metadata, pre-refreshing before expiry, and handling token-expired errors consistently.

**Architecture:** Keep the existing token cache and `data/tokens.json` flow, but upgrade both to a shared record shape with expiry metadata. Derive expiry from login response or JWT `exp`, fall back to a local TTL, and centralize refresh/error detection inside `get_source_token()` plus a small helper for refreshable token errors.

**Tech Stack:** FastAPI backend, Python 3.12, stdlib `unittest`, encrypted token persistence with `cryptography.fernet`.

---

### Task 1: Add failing tests for token persistence records

**Files:**
- Create: `tests/test_token_refresh.py`
- Modify: `main.py:212-310`

**Step 1: Write the failing test**

Add tests covering:
- legacy string records migrate to object records
- `refresh_after` triggers pre-refresh and persists the new token
- expired-token errors force refresh
- failed pre-refresh falls back to the old token only while it is still unexpired

**Step 2: Run test to verify it fails**

Run: `python -m unittest tests/test_token_refresh.py -v`
Expected: FAIL because persisted records only store strings and pre-refresh behavior does not exist yet

**Step 3: Write minimal implementation**

- Upgrade persisted token format to `{ token, updated_at, expires_at, refresh_after, last_error }`
- Add helpers for record normalization, JWT expiry parsing, and refresh scheduling
- Keep old string-format records readable and rewrite them to the new format

**Step 4: Run test to verify it passes**

Run: `python -m unittest tests/test_token_refresh.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add tests/test_token_refresh.py main.py
git commit -m "test: cover token refresh persistence"
```

Note: this directory is not a git repository, so skip the commit step locally.

### Task 2: Refresh tokens before expiry and persist refresh results

**Files:**
- Modify: `main.py:373-501`
- Test: `tests/test_token_refresh.py`

**Step 1: Write the failing test**

Extend the test file with cases proving:
- login-derived expiry populates cache and persisted records
- forced refresh replaces the old record and clears stale errors
- pre-refresh failure records `last_error`

**Step 2: Run test to verify it fails**

Run: `python -m unittest tests/test_token_refresh.py -v`
Expected: FAIL until `get_source_token()` and login handling are updated

**Step 3: Write minimal implementation**

- Return expiry metadata from login
- Have `get_source_token()` reuse a persisted record, pre-refresh at `refresh_after`, and write the new record after successful refresh
- Preserve a still-valid token if pre-refresh fails before hard expiry

**Step 4: Run test to verify it passes**

Run: `python -m unittest tests/test_token_refresh.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add main.py tests/test_token_refresh.py
git commit -m "feat: persist token refresh metadata"
```

Note: this directory is not a git repository, so skip the commit step locally.

### Task 3: Use the new refreshable-error helper across AList calls

**Files:**
- Modify: `main.py:1354-1364`
- Modify: `main.py:1668-1677`
- Modify: `main.py:1758-1767`
- Modify: `main.py:2133-2139`
- Test: `tests/test_token_refresh.py`

**Step 1: Write the failing test**

Add a case proving `token is expired` is treated the same as `token is invalidated`.

**Step 2: Run test to verify it fails**

Run: `python -m unittest tests/test_token_refresh.py -v`
Expected: FAIL because only `token is invalidated` triggers refresh

**Step 3: Write minimal implementation**

- Add a shared helper for refreshable token errors
- Replace the hard-coded string checks at each AList call boundary

**Step 4: Run test to verify it passes**

Run: `python -m unittest tests/test_token_refresh.py -v`
Expected: PASS

**Step 5: Commit**

```bash
git add main.py tests/test_token_refresh.py
git commit -m "fix: refresh expired alist tokens"
```

Note: this directory is not a git repository, so skip the commit step locally.
