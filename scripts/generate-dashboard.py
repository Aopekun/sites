#!/usr/bin/env python3
import html
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "dashboardagents" / "dashagents" / "index.html"


def run_json(cmd):
    return json.loads(subprocess.check_output(cmd, text=True))


def fmt_dt(ms):
    if not ms:
        return "—"
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def fmt_num(n):
    if n is None:
        return "—"
    return f"{int(n):,}".replace(",", " ")


def esc(v):
    return html.escape(str(v if v is not None else "—"))


def collect():
    status = run_json(["openclaw", "status", "--json", "--usage"])
    models_status = run_json(["openclaw", "models", "status", "--json"])
    models_list = run_json(["openclaw", "models", "list", "--json"])

    recent_by_agent = {}
    for entry in status.get("sessions", {}).get("byAgent", []):
        recent = entry.get("recent") or []
        if recent:
            recent_by_agent[entry.get("agentId")] = recent[0]

    configured_agents = [a.get("agentId") for a in status.get("heartbeat", {}).get("agents", []) if a.get("agentId")]
    if not configured_agents:
        configured_agents = sorted(recent_by_agent)

    resolved_default = models_status.get("resolvedDefault") or models_status.get("defaultModel") or status.get("sessions", {}).get("defaults", {}).get("model")
    agents = []
    for aid in configured_agents:
        recent = recent_by_agent.get(aid) or {}
        agents.append({
            "id": aid,
            "model": recent.get("model") or resolved_default,
            "lastUpdatedAtText": fmt_dt(recent.get("updatedAt")) if recent else "—",
            "contextTokens": recent.get("contextTokens"),
            "totalTokens": recent.get("totalTokens"),
            "percentUsed": recent.get("percentUsed"),
        })

    providers = []
    for p in status.get("usage", {}).get("providers", []):
        providers.append({
            "displayName": p.get("displayName") or p.get("provider"),
            "provider": p.get("provider"),
            "plan": p.get("plan"),
            "windows": [{
                "label": w.get("label"),
                "leftPercent": None if w.get("usedPercent") is None else max(0, 100 - int(w.get("usedPercent") or 0)),
                "resetAtText": fmt_dt(w.get("resetAt")),
            } for w in p.get("windows", [])],
        })

    oauth_map = {p.get("provider"): p for p in models_status.get("auth", {}).get("oauth", {}).get("providers", []) if isinstance(p, dict)}
    auths = []
    for p in models_status.get("auth", {}).get("providers", []):
        provider = p.get("provider")
        auths.append({
            "provider": provider,
            "sourceKind": (p.get("effective") or {}).get("kind") or "—",
            "status": (oauth_map.get(provider) or {}).get("status") or "static",
        })

    return {
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "agentsCount": len(agents),
        "modelsCount": models_list.get("count", len(models_list.get("models", []))),
        "sessionCount": status.get("sessions", {}).get("count"),
        "defaultModel": resolved_default,
        "fallbacks": models_status.get("fallbacks") or [],
        "usageUpdatedAt": fmt_dt(status.get("usage", {}).get("updatedAt")),
        "agents": agents,
        "models": models_list.get("models", []),
        "providers": providers,
        "auths": auths,
    }


