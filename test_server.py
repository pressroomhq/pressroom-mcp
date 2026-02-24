"""Test script for Pressroom MCP Server.

Tests each MCP tool against a running Pressroom backend.
Start the backend first: cd pressroomhq && python -m uvicorn main:app

Usage:
    python test_server.py
"""

import asyncio
import json
import sys

# Test against the server module directly (not via MCP transport)
sys.path.insert(0, ".")
from server import (
    # Org tools
    pressroom_list_orgs,
    pressroom_get_org,
    # Core pipeline
    pressroom_scout,
    pressroom_generate,
    pressroom_approve,
    pressroom_publish,
    pressroom_full_pipeline,
    # Content tools
    pressroom_list_content,
    pressroom_get_content,
    pressroom_spike_content,
    pressroom_edit_content,
    pressroom_humanize_content,
    pressroom_schedule_content,
    # Signal tools
    pressroom_list_signals,
    # Story tools
    pressroom_list_stories,
    pressroom_create_story,
    pressroom_get_story,
    pressroom_add_signal_to_story,
    pressroom_generate_from_story,
    pressroom_discover_signals,
    # Wire tools
    pressroom_list_wire_sources,
    pressroom_create_wire_source,
    pressroom_fetch_wire,
    pressroom_list_wire_signals,
    # SIGINT source tools
    pressroom_list_sources,
    pressroom_create_source,
    pressroom_sweep_sources,
    pressroom_get_feed,
    # Settings tools
    pressroom_get_settings,
    pressroom_update_settings,
    pressroom_connection_status,
    # Audit tools
    pressroom_audit,
    pressroom_scoreboard,
    pressroom_audit_history,
    # SEO PR tools
    pressroom_seo_pr_run,
    pressroom_seo_pr_list,
    pressroom_seo_pr_status,
    # Competitive tools
    pressroom_competitive_scan,
    pressroom_competitive_results,
    # AI visibility tools
    pressroom_ai_visibility_scan,
    pressroom_ai_visibility_results,
    pressroom_ai_visibility_questions,
    # Analytics
    pressroom_analytics,
    # Onboarding
    pressroom_onboard,
    pressroom_onboard_apply,
    pressroom_onboard_status,
    # Team tools
    pressroom_list_team,
    pressroom_add_team_member,
    pressroom_discover_team,
    # Email tools
    pressroom_compose_email,
    pressroom_list_email_drafts,
    # YouTube tools
    pressroom_youtube_script,
    pressroom_youtube_list,
    pressroom_youtube_export,
    # Skills tools
    pressroom_list_skills,
    pressroom_get_skill,
    pressroom_invoke_skill,
)


PASS = 0
FAIL = 0


async def test(name: str, coro, expect_error=False):
    global PASS, FAIL
    try:
        result = await coro
        if expect_error:
            print(f"  FAIL  {name} — expected error but got result")
            FAIL += 1
        else:
            preview = str(result)[:120].replace("\n", " ")
            print(f"  PASS  {name} — {preview}")
            PASS += 1
        return result
    except Exception as e:
        if expect_error:
            print(f"  PASS  {name} — got expected error: {e}")
            PASS += 1
        else:
            print(f"  FAIL  {name} — {e}")
            FAIL += 1
        return None


