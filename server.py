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

PRESSROOM_URL = os.getenv("PRESSROOM_URL", "https://app.pressroom.com")
PRESSROOM_API_KEY = os.getenv("PRESSROOM_API_KEY", "")

mcp = FastMCP("pressroom")

# Shared HTTP client
_client: httpx.AsyncClient | None = None


async def client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(base_url=PRESSROOM_URL, timeout=120.0)
    return _client


def org_headers(org_id: int | None = None) -> dict[str, str]:
    """Build headers with optional org context and auth."""
    h: dict[str, str] = {"Content-Type": "application/json"}
    if PRESSROOM_API_KEY:
        h["Authorization"] = f"Bearer {PRESSROOM_API_KEY}"
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


async def api_patch(path: str, org_id: int | None = None, body: dict | None = None) -> Any:
    """PATCH request to Pressroom API."""
    c = await client()
    r = await c.patch(path, headers=org_headers(org_id), json=body or {})
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


# ─── Story workbench tools ───────────────────────────────────────────────────

@mcp.tool()
async def pressroom_list_stories(org_id: int, limit: int = 20) -> str:
    """List editorial stories for an org.

    Args:
        org_id: The organization ID.
        limit: Max stories to return (default 20).
    """
    data = await api_get("/api/stories", org_id=org_id, params={"limit": limit})
    if err := _check_error(data):
        return err
    if not data:
        return "No stories yet."
    rows = []
    for s in data:
        sig_count = len(s.get("signals", []))
        rows.append(
            f"  #{s.get('id', '?')} {s.get('title', '?')} — "
            f"{sig_count} signals, angle: {s.get('angle', '—')}"
        )
    return f"{len(data)} stories:\n" + "\n".join(rows)


@mcp.tool()
async def pressroom_create_story(
    org_id: int,
    title: str,
    angle: str = "",
    editorial_notes: str = "",
    signal_ids: list[int] | None = None,
) -> str:
    """Create an editorial story — a curated collection of signals with an angle.

    Args:
        org_id: The organization ID.
        title: Story headline.
        angle: Editorial angle or thesis for this story.
        editorial_notes: Additional context or instructions for content generation.
        signal_ids: Optional list of signal IDs to attach to the story.
    """
    body: dict[str, Any] = {"title": title}
    if angle:
        body["angle"] = angle
    if editorial_notes:
        body["editorial_notes"] = editorial_notes
    if signal_ids:
        body["signal_ids"] = signal_ids
    data = await api_post("/api/stories", org_id=org_id, body=body)
    if err := _check_error(data):
        return err
    return (
        f"Story created: #{data.get('id', '?')}\n"
        f"Title: {data.get('title', '?')}\n"
        f"Angle: {data.get('angle', '—')}\n"
        f"Signals attached: {len(data.get('signals', []))}"
    )


@mcp.tool()
async def pressroom_get_story(org_id: int, story_id: int) -> str:
    """Get a story with all attached signals and editorial notes.

    Args:
        org_id: The organization ID.
        story_id: The story ID.
    """
    data = await api_get(f"/api/stories/{story_id}", org_id=org_id)
    if err := _check_error(data):
        return err
    return json.dumps(data, indent=2, default=str)


@mcp.tool()
async def pressroom_add_signal_to_story(
    org_id: int, story_id: int, signal_id: int, editor_notes: str = ""
) -> str:
    """Attach a signal to a story with optional editor notes.

    Args:
        org_id: The organization ID.
        story_id: The story to add the signal to.
        signal_id: The signal ID to attach.
        editor_notes: Optional editorial context for why this signal matters.
    """
    data = await api_post(
        f"/api/stories/{story_id}/signals",
        org_id=org_id,
        body={"signal_id": signal_id, "editor_notes": editor_notes},
    )
    if err := _check_error(data):
        return err
    return f"Signal #{signal_id} added to story #{story_id}."


@mcp.tool()
async def pressroom_generate_from_story(
    org_id: int, story_id: int, channels: list[str] | None = None, team_member_id: int | None = None
) -> str:
    """Generate content from a curated story. Uses the story's signals and angle to produce channel-specific content.

    Args:
        org_id: The organization ID.
        story_id: The story ID to generate from.
        channels: Optional list of channels (e.g. ["linkedin", "blog"]). Uses org defaults if empty.
        team_member_id: Optional team member ID to use their voice profile.
    """
    body: dict[str, Any] = {}
    if channels:
        body["channels"] = channels
    if team_member_id is not None:
        body["team_member_id"] = team_member_id
    data = await api_post(f"/api/stories/{story_id}/generate", org_id=org_id, body=body)
    if err := _check_error(data):
        return err
    items = data.get("content", [])
    return (
        f"Generated {data.get('generated', len(items))} items from story #{story_id}.\n\n"
        + "\n".join(
            f"  [{i.get('channel', '?')}] #{i.get('id', '?')} — {i.get('headline', '')}"
            for i in items
        )
    )


@mcp.tool()
async def pressroom_discover_signals(org_id: int, story_id: int, mode: str = "web") -> str:
    """Discover additional signals for a story using AI-powered search.

    Args:
        org_id: The organization ID.
        story_id: The story to discover signals for.
        mode: Discovery mode — "web" for web search (default).
    """
    data = await api_post(
        f"/api/stories/{story_id}/discover",
        org_id=org_id,
        body={"mode": mode},
    )
    if err := _check_error(data):
        return err
    signals = data if isinstance(data, list) else data.get("signals", [])
    if not signals:
        return "No additional signals discovered."
    rows = []
    for s in signals:
        rows.append(f"  [{s.get('type', '?')}] {s.get('source', '')}: {s.get('title', '')}")
    return f"Discovered {len(signals)} signals:\n" + "\n".join(rows)


# ─── Wire tools (company-owned sources) ─────────────────────────────────────

@mcp.tool()
async def pressroom_list_wire_sources(org_id: int) -> str:
    """List Wire sources — the company's own feeds (GitHub repos, blog RSS, changelogs, docs).

    Args:
        org_id: The organization ID.
    """
    data = await api_get("/api/wire/sources", org_id=org_id)
    if err := _check_error(data):
        return err
    if not data:
        return "No Wire sources configured."
    rows = []
    for s in data:
        active = "active" if s.get("active") else "paused"
        rows.append(
            f"  #{s.get('id', '?')} [{s.get('type', '?')}] {s.get('name', '?')} ({active})"
        )
    return f"{len(data)} Wire sources:\n" + "\n".join(rows)