def render(d):
    agent_rows = "".join(
        f"<tr><td><strong>{esc(a['id'])}</strong></td><td><span class='pill mono'>{esc(a['model'])}</span></td>" +
        (f"<td><div class='barrow'><div class='bar'><div class='fill' style='width:{int(a['percentUsed'])}%'></div></div><div>{int(a['percentUsed'])}%</div></div><div class='muted'>{fmt_num(a['totalTokens'])} / {fmt_num(a['contextTokens'])} токенов</div></td>" if a.get('percentUsed') is not None else "<td><span class='muted'>нет данных</span></td>") +
        f"<td>{esc(a['lastUpdatedAtText'])}</td></tr>"
        for a in d["agents"]
    )
    quota_blocks = "".join(
        f"<div class='quota-item'><div class='quota-row'><div><strong>{esc(p['displayName'])}</strong> <span class='muted'>({esc(p['provider'])})</span></div><div class='pill'>{esc(p.get('plan') or 'plan n/a')}</div></div>" +
        "".join(f"<div class='quota-window'><div class='quota-row'><div>{esc(w['label'])}</div><div>{esc(w['leftPercent'])}% left</div></div><div class='bar'><div class='fill' style='width:{w['leftPercent'] or 0}%'></div></div><div class='muted small'>Сброс: {esc(w['resetAtText'])}</div></div>" for w in p["windows"]) +
        "</div>" for p in d["providers"]
    ) or "<div class='muted'>Нет quota-данных</div>"
    model_rows = "".join(f"<tr><td><span class='mono'>{esc(m.get('key'))}</span></td><td>{esc(m.get('name'))}</td><td>{fmt_num(m.get('contextWindow'))}</td><td>{'✅ available' if m.get('available') else '—'}</td></tr>" for m in d["models"])
    auth_rows = "".join(f"<tr><td><strong>{esc(a['provider'])}</strong></td><td>{esc(a['sourceKind'])}</td><td>{esc(a['status'])}</td></tr>" for a in d["auths"])
    fallbacks = ", ".join(d["fallbacks"]) if d["fallbacks"] else "—"
    return f"""<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <meta http-equiv="refresh" content="60" />
  <title>OpenClaw Public Dashboard</title>
  <style>
    :root{{--bg:#0b1020;--panel:#121a30;--muted:#8da2c0;--text:#eaf1ff;--accent:#6ea8fe;--line:#223252;--soft:#0e162b;--good:#33d17a;--warn:#f6c453;--bad:#ff6b6b}}
    *{{box-sizing:border-box}} body{{margin:0;font-family:Inter,system-ui,-apple-system,Segoe UI,Roboto,sans-serif;background:linear-gradient(180deg,#0a0f1e,#10182b);color:var(--text)}}
    .wrap{{max-width:1320px;margin:0 auto;padding:24px}} h1{{margin:0 0 8px;font-size:30px}} .muted,.sub{{color:var(--muted)}} .small{{font-size:12px;margin-top:6px}}
    .topbar{{display:flex;justify-content:space-between;gap:14px;align-items:flex-start;margin-bottom:18px}} .actions{{display:flex;gap:10px;flex-wrap:wrap;align-items:center}}
    .btn{{appearance:none;border:1px solid var(--line);background:#1d2b4b;color:#eaf1ff;border-radius:12px;padding:10px 14px;font-weight:700;cursor:pointer;text-decoration:none}} .btn:hover{{border-color:#3b5280;background:#25385f}} .btn.primary{{background:linear-gradient(90deg,var(--accent),#9fd0ff);color:#08101f;border:0}} .btn:disabled{{opacity:.55;cursor:wait}}
    #refreshStatus{{font-size:12px;color:var(--muted);max-width:260px}}
    .grid{{display:grid;gap:16px}} .cards{{grid-template-columns:repeat(4,minmax(0,1fr))}} .two{{grid-template-columns:1.2fr .8fr}}
    .panel{{background:rgba(18,26,48,.9);border:1px solid var(--line);border-radius:18px;padding:18px;box-shadow:0 12px 30px rgba(0,0,0,.2)}} .label{{color:var(--muted);font-size:13px;margin-bottom:10px}} .value{{font-size:28px;font-weight:700}}
    table{{width:100%;border-collapse:collapse}} th,td{{text-align:left;padding:12px 10px;border-bottom:1px solid var(--line);vertical-align:top;font-size:14px}} th{{color:#b8cae6;font-size:13px}}
    .pill{{display:inline-block;padding:4px 10px;border-radius:999px;background:#1d2b4b;color:#dbe8ff;font-size:12px;margin:2px 6px 2px 0}} .mono{{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}}
    .barrow{{display:flex;align-items:center;gap:10px}} .bar{{height:10px;background:#1a2743;border-radius:999px;overflow:hidden;min-width:160px}} .fill{{height:100%;background:linear-gradient(90deg,var(--accent),#9fd0ff);border-radius:999px}}
    .quota-item{{padding:14px;border:1px solid var(--line);border-radius:14px;background:var(--soft);margin-bottom:12px}} .quota-row{{display:flex;justify-content:space-between;gap:16px;align-items:center;margin-bottom:8px}} .quota-window{{margin:10px 0 12px}}
    @media (max-width:1100px){{.cards,.two{{grid-template-columns:1fr 1fr}}}} @media (max-width:760px){{.cards,.two{{grid-template-columns:1fr}}.wrap{{padding:16px}}h1{{font-size:24px}}.topbar{{display:block}}.actions{{margin-top:14px}}}}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="topbar">
      <div>
        <h1>OpenClaw Public Dashboard</h1>
        <div class="sub">Публичная безопасная версия · автообновление страницы каждые 60 сек</div>
        <div class="muted" style="margin:10px 0 0">Обновлено {esc(d['generatedAt'])}</div>
      </div>
      <div class="actions">
        <button class="btn primary" type="button" id="regenerateBtn">Перегенерировать данные</button>
        <button class="btn" type="button" onclick="location.reload()">Обновить страницу</button>
        <div id="refreshStatus">Данные обновляются через VPS и GitHub/Cloudflare deploy.</div>
      </div>
    </div>
    <div class="grid cards">
      <div class="panel"><div class="label">Агенты</div><div class="value">{d['agentsCount']}</div></div>
      <div class="panel"><div class="label">Подключённые модели</div><div class="value">{d['modelsCount']}</div></div>
      <div class="panel"><div class="label">Модель по умолчанию</div><div class="value mono" style="font-size:22px">{esc(d['defaultModel'])}</div><div class="muted">Fallback: {esc(fallbacks)}</div></div>
      <div class="panel"><div class="label">Сессии</div><div class="value">{d['sessionCount']}</div></div>
    </div>
    <div class="grid two" style="margin-top:16px"><div class="panel"><h2>Агенты и модели</h2><table><thead><tr><th>Агент</th><th>Модель</th><th>Текущий контекст</th><th>Обновлено</th></tr></thead><tbody>{agent_rows}</tbody></table></div><div class="panel"><h2>Лимиты</h2><div class="muted">Лимиты видны по провайдеру/аккаунту. Usage обновлён: {esc(d['usageUpdatedAt'])}</div><div style="margin-top:12px">{quota_blocks}</div></div></div>
    <div class="grid two" style="margin-top:16px"><div class="panel"><h2>Подключённые модели</h2><table><thead><tr><th>Ключ</th><th>Имя</th><th>Context window</th><th>Статус</th></tr></thead><tbody>{model_rows}</tbody></table></div><div class="panel"><h2>Провайдеры</h2><table><thead><tr><th>Provider</th><th>Источник</th><th>Статус</th></tr></thead><tbody>{auth_rows}</tbody></table></div></div>
  </div>
  <script>
    const btn = document.getElementById('regenerateBtn');
    const status = document.getElementById('refreshStatus');
    btn?.addEventListener('click', async () => {{
      btn.disabled = true;
      status.textContent = 'Запускаю перегенерацию…';
      try {{
        const res = await fetch('https://dashrefresh.aiopekun.site/refresh', {{ method: 'POST' }});
        const data = await res.json().catch(() => ({{}}));
        if (!res.ok || data.ok === false) throw new Error(data.error || `HTTP ${{res.status}}`);
        status.textContent = data.changed ? 'Готово, жду деплой Cloudflare…' : 'Данные уже актуальны, обновляю страницу…';
        setTimeout(() => location.reload(), data.changed ? 18000 : 2500);
      }} catch (err) {{
        status.textContent = 'Ошибка обновления: ' + (err?.message || err);
        btn.disabled = false;
      }}
    }});
  </script>
</body>
</html>
"""


def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(render(collect()), encoding="utf-8")
    print(OUT)


if __name__ == "__main__":
    main()
