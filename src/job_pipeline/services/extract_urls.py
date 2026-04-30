"""Extract external apply URLs from LinkedIn job pages.

Ports scripts/extract_apply_urls.py — async Playwright with anti-detection
flags, periodic browser relaunch, retry/budget logic, and ___easy_apply___
sentinel writes.
"""
from __future__ import annotations

import asyncio
import json
import logging
import random
import sqlite3
from pathlib import Path

from playwright.async_api import async_playwright

from job_pipeline.db import get_connection
from job_pipeline.settings import APPLYPILOT_DIR  # noqa: F401  (kept for parity)

log = logging.getLogger(__name__)

LINKEDIN_SESSION = Path.home() / ".openclaw/workspace/.linkedin_session.json"
MIN_DELAY = 3
MAX_DELAY = 6
MAX_RETRIES = 3
RELAUNCH_EVERY = 10
DEFAULT_LIMIT = 50


def _app_url_missing(value) -> bool:
    return value is None or str(value).strip().lower() in {"", "none", "null"}


async def _load_linkedin_context(browser):
    session = json.loads(LINKEDIN_SESSION.read_text())
    context = await browser.new_context(
        user_agent=(
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        ),
        viewport={"width": 1280, "height": 900},
    )
    cookies = []
    for c in session.get("cookies", []):
        cookie = {
            "name": c["name"], "value": c["value"],
            "domain": c["domain"], "path": c.get("path", "/"),
        }
        if c.get("secure"):
            cookie["secure"] = True
        if c.get("sameSite"):
            cookie["sameSite"] = c["sameSite"]
        cookies.append(cookie)
    await context.add_cookies(cookies)
    return context


async def _extract_apply_url(page, job_url: str) -> tuple[str | None, str]:
    try:
        await page.goto(job_url, wait_until="domcontentloaded", timeout=20000)
        await page.wait_for_timeout(2000 + random.randint(0, 2000))
        content = await page.inner_text("body")

        if "sign in" in content.lower()[:200] and "job" not in content.lower()[:200]:
            return None, "auth_failed"

        easy = await page.query_selector(
            'button:has-text("Easy Apply"), span:has-text("Easy Apply")'
        )
        if easy:
            return None, "easy_apply"

        apply_link: str | None = None
        for el in await page.query_selector_all('a:has-text("Apply"), a[href*="apply"]'):
            href = await el.get_attribute("href") or ""
            if href and "linkedin.com" not in href:
                apply_link = href
                break

        if not apply_link:
            for el in await page.query_selector_all(
                'a[href*="externalApply"], a[href*="external-apply"]'
            ):
                href = await el.get_attribute("href") or ""
                if href:
                    apply_link = href
                    break

        if not apply_link:
            btn = await page.query_selector(
                'button:has-text("Apply"), a:has-text("Apply")'
            )
            if btn:
                async with page.expect_popup(timeout=5000) as popup_info:
                    try:
                        await btn.click()
                    except Exception:
                        pass
                try:
                    popup = await popup_info.value
                    await popup.wait_for_load_state("domcontentloaded", timeout=10000)
                    if "linkedin.com" not in popup.url:
                        apply_link = popup.url
                    await popup.close()
                except Exception:
                    await page.wait_for_timeout(2000)
                    if "linkedin.com" not in page.url:
                        apply_link = page.url
                        await page.go_back()

        return (apply_link, "external") if apply_link else (None, "unknown")
    except Exception as e:
        return None, f"error: {str(e)[:50]}"


