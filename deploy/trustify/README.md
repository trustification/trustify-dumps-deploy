# Trustify application

This directory manages the `trustify` namespace through the existing
`trustify-gitops` Argo CD instance. The application uses the upstream Helm chart;
the platform Application manages the existing OpenTelemetryCollector, TempoStack,
ServiceMonitor, and vanity Ingress. Their operators retain ownership of generated
workloads, Routes, certificates, and network policies.

## Sources and ownership

`argocd/trustify-application.yaml` pins the upstream chart Git commit. Its second
source supplies only this repository's values (`ref: values`, with no `path`);
it does not deploy dump workloads. The application image is pinned to the digest
published by upstream's successful main workflow, linked in `values.yaml`.
Changing the moving `latest` tag does not change the running application.

The infrastructure source is `trustify-installation/prod/terraform`. Terraform
continues to own the RDS instance, IAM credentials, Cognito clients, S3 buckets,
credential Secrets, and its ConfigMaps `aws-storage`, `aws-oidc`, and
`tempo-storage`. Do not import those objects into Argo CD or rotate their values
as part of this takeover. Existing cluster-scoped collector/Tempo RBAC remains
an administrator-managed prerequisite, documented in `prod/deploy` there.

Required Terraform Secrets are `postgresql-credentials`,
`postgresql-admin-credentials`, `storage-credentials`, `storage-tempo-credentials`,
`oidc-frontend`, and `oidc-cli`. Public OIDC issuer/client identifiers are nonsecret
configuration. No passwords, tokens, private keys, Secret exports, Terraform
state, or Helm release exports belong in this repository.

## Validate

```sh
helm unittest ../trustify-helm-charts/charts/trustify
helm lint ../trustify-helm-charts/charts/trustify -f deploy/trustify/values.yaml
helm template trustify ../trustify-helm-charts/charts/trustify -n trustify \
  -f deploy/trustify/values.yaml | oc apply --dry-run=server -n trustify -f -
oc apply --dry-run=server -k deploy/trustify/platform
oc create --dry-run=server -f operations/trustify/database.yaml
```

The chart's schema uses URNs and needs a compatible Helm version. The deployed
Argo CD repo-server has Helm 4.2.4; local validation uses Helm 4.3.2. Upstream CI
also validates the chart with its full registered external schemas.

## Bootstrap and first synchronization

Apply `argocd/trustify-project.yaml` and `argocd/trustify-rbac.yaml` as an
administrator, then label the existing namespace:

```sh
oc label namespace trustify argocd.argoproj.io/managed-by=trustify-gitops --overwrite
oc apply -f argocd/trustify-project.yaml -f argocd/trustify-rbac.yaml
for manifest in argocd/trustify-platform-application.yaml argocd/trustify-application.yaml; do
  oc patch --local -f "$manifest" --type=json \
    --patch '[{"op":"remove","path":"/spec/syncPolicy/automated"}]' -o yaml | oc apply -f -
done
```

The bootstrap RBAC includes the built-in `system:auth-delegator` role for the
application controller. Tempo admission requires TokenReview and
SubjectAccessReview creation privileges when submitting OpenShift tenancy
configuration. This binding is maintained manually, outside either Application.

The bootstrap command disables auto-sync for the first adoption. Neither
Application has a cascading-deletion finalizer.
Review their Argo CD differences before synchronization. First sync the platform
Application and check that its operators remain ready. Perform the one-time
fresh installation below before syncing the application. The migration PreSync
hook must succeed before the application starts.

## One-time fresh installation

This procedure deliberately discards the old Trustify database and documents.
No new snapshot or data migration is requested. Existing RDS backup retention
and Tempo traces remain unchanged. Do not delete the namespace or uninstall the
old Helm release: the Terraform credentials and shared observability stay in place.

1. Verify the pinned upstream image is available for the worker architectures,
   that the chart passes CI, and that all required Secrets exist.
2. Create `operations/trustify/database.yaml` with `oc create`. It defaults to
   `RESET_MODE=inspect`; read its job logs to verify connectivity, PostgreSQL
   version, and available extensions. Delete the completed inspection job.
3. Stop the old `server` and `importer` Deployments, wait for their pods to exit,
   and verify no other Trustify clients are writing. Automatic sync must remain off.
4. Recreate only `trustify_default` on the existing March 2025 RDS instance:

   ```sh
   set -o pipefail
   oc set env --local -f operations/trustify/database.yaml RESET_MODE=reset -o yaml | oc create -f -
   ```

   Wait for that generated job to complete and inspect its logs. The job refuses
   a different endpoint, database, or login; it retains administrator ownership,
   existing users and passwords, and prepares grants for admin-run migrations.
   It is outside every Argo CD source path and never runs on normal sync.
5. Empty only `s3://trustify-default`, preserving the bucket and IAM configuration.
   Check versioning first; if enabled, remove historical versions and delete
   markers as well. Never empty `storage-tempo-default` or any dumps bucket.
   For an unversioned bucket, use the [one-time batched cleanup Job](../../operations/trustify/s3/README.md).
6. Remove unused `data-infrastructure-postgresql-0` and `workdir-importer-0` PVCs
   after confirming no pod uses them. The old importer's ephemeral PVC is removed
   with its pod. Preserve `data-tempo-tempo-ingester-0`.
7. Sync the application manually. Its pinned migration image creates the schema
   on the empty database. Do not restore old data or importer state.
8. Render the single importer-seeding job from the same pinned chart and create
   it explicitly:

   ```sh
   helm template trustify ../trustify-helm-charts/charts/trustify -n trustify \
     -f deploy/trustify/values.yaml -f operations/trustify/importers.yaml \
     --show-only templates/init/create-importers/020-Job.yaml | oc create -n trustify -f -
   ```

   Verify success. This overlay is never included in the Argo CD Application.
   Regular sync has database creation and importer seeding disabled.
9. Require healthy server/importer pods, successful authentication and sample
   ingestion/retrieval, and working metrics/traces. Check both public endpoints.

   ```sh
   python3 operations/trustify/smoke-test.py --write --resync
   python3 operations/trustify/smoke-test.py --server https://server-trustify.apps.cluster.trustification.rocks
   ```

   Credentials are read from Terraform's existing Secrets into memory; neither
   credentials nor access tokens are printed or written to disk.
10. Reapply both committed Application manifests to enable automated sync with
    `prune: false` and `selfHeal: true`. The `--resync` test above verifies that
    existing data survives a second full sync.

Keep the old Helm release metadata for reference, but stop using Helm upgrades
and rollbacks for this namespace. Argo CD owns deployment lifecycle now.

## Recovery

Disable automatic sync before intervening. Application deletion is noncascading;
neither pruning nor a Git revert recovers erased data. Fix forward against the
pinned application or deliberately repeat fresh initialization. Any recovery
from an existing RDS backup is a separate operation; do not run the old image
against the new schema as a rollback.
