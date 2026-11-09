#!/usr/bin/env bash
# Idempotent (check-then-create) provisioning of everything Workshop0 needs on GCP.
#
#   bash deploy/cloudrun/provision.sh [--dry-run] [--rotate <secret-name>]
#
# Run from the repo root as an operator authenticated to gcloud (and gh, optional).
# Prints `CREATED <what>` for every resource it creates, `EXISTS <what>` for every
# pre-existing one, and `SKIPPED <what>` for an optional resource whose value is absent
# (Google client secret, Anthropic key/workspace id: export them or put them in .env and
# re-run). Touches only workshop0-prefixed resources. Secret values are piped via stdin
# (never argv) and never printed. Exits non-zero on any failure.
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-ai-agent-boilerplate0}"
PROJECT_NUMBER="${PROJECT_NUMBER:-870371939888}"
REGION="${REGION:-us-central1}"
SQL_INSTANCE="${SQL_INSTANCE:-ai-agent-db}"
SQL_PRIVATE_IP="${SQL_PRIVATE_IP:-10.110.112.7}"
AR_REPO="workshop0"
RUN_SA_ID="workshop0-run"
DEPLOYER_SA_ID="workshop0-deployer"
RUN_SA="${RUN_SA_ID}@${PROJECT_ID}.iam.gserviceaccount.com"
DEPLOYER_SA="${DEPLOYER_SA_ID}@${PROJECT_ID}.iam.gserviceaccount.com"
WIF_POOL="github"
WIF_PROVIDER_ID="workshop0-github"
GH_REPO="smallTechOrg/workshop0"
DB_NAME="workshop0"
DB_USER="workshop0_app"
SERVICE="workshop0"
DBINIT_JOB="workshop0-dbinit"
# dbinit runs from a public Google image (the app image does not exist before the
# first deploy); psycopg is pip-installed at job start, dbinit.py is passed as base64.
DBINIT_IMAGE="gcr.io/google.com/cloudsdktool/google-cloud-cli:slim"
# Phase 11: private CV bucket (architecture.md §CV storage).
CV_BUCKET="${CV_BUCKET:-${PROJECT_ID}-workshop0-cvs}"
SECRETS=(workshop0-database-url workshop0-openrouter-api-key workshop0-admin-key
         workshop0-session-secret workshop0-google-client-secret
         workshop0-anthropic-api-key workshop0-anthropic-workspace-id)

DRY=0
ROTATE=""
while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY=1 ;;
    --rotate) shift; ROTATE="${1:-}"; [ -n "$ROTATE" ] || { echo "--rotate needs a secret name" >&2; exit 2; } ;;
    *) echo "usage: $0 [--dry-run] [--rotate <secret-name>]" >&2; exit 2 ;;
  esac
  shift
done
if [ -n "$ROTATE" ]; then
  case " ${SECRETS[*]} " in *" $ROTATE "*) ;; *) echo "unknown secret '$ROTATE' (one of: ${SECRETS[*]})" >&2; exit 2 ;; esac
fi

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HERE/../.." && pwd)"
G=(--project "$PROJECT_ID")

created() { echo "CREATED $1"; }
exists()  { echo "EXISTS $1"; }
would()   { echo "WOULD CREATE $1"; }
skipped() { echo "SKIPPED $1"; }
info()    { echo "INFO $1"; }
die()     { echo "ERROR $1" >&2; exit 1; }

# Print the value of an env var, else of the same key in the repo-root .env.
# Used ONLY on the left of a pipe into `gcloud secrets ... --data-file=-`.
source_value() {
  local key="$1" v="${!1:-}"
  if [ -z "$v" ] && [ -f "$REPO_ROOT/.env" ]; then
    v="$(grep -E "^${key}=" "$REPO_ROOT/.env" | head -1 | cut -d= -f2- | tr -d '\r' | sed -E "s/^['\"]//; s/['\"]$//")"
  fi
  [ -n "$v" ] || return 1
  printf '%s' "$v"
}
have_source() { source_value "$1" >/dev/null 2>&1; }

