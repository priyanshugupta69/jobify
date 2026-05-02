"""Auto-apply runner using `opencode` + Vertex (Gemini) instead of `claude`.

Drops in for ``applypilot.apply.launcher.run_job`` with the same signature
``run_job(job, port, worker_id=0, model=..., dry_run=False) -> (status, duration_ms)``,
so ``services.applier`` can swap between the two by setting ``APPLY_AGENT``.

Reuses applypilot's reusable pieces:
  - ``applypilot.apply.prompt.build_prompt`` — model-agnostic; emits the
    ``RESULT:APPLIED|FAILED:reason`` sentinel contract baked into the prompt.
  - applypilot config paths (LOG_DIR, APP_DIR) for log + MCP config locations.

Replaces only the subprocess invocation + stdout parsing. The chrome bridge
itself is launched by the caller (applier.apply_one passes ``port`` in).

The dependency check belongs in ``services.applier._ensure_dependencies`` —
this module assumes ``opencode`` is on PATH (or pointed at via
``settings.apply_agent_path``) and that ``GOOGLE_APPLICATION_CREDENTIALS`` /
``GOOGLE_CLOUD_PROJECT`` / ``GOOGLE_CLOUD_LOCATION`` are set on env so opencode's
Vertex provider can authenticate.
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path

import urllib.error
import urllib.request

from applypilot.apply.chrome import cleanup_worker, setup_worker_profile
from applypilot.apply.prompt import build_prompt
from applypilot.config import APP_DIR, LOG_DIR

from job_pipeline.settings import resolve_chrome_path, settings

log = logging.getLogger(__name__)

TIMEOUT_SECONDS = 300


OPENCODE_NPM_PKG = "opencode-ai@latest"


# Prompt augmentation: Playwright-MCP gotchas that applypilot's prompt
# (designed for Claude) doesn't spell out. Gemini doesn't infer these
# from tool error messages the way Claude does, so making them explicit
# meaningfully improves the agent loop. Keep this concise — every token
# here counts against the model's context + thinking budget.
PLAYWRIGHT_MCP_RULES = """\
## CRITICAL: Playwright-MCP tool-use rules

You are using Playwright-MCP tools to drive a browser. Read these rules \
before you start; ignoring them will cause you to get stuck in retry loops.

1. **Element refs are EPHEMERAL.** `browser_snapshot` returns elements with \
refs like `e2`, `e152`, etc. These refs are valid ONLY for that one snapshot. \
After ANY of: a click, a type, a navigation, a page mutation, OR another \
snapshot, the previous refs are DEAD. You MUST take a fresh `browser_snapshot` \
and read it carefully to find the new ref for the element you want. NEVER \
reuse a ref number across snapshots — it will not be the same element.

2. **Uploading files is a TWO-STEP sequence:**
   - Step A: `browser_click` the `<input type="file">` element (or the visible \
button that opens it). This triggers the OS file picker and puts the browser \
into "modal state".
   - Step B: ONLY THEN call `browser_file_upload(paths=["..."])` to deliver \
the file into that open picker.
   Calling `browser_file_upload` first will fail with \
"can only be used when there is related modal state present". Do not retry \
file_upload without first opening a picker via click.

3. **If a tool errors, change strategy — don't retry the same call.** \
Re-read the error message; it usually tells you what to do. Common patterns:
   - "Ref not found" → take a fresh snapshot, find the new ref, then act.
   - "Modal state required" → click the trigger element first.
   - "Element not visible" → scroll to it (`browser_scroll`) or wait for it.

4. **Stop immediately on login/signup walls.** If the apply form is blocked \
by a "Create Account", "Sign in", "Log in", "Register", or similar dialog or \
wall, do NOT attempt to register, sign in, fill credentials, or click OAuth \
providers (Microsoft / Google / LinkedIn / SSO etc.). The orchestrator has \
no account on this site and there's no human available to complete an auth \
flow. Emit `RESULT:LOGIN_ISSUE` and stop. Same for paywalls and "verify \
you are human" walls that require external input — emit `RESULT:LOGIN_ISSUE` \
or `RESULT:CAPTCHA` respectively.

