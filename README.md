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

## Available Tools (101)

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
- `pressroom_spike_content(org_id, content_ids)` — Spike (reject) content items
- `pressroom_edit_content(org_id, content_id, body="", headline="")` — Edit content body or headline
- `pressroom_humanize_content(org_id, content_id)` — Run humanizer on content
- `pressroom_schedule_content(org_id, content_id, publish_at)` — Schedule content for future publish

### Content Performance
- `pressroom_content_performance(org_id)` — Get performance metrics for published content
- `pressroom_fetch_performance(org_id, content_id)` — Fetch latest performance for a content item

### Signals
- `pressroom_list_signals(org_id, limit=50)` — List wire signals

### Story Workbench
- `pressroom_list_stories(org_id, limit=20)` — List editorial stories
- `pressroom_create_story(org_id, title, angle="", editorial_notes="", signal_ids=None)` — Create a story
- `pressroom_get_story(org_id, story_id)` — Get story with signals and notes
- `pressroom_add_signal_to_story(org_id, story_id, signal_id, editor_notes="")` — Attach signal to story
- `pressroom_generate_from_story(org_id, story_id, channels=None, team_member_id=None)` — Generate content from story
- `pressroom_discover_signals(org_id, story_id, mode="web")` — Discover signals for a story

### Wire (Company-Owned Sources)
- `pressroom_list_wire_sources(org_id)` — List Wire sources
- `pressroom_create_wire_source(org_id, type, name, config=None)` — Create a Wire source
- `pressroom_fetch_wire(org_id, wire_source_id=None)` — Fetch signals from Wire sources
- `pressroom_list_wire_signals(org_id, limit=40, type="")` — List Wire signals

### SIGINT Sources (Global Library)
- `pressroom_list_sources(type="", active_only=True)` — List global source library
- `pressroom_create_source(type, name, config=None, category_tags=None, fetch_interval_hours=6)` — Create a global source
- `pressroom_sweep_sources(org_id, source_ids=None)` — Sweep sources for signals
- `pressroom_get_feed(org_id, limit=40, min_score=None)` — Get relevance-scored SIGINT feed

### Audit
- `pressroom_audit(org_id, domain="", deep=True)` — Run SEO audit
- `pressroom_scoreboard()` — All orgs ranked by SEO score
- `pressroom_audit_history(org_id, audit_type="", limit=20)` — Past audit results

### Company Audit
- `pressroom_company_audit(org_id)` — Run full company audit

### SEO PR Pipeline
- `pressroom_seo_pr_run(org_id, repo_url, domain="", base_branch="main")` — Start SEO PR pipeline
- `pressroom_seo_pr_list(org_id)` — List SEO PR runs
- `pressroom_seo_pr_status(org_id, run_id)` — Get SEO PR run status

### Competitive Intelligence
- `pressroom_competitive_scan(org_id, competitor_urls)` — Run competitive scan
- `pressroom_competitive_results(org_id)` — Get stored competitive results

### AI Visibility
- `pressroom_ai_visibility_scan(org_id)` — Scan AI models for citations
- `pressroom_ai_visibility_results(org_id)` — Get AI visibility results
- `pressroom_ai_visibility_questions(org_id, questions)` — Set visibility tracking questions

### Analytics
- `pressroom_analytics(org_id)` — Get analytics dashboard

### Scoreboard
- `pressroom_team_activity(org_id)` — Get team activity metrics from scoreboard

### YouTube Studio
- `pressroom_youtube_script(org_id, content_id=None, brief="")` — Generate YouTube script
- `pressroom_youtube_list(org_id)` — List scripts
- `pressroom_youtube_export(script_id)` — Export Remotion JSON package
- `pressroom_youtube_update(org_id, script_id, title="", hook="")` — Update script title or hook
- `pressroom_youtube_delete(org_id, script_id)` — Delete a YouTube script
- `pressroom_youtube_render(org_id, script_id)` — Render script to video via Remotion
- `pressroom_youtube_publish_video(org_id, script_id)` — Publish rendered video

