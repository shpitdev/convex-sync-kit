default:
  just --list

# Repo hygiene
install-hooks:
  git config --local core.hooksPath .githooks
  chmod +x .githooks/pre-commit

build-inspect:
  cargo build --locked -p convex-inspect

build-cli:
  cargo build --locked -p convex-sync

build-cli-release:
  cargo build --locked -p convex-sync --release

fmt:
  cargo fmt --all

fmt-check:
  cargo fmt --all --check

check:
  cargo check --workspace --locked

test:
  cargo test --workspace --locked

clippy:
  cargo clippy --workspace --locked --all-targets --all-features -- -D warnings

runtime-test:
  cargo build --workspace --locked
  python3 scripts/test-runtime.py

verify: fmt-check clippy test runtime-test

# CI
depot-ci *args:
  depot ci run --workflow .depot/workflows/ci.yml {{args}}

# S3/export CLI
dev-cli *args:
  ./scripts/convex-sync-dev {{args}}

schemas *args:
  cargo run -p convex-inspect -- schemas {{args}}

snapshot *args:
  cargo run -p convex-inspect -- snapshot {{args}}

deltas *args:
  cargo run -p convex-inspect -- deltas {{args}}

sync-once *args:
  cargo run -p convex-sync -- sync-once {{args}}

materialize-staging *args:
  cargo run -p convex-sync -- materialize-staging {{args}}

publish-s3 *args:
  cargo run -p convex-sync -- publish-s3 {{args}}

run *args:
  cargo run -p convex-sync -- run {{args}}

# Platform assets
aws-template-snapshot label="templates":
  ./scripts/snapshot-aws-templates.sh {{label}}

databricks-template-snapshot label="templates":
  ./scripts/snapshot-databricks-templates.sh {{label}}

# Databricks helpers
databricks-sync-staging-views *args:
  ./scripts/sync-databricks-staging-views.sh {{args}}

databricks-apply-sql-dir profile warehouse_id sql_dir:
  ./scripts/apply-databricks-sql-dir.sh {{profile}} {{warehouse_id}} {{sql_dir}}

databricks-delta-sync-secret *args:
  ./scripts/ensure-databricks-delta-secret.sh {{args}}

databricks-delta-bootstrap warehouse_id profile="DEFAULT":
  ./scripts/bootstrap-databricks-delta.sh {{profile}} {{warehouse_id}}

databricks-delta-render-dashboard output_file profile="":
  ./scripts/render-databricks-delta-dashboard.sh {{output_file}} {{profile}}

databricks-delta-publish-dashboard profile warehouse_id dashboard_id="":
  ./scripts/publish-databricks-delta-dashboard.sh {{profile}} {{warehouse_id}} {{dashboard_id}}

databricks-delta-render-pipeline profile output_file:
  ./scripts/render-databricks-delta-pipeline.sh {{profile}} {{output_file}}

databricks-delta-deploy-pipeline profile="DEFAULT" target="prod":
  ./scripts/deploy-databricks-delta-pipeline.sh {{profile}} {{target}}

databricks-delta-run-pipeline profile="DEFAULT" target="prod":
  ./scripts/run-databricks-delta-pipeline.sh {{profile}} {{target}}

databricks-delta-deploy profile="DEFAULT" target="dev":
  ./scripts/deploy-databricks-delta.sh {{profile}} {{target}}

databricks-delta-run profile="DEFAULT" target="dev" job_key="convex_delta_extract":
  ./scripts/run-databricks-delta-job.sh {{profile}} {{target}} {{job_key}}

databricks-delta-smoke warehouse_id profile="DEFAULT" target="dev":
  ./scripts/run-databricks-delta-smoke.sh {{profile}} {{target}} {{warehouse_id}}

# Install
install-dev:
  ./install.sh --mode dev --force
