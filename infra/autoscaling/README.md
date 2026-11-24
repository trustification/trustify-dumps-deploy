# Dedicated dump worker rollout

This infrastructure is managed from main and does not change any
CronJobs. ArgoCD owns the MachineSet, ClusterAutoscaler, MachineAutoscaler and
probe Jobs. Existing MachineSets remain unchanged. Default and ds4 will move to
this pool only after testing succeeds; small will remain on existing workers.

## GitOps bootstrap

The cluster has no parent Application. An administrator must register the
AppProject, controller RBAC and Application once; they are not worker resources.
Apply only `argocd/autoscaling-rbac.yaml`, `argocd/autoscaling-project.yaml` and
`argocd/autoscaling-application.yaml` during bootstrap. ArgoCD then creates all
resources from `infra/autoscaling`. Do not apply that directory with oc.

The infrastructure Application follows `main` after successful pool validation.
It has automatic sync/self-healing, no automatic pruning and no cascading deletion
finalizer. The separate test Application follows main's
`infra/autoscaling/tests` path and permits pruning disposable test Jobs.
Register `argocd/autoscaling-test-application.yaml` only after infrastructure sync
succeeds. Test Jobs are deliberately excluded from the infrastructure overlay.
The test Kustomization is currently empty: the test Application remains dormant
for the tuned-image checks that must precede CronJob migration. See
[the validation results](validation.md).

## Pool and ownership

One On-Demand `m9g.2xlarge` MachineSet in eu-west-1b scales between zero and two
workers. Only pods selecting `workload=trustify-dumps` and tolerating its
NoSchedule taint can use the pool, apart from necessary platform pods. The
MachineAutoscaler targets only this MachineSet. The ClusterAutoscaler omits global
resource limits so unrelated worker counts do not need to be tracked here.

The initial AWS configuration derives from the existing Arm pool in eu-west-1b;
there is no ongoing inheritance. Git owns instance type, networking, IAM, root
disk, labels and taints. The autoscaler owns replicas. MCO owns the boot AMI and
normal worker OS updates. Boot-image management is already enabled for all
MachineSets. ArgoCD ignores replicas and the AMI ID with
`RespectIgnoreDifferences=true`. Refresh the bootstrap AMI from the current Arm
pool before recreating a deleted MachineSet.

## Preflight and validation

Render `infra/autoscaling` and `infra/autoscaling/tests` with kubectl kustomize;
server-side dry-run them and all bootstrap manifests before publishing. Confirm
there is no pre-existing ClusterAutoscaler or MachineAutoscaler with conflicting
ownership. Check ARM64 xtask image availability and M9g/RHCOS compatibility.

AWS account checks require credentials: verify M9g offerings in eu-west-1b,
subnet IP headroom and EC2/EBS quotas versus usage. Two workers require up to 16
additional On-Demand vCPUs, two 120-GiB root disks and, after migration, two
512-GiB work volumes. Do not silently substitute another instance family.

1. Publish infrastructure only, then bootstrap its ArgoCD Application. Verify
   healthy sync, correct generated autoscaler arguments and zero worker replicas.
2. Register the test Application. Its first Job requests 6 CPUs / 24 GiB with the
   dedicated Arm selector/toleration. Observe pending-pod-triggered provisioning
   and check Machine events, ARM64 node readiness, workload taint/label, worker
   MachineConfigPool membership and MCO boot-image reconciliation. The probe runs
   `uname -m` then sleeps for ten minutes; its overall deadline is one hour.
3. After one worker succeeds, add a second matching probe Job through Git. Keep
   both pending/running together to verify the pool reaches two nodes, one per
   6-CPU pod. No MachineSet may exceed its maxReplicas of two.
4. Remove probe Jobs from their Kustomization through Git. The test Application
   prunes them; never apply or delete the Jobs manually. Verify scale-down to zero
   after the ten-minute unneeded interval and any remaining scale-up delay.
5. Before CronJob migration, test a small-input dump and a terminal failure through
   the test Application. Confirm S3 artifacts/failure logs, PVC/PV/EBS cleanup and
   no autoscaler eviction of running dump pods. Manual test Jobs are not owned by
   CronJobs: remove them through GitOps to release their ephemeral volumes.
6. The validated infrastructure is now on main, with both Applications following
   main. Keep test resources disabled while waiting for PR #2908 and its image.
   After the tuned-image tests pass, remove the test Application/temporary test
   RBAC and publish the separate workload changes. Existing workload auto-sync
   stays enabled throughout; no CronJob changes are published before validation.

The normal workloads will request 6 CPUs / 24 GiB, run Saturday 06:00 UTC and use
48-hour Job deadlines. Small stays daily 06:00 UTC. Keep correlation settings,
S3 uploads, zero successful/failed history retention and ephemeral gp3 storage.
External termination or deadline expiry can bypass final failure-log uploads.

## Failure and rollback

If provisioning fails, remove probe Jobs through GitOps first, inspect Machine
and autoscaler events, and return the dump pool to zero. Root disks must disappear
with Machines. Do not migrate CronJobs until compatibility and scale-from-zero
pass. A failed quota or unsupported-family check is a blocker, not permission to
provision different machines.

For later rollback, suspend large-job schedules through Git, handle active Jobs
explicitly, then remove the MachineAutoscaler and scale the dedicated pool to zero
through a reviewed infrastructure change. Infrastructure pruning is disabled:
request explicit ArgoCD pruning only for the intended removed resources. Remove
the singleton ClusterAutoscaler and its RBAC only if nobody else has adopted it.
Never change existing MachineSets or schedule large requests onto their smaller
workers. Startup, retries and scale-down delay all contribute to cost.