async def main():
    global PASS, FAIL
    print("=" * 60)
    print("Pressroom MCP Server — Test Suite")
    print("=" * 60)
    print()

    # 1. Org tools
    print("--- Org tools ---")
    orgs_result = await test("list_orgs", pressroom_list_orgs())
    orgs = json.loads(orgs_result) if orgs_result else []
    org_id = orgs[0]["id"] if orgs else None

    if org_id:
        await test("get_org", pressroom_get_org(org_id))
    else:
        print("  SKIP  get_org — no orgs found")

    print()

    # 2. Signal tools
    print("--- Signal tools ---")
    if org_id:
        await test("list_signals", pressroom_list_signals(org_id, limit=5))
    else:
        print("  SKIP  list_signals — no orgs")

    print()

    # 3. Content tools
    print("--- Content tools ---")
    if org_id:
        await test("list_content (queued)", pressroom_list_content(org_id, status="queued", limit=5))
        await test("list_content (all)", pressroom_list_content(org_id, status="", limit=5))
    else:
        print("  SKIP  content tools — no orgs")

    print()

    # 4. Story tools
    print("--- Story tools ---")
    if org_id:
        await test("list_stories", pressroom_list_stories(org_id))
    else:
        print("  SKIP  story tools — no orgs")

    print()

    # 5. Wire tools
    print("--- Wire tools ---")
    if org_id:
        await test("list_wire_sources", pressroom_list_wire_sources(org_id))
        await test("list_wire_signals", pressroom_list_wire_signals(org_id, limit=5))
    else:
        print("  SKIP  wire tools — no orgs")

    print()

    # 6. SIGINT source tools
    print("--- SIGINT source tools ---")
    await test("list_sources", pressroom_list_sources())
    if org_id:
        await test("get_feed", pressroom_get_feed(org_id, limit=5))
    else:
        print("  SKIP  get_feed — no orgs")

    print()

    # 7. Settings tools
    print("--- Settings tools ---")
    if org_id:
        await test("get_settings", pressroom_get_settings(org_id))
        await test("connection_status", pressroom_connection_status(org_id))
    else:
        print("  SKIP  settings tools — no orgs")

    print()

    # 8. Audit tools
    print("--- Audit tools ---")
    await test("scoreboard", pressroom_scoreboard())
    if org_id:
        await test("audit_history", pressroom_audit_history(org_id))
    else:
        print("  SKIP  audit_history — no orgs")

    print()

    # 9. SEO PR tools
    print("--- SEO PR tools ---")
    if org_id:
        await test("seo_pr_list", pressroom_seo_pr_list(org_id))
    else:
        print("  SKIP  seo_pr tools — no orgs")

    print()

    # 10. Competitive tools
    print("--- Competitive tools ---")
    if org_id:
        await test("competitive_results", pressroom_competitive_results(org_id))
    else:
        print("  SKIP  competitive tools — no orgs")

    print()

    # 11. AI visibility tools
    print("--- AI visibility tools ---")
    if org_id:
        await test("ai_visibility_results", pressroom_ai_visibility_results(org_id))
    else:
        print("  SKIP  ai_visibility tools — no orgs")

    print()

    # 12. Analytics tools
    print("--- Analytics tools ---")
    if org_id:
        await test("analytics", pressroom_analytics(org_id))
    else:
        print("  SKIP  analytics — no orgs")

    print()

    # 13. Onboarding tools
    print("--- Onboarding tools ---")
    if org_id:
        await test("onboard_status", pressroom_onboard_status(org_id))
    else:
        print("  SKIP  onboarding tools — no orgs")

    print()

    # 14. Team tools
    print("--- Team tools ---")
    if org_id:
        await test("list_team", pressroom_list_team(org_id))
    else:
        print("  SKIP  team tools — no orgs")

    print()

    # 15. Email tools
    print("--- Email tools ---")
    if org_id:
        await test("list_email_drafts", pressroom_list_email_drafts(org_id))
    else:
        print("  SKIP  email tools — no orgs")

    print()

    # 16. YouTube tools
    print("--- YouTube tools ---")
    if org_id:
        await test("youtube_list", pressroom_youtube_list(org_id))
    else:
        print("  SKIP  youtube tools — no orgs")

    print()

    # 17. Skills tools
    print("--- Skills tools ---")
    await test("list_skills", pressroom_list_skills())
    await test("get_skill (humanizer)", pressroom_get_skill("humanizer"))
    await test("get_skill (nonexistent)", pressroom_get_skill("nonexistent_xyz"))

    print()

    # Summary
    print("=" * 60)
    print(f"Results: {PASS} passed, {FAIL} failed")
    total = PASS + FAIL
    print(f"Tools tested: {total} (of ~55 total tools)")
    print("=" * 60)

    if FAIL > 0:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