secret_exists() { gcloud secrets describe "$1" "${G[@]}" >/dev/null 2>&1; }

# Robust check using gcloud's own flatten/filter instead of parsing JSON by hand.
project_has_role() { # member role
  [ -n "$(gcloud projects get-iam-policy "$PROJECT_ID" --flatten='bindings[].members' \
    --filter="bindings.role=$2 AND bindings.members=$1" --format='value(bindings.role)' 2>/dev/null)" ]
}
secret_has_role() { # secret member role
  [ -n "$(gcloud secrets get-iam-policy "$1" "${G[@]}" --flatten='bindings[].members' \
    --filter="bindings.role=$3 AND bindings.members=$2" --format='value(bindings.role)' 2>/dev/null)" ]
}
sa_has_role() { # sa member role
  [ -n "$(gcloud iam service-accounts get-iam-policy "$1" "${G[@]}" --flatten='bindings[].members' \
    --filter="bindings.role=$3 AND bindings.members=$2" --format='value(bindings.role)' 2>/dev/null)" ]
}

echo "== Workshop0 provisioning: project=$PROJECT_ID region=$REGION dry-run=$DRY =="

gcloud auth list --filter=status:ACTIVE --format='value(account)' | grep -q . || die "gcloud is not authenticated"

# 1. APIs ------------------------------------------------------------------
enabled="$(gcloud services list --enabled "${G[@]}" --format='value(config.name)')"
for api in run artifactregistry secretmanager sqladmin iamcredentials storage; do
  if grep -qx "${api}.googleapis.com" <<<"$enabled"; then exists "api ${api}"
  elif [ $DRY -eq 1 ]; then would "api ${api}"
  else gcloud services enable "${api}.googleapis.com" "${G[@]}" >/dev/null; created "api ${api}"; fi
done

# 2. Artifact Registry -----------------------------------------------------
if gcloud artifacts repositories describe "$AR_REPO" --location "$REGION" "${G[@]}" >/dev/null 2>&1; then
  exists "artifact-registry-repo $AR_REPO"
elif [ $DRY -eq 1 ]; then would "artifact-registry-repo $AR_REPO"
else
  gcloud artifacts repositories create "$AR_REPO" --repository-format docker --location "$REGION" \
    --description "Workshop0 images" "${G[@]}" >/dev/null
  created "artifact-registry-repo $AR_REPO"
fi

# 3. Service accounts ------------------------------------------------------
for sa in "$RUN_SA_ID:Workshop0 Cloud Run runtime" "$DEPLOYER_SA_ID:Workshop0 GitHub Actions deployer"; do
  id="${sa%%:*}"; name="${sa#*:}"
  if gcloud iam service-accounts describe "${id}@${PROJECT_ID}.iam.gserviceaccount.com" "${G[@]}" >/dev/null 2>&1; then
    exists "service-account $id"
  elif [ $DRY -eq 1 ]; then would "service-account $id"
  else
    gcloud iam service-accounts create "$id" --display-name "$name" "${G[@]}" >/dev/null
    created "service-account $id"
    # IAM is eventually consistent for brand-new SAs.
    for _ in 1 2 3 4 5 6 7 8 9 10; do
      gcloud iam service-accounts describe "${id}@${PROJECT_ID}.iam.gserviceaccount.com" "${G[@]}" >/dev/null 2>&1 && break
      sleep 3
    done
  fi
done

# 4. Workload Identity Federation provider + binding -----------------------
WIF_POOL_PATH="projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${WIF_POOL}"
if gcloud iam workload-identity-pools providers describe "$WIF_PROVIDER_ID" --workload-identity-pool "$WIF_POOL" \
     --location global "${G[@]}" >/dev/null 2>&1; then
  exists "wif-provider $WIF_PROVIDER_ID"
