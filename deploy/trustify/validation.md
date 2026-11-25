# Takeover validation — 2026-11-25

- Application: upstream main `5c6af24e02e19af674c52a15059d78679ea5814e`, using the existing published digest recorded in `values.yaml`. No images were published for this takeover.
- Helm chart: upstream commit `581135ce301102f871a3456a13d41d562cfe5c34`, containing the merged service-CA and image-schema fixes from [PR #107](https://github.com/guacsec/trustify-helm-charts/pull/107).
- The existing RDS instance was retained, `trustify_default` recreated empty, and PostgreSQL upgraded in place to **18.6** with a `postgres18` parameter group. Post-upgrade connectivity and extension availability passed.
- Production Terraform state was migrated to the dedicated encrypted, versioned S3 backend. Existing database and OIDC credentials were retained. The inactive S3 IAM access key was rotated through Terraform, updating `storage-credentials` in place.
- The remaining **1,995,151** document deletions completed in the cluster in approximately 13 minutes. Both the Job and an independent S3 LIST verified an empty bucket before application startup. Tempo data and its PVC were preserved; unused legacy application PVCs were removed.
- The first Argo CD sync completed, including the database migration hook. Four fresh importer definitions were seeded once in `trustify`; CVE ingestion is progressing. Initial corpus ingestion is expected to continue after takeover completion.
- Both public hostnames served the UI and passed authenticated API access. Sample SBOM ingestion and S3 retrieval passed; samples were removed from the database.
- A sample SBOM survived a second full Argo CD sync, confirming recurring synchronization does not reset data or reseed importers.
- The collector exposed 1,876 metric samples associated with the new server/importer pods. A sampled validation trace was retrieved through the retained Tempo gateway with 40 spans.
- Checks passed: 19 upstream chart tests, chart lint/offline rendering, six cleanup unit tests, and Kubernetes server-side validation.

Final desired policy is automated sync and self-healing for `trustify` and
`trustify-platform`, with pruning disabled and no cascading-deletion finalizer.
Database reset, document cleanup, and importer seeding remain manual operations
outside every Argo CD source path.
