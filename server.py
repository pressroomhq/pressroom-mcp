"""Pressroom MCP Server — run the full Pressroom pipeline headless.

Exposes the entire Pressroom pipeline as MCP tools. Any Claude Code session
or MCP-compatible client can scout, generate, audit, publish, and more —
no browser, no UI.
"""

import json
import os
from typing import Any

import httpx
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

load_dotenv()

PRESSROOM_URL = os.getenv("PRESSROOM_URL", "http://localhost:8000")

mcp = FastMCP("pressroom")

# Shared HTTP client
_client: httpx.AsyncClient | None = None


async def client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(base_url=PRESSROOM_URL, timeout=120.0)
    return _client


def org_headers(org_id: int | None = None) -> dict[str, str]:
    """Build headers with optional org context."""
    h: dict[str, str] = {"Content-Type": "application/json"}
    if org_id is not None:
        h["X-Org-Id"] = str(org_id)
    return h


def _handle_response(r: httpx.Response) -> Any:
    """Handle HTTP response, returning error dict for non-2xx status codes."""
    if r.status_code >= 400:
        try:
            data = r.json()
            if isinstance(data, dict) and "error" in data:
                return data
        except Exception:
            pass
        return {"error": f"HTTP {r.status_code}: {r.text[:200]}"}
    return r.json()


async def api_get(path: str, org_id: int | None = None, params: dict | None = None) -> Any:
    """GET request to Pressroom API."""
    c = await client()
    r = await c.get(path, headers=org_headers(org_id), params=params or {})
    return _handle_response(r)


async def api_post(path: str, org_id: int | None = None, body: dict | None = None, params: dict | None = None) -> Any:
    """POST request to Pressroom API."""
    c = await client()
    r = await c.post(path, headers=org_headers(org_id), json=body or {}, params=params or {})
    return _handle_response(r)


async def api_put(path: str, org_id: int | None = None, body: dict | None = None) -> Any:
    """PUT request to Pressroom API."""
    c = await client()
    r = await c.put(path, headers=org_headers(org_id), json=body or {})
    return _handle_response(r)


async def api_delete(path: str, org_id: int | None = None) -> Any:
    """DELETE request to Pressroom API."""
    c = await client()
    r = await c.delete(path, headers=org_headers(org_id))
    return _handle_response(r)


def _check_error(data: Any) -> str | None:
    """If data is an error dict, return the error message. Otherwise None."""
    if isinstance(data, dict) and "error" in data:
        return f"Error: {data['error']}"
    return None


# ─── Org tools ────────────────────────────────────────────────────────────────

@mcp.tool()
async def pressroom_list_orgs() -> str:
    """List all organizations in Pressroom. Returns org id, name, and domain for each."""
    data = await api_get("/api/orgs")
    return json.dumps(data, indent=2)


@mcp.tool()
async def pressroom_get_org(org_id: int) -> str:
    """Get details for a specific organization including settings and team members.

    Args:
        org_id: The organization ID.
    """
    data = await api_get(f"/api/orgs/{org_id}")
    return json.dumps(data, indent=2)


# ─── Core pipeline tools ─────────────────────────────────────────────────────

@mcp.tool()
async def pressroom_scout(org_id: int, since_hours: int = 24) -> str:
    """Run the scout pipeline — pull signals from GitHub, HN, Reddit, RSS and other configured sources.

    Args:
        org_id: The organization ID to scout for.
        since_hours: How far back to look for signals (default 24 hours).
    """
    data = await api_post(
        "/api/pipeline/scout",
        org_id=org_id,
        params={"since_hours": since_hours},
    )
    if "error" in data:
        return f"Error: {data['error']}"
    return (
        f"Scout complete. "
        f"Raw: {data.get('signals_raw', 0)}, "
        f"Relevant: {data.get('signals_relevant', 0)}, "
        f"Saved: {data.get('signals_saved', 0)}, "
        f"Dupes skipped: {data.get('signals_skipped_dupes', 0)}.\n\n"
        f"Signals:\n" +
        "\n".join(f"  [{s.get('type', '?')}] {s.get('source', '')}: {s.get('title', '')}" for s in data.get("signals", []))
    )


