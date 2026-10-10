# Release Artifacts

The operator-facing release artifact is the `convex-sync` CLI.

## Stable and Prerelease Assets

Each GitHub release should publish:

- `convex-sync_<tag>_linux_amd64.tar.gz`
- `SHA256SUMS`

The archive contains:

- `convex-sync`
- `LICENSE`
- `NOTICE`
- `README.md`

For now, that is enough to make the maintained Rust runtime easy to install and
verify.

`convex-inspect` is intentionally excluded from release artifacts for now. It is
a repo-local source-inspection binary, not the published operator entrypoint.

## Maintenance verification

Local checks, Depot CI, and release builds use Rust 1.95.0 and `Cargo.lock`.
Keep `rust-toolchain.toml` and the Rust action versions in all three Depot
workflows aligned when changing the toolchain.

The S3 client uses the supported default HTTPS transport, without the legacy
Hyper 0.14 / Rustls 0.21 feature. SSO, process credentials, and SigV4a remain
enabled. Arrow and Parquet use the same major version.

After the maintenance PR is merged, the existing `release` workflow updates the
release-please PR. The `release-rc` workflow publishes the merged main commit as
a prerelease; a stable release follows the release-please PR merge. Verify the
actual release target SHA, download its archive and `SHA256SUMS`, check the
checksum, and run the extracted CLI's `--version` before calling it shipped.

To test a released CLI against the same local fixtures and check raw Parquet
compatibility in both directions:

```bash
cargo build --workspace --locked
python3 scripts/test-runtime.py --legacy-sync /path/to/extracted/convex-sync
```

This checks executable behavior with synthetic data and local HTTP endpoints,
not live service access or TLS negotiation. Databricks assets are deployed by
the existing operator scripts, not by the Rust CLI release workflow.

## Dev Install Surface

This repo also ships a checkout-linked dev command:

- `scripts/convex-sync-dev`
- installed as `convex-sync-dev` via `./install.sh --mode dev`

That is not a release artifact, but it is part of the supported operator
experience for local development.

## Repo-Versioned Platform Assets

These stay versioned with the repo and release tag, but they are not published
as separate binary assets:

- `platform/aws/`
- `platform/databricks/s3/`
- `platform/databricks/delta/databricks.yml`
- `platform/databricks/delta/resources/`
- `platform/databricks/delta/extractor/convex_cdc_job.py`
- `platform/databricks/delta/sql/bootstrap/`
- `platform/databricks/delta/lakeflow/`

## Explicit Non-Artifacts

This repo should not publish:

- Terraform state
- rendered `.tfvars`
- Databricks smoke notebooks or secret scopes
- `.memory/` outputs
- internal library crates as standalone public packages

## Follow-up Candidates

Not in the first release slice:

- wider platform matrix beyond `linux-amd64`
- container images for the S3/export runtime
- separate packaging for Databricks Delta assets
