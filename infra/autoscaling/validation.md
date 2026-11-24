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

Probe resources are disabled via an empty test Kustomization. The test
Application allows an empty desired state and prunes its Jobs, releasing their
pods and pod-owned storage. Confirm final volume deletion and scale-down before
declaring the lifecycle test complete.

## Migration blocker

The running ARM64 `ghcr.io/guacsec/xtask:latest` image does **not** expose the
correlation or embedded PostgreSQL options from PR #2908 in `generate-dump --help`.
Do not migrate the CronJobs until an image containing that PR is identified and
validated. S3 dump/failure-log tests using the tuned image are still outstanding.