elif [ $DRY -eq 1 ]; then would "wif-provider $WIF_PROVIDER_ID"
else
  gcloud iam workload-identity-pools providers create-oidc "$WIF_PROVIDER_ID" --workload-identity-pool "$WIF_POOL" \
    --location global --issuer-uri "https://token.actions.githubusercontent.com" \
    --attribute-mapping "google.subject=assertion.sub,attribute.repository=assertion.repository,attribute.ref=assertion.ref" \
    --attribute-condition "assertion.repository=='${GH_REPO}'" "${G[@]}" >/dev/null
  created "wif-provider $WIF_PROVIDER_ID"
fi
WIF_MEMBER="principalSet://iam.googleapis.com/${WIF_POOL_PATH}/attribute.repository/${GH_REPO}"
if sa_has_role "$DEPLOYER_SA" "$WIF_MEMBER" roles/iam.workloadIdentityUser; then
  exists "binding workloadIdentityUser $GH_REPO -> $DEPLOYER_SA_ID"
elif [ $DRY -eq 1 ]; then would "binding workloadIdentityUser $GH_REPO -> $DEPLOYER_SA_ID"
else
  gcloud iam service-accounts add-iam-policy-binding "$DEPLOYER_SA" --member "$WIF_MEMBER" \
    --role roles/iam.workloadIdentityUser "${G[@]}" >/dev/null
  created "binding workloadIdentityUser $GH_REPO -> $DEPLOYER_SA_ID"
fi

# 5. Database user (the database itself is created by the dbinit job, step 8) ----
# Password lives only in Secret Manager (inside workshop0-database-url).
db_password_from_secret() {
  gcloud secrets versions access latest --secret workshop0-database-url "${G[@]}" 2>/dev/null \
    | sed -E 's#^[^:]+://[^:]+:([^@]+)@.*#\1#'
}
make_url() { printf 'postgresql+psycopg://%s:%s@%s:5432/%s?sslmode=require' "$DB_USER" "$1" "$SQL_PRIVATE_IP" "$DB_NAME"; }
# Cloud SQL password policy wants upper+lower+digit+symbol; "_" keeps it URL-safe.
new_password() { printf 'Hm_%s9' "$(openssl rand -hex 24)"; }
user_exists() { gcloud sql users list --instance "$SQL_INSTANCE" "${G[@]}" --format='value(name)' | grep -qx "$DB_USER"; }

DB_URL_SECRET_EXISTS=0; secret_exists workshop0-database-url && DB_URL_SECRET_EXISTS=1
USER_EXISTS=0; user_exists && USER_EXISTS=1
PW=""
if [ $DRY -eq 0 ]; then
  if [ "$DB_URL_SECRET_EXISTS" -eq 1 ] && [ "$ROTATE" != "workshop0-database-url" ]; then
    PW="$(db_password_from_secret)"
    [ -n "$PW" ] || die "could not read the password back from workshop0-database-url"
  else
    PW="$(new_password)"   # fresh secret, or explicit rotation
  fi
fi
if [ "$USER_EXISTS" -eq 1 ]; then
  exists "sql-user $DB_USER"
  if [ $DRY -eq 0 ] && { [ "$DB_URL_SECRET_EXISTS" -eq 0 ] || [ "$ROTATE" = "workshop0-database-url" ]; }; then
    # Our own user, but the stored secret is absent/being rotated: re-apply the password.
    gcloud sql users set-password "$DB_USER" --instance "$SQL_INSTANCE" --password "$PW" "${G[@]}" >/dev/null
    info "sql-user $DB_USER password re-applied"
  fi
elif [ $DRY -eq 1 ]; then would "sql-user $DB_USER"
else
  gcloud sql users create "$DB_USER" --instance "$SQL_INSTANCE" --password "$PW" "${G[@]}" >/dev/null
  created "sql-user $DB_USER"
fi

