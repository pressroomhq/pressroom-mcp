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
    pressroom_list_orgs,
    pressroom_get_org,
    pressroom_scout,
    pressroom_generate,
    pressroom_approve,
    pressroom_publish,
    pressroom_full_pipeline,
    pressroom_list_content,
    pressroom_get_content,
    pressroom_audit,
    pressroom_scoreboard,
    pressroom_audit_history,
    pressroom_youtube_script,
    pressroom_youtube_list,
    pressroom_youtube_export,
    pressroom_list_skills,
    pressroom_get_skill,
    pressroom_invoke_skill,
    pressroom_list_signals,
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
        content_result = await test("list_content (queued)", pressroom_list_content(org_id, status="queued", limit=5))
        await test("list_content (all)", pressroom_list_content(org_id, status="", limit=5))
    else:
        print("  SKIP  content tools — no orgs")

    print()

    # 4. Audit tools
    print("--- Audit tools ---")
    await test("scoreboard", pressroom_scoreboard())
    if org_id:
        await test("audit_history", pressroom_audit_history(org_id))
    else:
        print("  SKIP  audit_history — no orgs")

    print()

    # 5. YouTube tools
    print("--- YouTube tools ---")
    if org_id:
        await test("youtube_list", pressroom_youtube_list(org_id))
    else:
        print("  SKIP  youtube tools — no orgs")

    print()

    # 6. Skills tools
    print("--- Skills tools ---")
    await test("list_skills", pressroom_list_skills())
    await test("get_skill (humanizer)", pressroom_get_skill("humanizer"))
    await test("get_skill (nonexistent)", pressroom_get_skill("nonexistent_xyz"))

    print()

    # Summary
    print("=" * 60)
    print(f"Results: {PASS} passed, {FAIL} failed")
    print("=" * 60)

    if FAIL > 0:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
