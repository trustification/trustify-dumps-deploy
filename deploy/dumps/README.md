# Trustify dump generation

Artifacts: <https://serve-trustify-dumps.apps.cluster.trustification.rocks/>


Manifests are managed with [kustomize](https://kustomize.io/) (built into `kubectl` and `oc`)
and deployed by ArgoCD (OpenShift GitOps, instance `trustify-gitops`) from the `main` branch.

```text
deploy/dumps/
  base/                 # CronJob template
  common/               # shared import ConfigMap
  overlays/
    all/                # all dump resources, synced by Argo CD
    default/            # weekly default dump
    ds4/                # weekly ds4 dump
    small/              # daily small dump
```

Commands below run from the repository root.

### Secrets

Secrets are **not** stored in this (public) repository. The CronJobs expect a Secret named
`aws-secret` (keys `access_key_id`, `secret_access_key`) in the `trustify-dumps` namespace,
created out-of-band:

```bash
oc create secret generic aws-secret -n trustify-dumps \
  --from-literal=access_key_id=... --from-literal=secret_access_key=...
```

### Render manifests locally

```bash
kubectl kustomize deploy/dumps/overlays/all
kubectl kustomize infra/autoscaling
oc apply --dry-run=server -k deploy/dumps/overlays/all
oc apply --dry-run=server -k infra/autoscaling
```

### One-time ArgoCD setup

Deployment uses a dedicated, namespace-scoped Argo CD instance in the `trustify-gitops` namespace
(the cluster-wide `openshift-gitops` instance is reserved for cluster configuration). The
`trustify-dumps` AppProject restricts it to this repository, the `trustify-dumps` namespace and
ConfigMaps/CronJobs. These bootstrap resources are applied manually by a cluster admin:

```bash
oc apply -f argocd/instance.yaml       # namespace + ArgoCD instance
oc label namespace trustify-dumps argocd.argoproj.io/managed-by=trustify-gitops
oc apply -f argocd/dumps/project.yaml -f argocd/dumps/application.yaml
```

UI: <https://trustify-gitops-server-trustify-gitops.apps.cluster.trustification.rocks/>

After that, changes merged to `main` are synced automatically.

### Job resources

Each dump job gets a fresh ephemeral volume: default and ds4 request 512 GiB each,
while small requests 16 GiB. The shared size is set in `deploy/dumps/base/CronJob.yaml`;
the small overlay overrides it. The base also requests 6 CPUs and 24 GiB of memory
for default and ds4; the small overlay removes that CPU request and requests 6 GiB
of memory. Changes apply to newly created jobs.

Successful and failed jobs are automatically deleted (`successfulJobsHistoryLimit: 0`
and `failedJobsHistoryLimit: 0`),
along with their pods and ephemeral volume claims. The `gp3-csi` storage class
deletes the backing EBS volumes when the claims are deleted. Successful dump
artifacts and uploaded failure logs remain in S3. Jobs still running or retrying
are not removed by these history limits.

We clean up finished jobs to avoid paying for their provisioned EBS storage
between runs. Retaining a completed or failed pod also retains its ephemeral
volume claim and backing EBS volume, even when no worker is using it. Artifacts
and failure logs are uploaded to S3, so keeping these volumes is unnecessary.

The base requests a database connection pool of 8–32 connections; small keeps
2–4 connections. These variables are read by the embedded database setup used by
`xtask generate-dump`.

Default and ds4 use 4 correlation workers (`TRUSTD_CORRELATION_WORKERS`),
256 MiB PostgreSQL work memory for correlation transactions
(`TRUSTD_CORRELATION_WORK_MEM`), and an 8 GiB WAL checkpoint target
(`TRUSTD_EMBEDDED_PG_SETTINGS=max_wal_size=8GB`). Small keeps the upstream defaults
by removing these overrides. Work memory applies per sort/hash operation, rather
than acting as a total memory cap; WAL can also exceed `max_wal_size`.
These settings require the xtask support added in
[Trustify PR #2908](https://github.com/guacsec/trustify/pull/2908).

Default and ds4 run weekly on Saturday at 06:00 UTC, on dedicated Arm workers.
Small still runs every day at 06:00 UTC on the existing workers. All schedules
explicitly use `Etc/UTC`. Large jobs have a 48-hour deadline covering scheduling,
execution, and retries; small has no new deadline. The autoscaler cannot evict
running large jobs for consolidation. Deadline termination, node failure, and
forced deletion can bypass the final S3 failure-log upload.

See [the autoscaling runbook](../../infra/autoscaling/README.md) for infrastructure
ownership, preflight checks, staged activation, and rollback. Deploy and validate
the dedicated pool before syncing the new large-job configuration.