# 6. Secrets (values via stdin only) ---------------------------------------
put_secret() { # name, value-producing function
  local name="$1" fn="$2"
  if secret_exists "$name"; then
    if [ "$ROTATE" = "$name" ]; then
      if [ $DRY -eq 1 ]; then would "secret-version $name (rotate)"; return; fi
      "$fn" | gcloud secrets versions add "$name" --data-file=- "${G[@]}" >/dev/null
      created "secret-version $name (rotated)"
    else
      exists "secret $name"
    fi
  elif [ $DRY -eq 1 ]; then would "secret $name"
  else
    gcloud secrets create "$name" --replication-policy automatic "${G[@]}" >/dev/null
    "$fn" | gcloud secrets versions add "$name" --data-file=- "${G[@]}" >/dev/null
    created "secret $name"
  fi
}
val_dburl()  { make_url "$PW"; }
val_openrouter() { source_value OPENROUTER_API_KEY; }
val_adminkey()   { source_value WORKSHOP0_ADMIN_KEY; }
val_session()    { openssl rand -hex 32; }   # generated; goes straight into the pipe
val_google()     { source_value WORKSHOP0_GOOGLE_CLIENT_SECRET; }
val_anthropic_key()       { source_value ANTHROPIC_API_KEY; }
val_anthropic_workspace() { source_value ANTHROPIC_WORKSPACE_ID; }

# Optional operator-supplied secret: an absent source value prints SKIPPED, never dies.
# Only a create or an explicit --rotate needs the value; an existing secret is left as is.
put_optional_secret() { # name, source-env-key, value-producing function
  local name="$1" key="$2" fn="$3"
  if secret_exists "$name" && [ "$ROTATE" != "$name" ]; then exists "secret $name"; return; fi
  if ! have_source "$key"; then skipped "secret $name (set $key and re-run)"; return; fi
  put_secret "$name" "$fn"
}

# Pre-flight: refuse before creating anything half-way if a needed source value is missing.
if ! secret_exists workshop0-openrouter-api-key || [ "$ROTATE" = "workshop0-openrouter-api-key" ]; then
  have_source OPENROUTER_API_KEY || die "OPENROUTER_API_KEY not in the environment or .env"
fi
if ! secret_exists workshop0-admin-key || [ "$ROTATE" = "workshop0-admin-key" ]; then
  have_source WORKSHOP0_ADMIN_KEY || die "WORKSHOP0_ADMIN_KEY not in the environment or .env"
fi
put_secret workshop0-database-url val_dburl
put_secret workshop0-openrouter-api-key val_openrouter
put_secret workshop0-admin-key val_adminkey
put_secret workshop0-session-secret val_session
put_optional_secret workshop0-google-client-secret WORKSHOP0_GOOGLE_CLIENT_SECRET val_google
put_optional_secret workshop0-anthropic-api-key ANTHROPIC_API_KEY val_anthropic_key
put_optional_secret workshop0-anthropic-workspace-id ANTHROPIC_WORKSPACE_ID val_anthropic_workspace
PW=""

# 7. IAM -------------------------------------------------------------------
RUN_MEMBER="serviceAccount:${RUN_SA}"
DEPLOYER_MEMBER="serviceAccount:${DEPLOYER_SA}"
bind_secret() { # secret member role label
  if secret_has_role "$1" "$2" "$3"; then exists "iam $4 on $1"
  elif [ $DRY -eq 1 ]; then would "iam $4 on $1"
  else gcloud secrets add-iam-policy-binding "$1" --member "$2" --role "$3" "${G[@]}" >/dev/null; created "iam $4 on $1"; fi
}
# Source env key of each optional secret (absent value => secret SKIPPED above).
optional_secret_key() {
  case "$1" in
    workshop0-google-client-secret)   echo WORKSHOP0_GOOGLE_CLIENT_SECRET ;;
    workshop0-anthropic-api-key)      echo ANTHROPIC_API_KEY ;;
    workshop0-anthropic-workspace-id) echo ANTHROPIC_WORKSPACE_ID ;;
    *) echo "" ;;
  esac
}
for s in "${SECRETS[@]}"; do
  if ! secret_exists "$s"; then
    k="$(optional_secret_key "$s")"
    if [ -n "$k" ] && ! have_source "$k"; then skipped "iam secretAccessor(runtime) + viewer(deployer) on $s (secret not created)"; continue; fi
    if [ $DRY -eq 1 ]; then would "iam secretAccessor(runtime) + viewer(deployer) on $s"; continue; fi
    die "secret $s is missing after the secrets step"
  fi
  bind_secret "$s" "$RUN_MEMBER" roles/secretmanager.secretAccessor "secretAccessor($RUN_SA_ID)"
  bind_secret "$s" "$DEPLOYER_MEMBER" roles/secretmanager.viewer "viewer($DEPLOYER_SA_ID)"
