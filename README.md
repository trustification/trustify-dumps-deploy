# Trustify GitOps

GitOps configuration for the Trustify service, dump generation, and dedicated
dump worker infrastructure on the Trustification OpenShift cluster.

```text
argocd/
  instance.yaml       # shared namespace-scoped Argo CD instance
  dumps/              # dump Application and AppProject
  trustify/           # service/platform Applications, AppProject, bootstrap RBAC
  autoscaling/        # infrastructure Application, AppProject, RBAC, optional tests
deploy/
  dumps/              # dump CronJobs and input configuration
  trustify/           # upstream Helm values and operator-managed platform resources
infra/
  autoscaling/        # dedicated Arm worker pool and optional validation Jobs
```

## Deployments and ownership

| Component | Configuration and runbook | Argo CD instance |
| --- | --- | --- |
| Dump generation | [Dump runbook](deploy/dumps/README.md) | `trustify-gitops` |
| Trustify service and observability | [Trustify runbook](deploy/trustify/README.md) | `trustify-gitops` |
| Dedicated dump workers | [Autoscaling runbook](infra/autoscaling/README.md) | `openshift-gitops` |

Applications follow `main`. Dump resources enable pruning; service, platform,
and worker infrastructure disable automatic pruning. Optional infrastructure
tests are disabled and their Application is registered only when needed.

The cluster has no parent Application. Administrators register Applications,
AppProjects, and bootstrap RBAC explicitly using the component runbooks. Changes
to those registrations in Git must also be applied to the existing registrations.
Do not recursively apply `argocd/`: its components use different controllers,
permissions, and bootstrap procedures.

Terraform in the separate `trustify-installation` repository owns Trustify's AWS
resources and credentials. Operators own generated observability workloads.
Secrets are provisioned out of band and must never be committed here.

## Local validation

Run commands from the repository root:

```sh
kubectl kustomize deploy/dumps/overlays/all
kubectl kustomize deploy/trustify/platform
kubectl kustomize infra/autoscaling
kubectl kustomize infra/autoscaling/tests
```

The component runbooks describe Helm validation and cluster-side checks.
Historical validation records are retained alongside their components. One-time
takeover tools remain available in Git history.

See [the repository migration runbook](argocd/README.md) for the rename and source
path handoff.