@mcp.tool()
async def pressroom_create_wire_source(
    org_id: int, type: str, name: str, config: dict[str, Any] | None = None
) -> str:
    """Create a Wire source — a company-owned feed like a GitHub repo, blog RSS, or changelog.

    Args:
        org_id: The organization ID.
        type: Source type: "github_release", "github_commit", "rss", "changelog".
        name: Display name for the source.
        config: Source config (e.g. {"repo": "owner/repo"} for GitHub, {"url": "..."} for RSS).
    """
    data = await api_post(
        "/api/wire/sources",
        org_id=org_id,
        body={"type": type, "name": name, "config": config or {}},
    )
    if err := _check_error(data):
        return err
    return f"Wire source created: #{data.get('id', '?')} [{data.get('type', '?')}] {data.get('name', '?')}"


@mcp.tool()
async def pressroom_fetch_wire(org_id: int, wire_source_id: int | None = None) -> str:
    """Fetch new signals from Wire sources. Pulls from company's own channels.

    Args:
        org_id: The organization ID.
        wire_source_id: Optional specific Wire source ID to fetch. Fetches all if empty.
    """
    body: dict[str, Any] = {}
    if wire_source_id is not None:
        body["wire_source_id"] = wire_source_id
    data = await api_post("/api/wire/fetch", org_id=org_id, body=body)
    if err := _check_error(data):
        return err
    return (
        f"Wire fetch complete. Sources: {data.get('fetched_sources', 0)}, "
        f"New signals: {data.get('total_new', 0)}"
    )


@mcp.tool()
async def pressroom_list_wire_signals(org_id: int, limit: int = 40, type: str = "") -> str:
    """List signals from the Wire — the company's own activity (releases, commits, blog posts).

    Args:
        org_id: The organization ID.
        limit: Max signals to return (default 40).
        type: Optional type filter (e.g. "github_release", "rss").
    """
    params: dict[str, Any] = {"limit": limit}
    if type:
        params["type"] = type
    data = await api_get("/api/wire/signals", org_id=org_id, params=params)
    if err := _check_error(data):
        return err
    if not data:
        return "No Wire signals."
    rows = []
    for s in data:
        rows.append(f"  #{s.get('id', '?')} [{s.get('type', '?')}] {s.get('title', '')}")
    return f"{len(data)} Wire signals:\n" + "\n".join(rows)


# ─── SIGINT source tools (global source library) ────────────────────────────

@mcp.tool()
async def pressroom_list_sources(type: str = "", active_only: bool = True) -> str:
    """List the global source library — Reddit, HN, RSS feeds, X search, trends.

    Args:
        type: Optional type filter (e.g. "reddit", "hackernews", "rss", "x_search", "trend").
        active_only: Only show active sources (default True).
    """
    params: dict[str, Any] = {"active_only": str(active_only).lower()}
    if type:
        params["type"] = type
    data = await api_get("/api/sources", params=params)
    if err := _check_error(data):
        return err
    if not data:
        return "No sources found."
    rows = []
    for s in data:
        tags = ", ".join(s.get("category_tags", []))
        rows.append(
            f"  #{s.get('id', '?')} [{s.get('type', '?')}] {s.get('name', '?')}"
            + (f" — tags: {tags}" if tags else "")
        )
    return f"{len(data)} sources:\n" + "\n".join(rows)


@mcp.tool()
async def pressroom_create_source(
    type: str,
    name: str,
    config: dict[str, Any] | None = None,
    category_tags: list[str] | None = None,
    fetch_interval_hours: int = 6,
) -> str:
    """Create a global source in the SIGINT library.

    Args:
        type: Source type: "reddit", "hackernews", "rss", "x_search", "trend".
        name: Display name (e.g. "r/programming", "HN: AI").
        config: Source config (e.g. {"subreddit": "programming"}, {"keywords": ["AI"]}, {"url": "..."}).
        category_tags: Optional tags for categorization.
        fetch_interval_hours: How often to fetch (default 6 hours).
    """
    body: dict[str, Any] = {
        "type": type,
        "name": name,
        "config": config or {},
        "fetch_interval_hours": fetch_interval_hours,
    }
    if category_tags:
        body["category_tags"] = category_tags
    data = await api_post("/api/sources", body=body)
    if err := _check_error(data):
        return err
    return f"Source created: #{data.get('id', '?')} [{data.get('type', '?')}] {data.get('name', '?')}"


@mcp.tool()
async def pressroom_sweep_sources(org_id: int, source_ids: list[int] | None = None) -> str:
    """Run a sweep — crawl sources and pull raw signals into the SIGINT feed.

    Args:
        org_id: The organization ID.
        source_ids: Optional list of specific source IDs to sweep. Sweeps all if empty.
    """
    body: dict[str, Any] = {}
    if source_ids:
        body["source_ids"] = source_ids
    data = await api_post("/api/sources/sweep", org_id=org_id, body=body)
    if err := _check_error(data):
        return err
    return json.dumps(data, indent=2, default=str)


@mcp.tool()
async def pressroom_get_feed(org_id: int, limit: int = 40, min_score: float | None = None) -> str:
    """Get the SIGINT feed — relevance-scored signals from the global source library.

    Args:
        org_id: The organization ID.
        limit: Max items (default 40).
        min_score: Optional minimum relevance score filter.
    """
    params: dict[str, Any] = {"limit": limit}
    if min_score is not None:
        params["min_score"] = min_score
    data = await api_get("/api/sources/feed", org_id=org_id, params=params)
    if err := _check_error(data):
        return err
    if not data:
        return "Feed is empty. Run a sweep first."
    rows = []
    for s in data:
        score = s.get("relevance_score", "?")
        rows.append(
            f"  #{s.get('id', '?')} [{s.get('type', '?')}] score={score} — "
            f"{s.get('source', '')}: {s.get('title', '')}"
        )
    return f"{len(data)} feed items:\n" + "\n".join(rows)


# ─── Settings tools ──────────────────────────────────────────────────────────