done

if project_has_role "$DEPLOYER_MEMBER" roles/run.developer; then exists "iam run.developer -> $DEPLOYER_SA_ID"
elif [ $DRY -eq 1 ]; then would "iam run.developer -> $DEPLOYER_SA_ID"
else
  gcloud projects add-iam-policy-binding "$PROJECT_ID" --member "$DEPLOYER_MEMBER" --role roles/run.developer \
    --condition=None >/dev/null
  created "iam run.developer -> $DEPLOYER_SA_ID"
fi

if [ -n "$(gcloud artifacts repositories get-iam-policy "$AR_REPO" --location "$REGION" "${G[@]}" --flatten='bindings[].members' \
     --filter="bindings.role=roles/artifactregistry.writer AND bindings.members=$DEPLOYER_MEMBER" --format='value(bindings.role)' 2>/dev/null)" ]; then
  exists "iam artifactregistry.writer -> $DEPLOYER_SA_ID on $AR_REPO"
elif [ $DRY -eq 1 ]; then would "iam artifactregistry.writer -> $DEPLOYER_SA_ID on $AR_REPO"
else
  gcloud artifacts repositories add-iam-policy-binding "$AR_REPO" --location "$REGION" --member "$DEPLOYER_MEMBER" \
    --role roles/artifactregistry.writer "${G[@]}" >/dev/null
  created "iam artifactregistry.writer -> $DEPLOYER_SA_ID on $AR_REPO"
fi

if sa_has_role "$RUN_SA" "$DEPLOYER_MEMBER" roles/iam.serviceAccountUser; then exists "iam serviceAccountUser -> $DEPLOYER_SA_ID on $RUN_SA_ID"
elif [ $DRY -eq 1 ]; then would "iam serviceAccountUser -> $DEPLOYER_SA_ID on $RUN_SA_ID"
else
  gcloud iam service-accounts add-iam-policy-binding "$RUN_SA" --member "$DEPLOYER_MEMBER" \
    --role roles/iam.serviceAccountUser "${G[@]}" >/dev/null
  created "iam serviceAccountUser -> $DEPLOYER_SA_ID on $RUN_SA_ID"
fi

# 7b. CV bucket (private) + runtime IAM for objects and V4 signed URLs -------
# Uniform bucket-level access, public access prevention enforced, no lifecycle rule.
CV_BUCKET_URL="gs://${CV_BUCKET}"
if gcloud storage buckets describe "$CV_BUCKET_URL" "${G[@]}" >/dev/null 2>&1; then
  exists "bucket $CV_BUCKET"
  if [ $DRY -eq 0 ]; then
    flags="$(gcloud storage buckets describe "$CV_BUCKET_URL" "${G[@]}" \
      --format='value(uniform_bucket_level_access,public_access_prevention)' 2>/dev/null || true)"
    if ! grep -qi 'true' <<<"$flags" || ! grep -qi 'enforced' <<<"$flags"; then
      gcloud storage buckets update "$CV_BUCKET_URL" --uniform-bucket-level-access \
        --public-access-prevention "${G[@]}" >/dev/null
      info "bucket $CV_BUCKET uniform access + public access prevention re-applied"
    fi
  fi
