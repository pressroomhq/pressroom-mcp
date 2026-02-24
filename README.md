# Pressroom MCP Server

Run the full Pressroom pipeline headless — no browser, no UI.

Any Claude Code session or MCP-compatible client can scout, generate, audit, publish, and more from a prompt.

## Setup

```bash
cd /home/captain/data/projects/pressroom-mcp
./install.sh
```

Or manually:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env if your Pressroom backend is not on localhost:8000
```

## Usage

### Run standalone (stdio transport)

```bash
source venv/bin/activate
python server.py
```

### Add to Claude Code

Add to your `~/.claude/settings.json` or project `.claude/settings.json`:

```json
{
  "mcpServers": {
    "pressroom": {
      "command": "/home/captain/data/projects/pressroom-mcp/venv/bin/python",
      "args": ["/home/captain/data/projects/pressroom-mcp/server.py"],
      "env": {
        "PRESSROOM_URL": "http://localhost:8000"
      }
    }
  }
}
```

## Available Tools

### Org Management
- `pressroom_list_orgs()` — List all organizations
- `pressroom_get_org(org_id)` — Get org details

### Pipeline
- `pressroom_scout(org_id, since_hours=24)` — Pull signals from sources
- `pressroom_generate(org_id, channels=None)` — Generate content from signals
- `pressroom_approve(org_id, content_ids)` — Approve content items
- `pressroom_publish(org_id)` — Publish approved content
- `pressroom_full_pipeline(org_id, channels=None)` — Scout + Generate in one shot

### Content
- `pressroom_list_content(org_id, status="queued", limit=50)` — List content items
- `pressroom_get_content(content_id)` — Get full content item

### Signals
- `pressroom_list_signals(org_id, limit=50)` — List wire signals

### Audit
- `pressroom_audit(org_id, domain="", deep=True)` — Run SEO audit
- `pressroom_scoreboard()` — All orgs ranked by SEO score
- `pressroom_audit_history(org_id, audit_type="", limit=20)` — Past audit results

### YouTube Studio
- `pressroom_youtube_script(org_id, content_id=None, brief="")` — Generate YouTube script
- `pressroom_youtube_list(org_id)` — List scripts
- `pressroom_youtube_export(script_id)` — Export Remotion JSON package

### Skills
- `pressroom_list_skills()` — List available skills
- `pressroom_get_skill(skill_name)` — Get skill content
- `pressroom_invoke_skill(skill_name, input_text)` — Run text through a skill

## Requirements

- Pressroom backend running at `PRESSROOM_URL` (default: `http://localhost:8000`)
- Python 3.10+