def _select_pending(conn: sqlite3.Connection, limit: int) -> list[tuple[str, str]]:
    rows = conn.execute(
        """
        SELECT url, title FROM jobs
         WHERE site = 'linkedin'
           AND (application_url IS NULL
                OR trim(lower(application_url)) IN ('', 'none', 'null'))
           AND fit_score >= 7
         ORDER BY fit_score DESC
         LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [(r[0], r[1]) for r in rows]


async def _run_async(limit: int, urls_subset: list[str] | None) -> dict:
    if not LINKEDIN_SESSION.exists():
        log.warning("LinkedIn session not found at %s", LINKEDIN_SESSION)
        return {"status": "no_session"}

    conn = get_connection()
    if urls_subset:
        rows = []
        for url in urls_subset:
            r = conn.execute(
                "SELECT url, title, application_url FROM jobs WHERE url = ?",
                (url,),
            ).fetchone()
            if r and _app_url_missing(r["application_url"]) and "linkedin.com" in url:
                rows.append((r["url"], r["title"]))
    else:
        rows = _select_pending(conn, limit)

    if not rows:
        log.info("No LinkedIn jobs need URL extraction")
        return {"status": "ok", "extracted": 0}

    log.info("Extracting apply URLs for %d LinkedIn jobs", len(rows))
    stats = {"external": 0, "easy_apply": 0, "error": 0, "unknown": 0}

    async with async_playwright() as p:
        async def _launch():
            b = await p.chromium.launch(
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox", "--disable-dev-shm-usage",
                    "--disable-gpu", "--single-process", "--disable-extensions",
                ],
            )
            ctx = await _load_linkedin_context(b)
            pg = await ctx.new_page()
            await pg.add_init_script(
                "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
            )
            await pg.route(
                "**/*",
                lambda route: (
                    route.abort()
                    if route.request.resource_type
                    in ("image", "font", "stylesheet", "media")
                    else route.continue_()
                ),
            )
            return b, pg

        browser, page = await _launch()

        try:
            await page.goto(
                "https://www.linkedin.com/feed/",
                wait_until="domcontentloaded",
                timeout=15000,
            )
            await page.wait_for_timeout(3000)
            test_content = await page.inner_text("body")
        except Exception as e:
            log.error("LinkedIn auth check failed: %s", str(e)[:120])
            await browser.close()
            return {"status": "auth_failed"}
        if "sign in" in test_content.lower()[:300]:
            log.error("LinkedIn auth failed — session expired")
            await browser.close()
            return {"status": "auth_failed"}
        log.info("LinkedIn session active")

        retries = 0
        i = 0
        while i < len(rows):
            url, title = rows[i]

            if i > 0:
                await asyncio.sleep(random.uniform(MIN_DELAY, MAX_DELAY))
            if i > 0 and i % RELAUNCH_EVERY == 0:
                try:
                    await browser.close()
                except Exception:
                    pass
                await asyncio.sleep(2)
                browser, page = await _launch()
                log.info("[Relaunched browser at job %d]", i)

            try:
                apply_url, apply_type = await _extract_apply_url(page, url)
                retries = 0
            except Exception as e:
                log.error("Browser error on job %d: %s", i, e)
                retries += 1
                if retries > MAX_RETRIES:
                    log.error("Max retries reached — stopping")
                    break
                try:
                    await browser.close()
                except Exception:
                    pass
                await asyncio.sleep(5)
                browser, page = await _launch()
                continue

            stats[apply_type if apply_type in stats else "error"] += 1

            if apply_url:
                conn.execute(
                    "UPDATE jobs SET application_url = ? WHERE url = ?",
                    (apply_url, url),
                )
                log.info(
                    "  %d/%d [EXTERNAL] %s -> %s",
                    i + 1, len(rows), (title or "")[:40], apply_url[:60],
                )
            else:
                conn.execute(
                    "UPDATE jobs SET application_url = ? WHERE url = ?",
                    (f"___{apply_type}___", url),
                )
                log.info("  %d/%d [%s] %s",
                        i + 1, len(rows), apply_type.upper(), (title or "")[:40])
            conn.commit()

            if apply_type == "auth_failed":
                log.error("Auth failed mid-run — stopping")
                break

            i += 1

        await browser.close()

    log.info("extract_urls.run done: %s", stats)
    return {"status": "ok", "stats": stats, "processed": i}


def run(limit: int = DEFAULT_LIMIT, urls: list[str] | None = None) -> dict:
    """Sync wrapper around the async Playwright extraction.

    Args:
        limit: Max jobs to process when ``urls`` is None (default 50).
        urls: Optional explicit list of LinkedIn URLs to extract. When supplied,
            only those are processed (matches daily_pipeline.step_extract_urls).
    """
    return asyncio.run(_run_async(limit, urls))
