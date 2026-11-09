# Deploy Runbook — Workshop0 (Cloud Run)

Workshop0 was previously called Workshop Helmsman. Workshop0 runs on **Cloud Run + Cloud SQL**. Architecture detail: `spec/architecture.md` §Production topology. All commands run from the repo root unless stated otherwise; the operator is authenticated with `gcloud auth login` and `gh auth login`. Never paste or echo secret values.

## Topology

```
GitHub Actions (keyless, Workload Identity Federation)
  test (postgres:17) ─▶ build image ─▶ Artifact Registry us-central1/workshop0
     ─▶ Cloud Run Job workshop0-migrate (alembic upgrade head)
     ─▶ Cloud Run service workshop0: new revision --no-traffic (tag candidate)
     ─▶ health check ─▶ route traffic to LATEST ─▶ health check ─▶ (any failure => restore previous revision)

Browser ─HTTPS─▶ Cloud Run service workshop0 (project ai-agent-boilerplate0, us-central1, 0-3 instances)
                    │  private VPC egress, TLS
                    ▼
                 Cloud SQL PostgreSQL instance ai-agent-db (shared) ─ database workshop0, user workshop0_app
Secrets (Secret Manager): workshop0-database-url, workshop0-openrouter-api-key, workshop0-admin-key
  + Phase 11 (trainer network): workshop0-session-secret, workshop0-google-client-secret,
    workshop0-anthropic-api-key, workshop0-anthropic-workspace-id
CV bucket (Phase 11): gs://ai-agent-boilerplate0-workshop0-cvs (private; uniform access, public access prevention)
Public URL: https://workshop0.smalltech.in (domain mapping -> ghs.googlehosted.com) and the *.run.app URL
```

One uvicorn process per container serves `/api/*` and the built frontend. Instances are stateless; the database is the only shared state.

## One-time provisioning (idempotent)

```bash
# WORKSHOP0_ADMIN_KEY / OPENROUTER_API_KEY are read from the environment or .env (never echoed)
bash deploy/cloudrun/provision.sh --dry-run    # preview
bash deploy/cloudrun/provision.sh              # prints CREATED <thing> / EXISTS <thing>; safe to re-run
```

It enables the APIs, creates the Artifact Registry repo, service accounts, the keyless GitHub WIF provider, the database and user, the `workshop0-*` secrets with per-secret IAM, a placeholder Cloud Run service, and the public-invoker binding. It never prompts: the `workshop0-dbinit` Cloud Run job creates the database as `workshop0_app`. An existing secret is never overwritten unless you pass `--rotate <name>`.

## The pipeline

Every push to `main` runs `.github/workflows/deploy-cloudrun.yml`:

1. **test** — `uv run pytest tests/unit tests/integration -q` against a `postgres:17` service container.
2. **deploy** — keyless auth (service account `workshop0-deployer`), build and push the image tagged with the commit's first 12 characters, run the `workshop0-migrate` job to completion, deploy a **no-traffic** revision tagged `candidate`, health-check it (`/api/health`, up to ~60 s), route traffic to `LATEST` (so later `services update` calls take effect immediately), health-check the service URL.
3. **Rollback guard** — any failure after the previous revision was captured restores it to 100% and removes the `candidate` tag; the run ends red. The workflow never passes `--allow-unauthenticated`; `provision.sh` owns the public invoker binding.

Manual run (any branch or tag ref): `gh workflow run deploy-cloudrun.yml --ref <ref>` or Actions -> "Deploy (Cloud Run)" -> Run workflow. Inputs: `min_instances` (empty = unchanged, `0`, `1`) and `drill_rollback` (health-checks a path that 404s, so the run **must** fail and roll back — use it to prove the guard).

Repository variable `WORKSHOP0_BASE_URL` (set at cutover, e.g. `https://workshop0.smalltech.in`) is passed to the service **only when non-empty**; share links then use that domain. Unset, links derive from the request. Set it with `gh variable set WORKSHOP0_BASE_URL --body https://workshop0.smalltech.in`.

Migrations must stay backward-compatible with the previous revision for the one-deploy overlap window (additive first, destructive in a later release).

## Workshop mode (avoid cold starts)

```bash
# one warm instance, at least 10 minutes before the workshop starts
gcloud run services update workshop0 --region us-central1 --project ai-agent-boilerplate0 --min-instances=1
# back to scale-to-zero afterwards
gcloud run services update workshop0 --region us-central1 --project ai-agent-boilerplate0 --min-instances=0
# check the live value
gcloud run services describe workshop0 --region us-central1 --project ai-agent-boilerplate0 --format='value(spec.template.metadata.annotations."autoscaling.knative.dev/minScale")'   # empty = 0
```