5. **Always finish with a RESULT line.** When you're done — success or \
failure — emit one of:
   - `RESULT:APPLIED` (submitted successfully)
   - `RESULT:FAILED:<short_reason>` (e.g. `RESULT:FAILED:login_required`, \
`RESULT:FAILED:no_apply_button`, `RESULT:FAILED:form_validation_failed`)
   - `RESULT:CAPTCHA`, `RESULT:LOGIN_ISSUE`, `RESULT:EXPIRED`
   The orchestrator only knows what happened from this line. If you give up \
without one, the run is recorded as an unknown failure.

---

"""


def _resolve_command() -> list[str]:
    """Resolve the opencode invocation prefix.

    Priority:
      1. ``APPLY_AGENT_PATH`` if set (explicit binary).
      2. ``opencode`` on PATH (global install, e.g. ``npm i -g opencode-ai``).
      3. ``npx -y opencode-ai@latest`` (zero-install, cached after first run).

    Falling back to npx mirrors how the Playwright MCP server is already
    launched (``npx @playwright/mcp@latest``) so we don't introduce a new
    install requirement.
    """
    if settings.apply_agent_path:
        return [settings.apply_agent_path]
    found = shutil.which("opencode")
    if found:
        return [found]
    npx = shutil.which("npx")
    if not npx:
        raise FileNotFoundError(
            "Neither `opencode` nor `npx` found in PATH. "
            "Install Node (npx ships with it) or set APPLY_AGENT_PATH "
            "in ~/.applypilot/.env."
        )
    return [npx, "-y", OPENCODE_NPM_PKG]


def _vertex_config_from_env() -> tuple[str, str, str]:
    """Resolve (sa_key_path, project, location) for the apply agent.

    SA + project come from env (accepting both the GOOGLE_* and VERTEX_*
    names already used by ``vertex_llm.py``). Location uses
    ``settings.apply_agent_location`` — defaults to ``global`` because
    Gemini 3.x previews only resolve at the global endpoint, while
    ``vertex_llm.py`` keeps using ``VERTEX_LOCATION`` (typically a
    region) for its scoring/tailor calls.
    """
    sa_key = (
        os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
        or os.environ.get("VERTEX_SA_KEY", "")
    )
    project = (
        os.environ.get("GOOGLE_CLOUD_PROJECT")
        or os.environ.get("VERTEX_PROJECT", "")
    )
    location = settings.apply_agent_location or "global"
    return sa_key, project, location


OPENCODE_CONFIG_DIR = Path.home() / ".config" / "opencode"
OPENCODE_CONFIG_FILE = OPENCODE_CONFIG_DIR / "opencode.json"


def _build_config(cdp_port: int) -> dict:
    """opencode config: Vertex provider + Playwright-MCP attached to our Chrome.

    opencode reads this from ``~/.config/opencode/opencode.json`` automatically.
    There is no CLI flag to point it elsewhere, so we write the global file.
    Provider/credential values come from env (mirroring vertex_llm.py's setup).
    """
    _, project, location = _vertex_config_from_env()
    return {
        "$schema": "https://opencode.ai/config.json",
        "provider": {
            "google-vertex": {
                "options": {"project": project, "location": location},
            },
        },
        "mcp": {
            "playwright": {
                "type": "local",
                # IMPORTANT: 127.0.0.1, not localhost. Node 17+ resolves
                # ``localhost`` to IPv6 (``::1``) first; Chrome's CDP server
                # only listens on IPv4, so MCP gets ECONNREFUSED ::1:9222.
                "command": [
                    "npx",
                    "@playwright/mcp@latest",
                    f"--cdp-endpoint=http://127.0.0.1:{cdp_port}",
                ],
                "enabled": True,
            },
        },
    }


def _launch_chrome_server_safe(worker_id: int, port: int, headless: bool) -> subprocess.Popen:
    """Launch Chrome with the flags headless-on-Linux-server actually needs.

    applypilot's ``launch_chrome`` is missing ``--no-sandbox`` /
    ``--disable-dev-shm-usage`` / ``--disable-gpu``, which makes Chrome SIGABRT
    on startup in a systemd service environment. We mirror the flag set already
    proven to work in ``services/extract_urls.py:158-181`` for the LinkedIn
    scraper, while keeping applypilot's per-worker profile dir (so apply-time
    cookies/state stay isolated per worker).
    """
    chrome_exe = resolve_chrome_path()
    if not chrome_exe:
        raise FileNotFoundError("No Chrome/Chromium binary resolved (set CHROME_PATH).")

    profile_dir = setup_worker_profile(worker_id)

    cmd = [
        chrome_exe,
        f"--remote-debugging-port={port}",
        f"--user-data-dir={profile_dir}",
        "--profile-directory=Default",
        "--no-first-run",
        "--no-default-browser-check",
        "--no-sandbox",                # required when running as the systemd user
        "--disable-dev-shm-usage",     # required on small /dev/shm hosts
        "--disable-gpu",               # required for headless on most Linux servers
        "--disable-extensions",
        "--disable-popup-blocking",
        "--use-fake-device-for-media-stream",
        "--use-fake-ui-for-media-stream",
        "--deny-permission-prompts",
        "--disable-notifications",
        "--window-size=1280,900",
    ]
    if headless:
        cmd.append("--headless=new")

    kwargs: dict = dict(stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if os.name != "nt":
        kwargs["preexec_fn"] = os.setsid

    proc = subprocess.Popen(cmd, **kwargs)

    # Poll the CDP port until ready (max ~10s). Beats applypilot's blind
    # ``time.sleep(3)`` — surfaces fast crashes immediately and avoids
    # racing with slow startups.
    deadline = time.time() + 10
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(
                f"Chrome exited with code {proc.returncode} during startup"
            )
        try:
            urllib.request.urlopen(
                f"http://127.0.0.1:{port}/json/version", timeout=0.5
            ).close()
            log.info("apply_opencode: chrome up on cdp port %d (pid=%d)", port, proc.pid)
            return proc
        except (urllib.error.URLError, OSError):
            time.sleep(0.25)

    proc.terminate()
    raise TimeoutError(f"Chrome did not open CDP port {port} within 10s")


def _ensure_global_config(cdp_port: int) -> Path:
    """Write the opencode config to its expected global location.

    Idempotent: rewrites the file each call so a port change (e.g. multi-worker)
    or env-var change is picked up without a manual edit.
    """
    OPENCODE_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    OPENCODE_CONFIG_FILE.write_text(
        json.dumps(_build_config(cdp_port), indent=2), encoding="utf-8"
    )
    return OPENCODE_CONFIG_FILE


_REASON_RE = re.compile(r"[a-zA-Z_][a-zA-Z0-9_]*")


def _parse_result(output: str) -> str:
    """Sentinel-string parser, mirroring applypilot launcher.py:468-498.

    The output may have the sentinel embedded inside opencode's JSON event
    stream (``"text":"...RESULT:FAILED:reason..."``), so we extract the reason
    as the first identifier-like token after ``RESULT:FAILED:`` rather than
    "everything to end of line".
    """
    for status in ("APPLIED", "EXPIRED", "CAPTCHA", "LOGIN_ISSUE"):
        if f"RESULT:{status}" in output:
            return status.lower()

    idx = output.find("RESULT:FAILED:")
    if idx != -1:
        tail = output[idx + len("RESULT:FAILED:"):]
        m = _REASON_RE.search(tail)
        reason = (m.group(0) if m else "unknown").lower()
        if reason in {"captcha", "expired", "login_issue"}:
            return reason
        return f"failed:{reason}"

    if "RESULT:FAILED" in output:
        return "failed:unknown"

    return "failed:no_result_line"


def run_job(
    job: dict,
    port: int,
    worker_id: int = 0,
    model: str | None = None,
    dry_run: bool = False,
) -> tuple[str, int]:
    """Apply to one job using opencode + Vertex Gemini.

    Args:
        job: Row dict from the jobs table.
        port: CDP port that an already-launched Chrome is listening on.
        worker_id: Per-worker isolation key (matches applypilot conventions).
        model: opencode model id; defaults to ``settings.apply_agent_model``.
        dry_run: When True, the prompt instructs the agent not to click Submit.

    Returns:
        ``(status, duration_ms)`` — same shape as applypilot launcher.run_job.
        Status is one of ``"applied" | "expired" | "captcha" | "login_issue" |
        "failed:<reason>" | "skipped"``.
    """
    cmd_prefix = _resolve_command()
    chosen_model = model or settings.apply_agent_model
    config_path = _ensure_global_config(port)

    resume_path = job.get("tailored_resume_path")
    txt_path = Path(resume_path).with_suffix(".txt") if resume_path else None
    resume_text = ""
    if txt_path and txt_path.exists():
        resume_text = txt_path.read_text(encoding="utf-8")

    base_prompt = build_prompt(job=job, tailored_resume=resume_text, dry_run=dry_run)
    # Prepend Playwright-MCP-specific guidance (see PLAYWRIGHT_MCP_RULES).
    # applypilot's prompt was tuned for Claude; Gemini needs these gotchas
    # spelled out explicitly to avoid the ref-reuse and upload-without-modal
    # failure modes we hit on the first end-to-end runs.
    agent_prompt = PLAYWRIGHT_MCP_RULES + base_prompt

    cmd = [
        *cmd_prefix,
        "run",
        "--model", chosen_model,
        "--format", "json",
        "--dangerously-skip-permissions",
        agent_prompt,
    ]

    # opencode's Vertex provider expects the Google-standard env names.
    # Mirror VERTEX_* → GOOGLE_* on the subprocess env so users with the
    # repo's existing VERTEX_* setup don't have to duplicate vars.
    env = os.environ.copy()
    sa_key, project, location = _vertex_config_from_env()
    if sa_key and not env.get("GOOGLE_APPLICATION_CREDENTIALS"):
        env["GOOGLE_APPLICATION_CREDENTIALS"] = str(Path(sa_key).expanduser())
    if project and not env.get("GOOGLE_CLOUD_PROJECT"):
        env["GOOGLE_CLOUD_PROJECT"] = project
    if location and not env.get("GOOGLE_CLOUD_LOCATION"):
        env["GOOGLE_CLOUD_LOCATION"] = location

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    job_log = LOG_DIR / (
        f"opencode_{ts}_w{worker_id}_{(job.get('site') or 'unknown')[:20]}.txt"
    )

    log.info(
        "apply_opencode.run_job: worker=%d port=%d dry_run=%s model=%s config=%s url=%s",
        worker_id, port, dry_run, chosen_model, config_path,
        (job.get("url") or "")[:80],
    )

    # Bring up a per-worker Chrome on the CDP port the MCP server connects to.
    # ``cleanup_worker`` (still applypilot's) tears it down in the finally
    # block so we don't leak browser processes between bulk-action runs.
    chrome_proc = None
    try:
        chrome_proc = _launch_chrome_server_safe(
            worker_id=worker_id, port=port, headless=settings.auto_apply_headless,
        )
    except Exception as e:
        log.exception("apply_opencode: chrome launch failed")
        return f"failed:chrome_launch:{type(e).__name__}", 0

    start = time.time()
    text_parts: list[str] = []
    proc = None
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
        )

        with open(job_log, "a", encoding="utf-8") as lf:
            lf.write(f"=== {job.get('title', '')} @ {job.get('site', '')} ===\n")
            for line in proc.stdout:
                line = line.rstrip("\n")
                if not line:
                    continue
                lf.write(line + "\n")
                lf.flush()  # so `tail -F` of the per-job log isn't laggy
                # Mirror to journald so `journalctl --user -u job-pipeline -f`
                # shows the agent's progress live (truncate to keep journal sane).
                log.info("[opencode w%d] %s", worker_id, line[:500])
                try:
                    msg = json.loads(line)
                    if isinstance(msg, dict):
                        for key in ("text", "content", "result", "message"):
                            val = msg.get(key)
                            if isinstance(val, str) and val:
                                text_parts.append(val)
                                break
                        else:
                            text_parts.append(line)
                    else:
                        text_parts.append(line)
                except json.JSONDecodeError:
                    text_parts.append(line)

        proc.wait(timeout=TIMEOUT_SECONDS)
        returncode = proc.returncode
    except subprocess.TimeoutExpired:
        log.warning("apply_opencode.run_job: timeout after %ds", TIMEOUT_SECONDS)
        if proc:
            try:
                proc.kill()
            except Exception:
                pass
        return "failed:timeout", int((time.time() - start) * 1000)
    except Exception as e:
        log.exception("apply_opencode.run_job: subprocess error")
        return f"failed:subprocess:{type(e).__name__}", int((time.time() - start) * 1000)
    finally:
        # Always tear down Chrome so the next run starts clean and we don't
        # leak browser processes pinned to the CDP port.
        try:
            cleanup_worker(worker_id, chrome_proc)
        except Exception:
            log.exception("apply_opencode: chrome cleanup failed (non-fatal)")

    duration_ms = int((time.time() - start) * 1000)

    if returncode is not None and returncode < 0:
        return "skipped", duration_ms

    output = "\n".join(text_parts)
    return _parse_result(output), duration_ms
