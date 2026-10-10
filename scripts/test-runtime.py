#!/usr/bin/env python3
"""Exercise built CLIs against local Convex/S3 fixtures, without credentials.

Usage: python3 scripts/test-runtime.py [--sync PATH] [--inspect PATH]
       [--legacy-sync PATH]
The optional released CLI checks Parquet compatibility in both directions.
"""

import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit


class Fixture(BaseHTTPRequestHandler):
    objects = {}
    writes = []
    deny_manifest = False
    delete_user = False

    def log_message(self, *_):
        pass

    def reply(self, status, body, content_type="application/json"):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlsplit(self.path).path
        if path.startswith("/api/"):
            if self.headers.get("Authorization") != "Convex test-key":
                self.reply(401, b"{}")
                return
            user = {"_component": "", "_table": "users", "_id": "users:1",
                    "_ts": 42, "name": "Ada", "active": True, "score": 1.5}
            if path == "/api/json_schemas":
                body = {"users": {"type": "object"}}
            elif path == "/api/list_snapshot":
                body = {"values": [user], "snapshot": 42,
                        "cursor": None, "hasMore": False}
            elif path == "/api/document_deltas":
                body = {"values": [dict(user, _ts=44, _deleted=True)]
                        if self.delete_user else [],
                        "cursor": 44 if self.delete_user else 43, "hasMore": False}
            else:
                self.reply(404, b"{}")
                return
            self.reply(200, json.dumps(body).encode())
        elif self.deny_manifest:
            # The message mentions NoSuchKey, but the service error is AccessDenied.
            self.reply(403, b"<Error><Code>AccessDenied</Code>"
                       b"<Message>NoSuchKey is not the error code</Message></Error>",
                       "application/xml")
        elif path in self.objects:
            self.reply(200, self.objects[path])
        else:
            self.reply(404, b"<Error><Code>NoSuchKey</Code></Error>", "application/xml")

    def do_PUT(self):
        path = urlsplit(self.path).path
        self.objects[path] = self.rfile.read(int(self.headers["Content-Length"]))
        self.writes.append(("PUT", path))
        self.reply(200, b"")

    def do_DELETE(self):
        path = urlsplit(self.path).path
        self.objects.pop(path, None)
        self.writes.append(("DELETE", path))
        self.reply(204, b"")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sync", default="target/debug/convex-sync")
    parser.add_argument("--inspect", default="target/debug/convex-inspect")
    parser.add_argument("--legacy-sync")
    args = parser.parse_args()
    sync = str(Path(args.sync).resolve())
    inspect = str(Path(args.inspect).resolve())
    legacy = str(Path(args.legacy_sync).resolve()) if args.legacy_sync else None

    server = ThreadingHTTPServer(("127.0.0.1", 0), Fixture)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with tempfile.TemporaryDirectory(prefix="convex-runtime-") as temp:
            root = Path(temp)
            endpoint = f"http://127.0.0.1:{server.server_port}"
            # Do not inherit AWS profiles, endpoint overrides, proxy or Convex secrets.
            env = {"PATH": os.environ["PATH"], "HOME": temp, "RUST_LOG": "off",
                   "CONVEX_DEPLOYMENT_URL": endpoint, "CONVEX_DEPLOY_KEY": "test-key",
                   "AWS_ACCESS_KEY_ID": "test", "AWS_SECRET_ACCESS_KEY": "test",
                   "AWS_REGION": "us-east-1", "AWS_ENDPOINT_URL": endpoint,
                   "AWS_EC2_METADATA_DISABLED": "true", "AWS_MAX_ATTEMPTS": "1",
                   "AWS_CONFIG_FILE": str(root / "no-config"),
                   "AWS_SHARED_CREDENTIALS_FILE": str(root / "no-credentials"),
                   "AWS_REQUEST_CHECKSUM_CALCULATION": "WHEN_REQUIRED"}

            def run(binary, *argv, success=True):
                result = subprocess.run([binary, *map(str, argv)], cwd=temp, env=env,
                                        text=True, capture_output=True, timeout=45)
                if success:
                    if result.returncode:
                        raise AssertionError(f"{argv}: {result.stderr}")
                    return json.loads(result.stdout)
                if result.returncode == 0:
                    raise AssertionError(f"{argv}: unexpectedly succeeded")
                return result

            assert "users" in run(inspect, "schemas")
            assert len(run(inspect, "snapshot", "--raw")["values"]) == 1
            assert run(inspect, "deltas", "--cursor", "42", "--raw")["values"] == []

            raw, staging = root / "raw", root / "staging"
            checkpoint = root / "checkpoint.json"
            first = run(sync, "sync-once", "--output", raw, "--checkpoint-path", checkpoint)
            assert first["events_written"] == 1
            resumed = run(sync, "sync-once", "--output", raw, "--checkpoint-path", checkpoint)
            assert resumed["snapshot_pages_fetched"] == 0
            assert resumed["events_written"] == 0

            def materialize(binary, source, output):
                return run(binary, "materialize-staging", "--raw-change-log", source,
                           "--output", output, "--incremental")

            assert materialize(sync, raw, staging)["rows_materialized"] == 1
            assert materialize(sync, raw, staging)["files_read"] == 0
            parquet = staging / "_root/users.parquet"
            assert parquet.read_bytes().startswith(b"PAR1")

            if legacy:
                legacy_raw = root / "legacy-raw"
                run(legacy, "sync-once", "--output", legacy_raw,
                    "--checkpoint-path", root / "legacy-checkpoint.json")
                assert materialize(sync, legacy_raw, root / "new-reader")["rows_materialized"] == 1
                assert materialize(legacy, raw, root / "old-reader")["rows_materialized"] == 1
                print("PASS: released/new Parquet readers accept each other's raw logs")

            def publish(success=True):
                return run(sync, "publish-s3", "--staging-dir", staging,
                           "--bucket", "test-bucket", "--prefix", "exports", success=success)

            assert publish()["tables_uploaded"] == 1
            current = "/test-bucket/exports/staging/current/_root/users.parquet"
            assert Fixture.objects[current] == parquet.read_bytes()
            assert publish()["tables_unchanged"] == 1

            Fixture.deny_manifest = True
            before = len(Fixture.writes)
            denied = publish(success=False)
            assert "AccessDenied" in denied.stderr
            assert len(Fixture.writes) == before, "manifest read failure must not write objects"
            Fixture.deny_manifest = False

            Fixture.delete_user = True
            assert run(sync, "sync-once", "--output", raw,
                       "--checkpoint-path", checkpoint)["events_written"] == 1
            assert materialize(sync, raw, staging)["rows_materialized"] == 0
            assert not parquet.exists()
            assert publish()["tables_deleted"] == 1
            assert current not in Fixture.objects
            print("PASS: inspect, snapshot/resume/delete, Parquet, incremental staging, "
                  "S3 upload/no-op/delete, and fail-closed manifest errors (local fixtures)")
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


if __name__ == "__main__":
    main()
