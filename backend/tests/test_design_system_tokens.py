"""
Test suite for Phase 14: Design System Tokens, Contrast Ratios, and Web/Mobile Synchronization.
Verifies:
- All required tokens defined in ImplementationGuide Phase 14
- WCAG 2.1 AA contrast ratio compliance for all token pairs
- Synchronization between docs/design/tokens.json and web/mobile codebases
- Status mapping for all seven specified domains
"""
import json
import sys
from pathlib import Path
import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.check_contrast import run_checks, contrast_ratio


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
TOKENS_JSON = REPO_ROOT / "docs" / "design" / "tokens.json"
WEB_TOKENS = REPO_ROOT / "apps" / "web" / "src" / "design" / "tokens.ts"
MOBILE_TOKENS = REPO_ROOT / "apps" / "mobile" / "src" / "design" / "tokens.ts"


@pytest.fixture(scope="module")
def tokens_data():
    assert TOKENS_JSON.exists(), f"tokens.json missing at {TOKENS_JSON}"
    with open(TOKENS_JSON, "r", encoding="utf-8") as f:
        return json.load(f)


def test_required_color_tokens(tokens_data):
    colors = tokens_data["colors"]
    expected = {
        "primary": "#0F766E",
        "primaryHover": "#115E59",
        "primarySubtle": "#F0FDFA",
        "primaryBorder": "#99F6E4",
        "text": "#0F172A",
        "textSecondary": "#475569",
        "textMuted": "#64748B",
        "bg": "#F8FAFC",
        "surface": "#FFFFFF",
        "border": "#E2E8F0",
        "borderStrong": "#CBD5E1",
        "success": "#15803D",
        "successSubtle": "#F0FDF4",
        "warning": "#B45309",
        "warningSubtle": "#FFFBEB",
        "danger": "#B91C1C",
        "dangerSubtle": "#FEF2F2",
        "info": "#1D4ED8",
        "infoSubtle": "#EFF6FF",
        "neutralState": "#475569",
    }
    for k, v in expected.items():
        assert colors.get(k) == v, f"Color token {k} expected {v}, got {colors.get(k)}"


def test_scanner_result_colors(tokens_data):
    results = tokens_data["scannerResults"]
    assert results["SUCCESS"]["bg"] == "#15803D"
    assert results["DUPLICATE"]["bg"] == "#B45309"
    assert results["INVALID_CODE"]["bg"] == "#B91C1C"
    assert results["UNKNOWN_ROLL"]["bg"] == "#B91C1C"
    assert results["SUCCESS_PAUSE_NOTICE"]["bg"] == "#15803D"
    assert results["TIME_INVALID"]["bg"] == "#1E293B"


def test_all_status_mappings(tokens_data):
    mapping = tokens_data["statusMapping"]
    # 1. Sync transaction
    assert mapping["syncTransaction"]["PENDING"] == "neutral"
    assert mapping["syncTransaction"]["SENDING"] == "info"
    assert mapping["syncTransaction"]["SYNCHRONIZED"] == "success"
    assert mapping["syncTransaction"]["CONFLICT"] == "warning"
    assert mapping["syncTransaction"]["REJECTED"] == "danger"

    # 2. Manager authorization
    assert mapping["managerAuthorization"]["ACTIVE"] == "success"
    assert mapping["managerAuthorization"]["OFFLINE_NORMAL"] == "info"
    assert mapping["managerAuthorization"]["OFFLINE_GRACE"] == "warning"
    assert mapping["managerAuthorization"]["SYNC_REQUIRED"] == "danger"
    assert mapping["managerAuthorization"]["REVOKE_PENDING_SYNC"] == "warning"
    assert mapping["managerAuthorization"]["REVOKED"] == "danger"

    # 3. Trusted time
    assert mapping["trustedTime"]["VALID"] == "success"
    assert mapping["trustedTime"]["EXPIRING"] == "warning"
    assert mapping["trustedTime"]["EXPIRED"] == "danger"
    assert mapping["trustedTime"]["REQUIRES_SYNC"] == "danger"
    assert mapping["trustedTime"]["INVALID_AFTER_REBOOT"] == "danger"

    # 4. Pause
    assert mapping["pause"]["SCHEDULED"] == "info"
    assert mapping["pause"]["ACTIVE"] == "warning"
    assert mapping["pause"]["COMPLETED"] == "neutral"
    assert mapping["pause"]["CANCELLED"] == "neutral"

    # 5. Billing period
    assert mapping["billingPeriod"]["OPEN"] == "neutral"
    assert mapping["billingPeriod"]["BILL_GENERATED"] == "info"
    assert mapping["billingPeriod"]["REVIEWED"] == "warning"
    assert mapping["billingPeriod"]["LOCKED"] == "success"

    # 6. Menu
    assert mapping["menu"]["DRAFT"] == "neutral"
    assert mapping["menu"]["PUBLISHED"] == "success"

    # 7. Assignment
    assert mapping["assignment"]["PENDING_VERIFICATION"] == "warning"
    assert mapping["assignment"]["ACTIVE"] == "success"
    assert mapping["assignment"]["ENDED"] == "neutral"
    assert mapping["assignment"]["REJECTED"] == "danger"


def test_wcag_contrast_ratios(tokens_data):
    passed = run_checks(TOKENS_JSON)
    assert passed is True, "WCAG contrast ratio audit must pass for all token pairs."


def test_tokens_web_mobile_sync():
    assert WEB_TOKENS.exists(), f"Web tokens file {WEB_TOKENS} missing"
    assert MOBILE_TOKENS.exists(), f"Mobile tokens file {MOBILE_TOKENS} missing"

    web_content = WEB_TOKENS.read_text(encoding="utf-8")
    mobile_content = MOBILE_TOKENS.read_text(encoding="utf-8")

    assert "#0F766E" in web_content
    assert "#0F766E" in mobile_content
    assert "scannerResults" in web_content
    assert "scannerResults" in mobile_content
    assert "statusMapping" in web_content
    assert "statusMapping" in mobile_content
