# Trustify application

This directory manages the `trustify` namespace through the `trustify-gitops`
Argo CD instance. The application uses the upstream Helm chart; the platform
Application manages the OpenTelemetryCollector, TempoStack, ServiceMonitor, and
vanity Ingress. Operators own generated workloads, Routes, certificates,
and network policies.

## Sources and ownership

`argocd/trustify/application.yaml` pins the upstream chart Git commit. Its second
source supplies this repository's values (`ref: values`, with no `path`). The
application image is pinned to the digest recorded in `values.yaml`.

Terraform in `trustify-installation/prod/terraform` owns the RDS instance, IAM
credentials, Cognito clients, S3 buckets, credential Secrets, and ConfigMaps
`aws-storage`, `aws-oidc`, and `tempo-storage`. Maintain those in their owning
repository. Existing cluster-scoped collector/Tempo RBAC is an administrator
prerequisite documented in `prod/deploy` there.

Required Terraform Secrets are `postgresql-credentials`,
`postgresql-admin-credentials`, `storage-credentials`, `storage-tempo-credentials`,
`oidc-frontend`, and `oidc-cli`. Public OIDC issuer/client identifiers are nonsecret
configuration. Do not commit credentials, Terraform state, or Helm release exports.

## Validate

Run commands from the repository root, with the upstream chart checked out at
the commit pinned in the Application:

```sh
helm unittest ../trustify-helm-charts/charts/trustify
helm lint ../trustify-helm-charts/charts/trustify -f deploy/trustify/values.yaml
helm template trustify ../trustify-helm-charts/charts/trustify -n trustify \
  -f deploy/trustify/values.yaml | oc apply --dry-run=server -n trustify -f -
oc apply --dry-run=server -k deploy/trustify/platform
```

The chart's schema uses URNs and needs a compatible Helm version. Takeover
validation used Helm 4.3.2 locally and Helm 4.2.4 in Argo CD. Upstream CI also
validates the chart with its registered external schemas.

## Deployment and reconciliation

For initial controller registration, an administrator labels the existing
namespace and applies the bootstrap permissions and registrations:

```sh
oc label namespace trustify argocd.argoproj.io/managed-by=trustify-gitops --overwrite
oc apply -f argocd/trustify/project.yaml -f argocd/trustify/rbac.yaml
oc apply -f argocd/trustify/platform-application.yaml -f argocd/trustify/application.yaml
```

These registrations assume existing Terraform-managed infrastructure and an
initialized service. The completed takeover is recorded in
[the historical validation results](validation.md); database reset, document
cleanup, and importer seeding tooling is retained only in Git history.

Bootstrap RBAC includes `system:auth-delegator` for the application controller.
Tempo admission requires TokenReview and SubjectAccessReview privileges for
OpenShift tenancy. Bootstrap RBAC is outside both Applications' sync paths.

For ongoing updates, change the pinned chart/image or Helm values, validate the
rendered differences, and merge to `main`. Both Applications use automatic sync,
self-healing, `prune: false`, and no cascading-deletion finalizer. Database
migrations run through the chart's PreSync hook. Regular synchronization has
database creation and importer seeding disabled.

After reconciliation, require Healthy/Synced Applications, ready server/importer
pods, successful authentication and sample ingestion/retrieval, and working
metrics and traces. Check both public endpoints: <https://trustification.dev>
and <https://server-trustify.apps.cluster.trustification.rocks>.

## Recovery

Disable automatic sync before intervening. Application deletion is noncascading;
neither pruning nor a Git revert recovers erased data. Fix forward against the
pinned application. Recovery from RDS backups is a separate infrastructure and
data operation; do not run an old image against an incompatible schema.

Argo CD owns the deployment lifecycle. Retain old Helm release metadata for
reference and use GitOps for deployment changes rather than Helm upgrades or
rollbacks.
