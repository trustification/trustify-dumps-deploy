# Repository migration — completed 26 November 2026

The repository moved from `trustification/trustify-dumps-deploy` to
`trustification/trustify-gitops`. Deployed names, namespaces, Helm chart sources,
and workload configuration remain unchanged.

The four existing Applications resolved the new URL and reported Synced/Healthy.
Their original automated sync policies were restored, the old project allowlist
entries were removed, and the temporary dump-path wrapper was deleted. Optional
test Applications were not registered. The local checkout directory was retained.

## Handoff sequence

The following sequence records the migration for future reference. It requires
GitHub administrator and cluster administrator access:

1. Inventory registered Applications and their AppProjects in `trustify-gitops`
   and `openshift-gitops`. Record their source settings and automated sync policies.
   Do not register optional test Applications that are currently absent.
2. Publish the reorganized layout using the existing URL. Keep the temporary
   `deploy/overlays/all` Kustomize wrapper until the dump registration moves to
   `deploy/dumps/overlays/all`.
3. Temporarily disable automated sync on affected Applications, preserving all
   other settings. Check that no operation is in progress before the rename.
4. Rename GitHub and update the local remote:

   ```sh
   gh repo rename trustify-gitops --repo trustification/trustify-dumps-deploy --yes
   git remote set-url origin git@github.com:trustification/trustify-gitops.git
   ```

5. Publish the new repository URL in all committed Applications and AppProjects.
   Add the new URL to live AppProject allowlists before changing Applications.
6. Patch only matching live repository URLs and the dump source path. The
   Trustify multi-source Application retains its upstream Helm source and uses
   the new URL only for its values source. Refresh Applications and verify source
   resolution and rendered differences before restoring their recorded policies.
7. Require successful reconciliation with equivalent resources, then remove the
   old URL from project allowlists. Remove the compatibility wrapper only after
   confirming no Application references the old dump path.

If source resolution fails, leave automated sync disabled while correcting the
source or project permissions. The wrapper supports reverting the dump path
during the handoff. Reverting a repository URL also requires that URL to resolve
and be permitted by the AppProject; if necessary, reverse the GitHub rename and
restore the local remote. Do not delete Applications or deployed resources to
repair a source registration.
