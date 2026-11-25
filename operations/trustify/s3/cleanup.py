"""One-time cleanup of the unversioned Trustify document bucket."""
import os
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait

BUCKET = "trustify-default"
OWNER = "469459763996"
REGION = "eu-west-1"
WORKERS = 8
RETRYABLE = {"InternalError", "ServiceUnavailable", "SlowDown", "RequestTimeout"}


def delete_batch(client, keys, sleep=time.sleep):
    remaining = keys
    for attempt in range(5):
        response = client.delete_objects(
            Bucket=BUCKET, ExpectedBucketOwner=OWNER,
            Delete={"Objects": [{"Key": key} for key in remaining], "Quiet": True},
        )
        errors = response.get("Errors", [])
        if not errors:
            return len(keys)
        codes = sorted({error.get("Code", "Unknown") for error in errors})
        if any(error.get("Code") not in RETRYABLE or "Key" not in error for error in errors):
            raise RuntimeError("S3 refused deletions: " + ", ".join(codes))
        remaining = [error["Key"] for error in errors]
        if attempt < 4:
            sleep(2 ** attempt)
    raise RuntimeError("S3 deletions failed after retries: " + ", ".join(codes))


def empty_bucket(client, report=print, workers=WORKERS):
    processed = 0
    started = last_report = time.monotonic()

    def collect(futures):
        nonlocal processed, last_report
        for future in futures:
            processed += future.result()
        now = time.monotonic()
        if now - last_report >= 10:
            report(f"Processed {processed:,} deletions in {now - started:.0f}s", flush=True)
            last_report = now

    # A final strongly consistent LIST verifies the result. Repeat the scan if
    # deletion during pagination left any objects behind; never report success early.
    for _ in range(3):
        with ThreadPoolExecutor(max_workers=workers) as pool:
            pending = set()
            pages = client.get_paginator("list_objects_v2").paginate(
                Bucket=BUCKET, ExpectedBucketOwner=OWNER,
                PaginationConfig={"PageSize": 1000},
            )
            for page in pages:
                keys = [obj["Key"] for obj in page.get("Contents", [])]
                for offset in range(0, len(keys), 1000):
                    pending.add(pool.submit(delete_batch, client, keys[offset:offset + 1000]))
                    if len(pending) >= workers * 2:
                        done, pending = wait(pending, return_when=FIRST_COMPLETED)
                        collect(done)
            while pending:
                done, pending = wait(pending, return_when=FIRST_COMPLETED)
                collect(done)
        remaining = client.list_objects_v2(
            Bucket=BUCKET, ExpectedBucketOwner=OWNER, MaxKeys=1,
        )
        if not remaining.get("Contents"):
            report(f"Bucket verified empty; processed {processed:,} deletions.", flush=True)
            return processed
        report("Objects remain after pagination; scanning again.", flush=True)
    raise RuntimeError("Bucket is still nonempty after three passes")


def main():
    import boto3
    from botocore.config import Config

    mode = os.environ.get("CLEANUP_MODE", "inspect")
    if mode not in {"inspect", "delete"}:
        raise ValueError("CLEANUP_MODE must be inspect or delete")
    if os.environ.get("AWS_DEFAULT_REGION") != REGION:
        raise ValueError("Unexpected AWS region")
    client = boto3.client(
        "s3", region_name=REGION,
        config=Config(max_pool_connections=WORKERS * 2,
                      retries={"mode": "adaptive", "max_attempts": 10}),
    )
    if mode == "inspect":
        response = client.list_objects_v2(
            Bucket=BUCKET, ExpectedBucketOwner=OWNER, MaxKeys=1,
        )
        print(f"Authenticated to {BUCKET}; empty={not bool(response.get('Contents'))}", flush=True)
    else:
        print(f"Cleaning {BUCKET} with {WORKERS} workers and batches of 1,000.", flush=True)
        empty_bucket(client)


if __name__ == "__main__":
    main()
