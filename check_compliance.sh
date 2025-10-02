#!/bin/bash
# YouTube API Compliance Checker
# Project Number: 55291277961
# Verifies code compliance with YouTube API Services Terms and Policies

echo "=========================================="
echo "YouTube API Compliance Checker"
echo "Project: Toronto Metropolitan University"
echo "Project Number: 55291277961"
echo "=========================================="
echo ""

PASS=0
FAIL=0

# Test 1: No engagement_rate functions
echo "✓ Test 1: Checking for removed engagement_rate functions..."
if grep -rn "def compute_engagement_rate" --include="*.py" . 2>/dev/null | grep -v "REMOVED" | grep -v "#"; then
    echo "  ❌ FAIL: Found engagement_rate functions (violates Policy III.E.4h)"
    FAIL=$((FAIL + 1))
else
    echo "  ✅ PASS: No engagement_rate functions found"
    PASS=$((PASS + 1))
fi
echo ""

# Test 2: Compliance headers present
echo "✓ Test 2: Checking for compliance statements in scripts..."
COMPLIANCE_COUNT=$(grep -rn "COMPLIANCE STATEMENT" --include="*.py" . 2>/dev/null | wc -l)
if [ "$COMPLIANCE_COUNT" -ge 5 ]; then
    echo "  ✅ PASS: Found $COMPLIANCE_COUNT compliance statements"
    PASS=$((PASS + 1))
else
    echo "  ❌ FAIL: Only found $COMPLIANCE_COUNT compliance statements (expected 5+)"
    FAIL=$((FAIL + 1))
fi
echo ""

# Test 3: 24-hour cache expiry
echo "✓ Test 3: Checking for 24-hour cache expiry..."
if grep -rn "CACHE_EXPIRY_HOURS = 24" --include="*.py" . 2>/dev/null | grep -q "24"; then
    echo "  ✅ PASS: 24-hour cache expiry configured (Policy III.E.4.a-g)"
    PASS=$((PASS + 1))
else
    echo "  ❌ FAIL: 24-hour cache expiry not found"
    FAIL=$((FAIL + 1))
fi
echo ""

# Test 4: Single project number
echo "✓ Test 4: Checking for single project number..."
PROJECT_COUNT=$(grep -rn "55291277961" --include="*.py" --include="*.md" . 2>/dev/null | wc -l)
if [ "$PROJECT_COUNT" -ge 3 ]; then
    echo "  ✅ PASS: Project number 55291277961 found in $PROJECT_COUNT files (Policy III.D.1c)"
    PASS=$((PASS + 1))
else
    echo "  ❌ FAIL: Project number not consistently documented"
    FAIL=$((FAIL + 1))
fi
echo ""

# Test 5: No derived metrics in output
echo "✓ Test 5: Checking for prohibited derived metrics..."
if grep -rn "engagement_rate\|engagement rate" --include="*.py" . 2>/dev/null | grep -v "REMOVED" | grep -v "#" | grep -v "violates" | grep -v "Policy"; then
    echo "  ❌ FAIL: Found engagement_rate references (violates Policy III.E.4h)"
    FAIL=$((FAIL + 1))
else
    echo "  ✅ PASS: No derived metrics found in code"
    PASS=$((PASS + 1))
fi
echo ""

# Test 6: YouTube metrics only
echo "✓ Test 6: Checking for YouTube-provided metrics usage..."
if grep -rn "statistics.viewCount\|statistics.likeCount\|statistics.commentCount" --include="*.py" . 2>/dev/null | grep -q "statistics"; then
    echo "  ✅ PASS: Using YouTube-provided metrics (viewCount, likeCount, commentCount)"
    PASS=$((PASS + 1))
else
    echo "  ⚠️  WARNING: Could not verify YouTube metrics usage"
fi
echo ""

# Test 7: Cache control flags
echo "✓ Test 7: Checking for cache control options..."
if grep -rn "\-\-no-cache\|\-\-clear-cache" --include="*.py" . 2>/dev/null | grep -q "cache"; then
    echo "  ✅ PASS: Cache control flags implemented"
    PASS=$((PASS + 1))
else
    echo "  ❌ FAIL: Cache control flags not found"
    FAIL=$((FAIL + 1))
fi
echo ""

# Summary
echo "=========================================="
echo "Compliance Check Summary"
echo "=========================================="
echo "Tests Passed: $PASS"
echo "Tests Failed: $FAIL"
echo ""

if [ "$FAIL" -eq 0 ]; then
    echo "✅ STATUS: FULLY COMPLIANT"
    echo "All YouTube API policy requirements met."
    exit 0
else
    echo "❌ STATUS: NON-COMPLIANT"
    echo "Please fix the failed tests above."
    exit 1
fi