- **Why a plain update works:** the service routes traffic to `LATEST` (the deploy workflow ends with `update-traffic --to-latest`), so the revision a `services update` creates serves 100% of traffic as soon as it is ready. A normal deploy never changes `min-instances`; the manual-run input `min_instances` (`""`, `0`, `1`) can set it.
- **After a manual rollback or the automatic rollback guard**, traffic is pinned to a named revision and a plain `services update` would create a 0%-traffic revision. Re-enable latest-routing first: `gcloud run services update-traffic workshop0 --region us-central1 --project ai-agent-boilerplate0 --to-latest` (the next successful deploy does this too).
- **Rehearse with the actual participant count** (join that many browsers or run the e2e/poll-burst checks) before a large workshop.

**Cold start:** with `min-instances=0` the first request after idle takes a few seconds while an instance boots (CPU boost is on). That is expected, not a bug; workshop mode removes it.

## Connection-budget rule

The shared Cloud SQL instance has a limited connection budget. Each instance holds up to `WORKSHOP0_DB_POOL_SIZE + WORKSHOP0_DB_MAX_OVERFLOW` (3 + 2) connections. **Never raise `max-instances` (or the pool settings) without recomputing**: `max-instances x (pool_size + max_overflow) <= ~15`. Today: 3 x 5 = 15.

## Operations: logs, health, rollback

```bash
gcloud run services logs read workshop0 --region us-central1 --project ai-agent-boilerplate0 --limit 100
gcloud run revisions list --service workshop0 --region us-central1 --project ai-agent-boilerplate0
curl -fsS "$(gcloud run services describe workshop0 --region us-central1 --project ai-agent-boilerplate0 --format='value(status.url)')/api/health"
# manual rollback to a known-good revision (pins traffic; run `update-traffic ... --to-latest` afterwards to resume latest-routing)
gcloud run services update-traffic workshop0 --region us-central1 --project ai-agent-boilerplate0 --to-revisions <REVISION>=100
```

Logs are JSON lines with a `severity` key.

## Database backup and restore

Cloud SQL automated backups / PITR are owned by the instance's owner (the instance is shared); Workshop0 does not alter them. Per-database logical export (needs a bucket you own):

```bash
gcloud sql export sql ai-agent-db gs://<bucket>/workshop0-$(date +%F).sql --database=workshop0 --project ai-agent-boilerplate0
```

Restore (into the empty `workshop0` database; this is destructive, so stop and confirm first):

```bash
gcloud sql import sql ai-agent-db gs://<bucket>/workshop0-<date>.sql --database=workshop0 --project ai-agent-boilerplate0
```

The Cloud SQL service account needs read access to the bucket for imports and write access for exports.

## Cutover from the VM to Cloud Run (human gate)

Prerequisites: provisioned, the Phase-8 image deployed (it contains `scripts/`), `gcloud` and `gh` authenticated, `smalltech.in` verified with Google (`domain-map.sh` tells you if not).

1. **Day before:** the production host is `workshop0.smalltech.in` (host label `workshop0`). Pick a window with **no live workshop**: the DNS flip and certificate issuance cause a short HTTPS gap (up to ~30-60 minutes), and anything written on the VM after the final import is not carried over. Note the names, statuses and participant counts of the VM's workshops for comparison.
2. **Import the SQLite backup** of the old deployment (wipes the throw-away Cloud Run data; historical step, the cutover is done):

   ```bash
   bash deploy/cloudrun/import-data.sh --sqlite <path-to-sqlite-backup> --replace
   ```

   It prints a per-table verification table; every row must say `OK`.
3. **Create the domain mapping:**

   ```bash
   bash deploy/cloudrun/domain-map.sh
   ```

   It prints the DNS records to set. If it reports the domain is unverified, add the TXT record below first and re-run it.
4. **GoDaddy DNS for `smalltech.in` (manual).** In the DNS records for `smalltech.in`:
   - **Add** `CNAME` · Host `workshop0` · Points to `ghs.googlehosted.com` · TTL `600`. (Done: the user created this record directly; the old `workshops` A record `35.200.241.145` is gone and `workshops.smalltech.in` no longer resolves.)
   - If any `A` or `AAAA` record exists for host `workshop0`, delete it (a CNAME cannot coexist with them).
   - Only if `domain-map.sh` reports the domain as unverified: add the `TXT` record it prints at host `@` (`google-site-verification=...`).

   If `gcloud beta run domain-mappings describe` shows different `resourceRecords`, **those win**: use the values it prints.