@mcp.tool()
async def pressroom_generate(org_id: int, channels: list[str] | None = None) -> str:
    """Generate content from current signals. Runs brief -> content -> humanizer pipeline.

    Args:
        org_id: The organization ID.
        channels: Optional list of channels (e.g. ["linkedin", "blog", "x_thread"]). If empty, uses org defaults.
    """
    body: dict[str, Any] = {}
    if channels:
        body["channels"] = channels
    data = await api_post("/api/pipeline/generate", org_id=org_id, body=body)
    if "error" in data:
        return f"Error: {data['error']}"
    items = data.get("items", [])
    return (
        f"Generated {len(items)} content items.\n\n" +
        "\n".join(f"  [{i.get('channel', '?')}] {i.get('headline', '')}" for i in items)
    )


@mcp.tool()
async def pressroom_approve(org_id: int, content_ids: list[int]) -> str:
    """Approve content items, moving them from queued to approved status.

    Args:
        org_id: The organization ID.
        content_ids: List of content IDs to approve.
    """
    results = []
    for cid in content_ids:
        data = await api_post(
            f"/api/content/{cid}/action",
            org_id=org_id,
            body={"action": "approve"},
        )
        results.append(f"  #{cid}: {'approved' if 'error' not in data else data['error']}")
    return f"Approved {len(content_ids)} items:\n" + "\n".join(results)


@mcp.tool()
async def pressroom_publish(org_id: int) -> str:
    """Publish all approved content to their destinations (LinkedIn, X, blog, etc).

    Args:
        org_id: The organization ID.
    """
    data = await api_post("/api/publish", org_id=org_id)
    return (
        f"Published: {data.get('published', 0)}, Errors: {data.get('errors', 0)}\n\n" +
        "\n".join(
            f"  [{r.get('channel', '?')}] {'sent' if 'error' not in r else 'FAILED: ' + r.get('error', '')}"
            for r in data.get("results", [])
        )
    )


@mcp.tool()
async def pressroom_full_pipeline(org_id: int, channels: list[str] | None = None) -> str:
    """Run the full pipeline: scout -> generate. Does NOT auto-approve — returns content for review.

    Args:
        org_id: The organization ID.
        channels: Optional list of channels to generate for.
    """
    # Step 1: Scout
    scout_data = await api_post("/api/pipeline/scout", org_id=org_id)
    scout_summary = f"Scout: {scout_data.get('signals_saved', 0)} new signals"
    if "error" in scout_data:
        return f"Scout failed: {scout_data['error']}"

    # Step 2: Generate
    body: dict[str, Any] = {}
    if channels:
        body["channels"] = channels
    gen_data = await api_post("/api/pipeline/generate", org_id=org_id, body=body)
    if "error" in gen_data:
        return f"{scout_summary}\nGenerate failed: {gen_data['error']}"

    items = gen_data.get("items", [])
    gen_summary = f"Generate: {len(items)} content items"

    content_list = "\n".join(
        f"  [{i.get('channel', '?')}] #{i.get('id', '?')} — {i.get('headline', '')}"
        for i in items
    )

    return (
        f"Pipeline complete.\n{scout_summary}\n{gen_summary}\n\n"
        f"Content awaiting approval:\n{content_list}\n\n"
        f"Use pressroom_approve() to approve items, then pressroom_publish() to send them."
    )


# ─── Content tools ────────────────────────────────────────────────────────────