@mcp.tool()
async def pressroom_get_settings(org_id: int) -> str:
    """Get all settings for an org — API keys, voice profile, scout config, integrations.

    Args:
        org_id: The organization ID.
    """
    data = await api_get("/api/settings", org_id=org_id)
    if err := _check_error(data):
        return err
    return json.dumps(data, indent=2, default=str)


@mcp.tool()
async def pressroom_update_settings(org_id: int, settings: dict[str, str]) -> str:
    """Update settings for an org. Pass a dict of key-value pairs.

    Common settings:
    - voice_persona, voice_audience, voice_tone, voice_brand_keywords (voice profile)
    - onboard_company_name, onboard_industry, onboard_topics (company info)
    - scout_github_repos, scout_hn_keywords, scout_subreddits, scout_rss_feeds (scout sources)

    Args:
        org_id: The organization ID.
        settings: Dict of setting key-value pairs to update.
    """
    data = await api_put("/api/settings", org_id=org_id, body={"settings": settings})
    if err := _check_error(data):
        return err
    updated = data.get("updated", [])
    return f"Updated {len(updated)} settings: {', '.join(updated)}"


@mcp.tool()
async def pressroom_connection_status(org_id: int) -> str:
    """Check connection status for all configured services (Claude, GitHub, LinkedIn, DreamFactory, etc).

    Args:
        org_id: The organization ID.
    """
    data = await api_get("/api/settings/status", org_id=org_id)
    if err := _check_error(data):
        return err
    return json.dumps(data, indent=2, default=str)


# ─── Content enhancement tools ───────────────────────────────────────────────

@mcp.tool()
async def pressroom_spike_content(org_id: int, content_ids: list[int]) -> str:
    """Spike (reject) content items, removing them from the queue.

    Args:
        org_id: The organization ID.
        content_ids: List of content IDs to spike.
    """
    results = []
    for cid in content_ids:
        data = await api_patch(
            f"/api/content/{cid}",
            org_id=org_id,
            body={"status": "spiked"},
        )
        results.append(f"  #{cid}: {'spiked' if 'error' not in data else data['error']}")
    return f"Spiked {len(content_ids)} items:\n" + "\n".join(results)


@mcp.tool()
async def pressroom_edit_content(
    org_id: int, content_id: int, body: str = "", headline: str = ""
) -> str:
    """Edit a content item's body text or headline.

    Args:
        org_id: The organization ID.
        content_id: The content item ID.
        body: New body text (leave empty to keep current).
        headline: New headline (leave empty to keep current).
    """
    patch: dict[str, Any] = {}
    if body:
        patch["body"] = body
    if headline:
        patch["headline"] = headline
    if not patch:
        return "Nothing to update — provide body or headline."
    data = await api_patch(f"/api/content/{content_id}", org_id=org_id, body=patch)
    if err := _check_error(data):
        return err
    return f"Content #{content_id} updated."


@mcp.tool()
async def pressroom_humanize_content(org_id: int, content_id: int) -> str:
    """Run the humanizer on a content item — removes AI patterns and adds voice.

    Args:
        org_id: The organization ID.
        content_id: The content item ID to humanize.
    """
    data = await api_patch(f"/api/content/{content_id}/humanize", org_id=org_id)
    if err := _check_error(data):
        return err
    return f"Content #{content_id} humanized."


@mcp.tool()
async def pressroom_schedule_content(org_id: int, content_id: int, publish_at: str) -> str:
    """Schedule a content item for future auto-publish.

    Args:
        org_id: The organization ID.
        content_id: The content item ID.
        publish_at: ISO datetime string for when to publish (e.g. "2025-01-15T09:00:00Z").
    """
    data = await api_post(
        f"/api/content/{content_id}/schedule",
        org_id=org_id,
        body={"publish_at": publish_at},
    )
    if err := _check_error(data):
        return err
    return f"Content #{content_id} scheduled for {publish_at}."


# ─── SEO PR pipeline tools ──────────────────────────────────────────────────

@mcp.tool()
async def pressroom_seo_pr_run(
    org_id: int, repo_url: str, domain: str = "", base_branch: str = "main"
) -> str:
    """Start an SEO PR pipeline run — audits a domain, analyzes issues, generates fixes, and opens a PR.

    Args:
        org_id: The organization ID.
        repo_url: GitHub repo URL (e.g. "https://github.com/owner/repo").
        domain: Domain to audit. Uses org default if empty.
        base_branch: Branch to target for the PR (default "main").
    """
    data = await api_post(
        "/api/seo-pr/run",
        org_id=org_id,
        body={"repo_url": repo_url, "domain": domain, "base_branch": base_branch},
    )
    if err := _check_error(data):
        return err
    return (
        f"SEO PR run started: #{data.get('id', '?')}\n"
        f"Status: {data.get('status', '?')}\n"
        f"Domain: {data.get('domain', '?')}"
    )


@mcp.tool()
async def pressroom_seo_pr_list(org_id: int) -> str:
    """List SEO PR pipeline runs for an org.

    Args:
        org_id: The organization ID.
    """
    data = await api_get("/api/seo-pr/runs", org_id=org_id)
    if err := _check_error(data):
        return err
    if not data:
        return "No SEO PR runs."
    rows = []
    for r in data:
        pr_url = r.get("pr_url", "")
        rows.append(
            f"  #{r.get('id', '?')} [{r.get('status', '?')}] {r.get('domain', '?')}"
            + (f" — PR: {pr_url}" if pr_url else "")
        )
    return f"{len(data)} SEO PR runs:\n" + "\n".join(rows)


@mcp.tool()
async def pressroom_seo_pr_status(org_id: int, run_id: int) -> str:
    """Get detailed status of an SEO PR pipeline run — plan, PR URL, deployment log.

    Args:
        org_id: The organization ID.
        run_id: The SEO PR run ID.
    """
    data = await api_get(f"/api/seo-pr/runs/{run_id}", org_id=org_id)
    if err := _check_error(data):
        return err
    return json.dumps(data, indent=2, default=str)


# ─── Competitive intelligence tools ─────────────────────────────────────────