5. **Wait for the certificate and health:**

   ```bash
   bash deploy/cloudrun/domain-map.sh --wait
   ```

   Then set share links to the pretty domain and redeploy (merge the PR first):

   ```bash
   gh variable set WORKSHOP0_BASE_URL --body https://workshop0.smalltech.in
   gh workflow run deploy-cloudrun.yml --ref main
   ```
6. **Smoke test** on the real domain: `curl -sI https://workshop0.smalltech.in/ | grep -i '^server: Google Frontend'`; open `/admin` with the admin key and compare workshops with your notes; open an old facilitator link (`/f/<admin_token>`) and an old participant link (`/p/<token>`); create a workshop, join from a second browser, complete a milestone, and check the shown links start with `https://workshop0.smalltech.in/`.
7. The VM has since been decommissioned (see "Disaster recovery").

## Rollback plan

The VM was retired on 2026-10-29 (see "Disaster recovery"), so there is no VM fallback any more. For a bad application release use the pipeline's automatic rollback or the manual `update-traffic` command in "Operations". For data, use the Cloud SQL export/restore above. A final consistent copy of the old VM's SQLite database (taken before deletion, integrity-checked, row counts and sha256 verified) is kept in the operator's local backups outside this repository; `deploy/cloudrun/import-data.sh --sqlite PATH` can load such a file. The old VM deploy path is recoverable from git tag `vm-deploy-final`.

## Disaster recovery

Everything is reproducible from this repository plus three things that live outside it:

1. **Infrastructure:** `bash deploy/cloudrun/provision.sh` recreates the Artifact Registry repo `workshop0`, service accounts `workshop0-run` / `workshop0-deployer`, the WIF provider `workshop0-github` (pool `github`, condition `smallTechOrg/workshop0`), the `workshop0` database and `workshop0_app` user, the `workshop0-*` secrets, the `workshop0-dbinit` job and a placeholder service `workshop0` with the public invoker binding.
2. **Code:** push to `main` (or `gh workflow run deploy-cloudrun.yml --ref <ref>`) builds the image `us-central1-docker.pkg.dev/ai-agent-boilerplate0/workshop0/workshop0:<sha12>`, runs the `workshop0-migrate` job and deploys the service.
3. **Data:** restore the latest logical export into the empty `workshop0` database (see "Database backup and restore"), or load a SQLite file with `deploy/cloudrun/import-data.sh --sqlite PATH`.

The admin key is `WORKSHOP0_ADMIN_KEY` (secret `workshop0-admin-key`); losing it invalidates saved admin sessions but not facilitator or participant links. A final consistent copy of the retired VM's SQLite database is kept in the operator's local backups at `~/Backups/helmsman/` (outside this repository). The retired VM deploy path is recoverable from git tag `vm-deploy-final`; the VM, its disk and static IP are deleted and nothing in the repository depends on them.

## Appendix: Phase 9 cutover (rename to Workshop0)

Performed once by the operator, strictly in this order; the old service keeps serving until step 9. Full detail: `spec/roadmap.md` Phase 9.

1. Back up the existing database (Cloud SQL export plus a local copy) and record baseline workshop/participant/completion counts.
2. Create user `workshop0_app` and create database `workshop0` as a copy of the existing one (template copy in a window with no live workshop), then re-own its objects to `workshop0_app`.
3. Create secrets `workshop0-database-url`, `workshop0-openrouter-api-key`, `workshop0-admin-key`; the admin-key and OpenRouter values are copied byte-for-byte from the existing secrets so saved admin keys keep working.
4. Run `bash deploy/cloudrun/provision.sh`: new resources print `CREATED`, the database, user and secrets print `EXISTS`; a second run prints no `CREATED`.
5. Confirm WIF provider `workshop0-github` and its `workloadIdentityUser` binding for `smallTechOrg/workshop0` exist, **then** rename the GitHub repository to `workshop0` and update the local `origin`.
6. Leave `WORKSHOP0_BASE_URL` unset until step 9; merge the Phase 9 PR to `main` so the pipeline deploys the new service `workshop0` beside the old one.
7. Verify the new service at its own `*.run.app` URL (health, counts, an old participant link, the admin key, rollback drill).
8. Move the domain mapping from the old service to `workshop0` with `bash deploy/cloudrun/domain-map.sh --wait` (short HTTPS gap; no live workshop).
9. `gh variable set WORKSHOP0_BASE_URL --body https://workshop0.smalltech.in`, then `gh workflow run deploy-cloudrun.yml --ref main`.
10. Only after verification and explicit approval, delete the previous Cloud Run service and jobs, Artifact Registry repo, service accounts, secrets, WIF provider, database and user.
