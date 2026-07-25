#!/usr/bin/env bash
#
# KrishiSetu security scan runner.
#
# Runs the full security toolchain against the codebase and the running API:
#   1. Bandit — Python AST-based security lint
#   2. pip-audit — Python dependency vulnerability scan
#   3. npm audit — JS dependency vulnerability scan
#   4. OWASP ZAP baseline — runtime HTTP security scan (requires API running)
#   5. Trivy — Docker image vulnerability scan (optional, requires Docker)
#
# Usage:
#   ./infra/security/run-security-scan.sh              # run all scanners
#   ./infra/security/run-security-scan.sh --quick      # skip ZAP and Trivy
#   ./infra/security/run-security-scan.sh --zap-only   # only run ZAP
#
# Output:
#   - Console output from each scanner
#   - Reports saved to ./security-reports/
#
# Exit codes:
#   0 — all scanners passed (or only warnings)
#   1 — at least one scanner reported FAIL-level findings
#   2 — scanner infrastructure failure (couldn't run a tool)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
REPORT_DIR="$ROOT_DIR/security-reports"
mkdir -p "$REPORT_DIR"

# Colors for terminal output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info()  { echo -e "${BLUE}[INFO]${NC} $*"; }
log_pass()  { echo -e "${GREEN}[PASS]${NC} $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
log_fail()  { echo -e "${RED}[FAIL]${NC} $*"; }

QUICK=false
ZAP_ONLY=false
for arg in "$@"; do
  case "$arg" in
    --quick) QUICK=true ;;
    --zap-only) ZAP_ONLY=true ;;
    *) log_warn "Unknown argument: $arg" ;;
  esac
done

OVERALL_EXIT=0
record_fail() { OVERALL_EXIT=1; }
record_warn() { :; }  # warnings don't fail the build

# ---------------------------------------------------------------------------
# 1. Bandit — Python AST security linter
# ---------------------------------------------------------------------------
run_bandit() {
  log_info "Running Bandit (Python security lint)..."
  cd "$ROOT_DIR/apps/api"
  if ! command -v bandit &> /dev/null; then
    log_warn "bandit not installed — install with: pip install bandit"
    record_warn
    return
  fi

  local report="$REPORT_DIR/bandit-report.txt"
  if bandit -r krishisetu -ll -ii -q 2>&1 | tee "$report"; then
    log_pass "Bandit: no HIGH severity findings"
  else
    local rc=$?
    if [ $rc -eq 1 ]; then
      log_fail "Bandit: HIGH severity findings detected (see $report)"
      record_fail
    else
      log_warn "Bandit: medium/low findings (see $report)"
      record_warn
    fi
  fi
}

# ---------------------------------------------------------------------------
# 2. pip-audit — Python dependency vulnerability scan
# ---------------------------------------------------------------------------
run_pip_audit() {
  log_info "Running pip-audit (Python dependency vulnerability scan)..."
  cd "$ROOT_DIR/apps/api"
  if ! command -v pip-audit &> /dev/null; then
    log_warn "pip-audit not installed — install with: pip install pip-audit"
    record_warn
    return
  fi

  local report="$REPORT_DIR/pip-audit-report.txt"
  if pip-audit --strict 2>&1 | tee "$report"; then
    log_pass "pip-audit: no known vulnerabilities in dependencies"
  else
    log_fail "pip-audit: vulnerable dependencies found (see $report)"
    record_fail
  fi
}

# ---------------------------------------------------------------------------
# 3. npm audit — JS dependency vulnerability scan
# ---------------------------------------------------------------------------
run_npm_audit() {
  log_info "Running npm audit (JS dependency vulnerability scan)..."
  cd "$ROOT_DIR/apps/web"
  if ! command -v npm &> /dev/null; then
    log_warn "npm not installed"
    record_warn
    return
  fi

  local report="$REPORT_DIR/npm-audit-report.txt"
  if npm audit --omit=dev --audit-level=high 2>&1 | tee "$report"; then
    log_pass "npm audit: no HIGH or CRITICAL vulnerabilities"
  else
    log_fail "npm audit: HIGH/CRITICAL vulnerabilities found (see $report)"
    record_fail
  fi
}

# ---------------------------------------------------------------------------
# 4. OWASP ZAP — runtime HTTP security scan
# ---------------------------------------------------------------------------
run_zap() {
  log_info "Running OWASP ZAP baseline scan against http://localhost:8000..."
  cd "$ROOT_DIR"

  if ! curl -sf http://localhost:8000/api/v1/health > /dev/null 2>&1; then
    log_warn "API not running at http://localhost:8000 — skipping ZAP"
    log_warn "Start the API first with: docker compose -f infra/docker-compose.yml up -d api"
    record_warn
    return
  fi

  if ! docker compose -f infra/docker-compose.yml --profile security run --rm zap-scan 2>&1 | tee "$REPORT_DIR/zap-console.log"; then
    log_fail "ZAP scan reported FAIL-level findings"
    record_fail
  fi

  if [ -f "$REPORT_DIR/zap-report.html" ]; then
    log_pass "ZAP report saved: $REPORT_DIR/zap-report.html"
  fi
}

# ---------------------------------------------------------------------------
# 5. Trivy — Docker image vulnerability scan (optional)
# ---------------------------------------------------------------------------
run_trivy() {
  log_info "Running Trivy (Docker image scan)..."
  if ! command -v trivy &> /dev/null; then
    log_warn "trivy not installed — install from https://trivy.dev"
    record_warn
    return
  fi

  cd "$ROOT_DIR"
  local report="$REPORT_DIR/trivy-report.txt"

  # Scan the API image (must be built first)
  if ! docker image inspect krishisetu-api:latest &> /dev/null; then
    log_warn "krishisetu-api:latest image not built — skipping Trivy"
    record_warn
    return
  fi

  if trivy image --severity HIGH,CRITICAL --exit-code 1 krishisetu-api:latest 2>&1 | tee "$report"; then
    log_pass "Trivy: no HIGH/CRITICAL vulnerabilities in API image"
  else
    log_fail "Trivy: HIGH/CRITICAL vulnerabilities found (see $report)"
    record_fail
  fi
}

# ---------------------------------------------------------------------------
# Run scanners
# ---------------------------------------------------------------------------

if [ "$ZAP_ONLY" = true ]; then
  run_zap
else
  run_bandit
  run_pip_audit
  run_npm_audit
  if [ "$QUICK" != true ]; then
    run_zap
    run_trivy
  fi
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "=========================================="
echo "         Security Scan Summary            "
echo "=========================================="
if [ $OVERALL_EXIT -eq 0 ]; then
  log_pass "All scanners passed (warnings may be present)"
else
  log_fail "One or more scanners reported failures"
fi
echo ""
echo "Reports saved to: $REPORT_DIR/"
ls -la "$REPORT_DIR/" 2>/dev/null || true
echo "=========================================="

exit $OVERALL_EXIT