@mcp.tool()
async def pressroom_competitive_scan(org_id: int, competitor_urls: list[str]) -> str:
    """Run a competitive intelligence scan on competitor URLs.

    Args:
        org_id: The organization ID.
        competitor_urls: List of competitor website URLs to scan.
    """
    data = await api_post(
        "/api/competitive/scan",
        org_id=org_id,
        body={"competitor_urls": competitor_urls},
    )
    if err := _check_error(data):
        return err
    competitors = data.get("competitors", [])
    rows = []
    for c in competitors:
        rows.append(
            f"  {c.get('domain', '?')} — SEO: {c.get('seo_score', '?')}, "
            f"AI citable: {c.get('ai_citability', '?')}"
        )
    return (
        f"Competitive scan complete ({data.get('scanned_at', '?')}):\n"
        + "\n".join(rows)
    )


@mcp.tool()
async def pressroom_competitive_results(org_id: int) -> str:
    """Get stored competitive intelligence results for an org.

    Args:
        org_id: The organization ID.
    """
    data = await api_get(f"/api/competitive/{org_id}", org_id=org_id)
    if err := _check_error(data):
        return err
    return json.dumps(data, indent=2, default=str)


# ─── AI visibility tools ────────────────────────────────────────────────────

@mcp.tool()
async def pressroom_ai_visibility_scan(org_id: int) -> str:
    """Scan AI models (ChatGPT, Perplexity, Claude) to see if they cite your content.

    Args:
        org_id: The organization ID.
    """
    data = await api_post("/api/ai-visibility/scan", org_id=org_id)
    if err := _check_error(data):
        return err
    questions = data.get("questions", [])
    rows = []
    for q in questions:
        cited = sum(1 for r in q.get("results", []) if r.get("cited"))
        total = len(q.get("results", []))
        rows.append(f"  \"{q.get('question', '?')}\" — cited in {cited}/{total} providers")
    return (
        f"AI visibility scan complete ({data.get('scanned_at', '?')}):\n"
        + "\n".join(rows)
    )


@mcp.tool()
async def pressroom_ai_visibility_results(org_id: int) -> str:
    """Get AI visibility results — which LLMs cite your content and for what queries.

    Args:
        org_id: The organization ID.
    """
    data = await api_get(f"/api/ai-visibility/{org_id}", org_id=org_id)
    if err := _check_error(data):
        return err
    return json.dumps(data, indent=2, default=str)


@mcp.tool()
async def pressroom_ai_visibility_questions(org_id: int, questions: list[str]) -> str:
    """Set the questions to ask AI models for visibility tracking.

    Args:
        org_id: The organization ID.
        questions: List of questions to track (e.g. ["What is the best CI/CD tool?", "How to deploy to Kubernetes?"]).
    """
    data = await api_put(
        f"/api/ai-visibility/{org_id}/questions",
        org_id=org_id,
        body={"questions": questions},
    )
    if err := _check_error(data):
        return err
    return f"Updated visibility questions: {data.get('count', len(questions))} questions set."


# ─── Analytics tools ─────────────────────────────────────────────────────────

@mcp.tool()
async def pressroom_analytics(org_id: int) -> str:
    """Get the analytics dashboard — signal volume, content stats, approval rate, top signals, leaderboard.

    Args:
        org_id: The organization ID.
    """
    data = await api_get("/api/analytics/dashboard", org_id=org_id)
    if err := _check_error(data):
        return err

    signals = data.get("signals", {})
    content = data.get("content", {})
    approval = data.get("approval_rate", 0)

    summary = (
        f"Analytics Dashboard\n"
        f"{'='*40}\n"
        f"Signals: {signals.get('total', 0)} total, "
        f"{signals.get('today', 0)} today, "
        f"{signals.get('week', 0)} this week\n"
        f"Content: {content.get('queued', 0)} queued, "
        f"{content.get('approved', 0)} approved, "
        f"{content.get('published', 0)} published, "
        f"{content.get('spiked', 0)} spiked\n"
        f"Approval rate: {approval:.0%}\n"
    )

    top = data.get("top_signals", [])
    if top:
        summary += f"\nTop signals:\n"
        for s in top[:5]:
            summary += f"  [{s.get('type', '?')}] {s.get('title', '')}\n"

    return summary


# ─── Onboarding tools ───────────────────────────────────────────────────────

@mcp.tool()
async def pressroom_onboard(org_id: int, domain: str, extra_context: str = "") -> str:
    """Onboard a company — crawl their domain and synthesize a company profile.

    Args:
        org_id: The organization ID.
        domain: Company domain to crawl (e.g. "example.com").
        extra_context: Optional extra context about the company.
    """
    # Step 1: Crawl
    crawl = await api_post("/api/onboard/crawl", org_id=org_id, body={"domain": domain})
    if err := _check_error(crawl):
        return f"Crawl failed: {err}"

    # Step 2: Synthesize profile
    profile_body: dict[str, Any] = {"crawl_data": crawl, "domain": domain}
    if extra_context:
        profile_body["extra_context"] = extra_context
    profile = await api_post("/api/onboard/profile", org_id=org_id, body=profile_body)
    if err := _check_error(profile):
        return f"Profile synthesis failed: {err}"

    p = profile.get("profile", {})
    return (
        f"Onboarding complete for {domain}\n"
        f"Company: {p.get('company_name', '?')}\n"
        f"Industry: {p.get('industry', '?')}\n"
        f"Topics: {', '.join(p.get('topics', []))}\n"
        f"Competitors: {', '.join(p.get('competitors', []))}\n\n"
        f"Use pressroom_onboard_apply() to save this profile."
    )


@mcp.tool()
async def pressroom_onboard_apply(org_id: int, profile: dict[str, Any]) -> str:
    """Apply an onboarding profile — saves company info, voice, scout sources to org settings.

    Args:
        org_id: The organization ID.
        profile: The profile dict from pressroom_onboard (company_name, industry, topics, etc).
    """
    data = await api_post(
        "/api/onboard/apply",
        org_id=org_id,
        body={"profile": profile},
    )
    if err := _check_error(data):
        return err
    return (
        f"Profile applied. {data.get('count', 0)} settings saved.\n"
        f"Org: {data.get('org', {}).get('name', '?')}\n"
        f"Blog posts scraped: {data.get('blog_posts_scraped', 0)}"
    )