@mcp.tool()
async def pressroom_list_content(org_id: int, status: str = "queued", limit: int = 50) -> str:
    """List content items for an org, optionally filtered by status.

    Args:
        org_id: The organization ID.
        status: Filter by status: "queued", "approved", "published", "spiked", or leave empty for all.
        limit: Max number of items to return (default 50).
    """
    params: dict[str, Any] = {"limit": limit}
    if status:
        params["status"] = status
    data = await api_get("/api/content", org_id=org_id, params=params)
    if err := _check_error(data):
        return err
    if not data:
        return f"No content found with status '{status}'."
    items = []
    for c in data:
        preview = (c.get("body", "") or "")[:200]
        items.append(
            f"  #{c.get('id', '?')} [{c.get('channel', '?')}] {c.get('status', '?')} — {c.get('headline', '')}\n"
            f"    {preview}{'...' if len(c.get('body', '')) > 200 else ''}"
        )
    return f"{len(data)} items:\n" + "\n".join(items)


@mcp.tool()
async def pressroom_get_content(content_id: int) -> str:
    """Get the full content item including body text.

    Args:
        content_id: The content item ID.
    """
    data = await api_get(f"/api/content/{content_id}")
    return json.dumps(data, indent=2)


# ─── Audit tools ──────────────────────────────────────────────────────────────

@mcp.tool()
async def pressroom_audit(org_id: int, domain: str = "", deep: bool = True) -> str:
    """Run an SEO audit on a domain. If domain is empty, uses the org's configured domain.

    Args:
        org_id: The organization ID.
        domain: Domain to audit (e.g. "example.com"). Leave empty to use org default.
        deep: If True, runs deep Claude-powered analysis. If False, basic checks only.
    """
    data = await api_post(
        "/api/audit/seo",
        org_id=org_id,
        body={"domain": domain},
        params={"deep": str(deep).lower()},
    )
    if "error" in data:
        return f"Audit error: {data['error']}"
    score = data.get("score", data.get("recommendations", {}).get("score", "?"))
    issues = data.get("total_issues", data.get("recommendations", {}).get("total_issues", 0))
    return f"SEO Audit complete. Score: {score}, Issues: {issues}\n\n{json.dumps(data, indent=2, default=str)}"


@mcp.tool()
async def pressroom_scoreboard() -> str:
    """Get the scoreboard — all orgs ranked by SEO score and content activity."""
    data = await api_get("/api/scoreboard")
    if err := _check_error(data):
        return err
    rows = []
    for org in data:
        rows.append(
            f"  {org.get('org_name', '?')} ({org.get('domain', '?')}) — "
            f"SEO: {org.get('seo_score', '—')}, "
            f"AI citable: {org.get('ai_citability', '?')}, "
            f"Signals 7d: {org.get('signals_count', 0)}, "
            f"Published: {org.get('content_published', 0)}, "
            f"Last active: {org.get('last_active', '—')}"
        )
    return f"Scoreboard ({len(data)} orgs):\n" + "\n".join(rows)


@mcp.tool()
async def pressroom_audit_history(org_id: int, audit_type: str = "", limit: int = 20) -> str:
    """Get audit history for an org — past SEO and README audit results.

    Args:
        org_id: The organization ID.
        audit_type: Optional filter: "seo" or "readme".
        limit: Max results to return.
    """
    params: dict[str, Any] = {"limit": limit}
    if audit_type:
        params["audit_type"] = audit_type
    data = await api_get("/api/audit/history", org_id=org_id, params=params)
    if err := _check_error(data):
        return err
    if not data:
        return "No audit history found."
    rows = []
    for a in data:
        rows.append(
            f"  #{a.get('id', '?')} [{a.get('audit_type', '?')}] {a.get('target', '?')} — "
            f"Score: {a.get('score', '?')}, Issues: {a.get('total_issues', 0)}, "
            f"Date: {a.get('created_at', '?')}"
        )
    return f"{len(data)} audits:\n" + "\n".join(rows)


# ─── YouTube / Studio tools ──────────────────────────────────────────────────

