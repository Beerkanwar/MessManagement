"""
WCAG 2.1 Contrast Checker for Design Tokens.
Validates the contrast ratios of token pairs specified in ImplementationGuide Phase 14:
- primary (#0F766E) with white text >= 4.5:1 (Guide note: 5.5:1)
- text (#0F172A) on white (#FFFFFF) >= 4.5:1 (Guide note: 17:1)
- text-secondary (#475569) on white >= 4.5:1 (Guide note: 7.5:1)
- text-muted (#64748B) on white >= 4.5:1 (Guide note: 4.8:1)
- success (#15803D) with white text >= 4.5:1 (Guide note: 5.0:1)
- warning (#B45309) with white text >= 4.5:1 (Guide note: 5.0:1)
- danger (#B91C1C) with white text >= 4.5:1 (Guide note: 6.5:1)
- info (#1D4ED8) with white text >= 4.5:1 (Guide note: 6.7:1)
- neutral-state (#475569) with white text >= 4.5:1 (Guide note: 7.6:1)
- time-invalid (#1E293B) with white text >= 4.5:1
"""
import json
import sys
from pathlib import Path


def hex_to_rgb(hex_str: str) -> tuple[float, float, float]:
    hex_clean = hex_str.lstrip("#")
    r = int(hex_clean[0:2], 16) / 255.0
    g = int(hex_clean[2:4], 16) / 255.0
    b = int(hex_clean[4:6], 16) / 255.0
    return r, g, b


def channel_luminance(c: float) -> float:
    if c <= 0.04045:
        return c / 12.92
    return ((c + 0.055) / 1.055) ** 2.4


def relative_luminance(hex_str: str) -> float:
    r, g, b = hex_to_rgb(hex_str)
    return (
        0.2126 * channel_luminance(r)
        + 0.7152 * channel_luminance(g)
        + 0.0722 * channel_luminance(b)
    )


def contrast_ratio(hex1: str, hex2: str) -> float:
    l1 = relative_luminance(hex1)
    l2 = relative_luminance(hex2)
    lighter = max(l1, l2)
    darker = min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def run_checks(tokens_path: Path) -> bool:
    with open(tokens_path, "r", encoding="utf-8") as f:
        tokens = json.load(f)

    colors = tokens["colors"]
    scanner = tokens["scannerResults"]

    # Target minimum ratios based on WCAG AA normal text (4.5:1)
    checks = [
        ("White on Primary", "#FFFFFF", colors["primary"], 4.5, 5.5),
        ("Text on White Surface", colors["text"], "#FFFFFF", 4.5, 17.0),
        ("Text Secondary on White", colors["textSecondary"], "#FFFFFF", 4.5, 7.5),
        ("Text Muted on White", colors["textMuted"], "#FFFFFF", 4.5, 4.8),
        ("White on Success", "#FFFFFF", colors["success"], 4.5, 5.0),
        ("White on Warning", "#FFFFFF", colors["warning"], 4.5, 5.0),
        ("White on Danger", "#FFFFFF", colors["danger"], 4.5, 6.5),
        ("White on Info", "#FFFFFF", colors["info"], 4.5, 6.7),
        ("White on Neutral-State", "#FFFFFF", colors["neutralState"], 4.5, 7.6),
        ("White on Time Invalid", "#FFFFFF", scanner["TIME_INVALID"]["bg"], 4.5, 13.0),
    ]

    all_passed = True
    print("=" * 70)
    print("DESIGN SYSTEM CONTRAST RATIO AUDIT (WCAG 2.1 AA)")
    print("=" * 70)
    print(f"{'Pair Name':<28} | {'Colors':<17} | {'Ratio':<7} | {'Min Req':<7} | {'Status'}")
    print("-" * 70)

    for name, c1, c2, min_req, guide_approx in checks:
        ratio = contrast_ratio(c1, c2)
        passed = ratio >= min_req
        status = "PASS" if passed else "FAIL"
        if not passed:
            all_passed = False
        print(f"{name:<28} | {c1} / {c2:<7} | {ratio:5.2f}:1 | {min_req:4.1f}:1  | {status}")

    print("=" * 70)
    if all_passed:
        print("[SUCCESS] All design system token contrast pairs meet or exceed WCAG AA requirements.")
    else:
        print("[FAILURE] One or more token pairs failed WCAG AA requirements.")
    return all_passed


if __name__ == "__main__":
    repo_root = Path(__file__).resolve().parent.parent
    tokens_file = repo_root / "docs" / "design" / "tokens.json"
    success = run_checks(tokens_file)
    sys.exit(0 if success else 1)