@mcp.tool()
async def pressroom_onboard_status(org_id: int) -> str:
    """Check onboarding status — is the org fully set up?

    Args:
        org_id: The organization ID.
    """
    data = await api_get("/api/onboard/status", org_id=org_id)
    if err := _check_error(data):
        return err
    checks = [
        ("Company info", data.get("has_company", False)),
        ("Voice profile", data.get("has_voice", False)),
        ("DreamFactory", data.get("has_df", False)),
        ("Service map", data.get("has_service_map", False)),
    ]
    status_lines = [f"  {'[x]' if ok else '[ ]'} {label}" for label, ok in checks]
    return (
        f"Onboarding {'complete' if data.get('complete') else 'incomplete'} "
        f"for {data.get('company_name', '?')} (org #{data.get('org_id', '?')})\n"
        + "\n".join(status_lines)
    )


# ─── Team tools ──────────────────────────────────────────────────────────────

@mcp.tool()
async def pressroom_list_team(org_id: int) -> str:
    """List team members for an org.

    Args:
        org_id: The organization ID.
    """
    data = await api_get("/api/team", org_id=org_id)
    if err := _check_error(data):
        return err
    if not data:
        return "No team members."
    rows = []
    for m in data:
        tags = ", ".join(m.get("expertise_tags", []))
        rows.append(
            f"  #{m.get('id', '?')} {m.get('name', '?')} — {m.get('title', '')}"
            + (f" [{tags}]" if tags else "")
        )
    return f"{len(data)} team members:\n" + "\n".join(rows)


@mcp.tool()
async def pressroom_add_team_member(
    org_id: int,
    name: str,
    title: str = "",
    bio: str = "",
    email: str = "",
    linkedin_url: str = "",
    expertise_tags: list[str] | None = None,
) -> str:
    """Add a team member to an org.

    Args:
        org_id: The organization ID.
        name: Full name.
        title: Job title.
        bio: Short bio.
        email: Email address.
        linkedin_url: LinkedIn profile URL.
        expertise_tags: List of expertise areas (e.g. ["backend", "devops", "kubernetes"]).
    """
    body: dict[str, Any] = {"name": name}
    if title:
        body["title"] = title
    if bio:
        body["bio"] = bio
    if email:
        body["email"] = email
    if linkedin_url:
        body["linkedin_url"] = linkedin_url
    if expertise_tags:
        body["expertise_tags"] = expertise_tags
    data = await api_post("/api/team", org_id=org_id, body=body)
    if err := _check_error(data):
        return err
    return f"Team member added: #{data.get('id', '?')} {data.get('name', '?')}"


@mcp.tool()
async def pressroom_discover_team(org_id: int) -> str:
    """Auto-discover team members from GitHub, LinkedIn, and company pages.

    Args:
        org_id: The organization ID.
    """
    data = await api_post("/api/team/discover", org_id=org_id)
    if err := _check_error(data):
        return err
    return (
        f"Team discovery complete.\n"
        f"Found: {data.get('total_found', 0)}, "
        f"Saved: {data.get('saved', 0)}, "
        f"Skipped (dupes): {data.get('skipped_duplicates', 0)}\n"
        f"Pages checked: {', '.join(data.get('pages_checked', []))}"
    )


# ─── Email tools ─────────────────────────────────────────────────────────────

@mcp.tool()
async def pressroom_compose_email(org_id: int, content_id: int) -> str:
    """Compose an email draft from a content item (typically release_email or newsletter channel).

    Args:
        org_id: The organization ID.
        content_id: The content item ID to compose the email from.
    """
    data = await api_post(
        "/api/email/drafts/compose",
        org_id=org_id,
        body={"content_id": content_id},
    )
    if err := _check_error(data):
        return err
    return (
        f"Email draft composed: #{data.get('id', '?')}\n"
        f"Subject: {data.get('subject', '?')}\n"
        f"Status: {data.get('status', 'draft')}"
    )


@mcp.tool()
async def pressroom_list_email_drafts(org_id: int, status: str = "", limit: int = 20) -> str:
    """List email drafts for an org.

    Args:
        org_id: The organization ID.
        status: Optional status filter.
        limit: Max drafts to return (default 20).
    """
    params: dict[str, Any] = {"limit": limit}
    if status:
        params["status"] = status
    data = await api_get("/api/email/drafts", org_id=org_id, params=params)
    if err := _check_error(data):
        return err
    if not data:
        return "No email drafts."
    rows = []
    for d in data:
        rows.append(
            f"  #{d.get('id', '?')} [{d.get('status', '?')}] {d.get('subject', '?')}"
        )
    return f"{len(data)} email drafts:\n" + "\n".join(rows)


# ─── Blog management tools ───────────────────────────────────────────────────

@mcp.tool()
async def pressroom_blog_scrape(org_id: int, url: str) -> str:
    """Scrape a blog post from a URL and import it into Pressroom.

    Args:
        org_id: The organization ID.
        url: The blog post URL to scrape.
    """
    data = await api_post("/api/blog/scrape", org_id=org_id, body={"url": url})
    if err := _check_error(data):
        return err
    return (
        f"Blog post scraped: #{data.get('id', '?')}\n"
        f"Title: {data.get('title', '?')}\n"
        f"URL: {url}"
    )


@mcp.tool()
async def pressroom_blog_list(org_id: int) -> str:
    """List all blog posts for an org.

    Args:
        org_id: The organization ID.
    """
    data = await api_get("/api/blog/posts", org_id=org_id)
    if err := _check_error(data):
        return err
    if not data:
        return "No blog posts found."
    rows = []
    for p in data:
        rows.append(
            f"  #{p.get('id', '?')} {p.get('title', '?')} — {p.get('url', '')}"
        )
    return f"{len(data)} blog posts:\n" + "\n".join(rows)


@mcp.tool()
async def pressroom_blog_delete(org_id: int, post_id: int) -> str:
    """Delete a blog post from the org.

    Args:
        org_id: The organization ID.
        post_id: The blog post ID to delete.
    """
    data = await api_delete(f"/api/blog/posts/{post_id}", org_id=org_id)
    if err := _check_error(data):
        return err
    return f"Blog post #{post_id} deleted."


# ─── Google Search Console tools ─────────────────────────────────────────────

@mcp.tool()
async def pressroom_gsc_status(org_id: int) -> str:
    """Check Google Search Console connection status for an org.

    Args:
        org_id: The organization ID.
    """
    data = await api_get("/api/gsc/status", org_id=org_id)
    if err := _check_error(data):
        return err
    return json.dumps(data, indent=2, default=str)


