#!/usr/bin/env python3
"""Artifact and HTML generation for the VS2 real-hardware acceptance test."""

import html
import json
import re
from datetime import datetime
from pathlib import Path

import numpy as np


def timestamp_now():
    return datetime.now().astimezone()


def safe_name(value):
    cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "-", value.strip()).strip("-._")
    return cleaned or "vs2-hardware"


def create_run_directory(root, name="vs2-hardware", now=None):
    """Create a timestamped, collision-safe report directory."""
    root = Path(root)
    timestamp = (now or timestamp_now()).strftime("%Y%m%d-%H%M%S")
    stem = "%s-%s" % (timestamp, safe_name(name))
    candidate = root / stem
    suffix = 2
    while candidate.exists():
        candidate = root / ("%s-%02d" % (stem, suffix))
        suffix += 1
    (candidate / "screenshots").mkdir(parents=True)
    return candidate


def _render_polar(raw, size):
    from pov_screenshot import render_polar
    return render_polar(raw, size=size)


def save_frame_screenshot(raw, output, size=640):
    """Save one physical APA102 frame as a polar PNG."""
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    image = _render_polar(raw, size)
    image.save(output, format="PNG", optimize=True)
    return output


def _aligned_expected(expected, shift):
    array = np.frombuffer(expected, dtype=np.uint8).reshape(256, 54, 4)
    return np.roll(array, shift, axis=0)


def save_parity_screenshot(captured, expected, metrics, output, panel_size=400):
    """Save actual/oracle/difference panels for a rendering parity sample."""
    from PIL import Image, ImageDraw

    captured_array = np.frombuffer(captured, dtype=np.uint8).reshape(256, 54, 4)
    expected_array = _aligned_expected(expected, metrics["shift"])
    different = np.any(captured_array != expected_array, axis=2)
    different[:, 0] = False  # shared centre LED is intentionally not compared

    difference_frame = np.zeros_like(captured_array)
    difference_frame[:, :, 0] = 0xE0
    difference_frame[different] = (0xFF, 0, 0, 0xFF)  # [GB, B, G, R]

    panels = (
        ("Physical capture", _render_polar(captured, panel_size)),
        ("Native C oracle", _render_polar(expected_array.tobytes(), panel_size)),
        ("Byte differences", _render_polar(difference_frame.tobytes(), panel_size)),
    )
    gap = 16
    label_height = 42
    canvas = Image.new(
        "RGB",
        (panel_size * len(panels) + gap * (len(panels) - 1), panel_size + label_height),
        (8, 12, 22),
    )
    draw = ImageDraw.Draw(canvas)
    for index, (label, image) in enumerate(panels):
        x = index * (panel_size + gap)
        canvas.paste(image, (x, label_height))
        draw.text((x + 10, 14), label, fill=(231, 238, 249))

    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output, format="PNG", optimize=True)
    return output


def _pct(value, digits=3):
    return "—" if value is None else ("%.*f%%" % (digits, value * 100))


def _number(value, digits=0):
    if value is None:
        return "—"
    return ("%.*f" % (digits, value))


def _status_class(failures):
    return "fail" if failures else "pass"


def _performance_cards(rows):
    cards = []
    for row in rows:
        failures = row.get("failures", [])
        screenshot = html.escape(row.get("screenshot", ""))
        image = (
            '<a href="{0}"><img loading="lazy" src="{0}" alt="{1}"></a>'.format(
                screenshot,
                html.escape("%s at %s RPM" % (row.get("game", "scene"), row.get("rpm", "?"))),
            )
            if screenshot else '<div class="missing">No screenshot</div>'
        )
        cards.append(
            """
            <article class="test-card {status}">
              <div class="card-image">{image}</div>
              <div class="card-body">
                <div class="eyebrow">{rpm} RPM · repetition {repetition}</div>
                <h3>{game}</h3>
                <div class="badge">{badge}</div>
                <dl>
                  <div><dt>Frame max</dt><dd>{frame_max} ms / {frame_budget} ms</dd></div>
                  <div><dt>Physical slack</dt><dd>{slack} µs</dd></div>
                  <div><dt>Skipped</dt><dd>{skipped} ({skip_pct})</dd></div>
                  <div><dt>Heap delta</dt><dd>{heap_delta} bytes free</dd></div>
                  <div><dt>Scene budget</dt><dd>{layers}L · {sprites}S · {tilemaps}T</dd></div>
                  <div><dt>Samples / frames</dt><dd>{samples} / {frames}</dd></div>
                </dl>
                {failure_html}
              </div>
            </article>
            """.format(
                status=_status_class(failures),
                image=image,
                rpm=html.escape(str(row.get("rpm", "—"))),
                repetition=html.escape(str(row.get("repetition", "—"))),
                game=html.escape(str(row.get("game", "Unknown scene"))),
                badge="FAIL" if failures else "PASS",
                frame_max=_number(row.get("max_frame_render_us", 0) / 1000.0, 2),
                frame_budget=_number(row.get("frame_deadline_us", 0) / 1000.0, 2),
                slack=html.escape(str(row.get("worst_slack_us", "—"))),
                skipped=html.escape(str(row.get("skipped", "—"))),
                skip_pct=_number(row.get("skip_pct", 0.0), 4) + "%",
                heap_delta=html.escape(str(row.get("heap_delta", "—"))),
                layers=html.escape(str(row.get("layers", "—"))),
                sprites=html.escape(str(row.get("sprites", "—"))),
                tilemaps=html.escape(str(row.get("tilemaps", "—"))),
                samples=html.escape(str(row.get("samples", "—"))),
                frames=html.escape(str(row.get("frames", "—"))),
                failure_html=_failure_list(failures),
            )
        )
    return "\n".join(cards) or '<p class="empty">Performance tests were skipped.</p>'


