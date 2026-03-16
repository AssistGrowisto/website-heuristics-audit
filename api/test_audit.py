#!/usr/bin/env python3
"""
Quick test script to verify audit engine functionality.
"""

from auditor import WebsiteAuditor
from excel_generator import AuditExcelGenerator
import json

def test_audit():
    """Test the audit engine with a sample URL."""
    print("Website Audit Engine - Test Script")
    print("=" * 50)
    print()

    # Test URL (using a well-known site)
    test_url = "https://example.com"
    print(f"Testing audit with: {test_url}")
    print()

    # Create auditor
    auditor = WebsiteAuditor(timeout=30)

    # Run audit
    print("Running audit...")
    results = auditor.run_full_audit(test_url)

    # Print summary
    print(f"\nAudit Results Summary:")
    print(f"  URL: {results['url']}")
    print(f"  Status: {results['status_code']}")
    print(f"  Timestamp: {results['timestamp']}")
    print(f"  Error: {results['error']}")
    print()

    # Print finding counts
    print("Finding Counts:")
    print(f"  SEO: {len(results['seo'])} checks")
    print(f"  Core Web Vitals: {len(results['cwv'])} checks")
    print(f"  UX & Usability: {len(results['ux'])} checks")
    print(f"  Conversion: {len(results['conversion'])} checks")
    print()

    # Show sample findings
    if results['seo']:
        print("Sample SEO Findings (first 3):")
        for finding in results['seo'][:3]:
            print(f"  - {finding['parameter']}: {finding['evaluation']} ({finding['score']}/{finding['max_score']})")
        print()

    # Test Excel generation
    print("Generating Excel report...")
    try:
        generator = AuditExcelGenerator(results)
        excel_bytes = generator.generate()
        print(f"Excel file generated successfully: {len(excel_bytes)} bytes")

        # Save for inspection
        with open('/sessions/gifted-compassionate-bardeen/website-heuristics-audit/test_audit_report.xlsx', 'wb') as f:
            f.write(excel_bytes)
        print("Sample Excel file saved to: test_audit_report.xlsx")
    except Exception as e:
        print(f"Error generating Excel: {e}")
        return False

    print()
    print("=" * 50)
    print("Test completed successfully!")
    return True

if __name__ == "__main__":
    test_audit()

