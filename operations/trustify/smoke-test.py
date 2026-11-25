#!/usr/bin/env python3
"""Validate the deployment using Terraform's existing OAuth credentials in memory."""
import argparse
import base64
import json
import subprocess
import urllib.error
import urllib.parse
import urllib.request
import uuid


def cluster(kind, name):
    return json.loads(subprocess.check_output(
        ["oc", "get", kind, name, "-n", "trustify", "-o", "json"]
    ))


def request(url, *, method="GET", data=None, headers=None):
    req = urllib.request.Request(url, method=method, data=data, headers=headers or {})
    with urllib.request.urlopen(req, timeout=120) as response:
        return response.read()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--server", default="https://trustification.dev")
    parser.add_argument("--auth-only", action="store_true")
    parser.add_argument("--write", action="store_true", help="Upload, download, and delete one sample SBOM")
    args = parser.parse_args()
    issuer = cluster("configmap", "aws-oidc")["data"]["issuer-url"]
    discovery = json.loads(request(issuer + "/.well-known/openid-configuration"))
    credentials = cluster("secret", "oidc-cli")["data"]
    client_id = base64.b64decode(credentials["client-id"]).decode()
    client_secret = base64.b64decode(credentials["client-secret"]).decode()
    basic = base64.b64encode((client_id + ":" + client_secret).encode()).decode()
    token = json.loads(request(
        discovery["token_endpoint"], method="POST",
        headers={"Authorization": "Basic " + basic, "Content-Type": "application/x-www-form-urlencoded"},
        data=urllib.parse.urlencode({
            "grant_type": "client_credentials",
            "scope": "trustify/sbom trustify/importer trustify/metadata",
        }).encode(),
    ))["access_token"]
    print("Existing Terraform OAuth credentials authenticate successfully.")
    if args.auth_only:
        return
    headers = {"Authorization": "Bearer " + token}
    server = args.server.rstrip("/")
    request(server + "/")
    json.loads(request(server + "/api/v3/importer", headers=headers))
    print("Public UI and authenticated importer API respond successfully.")
    if not args.write:
        return
    sample = {
        "bomFormat": "CycloneDX", "specVersion": "1.5", "version": 1,
        "serialNumber": "urn:uuid:" + str(uuid.uuid4()),
        "metadata": {"component": {
            "type": "application", "bom-ref": "gitops-smoke-test",
            "name": "trustify-gitops-smoke-test", "version": "1.0.0",
            "purl": "pkg:generic/trustify-gitops-smoke-test@1.0.0",
        }},
    }
    result = json.loads(request(
        server + "/api/v3/sbom?labels.validation=gitops-takeover", method="POST",
        headers={**headers, "Content-Type": "application/json"},
        data=json.dumps(sample).encode(),
    ))
    key = urllib.parse.quote(result["id"], safe="")
    try:
        downloaded = json.loads(request(server + "/api/v3/sbom/" + key + "/download", headers=headers))
        if downloaded != sample:
            raise RuntimeError("Downloaded SBOM differs from the uploaded sample")
        print("Sample SBOM ingestion and S3 retrieval passed.")
    finally:
        request(server + "/api/v3/sbom/" + key, method="DELETE", headers=headers)
        print("Sample SBOM removed from the database.")


if __name__ == "__main__":
    try:
        main()
    except urllib.error.HTTPError as error:
        raise SystemExit(f"HTTP validation failed: {error.code} at {error.url}") from None
