# Initial validation — 24 November 2026

All worker and probe resources were reconciled by ArgoCD from the isolated
`deploy/dump-autoscaling` branch. The existing CronJob Application and main branch
were not changed.

- Infrastructure Application synced Healthy at zero replicas.
- A pending 6-CPU / 24-GiB probe triggered scale-from-zero to one worker.
- A second matching probe triggered scaling to two workers, one per probe.
- Both On-Demand `m9g.2xlarge` workers became Ready on OCP 4.22.22 / RHCOS 9.8
  and ran the ARM64 xtask image. Both probes printed `aarch64` and completed.
- First node allocatable capacity: 7.5 CPUs and 31,063,872 KiB RAM; probe and
  platform requests together were 6,264m CPU / 26,909 MiB memory.
- MCO reported four of four MachineSets reconciled, including the new pool.
- ArgoCD preserved the autoscaler-owned replica count and remained Synced.
- A probe selecting the workload label without the toleration stayed Pending;
  autoscaler events explicitly reported an untolerated taint and no scale-up.
- A 512-GiB ephemeral `gp3-csi` PVC bound, mounted and passed a write/readability
  check. The storage probe completed.
- Existing MachineSet replica counts stayed 3 / 3 / 2.
- Generated autoscaler arguments contained no global node/CPU/memory ceilings.

Probe resources are disabled via an empty test Kustomization. ArgoCD pruned all
four probe Jobs and their pods. The 512-GiB PVC and PV disappeared. The autoscaler
then reduced the dedicated MachineSet from two workers to one and finally zero
after the configured idle intervals. Both Machine objects and both worker Nodes
were deleted. Existing MachineSets remained at 3 / 3 / 2. Infrastructure and test
Applications remained Synced / Healthy. The 0 → 1 → 2 → 0 lifecycle test passed.

## Original image blocker (resolved 25 November)

The running ARM64 `ghcr.io/guacsec/xtask:latest` image does **not** expose the
correlation or embedded PostgreSQL options from PR #2908 in `generate-dump --help`.
The user confirmed that no such image is available yet and migration must wait
for the PR to merge and a new image to be published. Do not migrate the CronJobs
until that image is identified and validated. S3 dump/failure-log tests using the
tuned image were deferred at that point.

## Tuned image validation — 25 November 2026

The published manifest list
`sha256:991685f3224b4544c705ccd4a8ae61a0743d992fbf641e3aace8450154ef8c27`
contains ARM64 image
`sha256:2a0d099cdfd3f2f2e729f2254cbc2e6d3eecb16cbda4352cd453856cff90686b`.
Its CLI exposes the correlation and embedded PostgreSQL options from PR #2908.

ArgoCD created a validation Job in the workload namespace, using its existing
AWS secret, a 512-GiB ephemeral gp3 volume, and 6 CPUs / 24 GiB on a fresh M9g
worker. It generated an empty-input SQL dump with four correlation workers,
256-MiB transaction work memory, max_wal_size=8GB, and an 8–32 connection pool.
Database startup, migrations, correlation draining and SQL export all completed.

The dump and compressed success log uploaded to
`s3://trustify-dumps-small/autoscaling-validation/20261125/`. A deliberately invalid
PostgreSQL argument then failed parsing; its compressed failure log uploaded to
the same prefix under `failed/job.log.xz`, and the Job exited with the expected
code 2. Successful upload responses were verified; no S3 read permission is
required. The first validation attempt's extra HeadObject check returned 403
because the production credentials are write-only; the corrected test passed
without changing IAM permissions.

The test Kustomization is empty again so ArgoCD prunes the Job, pod and volume.
This is a startup/upload smoke test, not a full dataset or throughput benchmark.
