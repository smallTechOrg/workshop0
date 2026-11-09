# tests/support

Test-only helpers. Nothing here is imported by `src/`.

## `fake_oidc.py` — local OpenID Connect issuer

A real OIDC authorization-code issuer (discovery, authorize page, PKCE, token endpoint,
RS256 ID tokens, JWKS) so sign-in runs end to end without Google. The module docstring is
the full reference; this is the short version.

### Run it

```bash
uv run python tests/support/fake_oidc.py --port 8099          # the Phase-11 gate does this
export WORKSHOP0_OIDC_ISSUER=http://localhost:8099           # point the app at it
export WORKSHOP0_GOOGLE_CLIENT_ID=test-client WORKSHOP0_GOOGLE_CLIENT_SECRET=test-secret
```

Options: `--issuer URL` (default `http://localhost:<port>`), `--host` (default `127.0.0.1`),
`--client-id ID` (refuse other client ids), `--quiet`, plus one switch per flag below.

In pytest, in-process:

```python
from tests.support.fake_oidc import authorize_redirect, run_in_thread

with run_in_thread() as issuer:              # port 0 = free port
    issuer.base_url                          # also the `iss` claim
    callback = authorize_redirect(location_from_app_start, "trainer@example.test")
    issuer.set_flags(expired=True); issuer.reset()
    issuer.mint_id_token(email="a@example.test", aud="test-client", nonce="n")
```

### Endpoints

| Path | Purpose |
|---|---|
| `GET /.well-known/openid-configuration` | discovery (`authorization_endpoint`, `token_endpoint`, `jwks_uri`, `userinfo_endpoint`) |
| `GET /authorize` | sign-in page; skipped when `login_hint` or `email` is in the query |
| `POST /authorize` | the page's form target; approves and 302s to `redirect_uri?code=…&state=…` (Cancel → `error=access_denied`) |
| `POST /token` | code → `{access_token, token_type, expires_in, scope, id_token}`; codes single-use, 5 min; PKCE checked when a challenge was sent; `client_id` via form or Basic |
| `GET /jwks` | RS256 public key, `kid=fake-oidc-key-1` |
| `GET /userinfo` | claims for `Authorization: Bearer <access_token>` |
| `GET/POST /_control`, `POST /_control/reset` | issuer-wide flags |

ID token: `iss`, `aud` (= client_id), `sub` (stable per lower-cased email), `email`,
`email_verified`, `nonce` (echoed), `iat`, `exp` (+1 h), `name`, `picture`.

### Playwright: the authorize page

```ts
await page.getByLabel('Email').fill(`trainer-${run}@example.test`);   // or page.locator('#email')
await page.getByRole('button', { name: 'Sign in' }).click();
```

Test ids: `fake-oidc-email`, `fake-oidc-signin`, `fake-oidc-error`.

### Negative cases

| Flag | Magic email tag | ID token |
|---|---|---|
| `unverified` | `unverified` | `email_verified: false` |
| `wrong_aud` | `wrongaud` | `aud: "wrong-client-id"` |
| `expired` | `expired` | `iat` now−2 h, `exp` now−1 h |
| `bad_signature` | `badsig` | signed by a second key not in the JWKS (header `kid` = the published kid) |
| `unknown_kid` | `unknownkid` | signed by the second key, `kid=fake-oidc-rogue-key` |
| `wrong_iss` | `wrongiss` | `iss: "http://wrong-issuer.example"` |
| `bad_nonce` | `badnonce` | `nonce` differs from the authorize request |

How to turn them on (the token gets the union):

1. **Magic email, per sign-in (preferred; safe for parallel tests):** any `+`-separated
   segment of the local part equal to a tag — `unverified+t1@example.test`,
   `alice+expired@example.test`, `badsig+wrongaud@example.test`. The `email` claim is the
   address as typed.
2. **Per authorize request:** `flags=unverified,expired` in the authorize query, or the
   checkboxes under "Negative-case flags" on the page.
3. **Issuer-wide:** CLI `--unverified --wrong-aud --expired --bad-signature --unknown-kid
   --wrong-iss --bad-nonce`; at runtime
   `curl -X POST localhost:8099/_control -d '{"flags":{"expired":true}}'` (merge; add
   `"replace":true` to replace), `curl -X POST localhost:8099/_control/reset`. This affects
   every concurrent sign-in, so use it only in serial tests.

Flags are fixed when the code is issued.

### Self-test

```bash
uv run pytest tests/support -q        # needs TEST_DATABASE_URL like every suite (root conftest)
```

It runs the in-process issuer and also launches the CLI as a subprocess on a free port.
Set `FAKE_OIDC_URL=http://localhost:8099` to also check an already-running instance.
