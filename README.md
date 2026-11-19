# Generate trustify dumps

See: <https://serve-trustify-dumps.apps.cluster.trustification.rocks/>

## Deploy

Manifests are managed with [kustomize](https://kustomize.io/) (built into `kubectl` and `oc`)
and deployed by ArgoCD (OpenShift GitOps) from the `main` branch.

```
argocd/                       # ArgoCD AppProject + Application (syncs deploy/overlays/all)
deploy/
  base/                        # CronJob template
  common/                      # shared resources (import ConfigMap)
  overlays/
    all/                       # everything below + common, synced by ArgoCD
    default/                   # trustify-dumps (daily at 01:00 UTC)
    ds4/                       # trustify-dumps-ds4 (daily at 12:00 UTC)
    small/                     # trustify-dumps-small (daily at 06:00 UTC)
```

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
kubectl kustomize deploy/overlays/all
```

### One-time ArgoCD setup

The Application lives in the `trustify-dumps` namespace ("apps in any namespace"), restricted by the
`trustify-dumps` AppProject to deploying ConfigMaps and CronJobs into that namespace.

```bash
# allow the openshift-gitops instance to manage the namespace
oc label namespace trustify-dumps argocd.argoproj.io/managed-by=openshift-gitops
# allow Applications in the trustify-dumps namespace (this replaces the whole list, include any existing entries)
oc patch argocd openshift-gitops -n openshift-gitops --type merge -p '{"spec":{"sourceNamespaces":["trustify-dumps"]}}'
oc apply -f argocd/appproject.yaml
oc apply -f argocd/application.yaml
```

After that, changes merged to `main` are synced automatically.