def _render_cards(rows, warmup=False):
    cards = []
    for row in rows:
        failures = row.get("failures", [])
        screenshot = html.escape(row.get("screenshot", ""))
        image = (
            '<a href="{0}"><img loading="lazy" src="{0}" alt="Rendering evidence"></a>'.format(
                screenshot
            )
            if screenshot else '<div class="missing">No screenshot</div>'
        )
        badge = "WARM-UP" if warmup else ("FAIL" if failures else "PASS")
        cards.append(
            """
            <article class="render-card {status}">
              {image}
              <div class="card-body">
                <div class="eyebrow">{rpm} RPM · capture {repetition}</div>
                <h3>{title}</h3>
                <div class="badge">{badge}</div>
                <dl>
                  <div><dt>All pixels exact</dt><dd>{exact}</dd></div>
                  <div><dt>Active pixels exact</dt><dd>{active}</dd></div>
                  <div><dt>Different pixels</dt><dd>{different} / {compared}</dd></div>
                  <div><dt>Angular alignment</dt><dd>{shift} columns</dd></div>
                </dl>
                {failure_html}
              </div>
            </article>
            """.format(
                status="warmup" if warmup else _status_class(failures),
                image=image,
                rpm=html.escape(str(row.get("rpm", "—"))),
                repetition=html.escape(str(row.get("repetition", "—"))),
                title="Parity warm-up" if warmup else "Physical vs native oracle",
                badge=badge,
                exact=_pct(row.get("exact_ratio")),
                active=_pct(row.get("active_exact_ratio")),
                different=html.escape(str(row.get("different_pixels", "—"))),
                compared=html.escape(str(row.get("compared_pixels", "—"))),
                shift=html.escape(str(row.get("shift", "—"))),
                failure_html=_failure_list(failures),
            )
        )
    return "\n".join(cards) or '<p class="empty">Rendering tests were skipped.</p>'


def _failure_list(failures):
    if not failures:
        return ""
    return '<ul class="failures">%s</ul>' % "".join(
        "<li>%s</li>" % html.escape(str(failure)) for failure in failures
    )