### Blog Management
- `pressroom_blog_scrape(org_id, url)` — Scrape and import a blog post
- `pressroom_blog_list(org_id)` — List blog posts
- `pressroom_blog_delete(org_id, post_id)` — Delete a blog post

### Google Search Console
- `pressroom_gsc_status(org_id)` — Check GSC connection status
- `pressroom_gsc_properties(org_id)` — List available GSC properties
- `pressroom_gsc_set_property(org_id, property_url)` — Set active GSC property
- `pressroom_gsc_analytics(org_id, days=28)` — Get GSC analytics data
- `pressroom_gsc_summary(org_id)` — Get GSC performance summary
- `pressroom_gsc_blog_performance(org_id)` — Get GSC blog post performance
- `pressroom_gsc_inspect_url(org_id, url)` — Inspect URL indexing status

### Site Properties
- `pressroom_list_properties(org_id)` — List site properties
- `pressroom_create_property(org_id, name, value, prop_type="domain")` — Create a property
- `pressroom_update_property(org_id, property_id, value)` — Update a property
- `pressroom_delete_property(org_id, property_id)` — Delete a property

### Brand
- `pressroom_brand_scrape(org_id, domain)` — Scrape brand info from domain
- `pressroom_brand_get(org_id)` — Get brand profile

### Assets
- `pressroom_list_assets(org_id, asset_type="")` — List assets
- `pressroom_create_asset(org_id, name, url, asset_type)` — Create an asset
- `pressroom_delete_asset(org_id, asset_id)` — Delete an asset

### Skills
- `pressroom_list_skills()` — List available skills
- `pressroom_get_skill(skill_name)` — Get skill content
- `pressroom_invoke_skill(skill_name, input_text)` — Run text through a skill

### Team
- `pressroom_list_team(org_id)` — List team members
- `pressroom_add_team_member(org_id, name, title="", bio="", email="", linkedin_url="", expertise_tags=None)` — Add team member
- `pressroom_discover_team(org_id)` — Auto-discover team members
- `pressroom_update_team_member(org_id, member_id, name="", title="", bio="")` — Update team member details
- `pressroom_analyze_voice(org_id, member_id)` — Analyze member's writing voice
- `pressroom_team_gist_check(org_id)` — Check gist status for all members
- `pressroom_generate_gist(org_id, member_id)` — Generate author bio page
- `pressroom_publish_gist(org_id, member_id)` — Publish author bio page

### Settings
- `pressroom_get_settings(org_id)` — Get all org settings
- `pressroom_update_settings(org_id, settings)` — Update org settings
- `pressroom_connection_status(org_id)` — Check service connection status

### Onboarding
- `pressroom_onboard(org_id, domain, extra_context="")` — Onboard a company
- `pressroom_onboard_apply(org_id, profile)` — Apply onboarding profile
- `pressroom_onboard_status(org_id)` — Check onboarding status

### Email
- `pressroom_compose_email(org_id, content_id)` — Compose email draft from content
- `pressroom_list_email_drafts(org_id, status="", limit=20)` — List email drafts

### Medium
- `pressroom_medium_publish(org_id, content_id)` — Publish content to Medium

### Slack
- `pressroom_slack_test(org_id)` — Send test Slack message
- `pressroom_slack_notify(org_id, content_id)` — Send Slack notification for content
- `pressroom_slack_notify_queue(org_id)` — Notify Slack about queued content

### Token Usage
- `pressroom_usage(org_id)` — Get current token usage
- `pressroom_usage_history(org_id)` — Get token usage history

### Imports
- `pressroom_import_paste(org_id, text, channel="linkedin")` — Import content from pasted text

### Activity Log
- `pressroom_log(org_id, limit=20)` — Get activity log

### Data Sources
- `pressroom_list_datasources(org_id)` — List data sources
- `pressroom_create_datasource(org_id, name, type, config)` — Create a data source
- `pressroom_test_datasource(org_id, ds_id)` — Test data source connection
- `pressroom_delete_datasource(org_id, ds_id)` — Delete a data source

## Requirements

- Pressroom backend running at `PRESSROOM_URL` (default: `http://localhost:8000`)
- Python 3.10+
