# One-time document cleanup

This manual Job empties only the unversioned `trustify-default` document bucket.
It uses eight concurrent workers, at most 1,000 keys per DeleteObjects request,
bounded retries, and a final LIST to verify that the bucket is empty. The bucket
owner is fixed to account `469459763996` on every list/delete request.

The existing Terraform Secret `storage-credentials` provides credentials at
runtime. No credentials are copied into Git. The Job uses an existing official
Python image and installs the pinned Boto3 dependency into its ephemeral work
volume; no image build or publication is required.

Keep the server and importer stopped, with application auto-sync disabled, until
cleanup completes. Verify through an administrative AWS session that bucket
versioning is disabled before running deletion. The application Secret does not
need additional permissions to inspect bucket versioning.

## Validate and inspect

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s operations/trustify/s3 -p '*_test.py'
oc apply --dry-run=server -k operations/trustify/s3
oc apply -k operations/trustify/s3
oc logs -f job/trustify-s3-cleanup -n trustify
```

The default mode is read-only. Require a completed Job and an authenticated LIST
before switching from another cleanup process. Stop that process before running
the deleting Job.

## Delete

After the inspection Job completes:

```sh
oc delete job trustify-s3-cleanup -n trustify
set -o pipefail
oc set env --local -f operations/trustify/s3/job.yaml CLEANUP_MODE=delete -o yaml | oc create -f -
oc logs -f job/trustify-s3-cleanup -n trustify
```

Require both Job completion and an independently verified empty bucket before
starting Trustify. An API error or remaining objects fail the Job; it must not
be treated as successful merely because its pod exited. A failed run can resume
by recreating the deleting Job. Do not edit its fixed-name ConfigMap while a
cleanup Job is running.

These resources are outside all Argo CD source paths. They are never part of
normal application synchronization. Job pods expire automatically after an hour;
the manual ConfigMap can be removed with `oc delete -k operations/trustify/s3`
after completion.