@mcp.tool()
async def pressroom_youtube_script(org_id: int, content_id: int | None = None, brief: str = "") -> str:
    """Generate a YouTube script from content or a free-form brief. Creates hook, sections, talking points, lower thirds, and YouTube metadata.

    Args:
        org_id: The organization ID.
        content_id: Optional content item ID to base the script on.
        brief: Optional free-form brief if not using content_id.
    """
    body: dict[str, Any] = {}
    if content_id is not None:
        body["content_id"] = content_id
    if brief:
        body["brief"] = brief
    data = await api_post("/api/youtube/generate", org_id=org_id, body=body)
    if "error" in data:
        return f"Error: {data['error']}"
    return (
        f"YouTube script generated: #{data.get('id', '?')}\n"
        f"Title: {data.get('title', '?')}\n"
        f"Hook: {data.get('hook', '?')}\n"
        f"Status: {data.get('status', '?')}\n\n"
        f"Full script:\n{json.dumps(data, indent=2, default=str)}"
    )


@mcp.tool()
async def pressroom_youtube_list(org_id: int) -> str:
    """List YouTube scripts for an org.

    Args:
        org_id: The organization ID.
    """
    data = await api_get("/api/youtube/scripts", org_id=org_id)
    if err := _check_error(data):
        return err
    if not data:
        return "No YouTube scripts found."
    rows = []
    for s in data:
        rows.append(f"  #{s.get('id', '?')} [{s.get('status', '?')}] {s.get('title', '?')} — {s.get('created_at', '?')}")
    return f"{len(data)} scripts:\n" + "\n".join(rows)


@mcp.tool()
async def pressroom_youtube_export(script_id: int) -> str:
    """Export a YouTube script as a Remotion JSON package for video production.

    Args:
        script_id: The YouTube script ID.
    """
    data = await api_get(f"/api/youtube/scripts/{script_id}/export")
    if "error" in data:
        return f"Error: {data['error']}"
    return json.dumps(data, indent=2)


# ─── Skills tools ─────────────────────────────────────────────────────────────

@mcp.tool()
async def pressroom_list_skills() -> str:
    """List available skills (Claude prompt templates) in Pressroom."""
    data = await api_get("/api/skills")
    if err := _check_error(data):
        return err
    if not data:
        return "No skills found."
    core = {"humanizer", "seo_geo"}
    rows = []
    for s in data:
        wired = "WIRED" if s.get("name", "") in core else "AVAILABLE"
        rows.append(f"  {s.get('name', '?')} [{wired}] — {s.get('first_line', '')}")
    return f"{len(data)} skills:\n" + "\n".join(rows)


@mcp.tool()
async def pressroom_get_skill(skill_name: str) -> str:
    """Get the full content of a skill file.

    Args:
        skill_name: The skill name (e.g. "humanizer", "seo_geo").
    """
    data = await api_get(f"/api/skills/{skill_name}")
    if "error" in data:
        return f"Error: {data['error']}"
    return f"Skill: {data.get('name', '?')}\n\n{data.get('content', '')}"


@mcp.tool()
async def pressroom_invoke_skill(skill_name: str, input_text: str) -> str:
    """Invoke a skill — run input text through a skill's Claude prompt.

    Args:
        skill_name: The skill to invoke (e.g. "humanizer").
        input_text: The text to process with the skill.
    """
    data = await api_post(
        f"/api/skills/invoke/{skill_name}",
        body={"text": input_text},
    )
    if "error" in data:
        return f"Error: {data['error']}"
    return json.dumps(data, indent=2, default=str)


# ─── Signal tools ─────────────────────────────────────────────────────────────

@mcp.tool()
async def pressroom_list_signals(org_id: int, limit: int = 50) -> str:
    """List current signals (wire items) for an org.

    Args:
        org_id: The organization ID.
        limit: Max signals to return (default 50).
    """
    data = await api_get("/api/signals", org_id=org_id, params={"limit": limit})
    if err := _check_error(data):
        return err
    if not data:
        return "No signals on the wire."
    rows = []
    for s in data:
        prio = " *" if s.get("prioritized") else ""
        rows.append(f"  #{s.get('id', '?')} [{s.get('type', '?')}]{prio} {s.get('source', '')}: {s.get('title', '')}")
    return f"{len(data)} signals:\n" + "\n".join(rows)


# ─── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    mcp.run()