@mcp.tool()
async def pressroom_gsc_properties(org_id: int) -> str:
    """List Google Search Console properties available for an org.

    Args:
        org_id: The organization ID.
    """
    data = await api_get("/api/gsc/properties", org_id=org_id)
    if err := _check_error(data):
        return err
    if not data:
        return "No GSC properties found."
    rows = []
    for p in data:
        rows.append(f"  {p.get('siteUrl', p.get('url', '?'))}")
    return f"{len(data)} GSC properties:\n" + "\n".join(rows)


@mcp.tool()
async def pressroom_gsc_set_property(org_id: int, property_url: str) -> str:
    """Set the active Google Search Console property for an org.

    Args:
        org_id: The organization ID.
        property_url: The GSC property URL to set as active.
    """
    data = await api_put("/api/gsc/property", org_id=org_id, body={"property_url": property_url})
    if err := _check_error(data):
        return err
    return f"GSC property set to: {property_url}"


@mcp.tool()
async def pressroom_gsc_analytics(org_id: int, days: int = 28) -> str:
    """Get Google Search Console analytics data for an org.

    Args:
        org_id: The organization ID.
        days: Number of days to look back (default 28).
    """
    data = await api_get("/api/gsc/analytics", org_id=org_id, params={"days": days})
    if err := _check_error(data):
        return err
    return json.dumps(data, indent=2, default=str)


@mcp.tool()
async def pressroom_gsc_summary(org_id: int) -> str:
    """Get a summary of Google Search Console performance for an org.

    Args:
        org_id: The organization ID.
    """
    data = await api_get("/api/gsc/summary", org_id=org_id)
    if err := _check_error(data):
        return err
    return json.dumps(data, indent=2, default=str)


@mcp.tool()
async def pressroom_gsc_blog_performance(org_id: int) -> str:
    """Get Google Search Console performance data for blog posts.

    Args:
        org_id: The organization ID.
    """
    data = await api_get("/api/gsc/blog-performance", org_id=org_id)
    if err := _check_error(data):
        return err
    return json.dumps(data, indent=2, default=str)


@mcp.tool()
async def pressroom_gsc_inspect_url(org_id: int, url: str) -> str:
    """Inspect a URL in Google Search Console to check indexing status.

    Args:
        org_id: The organization ID.
        url: The URL to inspect.
    """
    data = await api_post("/api/gsc/inspect", org_id=org_id, body={"url": url})
    if err := _check_error(data):
        return err
    return json.dumps(data, indent=2, default=str)


# ─── Site properties tools ───────────────────────────────────────────────────

@mcp.tool()
async def pressroom_list_properties(org_id: int) -> str:
    """List site properties for an org.

    Args:
        org_id: The organization ID.
    """
    data = await api_get("/api/properties", org_id=org_id)
    if err := _check_error(data):
        return err
    if not data:
        return "No site properties found."
    rows = []
    for p in data:
        rows.append(
            f"  #{p.get('id', '?')} [{p.get('type', '?')}] {p.get('name', '?')}: {p.get('value', '')}"
        )
    return f"{len(data)} properties:\n" + "\n".join(rows)


@mcp.tool()
async def pressroom_create_property(
    org_id: int, name: str, value: str, prop_type: str = "domain"
) -> str:
    """Create a site property for an org.

    Args:
        org_id: The organization ID.
        name: Property name.
        value: Property value.
        prop_type: Property type (default "domain").
    """
    data = await api_post(
        "/api/properties",
        org_id=org_id,
        body={"name": name, "value": value, "type": prop_type},
    )
    if err := _check_error(data):
        return err
    return f"Property created: #{data.get('id', '?')} {data.get('name', '?')}"


@mcp.tool()
async def pressroom_update_property(org_id: int, property_id: int, value: str) -> str:
    """Update a site property value.

    Args:
        org_id: The organization ID.
        property_id: The property ID to update.
        value: New property value.
    """
    data = await api_put(
        f"/api/properties/{property_id}",
        org_id=org_id,
        body={"value": value},
    )
    if err := _check_error(data):
        return err
    return f"Property #{property_id} updated."


@mcp.tool()
async def pressroom_delete_property(org_id: int, property_id: int) -> str:
    """Delete a site property.

    Args:
        org_id: The organization ID.
        property_id: The property ID to delete.
    """
    data = await api_delete(f"/api/properties/{property_id}", org_id=org_id)
    if err := _check_error(data):
        return err
    return f"Property #{property_id} deleted."


# ─── Brand tools ─────────────────────────────────────────────────────────────

@mcp.tool()
async def pressroom_brand_scrape(org_id: int, domain: str) -> str:
    """Scrape brand information from a domain.

    Args:
        org_id: The organization ID.
        domain: The domain to scrape brand info from.
    """
    data = await api_post("/api/brand/scrape", org_id=org_id, body={"domain": domain})
    if err := _check_error(data):
        return err
    return json.dumps(data, indent=2, default=str)


@mcp.tool()
async def pressroom_brand_get(org_id: int) -> str:
    """Get the brand profile for an org.

    Args:
        org_id: The organization ID.
    """
    data = await api_get(f"/api/brand/{org_id}", org_id=org_id)
    if err := _check_error(data):
        return err
    return json.dumps(data, indent=2, default=str)


# ─── Asset tools ─────────────────────────────────────────────────────────────

@mcp.tool()
async def pressroom_list_assets(org_id: int, asset_type: str = "") -> str:
    """List assets for an org, optionally filtered by type.

    Args:
        org_id: The organization ID.
        asset_type: Optional asset type filter (leave empty for all).
    """
    params: dict[str, Any] = {}
    if asset_type:
        params["type"] = asset_type
    data = await api_get("/api/assets", org_id=org_id, params=params)
    if err := _check_error(data):
        return err
    if not data:
        return "No assets found."
    rows = []
    for a in data:
        rows.append(
            f"  #{a.get('id', '?')} [{a.get('type', '?')}] {a.get('name', '?')} — {a.get('url', '')}"
        )
    return f"{len(data)} assets:\n" + "\n".join(rows)


