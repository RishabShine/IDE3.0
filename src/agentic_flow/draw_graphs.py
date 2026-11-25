"""Draw every LangGraph in agentic_flow, with subgraphs expanded (xray).

From src/:

    python -m agentic_flow.draw_graphs            # render with local headless Chrome
    python -m agentic_flow.draw_graphs --api      # render with mermaid.ink (sends the
                                                  # graph text to that web service)
    python -m agentic_flow.draw_graphs --mermaid  # only write the .mmd text files

Each image is saved next to the graph it shows; the whole flow is
agentic_flow/requirement_engineer_graph.png.
"""
import argparse
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from agentic_flow.api.pipeline import build_pipeline
from agentic_flow.artifact_graph.graph import build_artifact_graph_step
from agentic_flow.capture_intent.context_expected_benefits_current_situation.graph import (
    build_capture_context,
)
from agentic_flow.capture_intent.graph import build_capture_intent
from agentic_flow.capture_intent.sson.graph import build_capture_sson
from agentic_flow.goal2story.graph import build_goal2story
from agentic_flow.goals.graph import build_goals
from agentic_flow.impact_analysis.graph import build_impact_analysis
from agentic_flow.graph import build_ide3_chat
from agentic_flow.user_modelling.graph import build_user_modelling
from agentic_flow.user_modelling.personas.graph import build_personas
from agentic_flow.user_modelling.stakeholders.graph import build_stakeholders
from agentic_flow.use_cases.graph import build_use_cases

ROOT = Path(__file__).resolve().parent

# (builder, image path relative to agentic_flow/)
GRAPHS = [
    (build_ide3_chat, "requirement_engineer_graph.png"),
    (build_capture_intent, "capture_intent/capture_intent_graph.png"),
    (build_capture_sson, "capture_intent/sson/capture_sson_graph.png"),
    (build_capture_context,
     "capture_intent/context_expected_benefits_current_situation/capture_context_graph.png"),
    (build_user_modelling, "user_modelling/user_modelling_graph.png"),
    (build_stakeholders, "user_modelling/stakeholders/stakeholders_graph.png"),
    (build_personas, "user_modelling/personas/personas_graph.png"),
    (build_goals, "goals/goals_graph.png"),
    (build_use_cases, "use_cases/use_cases_graph.png"),
    (build_impact_analysis, "impact_analysis/impact_analysis_graph.png"),
    (build_artifact_graph_step, "artifact_graph/artifact_graph.png"),
    (build_goal2story, "goal2story/goal2story_graph.png"),
    (build_pipeline, "api/pipeline_graph.png"),
]

MERMAID_JS = "https://cdn.jsdelivr.net/npm/mermaid@10.9.1/dist/mermaid.min.js"
CHROME_PATHS = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "google-chrome", "chromium", "chromium-browser", "chrome",
]


def _chrome() -> str:
    for candidate in [os.environ.get("CHROME", "")] + CHROME_PATHS:
        if candidate and (Path(candidate).exists() or shutil.which(candidate)):
            return shutil.which(candidate) or candidate
    raise SystemExit("Chrome not found; set CHROME=/path/to/chrome or use --api.")


def _run_chrome(chrome: str, profile: str, *args: str) -> str:
    result = subprocess.run(
        [chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars",
         f"--user-data-dir={profile}", *args],
        capture_output=True, text=True, timeout=120,
    )
    return result.stdout


def render_local(mermaid: str, out: Path, chrome: str, work: Path) -> None:
    """Mermaid text -> PNG with headless Chrome: render the SVG, then screenshot it
    at its natural size. Only the Mermaid library is downloaded; the graph stays local."""
    page = work / "render.html"
    page.write_text(f"""<!doctype html><meta charset="utf-8">
<body style="margin:0;background:#fff"><pre class="mermaid">{mermaid}</pre>
<script src="{MERMAID_JS}"></script>
<script>mermaid.initialize({{startOnLoad: true, flowchart: {{useMaxWidth: false}}}});</script>
</body>""", encoding="utf-8")
    dom = _run_chrome(chrome, str(work / "profile"), "--virtual-time-budget=15000",
                      "--dump-dom", page.as_uri())
    match = re.search(r"<svg[\s\S]*?</svg>", dom)
    if not match:
        raise RuntimeError(f"Mermaid did not render {out.name}")
    svg = match.group(0)
    view = re.search(r'viewBox="[-\d.]+ [-\d.]+ ([\d.]+) ([\d.]+)"', svg)
    width, height = (int(float(v)) + 24 for v in view.groups())
    shot = work / "shot.html"
    shot.write_text('<!doctype html><meta charset="utf-8"><body style="margin:0;padding:12px;'
                    f'background:#fff">{svg}</body>', encoding="utf-8")
    _run_chrome(chrome, str(work / "profile"), f"--window-size={width},{height}",
                "--force-device-scale-factor=2", f"--screenshot={out}", shot.as_uri())


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--api", action="store_true", help="render with mermaid.ink")
    mode.add_argument("--mermaid", action="store_true", help="only write .mmd files")
    args = parser.parse_args()

    chrome = None if (args.api or args.mermaid) else _chrome()
    with tempfile.TemporaryDirectory() as tmp:
        for build, relative in GRAPHS:
            out = ROOT / relative
            graph = build().get_graph(xray=True)
            if args.mermaid:
                out.with_suffix(".mmd").write_text(graph.draw_mermaid(), encoding="utf-8")
            elif args.api:
                graph.draw_mermaid_png(output_file_path=str(out))
            else:
                render_local(graph.draw_mermaid(), out, chrome, Path(tmp))
            print(f"wrote {out.relative_to(ROOT.parent)}")


if __name__ == "__main__":
    main()
