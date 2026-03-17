# Generate trustify dumps

See: <https://serve-trustify-dumps.apps.cluster.trustification.rocks/>

## Deploy

Manifests are managed with [kustomize](https://kustomize.io/) (built into `kubectl` and `oc`).

```
deploy/
  base/                        # shared base resources
  overlays/
    default/                   # trustify-dumps (daily at 01:00 UTC)
    ds4/                       # trustify-dumps-ds4 (daily at 12:00 UTC)
    small/                     # trustify-dumps-small (daily at 06:00 UTC)
```

### Render manifests locally

```bash
mkdir -p out
kubectl kustomize deploy/overlays/default > out/default.yaml
kubectl kustomize deploy/overlays/ds4 > out/ds4.yaml
kubectl kustomize deploy/overlays/small > out/small.yaml
```

### Apply to cluster

```bash
oc apply -k deploy/overlays/default
oc apply -k deploy/overlays/ds4
oc apply -k deploy/overlays/small
```
