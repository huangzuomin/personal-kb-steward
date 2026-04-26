"""Generate an HTML demo report for personal-kb-steward.

This script parses the review queue and recent plan/run manifests in the
configured .openclaw directory, and generates a stunning, single-file HTML
report. It demonstrates the 'Knowledge Production' capabilities to the user.
"""
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.config import config, plan_dir, review_queue_path, runs_dir
from core.review_queue import load_queue

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Knowledge Steward - Demo Report</title>
    <style>
        :root {
            --bg-color: #0f172a;
            --surface-color: #1e293b;
            --border-color: #334155;
            --text-primary: #f8fafc;
            --text-secondary: #94a3b8;
            --accent-color: #3b82f6;
            --accent-hover: #60a5fa;
            --success: #10b981;
            --warning: #f59e0b;
            --danger: #ef4444;
        }

        body {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            background-color: var(--bg-color);
            color: var(--text-primary);
            line-height: 1.6;
            margin: 0;
            padding: 2rem;
        }

        .container {
            max-width: 1000px;
            margin: 0 auto;
        }

        header {
            text-align: center;
            margin-bottom: 3rem;
            animation: fadeInDown 0.8s ease-out;
        }

        h1 {
            font-size: 2.5rem;
            margin-bottom: 0.5rem;
            background: linear-gradient(135deg, #60a5fa, #a78bfa);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }

        .subtitle {
            color: var(--text-secondary);
            font-size: 1.1rem;
        }

        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 1.5rem;
            margin-bottom: 3rem;
        }

        .stat-card {
            background-color: var(--surface-color);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 1.5rem;
            text-align: center;
            transition: transform 0.3s ease, box-shadow 0.3s ease;
            animation: fadeIn 0.8s ease-out backwards;
        }

        .stat-card:hover {
            transform: translateY(-5px);
            box-shadow: 0 10px 25px rgba(0,0,0,0.5);
            border-color: var(--accent-color);
        }

        .stat-value {
            font-size: 2.5rem;
            font-weight: bold;
            color: var(--accent-hover);
            margin-bottom: 0.5rem;
        }

        .stat-label {
            color: var(--text-secondary);
            font-size: 0.9rem;
            text-transform: uppercase;
            letter-spacing: 0.05em;
        }

        .section {
            background-color: var(--surface-color);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 2rem;
            margin-bottom: 2rem;
            animation: slideUp 0.8s ease-out backwards;
        }

        .section h2 {
            margin-top: 0;
            border-bottom: 1px solid var(--border-color);
            padding-bottom: 1rem;
            color: var(--text-primary);
        }

        table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 1rem;
        }

        th, td {
            padding: 1rem;
            text-align: left;
            border-bottom: 1px solid var(--border-color);
        }

        th {
            color: var(--text-secondary);
            font-weight: 600;
        }

        tr:hover {
            background-color: rgba(255,255,255,0.02);
        }

        .badge {
            display: inline-block;
            padding: 0.25rem 0.75rem;
            border-radius: 9999px;
            font-size: 0.85rem;
            font-weight: 500;
        }

        .badge.success { background-color: rgba(16, 185, 129, 0.2); color: var(--success); }
        .badge.warning { background-color: rgba(245, 158, 11, 0.2); color: var(--warning); }
        .badge.danger { background-color: rgba(239, 68, 68, 0.2); color: var(--danger); }
        .badge.info { background-color: rgba(59, 130, 246, 0.2); color: var(--accent-hover); }

        pre {
            background-color: #0f172a;
            padding: 1rem;
            border-radius: 8px;
            overflow-x: auto;
            color: #e2e8f0;
            font-size: 0.9rem;
            border: 1px solid var(--border-color);
        }

        @keyframes fadeInDown {
            from { opacity: 0; transform: translateY(-20px); }
            to { opacity: 1; transform: translateY(0); }
        }

        @keyframes fadeIn {
            from { opacity: 0; }
            to { opacity: 1; }
        }

        @keyframes slideUp {
            from { opacity: 0; transform: translateY(20px); }
            to { opacity: 1; transform: translateY(0); }
        }

        /* Delay cascade for grid items */
        .stats-grid .stat-card:nth-child(1) { animation-delay: 0.1s; }
        .stats-grid .stat-card:nth-child(2) { animation-delay: 0.2s; }
        .stats-grid .stat-card:nth-child(3) { animation-delay: 0.3s; }
        .stats-grid .stat-card:nth-child(4) { animation-delay: 0.4s; }
        .section:nth-of-type(1) { animation-delay: 0.5s; }
        .section:nth-of-type(2) { animation-delay: 0.6s; }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>Knowledge Steward Demo Report</h1>
            <div class="subtitle">Generated dynamically from your local knowledge base runtime</div>
        </header>

        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-value">{total_plans}</div>
                <div class="stat-label">Execution Plans</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{total_runs}</div>
                <div class="stat-label">Applied Runs</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{pending_reviews}</div>
                <div class="stat-label">Pending Reviews</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{total_pages}</div>
                <div class="stat-label">Pages Generated</div>
            </div>
        </div>

        <div class="section">
            <h2>Manual Review Queue</h2>
            {queue_html}
        </div>

        <div class="section">
            <h2>Recent Plans & Runs</h2>
            {plans_html}
        </div>
    </div>