elif [ $DRY -eq 1 ]; then would "bucket $CV_BUCKET ($REGION, uniform access, public access prevention)"
else
  gcloud storage buckets create "$CV_BUCKET_URL" --location "$REGION" --uniform-bucket-level-access \
    --public-access-prevention "${G[@]}" >/dev/null
  created "bucket $CV_BUCKET ($REGION, uniform access, public access prevention)"
fi

if [ -n "$(gcloud storage buckets get-iam-policy "$CV_BUCKET_URL" "${G[@]}" --flatten='bindings[].members' \
     --filter="bindings.role=roles/storage.objectAdmin AND bindings.members=$RUN_MEMBER" --format='value(bindings.role)' 2>/dev/null)" ]; then
  exists "iam storage.objectAdmin -> $RUN_SA_ID on $CV_BUCKET"
elif [ $DRY -eq 1 ]; then would "iam storage.objectAdmin -> $RUN_SA_ID on $CV_BUCKET"
else
  gcloud storage buckets add-iam-policy-binding "$CV_BUCKET_URL" --member "$RUN_MEMBER" \
    --role roles/storage.objectAdmin "${G[@]}" >/dev/null
  created "iam storage.objectAdmin -> $RUN_SA_ID on $CV_BUCKET"
fi

# V4 signed URLs are signed via the IAM signBlob API with the runtime SA's own token
# (no key files): the SA needs serviceAccountTokenCreator on itself.
if sa_has_role "$RUN_SA" "$RUN_MEMBER" roles/iam.serviceAccountTokenCreator; then
  exists "iam serviceAccountTokenCreator -> $RUN_SA_ID on itself"
elif [ $DRY -eq 1 ]; then would "iam serviceAccountTokenCreator -> $RUN_SA_ID on itself"
else
  gcloud iam service-accounts add-iam-policy-binding "$RUN_SA" --member "$RUN_MEMBER" \
    --role roles/iam.serviceAccountTokenCreator "${G[@]}" >/dev/null
  created "iam serviceAccountTokenCreator -> $RUN_SA_ID on itself"
fi

# 8. dbinit job: create DB `workshop0` (owner workshop0_app) + schema privilege probe ----
DBINIT_B64="$(base64 < "$HERE/dbinit.py" | tr -d '\n')"
DBINIT_CMD='pip install -q --disable-pip-version-check --break-system-packages "psycopg[binary]>=3.2" 2>&1 | tail -3; echo "$DBINIT_PY_B64" | base64 -d > /tmp/dbinit.py && python3 /tmp/dbinit.py'
JOB_VERB=""
if gcloud run jobs describe "$DBINIT_JOB" --region "$REGION" "${G[@]}" >/dev/null 2>&1; then JOB_VERB=update; else JOB_VERB=create; fi
DB_EXISTED=0
gcloud sql databases list --instance "$SQL_INSTANCE" "${G[@]}" --format='value(name)' | grep -qx "$DB_NAME" && DB_EXISTED=1
if [ $DRY -eq 1 ]; then
  [ "$JOB_VERB" = create ] && would "run-job $DBINIT_JOB" || exists "run-job $DBINIT_JOB"
  [ "$DB_EXISTED" -eq 1 ] && exists "database $DB_NAME" || would "database $DB_NAME (via $DBINIT_JOB)"
