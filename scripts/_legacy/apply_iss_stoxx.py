#!/usr/bin/env python3
"""Apply to ISS STOXX Software Engineer role via Workday using existing account."""

import asyncio
import json
import sys
from pathlib import Path
from playwright.async_api import async_playwright

JOB_URL = "https://issgovernance.wd1.myworkdayjobs.com/ISScareers/job/Mumbai-India/Software-Engineer--Python--Database-_JR_9501"
EMAIL = "priyanshuraja456@gmail.com"
PASSWORD = "ApKing3AkhGNUx!1"
RESUME = "/home/ubuntu/.openclaw/media/inbound/PriyanshuGuptaCV---aca58e11-0bd7-4ddd-a16e-98b2159de749.pdf"
PROFILE = json.loads(Path("/home/ubuntu/.applypilot/profile.json").read_text())
SCREENSHOTS = Path("/home/ubuntu/.openclaw/workspace/job_pipeline/screenshots")
SCREENSHOTS.mkdir(exist_ok=True)

async def screenshot(page, name):
    path = SCREENSHOTS / f"iss_{name}.png"
    await page.screenshot(path=str(path), full_page=False)
    print(f"📸 {path}")
    return path

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        page.set_default_timeout(30000)

        # Step 1: Go to job page
        print("1. Navigating to job page...")
        await page.goto(JOB_URL, wait_until="networkidle", timeout=60000)
        await asyncio.sleep(3)
        await screenshot(page, "01_job_page")

        # Accept cookies if present
        try:
            cookies = page.locator("button:has-text('Accept Cookies')")
            if await cookies.count() > 0:
                await cookies.first.click()
                print("   Accepted cookies")
                await asyncio.sleep(1)
        except:
            pass

        # Step 2: Click Apply
        print("2. Clicking Apply...")
        apply_btn = page.locator("a:has-text('Apply'), button:has-text('Apply')")
        if await apply_btn.count() > 0:
            await apply_btn.first.click()
            await asyncio.sleep(3)
            await screenshot(page, "02_apply_popup")

        # Step 3: Handle "Start Your Application" popup
        # First, sign in via the header (need to close popup first or sign in)
        # The popup has: "Autofill with Resume", "Apply Manually", "Use My Last Application", "Apply With LinkedIn"
        # We need to sign in first. Let's close the popup, sign in, then apply.
        
        print("3. Closing popup to sign in first...")
        close_btn = page.locator("[data-automation-id='wd-popup-glass'] button, button[aria-label='close'], button:has-text('×'), div[data-automation-id='wd-popup-glass']")
        
        # Try clicking X to close popup
        x_btn = page.locator("button[aria-label='close'], button[aria-label='Close']")
        if await x_btn.count() > 0:
            await x_btn.first.click()
            await asyncio.sleep(2)
            print("   Closed popup via X button")
        else:
            # Press Escape
            await page.keyboard.press("Escape")
            await asyncio.sleep(2)
            print("   Pressed Escape to close popup")
        
        await screenshot(page, "03_popup_closed")

        # Step 4: Click Sign In in header
        print("4. Clicking Sign In in header...")
        signin_btn = page.locator("button[data-automation-id='utilityButtonSignIn']")
        if await signin_btn.count() > 0:
            await signin_btn.first.click()
            await asyncio.sleep(3)
            await screenshot(page, "04_signin_form")
        else:
            # Try generic sign in
            signin = page.locator("a:has-text('Sign In'), button:has-text('Sign In')")
            if await signin.count() > 0:
                await signin.first.click()
                await asyncio.sleep(3)
                await screenshot(page, "04_signin_form")

        # Step 5: Enter credentials
        print("5. Entering credentials...")
        
        # Workday sign in typically has email and password fields
        # Try various selectors
        email_filled = False
        for selector in [
            "input[data-automation-id='email']",
            "input[type='email']",
            "input[data-automation-id='userName']",
            "input[name='email']",
            "input[name='username']",
            "input[aria-label*='Email']",
            "input[aria-label*='email']",
            "input[placeholder*='Email']",
        ]:
            field = page.locator(selector)
            if await field.count() > 0:
                await field.first.fill(EMAIL)
                print(f"   Email entered via: {selector}")
                email_filled = True
                break
        
        if not email_filled:
            # Dump all inputs for debugging
            inputs = page.locator("input:visible")
            count = await inputs.count()
            print(f"   Visible inputs: {count}")
            for i in range(min(count, 15)):
                inp = inputs.nth(i)
                attrs = await inp.evaluate("el => ({type: el.type, name: el.name, id: el.id, placeholder: el.placeholder, automationId: el.getAttribute('data-automation-id')})")
                print(f"   Input {i}: {attrs}")
                # Fill first text/email input
                if attrs.get('type') in ('text', 'email') and not email_filled:
                    await inp.fill(EMAIL)
                    email_filled = True
                    print(f"   → Filled this one with email")

        pw_field = page.locator("input[type='password']")
        if await pw_field.count() > 0:
            await pw_field.first.fill(PASSWORD)
            print("   Password entered")
        
        await screenshot(page, "05_creds_entered")
        
        # Click sign in submit - Workday uses a click_filter overlay div
        print("6. Submitting sign in...")
        # The actual clickable element is the click_filter div overlay
        click_filter = page.locator("div[data-automation-id='click_filter'][aria-label='Sign In']")
        if await click_filter.count() > 0:
            await click_filter.first.click(force=True)
            print("   Clicked click_filter Sign In")
        else:
            # Fallback: force click the submit button
            submit = page.locator("button[data-automation-id='signInSubmitButton']")
            if await submit.count() > 0:
                await submit.first.click(force=True)
                print("   Force-clicked signInSubmitButton")
            else:
                # Last resort: JS click
                await page.evaluate("document.querySelector('button[type=submit]')?.click()")
                print("   JS-clicked submit button")
        
        await asyncio.sleep(5)
        await screenshot(page, "06_after_signin")
        print(f"   URL: {page.url}")
        
        # Check for errors
        error = page.locator("[data-automation-id='errorMessage'], .error-message, div[role='alert']")
        if await error.count() > 0:
            err_text = await error.first.inner_text()
            print(f"   ⚠️ Error: {err_text}")

        # Step 7: Now click Apply again (we're signed in)
        print("7. Clicking Apply again (now signed in)...")
        apply_btn = page.locator("a:has-text('Apply'), button:has-text('Apply')")
        if await apply_btn.count() > 0:
            await apply_btn.first.click()
            await asyncio.sleep(3)
            await screenshot(page, "07_apply_signed_in")
        
        # Handle the popup again - this time use "Use My Last Application" or "Autofill with Resume"
        print("8. Handling application popup...")
        
        # Try "Use My Last Application" first
        last_app = page.locator("button:has-text('Use My Last Application'), a:has-text('Use My Last Application')")
        if await last_app.count() > 0:
            print("   Found 'Use My Last Application' - clicking...")
            await last_app.first.click()
            await asyncio.sleep(5)
            await screenshot(page, "08_last_application")
        else:
            # Try "Autofill with Resume"
            autofill = page.locator("button:has-text('Autofill with Resume'), a:has-text('Autofill with Resume')")
            if await autofill.count() > 0:
                print("   Found 'Autofill with Resume' - clicking...")
                await autofill.first.click()
                await asyncio.sleep(3)
                
                # Upload resume
                file_input = page.locator("input[type='file']")
                if await file_input.count() > 0:
                    await file_input.first.set_input_files(RESUME)
                    print("   Resume uploaded!")
                    await asyncio.sleep(5)
                    await screenshot(page, "08_resume_uploaded")
            else:
                # Just click "Apply Manually"
                manual = page.locator("button:has-text('Apply Manually'), a:has-text('Apply Manually')")
                if await manual.count() > 0:
                    print("   Clicking 'Apply Manually'...")
                    await manual.first.click()
                    await asyncio.sleep(3)
                    await screenshot(page, "08_manual_apply")

        # Step 9: We should now be on the application form
        print("9. Checking application form state...")
        await asyncio.sleep(3)
        await screenshot(page, "09_form_state")
        
        # Print page text for debugging
        text = await page.inner_text("body")
        print(f"\n--- Page text (first 3000 chars) ---")
        print(text[:3000])
        print("--- End ---\n")
        
        # Look for form fields and fill them
        print("10. Looking for form fields to fill...")
        
        # Common Workday fields
        # Country
        country = page.locator("input[data-automation-id*='country'], select[data-automation-id*='country']")
        if await country.count() > 0:
            print("   Found country field")
        
        # Check for Next/Submit buttons
        next_btn = page.locator("button[data-automation-id='bottom-navigation-next-button'], button:has-text('Next'), button:has-text('Submit'), button:has-text('Continue')")
        count = await next_btn.count()
        print(f"   Navigation buttons found: {count}")
        for i in range(count):
            txt = await next_btn.nth(i).inner_text()
            print(f"   Button {i}: {txt}")
        
        await screenshot(page, "10_final")
        await browser.close()
        print("\n✅ Done! Check screenshots.")

if __name__ == "__main__":
    asyncio.run(main())