@mcp.tool()
async def pressroom_create_asset(org_id: int, name: str, url: str, asset_type: str) -> str:
    """Create an asset for an org.

    Args:
        org_id: The organization ID.
        name: Asset name.
        url: Asset URL.
        asset_type: Asset type (e.g. "image", "logo", "document").
    """
    data = await api_post(
        "/api/assets",
        org_id=org_id,
        body={"name": name, "url": url, "type": asset_type},
    )
    if err := _check_error(data):
        return err
    return f"Asset created: #{data.get('id', '?')} [{data.get('type', '?')}] {data.get('name', '?')}"


@mcp.tool()
async def pressroom_delete_asset(org_id: int, asset_id: int) -> str:
    """Delete an asset from an org.

    Args:
        org_id: The organization ID.
        asset_id: The asset ID to delete.
    """
    data = await api_delete(f"/api/assets/{asset_id}", org_id=org_id)
    if err := _check_error(data):
        return err
    return f"Asset #{asset_id} deleted."


# ─── Content performance tools ───────────────────────────────────────────────

@mcp.tool()
async def pressroom_content_performance(org_id: int) -> str:
    """Get performance metrics for all published content.

    Args:
        org_id: The organization ID.
    """
    data = await api_get("/api/content/published/performance", org_id=org_id)
    if err := _check_error(data):
        return err
    return json.dumps(data, indent=2, default=str)


@mcp.tool()
async def pressroom_fetch_performance(org_id: int, content_id: int) -> str:
    """Fetch latest performance data for a specific content item.

    Args:
        org_id: The organization ID.
        content_id: The content item ID.
    """
    data = await api_post(f"/api/content/{content_id}/fetch-performance", org_id=org_id)
    if err := _check_error(data):
        return err
    return json.dumps(data, indent=2, default=str)


# ─── Team enhancement tools ─────────────────────────────────────────────────

@mcp.tool()
async def pressroom_update_team_member(
    org_id: int, member_id: int, name: str = "", title: str = "", bio: str = ""
) -> str:
    """Update a team member's details. Only non-empty fields are sent.

    Args:
        org_id: The organization ID.
        member_id: The team member ID.
        name: New name (leave empty to keep current).
        title: New title (leave empty to keep current).
        bio: New bio (leave empty to keep current).
    """
    body: dict[str, Any] = {}
    if name:
        body["name"] = name
    if title:
        body["title"] = title
    if bio:
        body["bio"] = bio
    if not body:
        return "Nothing to update — provide name, title, or bio."
    data = await api_put(f"/api/team/{member_id}", org_id=org_id, body=body)
    if err := _check_error(data):
        return err
    return f"Team member #{member_id} updated."


@mcp.tool()
async def pressroom_analyze_voice(org_id: int, member_id: int) -> str:
    """Analyze a team member's writing voice from their content samples.

    Args:
        org_id: The organization ID.
        member_id: The team member ID.
    """
    data = await api_post(f"/api/team/{member_id}/analyze-voice", org_id=org_id)
    if err := _check_error(data):
        return err
    return json.dumps(data, indent=2, default=str)


@mcp.tool()
async def pressroom_team_gist_check(org_id: int) -> str:
    """Check gist status for all team members in an org.

    Args:
        org_id: The organization ID.
    """
    data = await api_get("/api/team/gist-check", org_id=org_id)
    if err := _check_error(data):
        return err
    return json.dumps(data, indent=2, default=str)


@mcp.tool()
async def pressroom_generate_gist(org_id: int, member_id: int) -> str:
    """Generate a gist (author bio page) for a team member.

    Args:
        org_id: The organization ID.
        member_id: The team member ID.
    """
    data = await api_post(f"/api/team/{member_id}/generate-gist", org_id=org_id)
    if err := _check_error(data):
        return err
    return json.dumps(data, indent=2, default=str)


@mcp.tool()
async def pressroom_publish_gist(org_id: int, member_id: int) -> str:
    """Publish a team member's gist (author bio page).

    Args:
        org_id: The organization ID.
        member_id: The team member ID.
    """
    data = await api_post(f"/api/team/{member_id}/publish-gist", org_id=org_id)
    if err := _check_error(data):
        return err
    return json.dumps(data, indent=2, default=str)


# ─── YouTube enhancement tools ──────────────────────────────────────────────

@mcp.tool()
async def pressroom_youtube_update(
    org_id: int, script_id: int, title: str = "", hook: str = ""
) -> str:
    """Update a YouTube script's title or hook. Only non-empty fields are sent.

    Args:
        org_id: The organization ID.
        script_id: The YouTube script ID.
        title: New title (leave empty to keep current).
        hook: New hook (leave empty to keep current).
    """
    body: dict[str, Any] = {}
    if title:
        body["title"] = title
    if hook:
        body["hook"] = hook
    if not body:
        return "Nothing to update — provide title or hook."
    data = await api_patch(f"/api/youtube/scripts/{script_id}", org_id=org_id, body=body)
    if err := _check_error(data):
        return err
    return f"YouTube script #{script_id} updated."


@mcp.tool()
async def pressroom_youtube_delete(org_id: int, script_id: int) -> str:
    """Delete a YouTube script.

    Args:
        org_id: The organization ID.
        script_id: The YouTube script ID to delete.
    """
    data = await api_delete(f"/api/youtube/scripts/{script_id}", org_id=org_id)
    if err := _check_error(data):
        return err
    return f"YouTube script #{script_id} deleted."


@mcp.tool()
async def pressroom_youtube_render(org_id: int, script_id: int) -> str:
    """Render a YouTube script into a video via Remotion.

    Args:
        org_id: The organization ID.
        script_id: The YouTube script ID to render.
    """
    data = await api_post(f"/api/youtube/scripts/{script_id}/render", org_id=org_id)
    if err := _check_error(data):
        return err
    return json.dumps(data, indent=2, default=str)


@mcp.tool()
async def pressroom_youtube_publish_video(org_id: int, script_id: int) -> str:
    """Publish a rendered YouTube video.

    Args:
        org_id: The organization ID.
        script_id: The YouTube script ID to publish.
    """
    data = await api_post(f"/api/youtube/scripts/{script_id}/publish-rendered", org_id=org_id)
    if err := _check_error(data):
        return err
    return json.dumps(data, indent=2, default=str)


# ─── Medium tools ────────────────────────────────────────────────────────────