else
  gcloud run jobs "$JOB_VERB" "$DBINIT_JOB" --region "$REGION" "${G[@]}" \
    --image "$DBINIT_IMAGE" --service-account "$RUN_SA" \
    --network default --subnet default --vpc-egress private-ranges-only \
    --max-retries 0 --task-timeout 300 \
    --command bash --args=-c --args="$DBINIT_CMD" \
    --set-env-vars "DBINIT_PY_B64=${DBINIT_B64}" \
    --set-secrets DATABASE_URL=workshop0-database-url:latest >/dev/null
  [ "$JOB_VERB" = create ] && created "run-job $DBINIT_JOB" || exists "run-job $DBINIT_JOB"
  if ! gcloud run jobs execute "$DBINIT_JOB" --region "$REGION" "${G[@]}" --wait >/dev/null 2>&1; then
    echo "ERROR dbinit job failed; recent job logs:" >&2
    gcloud logging read "resource.type=cloud_run_job AND resource.labels.job_name=$DBINIT_JOB" "${G[@]}" \
      --limit 15 --freshness 15m --format='value(textPayload)' >&2 || true
    exit 1
  fi
  if [ "$DB_EXISTED" -eq 1 ]; then exists "database $DB_NAME"; else created "database $DB_NAME (owner $DB_USER)"; fi
  info "dbinit ok: schema create privilege verified for $DB_USER on $DB_NAME"
fi

# 9. Placeholder service + public invoker binding --------------------------
# The deployer SA only has run.developer (no setIamPolicy), so the workflow cannot pass
# --allow-unauthenticated. We pre-create a placeholder service here (never touched if it
# already exists) and grant allUsers -> run.invoker on it; the workflow then only ever
# deploys new revisions (no-traffic candidate path).
SERVICE_EXISTS=0
gcloud run services describe "$SERVICE" --region "$REGION" "${G[@]}" >/dev/null 2>&1 && SERVICE_EXISTS=1
if [ "$SERVICE_EXISTS" -eq 1 ]; then
  exists "run-service $SERVICE"
elif [ $DRY -eq 1 ]; then would "run-service $SERVICE (placeholder hello image)"
else
  gcloud run deploy "$SERVICE" --region "$REGION" "${G[@]}" \
    --image us-docker.pkg.dev/cloudrun/container/hello --service-account "$RUN_SA" \
    --min-instances 0 --max-instances 3 --port 8080 --no-allow-unauthenticated >/dev/null
  created "run-service $SERVICE (placeholder hello image)"
  SERVICE_EXISTS=1
fi
if [ "$SERVICE_EXISTS" -eq 1 ]; then
  if [ -n "$(gcloud run services get-iam-policy "$SERVICE" --region "$REGION" "${G[@]}" --flatten='bindings[].members' \
       --filter='bindings.role=roles/run.invoker AND bindings.members=allUsers' --format='value(bindings.role)' 2>/dev/null)" ]; then
    exists "iam run.invoker allUsers on $SERVICE"
  elif [ $DRY -eq 1 ]; then would "iam run.invoker allUsers on $SERVICE"
  else
    gcloud run services add-iam-policy-binding "$SERVICE" --region "$REGION" --member allUsers \
      --role roles/run.invoker "${G[@]}" >/dev/null \
      || die "could not grant allUsers invoker (org policy blocking public access?)"
    created "iam run.invoker allUsers on $SERVICE"
  fi
else
  would "iam run.invoker allUsers on $SERVICE (after placeholder service is created)"
fi

# 10. GitHub Actions variables (non-sensitive) ----------------------------
if command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then
  existing_vars="$(gh variable list --repo "$GH_REPO" 2>/dev/null | cut -f1 || true)"
  for kv in "PROJECT_ID=$PROJECT_ID" "REGION=$REGION" "SERVICE=$SERVICE" "RUNTIME_SA=$RUN_SA" "DEPLOYER_SA=$DEPLOYER_SA" \
            "WIF_PROVIDER=${WIF_POOL_PATH}/providers/${WIF_PROVIDER_ID}"; do
    k="${kv%%=*}"; v="${kv#*=}"
    if grep -qx "$k" <<<"$existing_vars"; then exists "gh-variable $k"
    elif [ $DRY -eq 1 ]; then would "gh-variable $k"
    else gh variable set "$k" --repo "$GH_REPO" --body "$v" >/dev/null 2>&1 && created "gh-variable $k" || info "could not set gh-variable $k (optional; no repo admin?)"; fi
  done
else
  info "gh not available/authenticated; skipped GitHub Actions variables"
fi

echo "== done =="