def build_html(results):
    failures = results.get("failures", [])
    performance = results.get("performance", [])
    rendering = results.get("rendering", [])
    warmups = results.get("render_warmups", [])
    passing = not failures

    valid_performance = [row for row in performance if row.get("ok")]
    min_slack = min(
        (row.get("worst_slack_us", 0) for row in valid_performance),
        default=None,
    )
    max_frame = max(
        (row.get("max_frame_render_us", 0) for row in valid_performance),
        default=None,
    )
    max_skip = max(
        (row.get("skip_pct", 0.0) for row in valid_performance),
        default=None,
    )
    min_exact = min(
        (row.get("exact_ratio", 0.0) for row in rendering),
        default=None,
    )
    min_active = min(
        (row.get("active_exact_ratio", 0.0) for row in rendering),
        default=None,
    )
    config = results.get("config", {})
    git = results.get("git", {})

    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>VS2 hardware acceptance · {status}</title>
  <style>
    :root {{
      color-scheme: dark;
      --bg: #07101d; --panel: #0e1a2b; --panel2: #132238;
      --text: #e7eef9; --muted: #90a2bb; --line: #243752;
      --pass: #31d69b; --fail: #ff6b72; --warm: #ffbd5b; --accent: #6aa8ff;
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; background: radial-gradient(circle at 20% -10%, #17345e 0, var(--bg) 42%);
      color: var(--text); font: 15px/1.5 ui-sans-serif, system-ui, -apple-system, sans-serif; }}
    main {{ width: min(1480px, calc(100% - 32px)); margin: 0 auto; padding: 40px 0 72px; }}
    header {{ display: grid; grid-template-columns: 1fr auto; gap: 24px; align-items: end;
      padding: 28px; border: 1px solid var(--line); background: rgba(14,26,43,.88);
      border-radius: 20px; box-shadow: 0 18px 60px rgba(0,0,0,.3); }}
    h1 {{ margin: 4px 0 8px; font-size: clamp(30px, 5vw, 58px); line-height: 1; letter-spacing: -.04em; }}
    h2 {{ margin: 42px 0 16px; font-size: 25px; }}
    h3 {{ margin: 4px 0 10px; font-size: 20px; }}
    p {{ color: var(--muted); }}
    .eyebrow {{ color: var(--accent); text-transform: uppercase; letter-spacing: .11em; font-size: 11px; font-weight: 750; }}
    .hero-status {{ font-size: 28px; font-weight: 850; padding: 10px 18px; border-radius: 999px;
      color: #06110d; background: {status_color}; }}
    .summary {{ display: grid; grid-template-columns: repeat(5, minmax(0,1fr)); gap: 12px; margin-top: 18px; }}
    .metric {{ padding: 18px; background: var(--panel); border: 1px solid var(--line); border-radius: 14px; }}
    .metric strong {{ display: block; font-size: 25px; letter-spacing: -.03em; }}
    .metric span {{ color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: .08em; }}
    .metadata {{ display: grid; grid-template-columns: repeat(2, minmax(0,1fr)); gap: 8px 24px;
      padding: 18px 22px; border: 1px solid var(--line); border-radius: 14px; background: rgba(14,26,43,.75); }}
    .metadata div {{ display: flex; justify-content: space-between; gap: 16px; border-bottom: 1px solid rgba(36,55,82,.55); padding: 5px 0; }}
    .metadata dt {{ color: var(--muted); }} .metadata dd {{ margin: 0; text-align: right; }}
    .grid {{ display: grid; grid-template-columns: repeat(3, minmax(0,1fr)); gap: 16px; }}
    .render-grid {{ display: grid; grid-template-columns: repeat(2, minmax(0,1fr)); gap: 16px; }}
    .test-card, .render-card {{ min-width: 0; background: var(--panel); border: 1px solid var(--line);
      border-radius: 16px; overflow: hidden; }}
    .test-card.pass, .render-card.pass {{ border-color: rgba(49,214,155,.42); }}
    .test-card.fail, .render-card.fail {{ border-color: rgba(255,107,114,.6); }}
    .render-card.warmup {{ border-color: rgba(255,189,91,.45); }}
    .card-image, .render-card > a {{ display: block; background: #02060d; }}
    img {{ display: block; width: 100%; height: auto; }}
    .test-card .card-image img {{ aspect-ratio: 1; object-fit: cover; }}
    .card-body {{ padding: 17px; }}
    .badge {{ display: inline-block; margin-bottom: 12px; padding: 3px 8px; border-radius: 6px;
      background: var(--pass); color: #03120c; font-size: 11px; font-weight: 850; letter-spacing: .08em; }}
    .fail .badge {{ background: var(--fail); }} .warmup .badge {{ background: var(--warm); }}
    dl {{ margin: 0; }} dl div {{ display: flex; justify-content: space-between; gap: 12px;
      padding: 5px 0; border-top: 1px solid rgba(36,55,82,.55); }}
    dt {{ color: var(--muted); }} dd {{ margin: 0; font-variant-numeric: tabular-nums; text-align: right; }}
    .failures {{ color: #ffadb1; }} .empty, .missing {{ padding: 30px; text-align: center; color: var(--muted); }}
    .artifact-links a {{ color: #9ac2ff; margin-right: 18px; }}
    footer {{ margin-top: 42px; color: var(--muted); }}
    @media (max-width: 1050px) {{ .summary {{ grid-template-columns: repeat(2,1fr); }}
      .grid {{ grid-template-columns: repeat(2,1fr); }} }}
    @media (max-width: 700px) {{ main {{ width: min(100% - 20px, 1480px); padding-top: 10px; }}
      header {{ grid-template-columns: 1fr; }} .summary, .grid, .render-grid, .metadata {{ grid-template-columns: 1fr; }}
      .hero-status {{ justify-self: start; }} }}
  </style>
</head>
<body><main>
  <header>
    <div><div class="eyebrow">Ventilastation · API v2 · real hardware</div>
      <h1>Hardware acceptance report</h1>
      <p>{started} · {port}</p></div>
    <div class="hero-status">{status}</div>
  </header>

  <section class="summary">
    <div class="metric"><strong>{windows}</strong><span>performance windows</span></div>
    <div class="metric"><strong>{min_slack}</strong><span>minimum slack · µs</span></div>
    <div class="metric"><strong>{max_frame}</strong><span>maximum frame · ms</span></div>
    <div class="metric"><strong>{max_skip}</strong><span>maximum skipped</span></div>
    <div class="metric"><strong>{min_exact}</strong><span>minimum exact capture</span></div>
  </section>

  <h2>Run details</h2>
  <dl class="metadata">
    <div><dt>Started</dt><dd>{started}</dd></div>
    <div><dt>Finished</dt><dd>{finished}</dd></div>
    <div><dt>Branch / commit</dt><dd>{branch} · {commit}</dd></div>
    <div><dt>Working tree</dt><dd>{dirty}</dd></div>
    <div><dt>RPM matrix</dt><dd>{rpms}</dd></div>
    <div><dt>Performance window</dt><dd>{duration}s × {repeats} repetitions</dd></div>
    <div><dt>Skip ceiling</dt><dd>{skip_limit}%</dd></div>
    <div><dt>Pixel gates</dt><dd>{exact_limit}% all · {active_limit}% active</dd></div>
  </dl>

  {failure_section}

  <h2>Performance and heap stability</h2>
  <div class="grid">{performance_cards}</div>

  <h2>Physical rendering parity</h2>
  <p>Each evidence image shows the physical capture, the native C oracle, and byte-level differences.</p>
  <div class="render-grid">{render_cards}</div>

  <h2>Settling capture</h2>
  <p>The transition warm-up is recorded for traceability but is not part of the release gate.</p>
  <div class="render-grid">{warmup_cards}</div>

  <h2>Artifacts</h2>
  <p class="artifact-links"><a href="results.json">Raw JSON</a>
    <a href="screenshots/">Screenshot directory</a></p>
  <footer>Generated by tools/vs2_hardware_test.py from the USB-attached Ventilastation rotor and Workbench.</footer>
</main></body></html>
""".format(
        status="PASS" if passing else "FAIL",
        status_color="var(--pass)" if passing else "var(--fail)",
        started=html.escape(str(results.get("started_at", "—"))),
        finished=html.escape(str(results.get("finished_at", "—"))),
        port=html.escape(str(results.get("port", "—"))),
        windows=len(performance),
        min_slack="—" if min_slack is None else str(min_slack),
        max_frame="—" if max_frame is None else _number(max_frame / 1000.0, 2),
        max_skip="—" if max_skip is None else _number(max_skip, 4) + "%",
        min_exact="—" if min_exact is None else _pct(min_exact),
        branch=html.escape(str(git.get("branch", "—"))),
        commit=html.escape(str(git.get("commit", "—"))[:12]),
        dirty="modified" if git.get("dirty") else "clean",
        rpms=html.escape(", ".join(str(value) for value in results.get("rpms", []))),
        duration=html.escape(str(config.get("duration", "—"))),
        repeats=html.escape(str(results.get("repeats", "—"))),
        skip_limit=html.escape(str(results.get("max_skip_pct", "—"))),
        exact_limit=_number(config.get("min_exact", 0.0) * 100, 2),
        active_limit=_number(config.get("min_active_exact", 0.0) * 100, 2),
        failure_section=(
            "<h2>Failures</h2>" + _failure_list(failures) if failures else ""
        ),
        performance_cards=_performance_cards(performance),
        render_cards=_render_cards(rendering),
        warmup_cards=_render_cards(warmups, warmup=True),
    )


def write_report(report_dir, results):
    report_dir = Path(report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)
    results["artifacts"] = {
        "html": "report.html",
        "json": "results.json",
        "screenshots": "screenshots",
    }
    json_path = report_dir / "results.json"
    html_path = report_dir / "report.html"
    json_path.write_text(json.dumps(results, indent=2, sort_keys=True) + "\n")
    html_path.write_text(build_html(results))
    return html_path, json_path