@mcp.tool()
async def pressroom_medium_publish(org_id: int, content_id: int) -> str:
    """Publish a content item to Medium.

    Args:
        org_id: The organization ID.
        content_id: The content item ID to publish to Medium.
    """
    data = await api_post("/api/medium/publish", org_id=org_id, body={"content_id": content_id})
    if err := _check_error(data):
        return err
    return json.dumps(data, indent=2, default=str)


# ─── Slack tools ─────────────────────────────────────────────────────────────

@mcp.tool()
async def pressroom_slack_test(org_id: int) -> str:
    """Send a test message to the org's configured Slack channel.

    Args:
        org_id: The organization ID.
    """
    data = await api_post("/api/slack/test", org_id=org_id)
    if err := _check_error(data):
        return err
    return "Slack test message sent successfully."


@mcp.tool()
async def pressroom_slack_notify(org_id: int, content_id: int) -> str:
    """Send a Slack notification for a specific content item.

    Args:
        org_id: The organization ID.
        content_id: The content item ID to notify about.
    """
    data = await api_post(f"/api/slack/notify/{content_id}", org_id=org_id)
    if err := _check_error(data):
        return err
    return f"Slack notification sent for content #{content_id}."


@mcp.tool()
async def pressroom_slack_notify_queue(org_id: int) -> str:
    """Send Slack notifications for all queued content items.

    Args:
        org_id: The organization ID.
    """
    data = await api_post("/api/slack/notify-queue", org_id=org_id)
    if err := _check_error(data):
        return err
    return json.dumps(data, indent=2, default=str)


# ─── Token usage tools ──────────────────────────────────────────────────────

@mcp.tool()
async def pressroom_usage(org_id: int) -> str:
    """Get current token usage summary for an org.

    Args:
        org_id: The organization ID.
    """
    data = await api_get("/api/usage", org_id=org_id)
    if err := _check_error(data):
        return err
    return json.dumps(data, indent=2, default=str)


@mcp.tool()
async def pressroom_usage_history(org_id: int) -> str:
    """Get token usage history for an org.

    Args:
        org_id: The organization ID.
    """
    data = await api_get("/api/usage/history", org_id=org_id)
    if err := _check_error(data):
        return err
    return json.dumps(data, indent=2, default=str)


# ─── Import tools ────────────────────────────────────────────────────────────

@mcp.tool()
async def pressroom_import_paste(org_id: int, text: str, channel: str = "linkedin") -> str:
    """Import content by pasting text directly. Creates a content item from raw text.

    Args:
        org_id: The organization ID.
        text: The text content to import.
        channel: Target channel (default "linkedin").
    """
    data = await api_post(
        "/api/import/paste",
        org_id=org_id,
        body={"text": text, "channel": channel},
    )
    if err := _check_error(data):
        return err
    return json.dumps(data, indent=2, default=str)


# ─── Activity log tools ─────────────────────────────────────────────────────

@mcp.tool()
async def pressroom_log(org_id: int, limit: int = 20) -> str:
    """Get the activity log for an org.

    Args:
        org_id: The organization ID.
        limit: Max log entries to return (default 20).
    """
    data = await api_get("/api/log", org_id=org_id, params={"limit": limit})
    if err := _check_error(data):
        return err
    if not data:
        return "No activity log entries."
    rows = []
    for entry in data:
        rows.append(
            f"  [{entry.get('created_at', '?')}] {entry.get('action', '?')} — {entry.get('detail', '')}"
        )
    return f"{len(data)} log entries:\n" + "\n".join(rows)


# ─── Company audit tools ────────────────────────────────────────────────────

@mcp.tool()
async def pressroom_company_audit(org_id: int) -> str:
    """Run a full company audit — checks content, SEO, brand, and team completeness.

    Args:
        org_id: The organization ID.
    """
    data = await api_post("/api/company/audit", org_id=org_id)
    if err := _check_error(data):
        return err
    return json.dumps(data, indent=2, default=str)


# ─── Scoreboard enhancement tools ───────────────────────────────────────────

@mcp.tool()
async def pressroom_team_activity(org_id: int) -> str:
    """Get team activity metrics from the scoreboard.

    Args:
        org_id: The organization ID.
    """
    data = await api_get(f"/api/scoreboard/{org_id}/team-activity", org_id=org_id)
    if err := _check_error(data):
        return err
    return json.dumps(data, indent=2, default=str)


# ─── Data source tools ──────────────────────────────────────────────────────

@mcp.tool()
async def pressroom_list_datasources(org_id: int) -> str:
    """List data sources for an org.

    Args:
        org_id: The organization ID.
    """
    data = await api_get("/api/datasources", org_id=org_id)
    if err := _check_error(data):
        return err
    if not data:
        return "No data sources configured."
    rows = []
    for ds in data:
        rows.append(
            f"  #{ds.get('id', '?')} [{ds.get('type', '?')}] {ds.get('name', '?')}"
        )
    return f"{len(data)} data sources:\n" + "\n".join(rows)


@mcp.tool()
async def pressroom_create_datasource(
    org_id: int, name: str, type: str, config: dict[str, Any]
) -> str:
    """Create a new data source for an org.

    Args:
        org_id: The organization ID.
        name: Data source name.
        type: Data source type.
        config: Configuration dict for the data source.
    """
    data = await api_post(
        "/api/datasources",
        org_id=org_id,
        body={"name": name, "type": type, "config": config},
    )
    if err := _check_error(data):
        return err
    return f"Data source created: #{data.get('id', '?')} [{data.get('type', '?')}] {data.get('name', '?')}"


@mcp.tool()
async def pressroom_test_datasource(org_id: int, ds_id: int) -> str:
    """Test a data source connection.

    Args:
        org_id: The organization ID.
        ds_id: The data source ID to test.
    """
    data = await api_post(f"/api/datasources/{ds_id}/test", org_id=org_id)
    if err := _check_error(data):
        return err
    return json.dumps(data, indent=2, default=str)


@mcp.tool()
async def pressroom_delete_datasource(org_id: int, ds_id: int) -> str:
    """Delete a data source.

    Args:
        org_id: The organization ID.
        ds_id: The data source ID to delete.
    """
    data = await api_delete(f"/api/datasources/{ds_id}", org_id=org_id)
    if err := _check_error(data):
        return err
    return f"Data source #{ds_id} deleted."


# ─── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    mcp.run()