</body>
</html>
"""

def generate_report():
    cfg = config()
    queue_file = review_queue_path(cfg)
    queue_items = load_queue(queue_file) if queue_file.exists() else []
    
    pending = [q for q in queue_items if q.get("status") == "pending"]
    
    p_dir = plan_dir(cfg)
    r_dir = runs_dir(cfg)
    
    plans = list(p_dir.glob("*.json")) if p_dir.exists() else []
    runs = list(r_dir.glob("*.json")) if r_dir.exists() else []
    
    total_pages = 0
    plans_data = []
    
    # Process plans
    for p in sorted(plans, reverse=True)[:10]:
        try:
            data = json.loads(p.read_text("utf-8"))
            pages = len(data.get("planned_pages", []))
            total_pages += pages
            plans_data.append({
                "id": p.stem,
                "entry": data.get("entry", "N/A"),
                "task": data.get("task", "N/A"),
                "pages": pages,
                "is_applied": (r_dir / p.name).exists()
            })
        except Exception:
            pass

    # Build Queue HTML
    if not pending:
        queue_html = "<p style='color: var(--text-secondary);'>Queue is currently empty. All items processed.</p>"
    else:
        queue_html = "<table><tr><th>ID</th><th>Type</th><th>Task</th><th>Risk</th><th>Reason</th></tr>"
        for q in pending[:10]:
            risk = q.get("risk", "unknown")
            badge_class = "danger" if risk in ("P0", "P1") else "warning" if risk == "P2" else "info"
            queue_html += f"""
            <tr>
                <td><code>{q.get('id', 'N/A')[:8]}</code></td>
                <td><span class="badge {badge_class}">{q.get('type', 'N/A')}</span></td>
                <td>{q.get('task', 'N/A')}</td>
                <td>{risk}</td>
                <td>{q.get('reason', 'N/A')}</td>
            </tr>
            """
        queue_html += "</table>"
        if len(pending) > 10:
            queue_html += f"<p style='margin-top:1rem; color: var(--text-secondary);'>...and {len(pending) - 10} more items.</p>"

    # Build Plans HTML
    if not plans_data:
        plans_html = "<p style='color: var(--text-secondary);'>No execution plans found.</p>"
    else:
        plans_html = "<table><tr><th>Plan ID</th><th>Entry</th><th>Task</th><th>Pages</th><th>Status</th></tr>"
        for p in plans_data:
            status_badge = '<span class="badge success">Applied</span>' if p["is_applied"] else '<span class="badge warning">Dry Run</span>'
            plans_html += f"""
            <tr>
                <td><code>{p['id'].split('-')[-1][:8]}</code></td>
                <td>{p['entry']}</td>
                <td>{p['task']}</td>
                <td>{p['pages']}</td>
                <td>{status_badge}</td>
            </tr>
            """
        plans_html += "</table>"

    html = HTML_TEMPLATE.replace("{total_plans}", str(len(plans))) \
        .replace("{total_runs}", str(len(runs))) \
        .replace("{pending_reviews}", str(len(pending))) \
        .replace("{total_pages}", str(total_pages)) \
        .replace("{queue_html}", queue_html) \
        .replace("{plans_html}", plans_html)
    
    out_path = ROOT / "demo_report.html"
    out_path.write_text(html, encoding="utf-8")
    print(f"Report successfully generated at: {out_path}")
    return 0

if __name__ == "__main__":
    sys.exit(generate_report())
