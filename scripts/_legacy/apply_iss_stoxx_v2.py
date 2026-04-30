#!/usr/bin/env python3
"""Apply to ISS STOXX - complete all 5 steps. Already signed in with 'Use My Last Application'."""

import asyncio
import json
from pathlib import Path
from playwright.async_api import async_playwright

JOB_URL = "https://issgovernance.wd1.myworkdayjobs.com/ISScareers/job/Mumbai-India/Software-Engineer--Python--Database-_JR_9501"
EMAIL = "priyanshuraja456@gmail.com"
PASSWORD = "ApKing3AkhGNUx!1"
RESUME = "/home/ubuntu/.openclaw/media/inbound/PriyanshuGuptaCV---aca58e11-0bd7-4ddd-a16e-98b2159de749.pdf"
PROFILE = json.loads(Path("/home/ubuntu/.applypilot/profile.json").read_text())
SCREENSHOTS = Path("/home/ubuntu/.openclaw/workspace/job_pipeline/screenshots")
SCREENSHOTS.mkdir(exist_ok=True)

step_num = [0]

async def ss(page, name):
    step_num[0] += 1
    path = SCREENSHOTS / f"iss2_{step_num[0]:02d}_{name}.png"
    await page.screenshot(path=str(path), full_page=True)
    print(f"📸 {path}")

async def click_workday_btn(page, selector, force=True):
    """Click a Workday button handling click_filter overlays."""
    el = page.locator(selector)
    if await el.count() > 0:
        try:
            await el.first.click(force=force, timeout=5000)
            return True
        except:
            # Try JS click
            await el.first.evaluate("el => el.click()")
            return True
    return False

async def dump_fields(page):
    """Print all visible form fields."""
    inputs = page.locator("input:visible, select:visible, textarea:visible")
    count = await inputs.count()
    print(f"   Visible fields: {count}")
    for i in range(min(count, 30)):
        el = inputs.nth(i)
        attrs = await el.evaluate("""el => ({
            tag: el.tagName, type: el.type, name: el.name, 
            id: el.id, value: el.value,
            placeholder: el.placeholder,
            aid: el.getAttribute('data-automation-id'),
            label: el.getAttribute('aria-label'),
            required: el.required
        })""")
        print(f"   [{i}] {attrs}")

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 1200},
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        page.set_default_timeout(15000)

        # --- SIGN IN ---
        print("=== SIGNING IN ===")
        await page.goto(JOB_URL, wait_until="networkidle", timeout=60000)
        await asyncio.sleep(2)
        
        # Accept cookies
        try:
            await page.locator("button:has-text('Accept Cookies')").first.click(timeout=3000)
        except:
            pass

        # Click Sign In header
        try:
            await click_workday_btn(page, "button[data-automation-id='utilityButtonSignIn']")
            await asyncio.sleep(2)
        except:
            pass

        # Enter creds
        try:
            await page.locator("input[data-automation-id='email']").first.fill(EMAIL)
            await page.locator("input[type='password']").first.fill(PASSWORD)
            await asyncio.sleep(1)
            await click_workday_btn(page, "div[data-automation-id='click_filter'][aria-label='Sign In']")
            await asyncio.sleep(5)
            print(f"Signed in. URL: {page.url}")
        except Exception as e:
            print(f"Sign in issue: {e}")
        
        await ss(page, "signed_in")

        # --- APPLY ---
        print("\n=== STARTING APPLICATION ===")
        await click_workday_btn(page, "a:has-text('Apply'), button:has-text('Apply')")
        await asyncio.sleep(3)
        await ss(page, "apply_popup")
        
        # Use My Last Application
        try:
            last_app = page.locator("button:has-text('Use My Last Application'), a:has-text('Use My Last Application')")
            if await last_app.count() > 0:
                await last_app.first.click(force=True)
                print("Clicked 'Use My Last Application'")
                await asyncio.sleep(5)
            else:
                # Try Apply Manually
                await click_workday_btn(page, "button:has-text('Apply Manually')")
                await asyncio.sleep(3)
        except Exception as e:
            print(f"Popup handling: {e}")

        await ss(page, "form_start")
        
        # --- NAVIGATE THROUGH ALL 5 STEPS ---
        for step in range(1, 6):
            print(f"\n=== STEP {step}/5 ===")
            await asyncio.sleep(3)
            
            # Scroll down to see all fields
            await page.evaluate("window.scrollTo(0, 0)")
            await asyncio.sleep(1)
            
            # Get page text
            text = await page.inner_text("body")
            print(f"Page contains: {text[:1500]}")
            
            await ss(page, f"step{step}_top")
            
            # Scroll down
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(1)
            await ss(page, f"step{step}_bottom")
            
            # Dump visible fields
            await dump_fields(page)
            
            # Handle specific fields based on step
            if step == 1:  # My Information
                # Fill common fields if empty
                for aid, value in [
                    ("legalNameSection_firstName", "Priyanshu"),
                    ("legalNameSection_lastName", "Gupta"),
                    ("phone-number", "+917590082188"),
                    ("email", EMAIL),
                    ("addressSection_addressLine1", "India"),
                    ("addressSection_city", "Mumbai"),
                    ("addressSection_countryRegion", "India"),
                ]:
                    field = page.locator(f"input[data-automation-id='{aid}']")
                    if await field.count() > 0:
                        current = await field.first.input_value()
                        if not current:
                            await field.first.fill(value)
                            print(f"   Filled {aid} = {value}")
                
                # Check for resume upload
                file_input = page.locator("input[type='file']")
                if await file_input.count() > 0:
                    await file_input.first.set_input_files(RESUME)
                    print("   Uploaded resume")
                    await asyncio.sleep(3)
            
            elif step == 3:  # Application Questions
                # Common questions: How did you hear, salary expectations, etc.
                # Try to fill textareas
                textareas = page.locator("textarea:visible")
                ta_count = await textareas.count()
                for i in range(ta_count):
                    ta = textareas.nth(i)
                    current = await ta.input_value()
                    if not current:
                        label = await ta.evaluate("el => el.getAttribute('aria-label') || el.getAttribute('data-automation-id') || ''")
                        if 'salary' in label.lower() or 'compensation' in label.lower():
                            await ta.fill("25-35 LPA INR")
                        elif 'hear' in label.lower() or 'source' in label.lower():
                            await ta.fill("Company careers website")
                        else:
                            await ta.fill("N/A")
                        print(f"   Filled textarea: {label}")
                
                # Handle dropdowns
                selects = page.locator("select:visible")
                sel_count = await selects.count()
                for i in range(sel_count):
                    sel = selects.nth(i)
                    # Select first non-empty option
                    try:
                        await sel.select_option(index=1)
                        label = await sel.evaluate("el => el.getAttribute('aria-label') || ''")
                        print(f"   Selected option for: {label}")
                    except:
                        pass

            elif step == 4:  # Voluntary Disclosures
                # Usually optional, just move on
                print("   Voluntary disclosures - leaving defaults")
            
            elif step == 5:  # Review
                print("   Review step - checking for submit...")
                await ss(page, "review_page")
                
                # Look for Submit button
                submit = page.locator("button:has-text('Submit'), button[data-automation-id='submitButton']")
                if await submit.count() > 0:
                    print("   🚀 SUBMITTING APPLICATION!")
                    await submit.first.click(force=True)
                    await asyncio.sleep(5)
                    await ss(page, "submitted")
                    text = await page.inner_text("body")
                    if "thank" in text.lower() or "submitted" in text.lower() or "success" in text.lower():
                        print("   ✅ APPLICATION SUBMITTED SUCCESSFULLY!")
                    else:
                        print(f"   Post-submit page: {text[:500]}")
                    break
            
            # Click Save and Continue / Next
            if step < 5:
                print(f"   Clicking Save and Continue...")
                clicked = False
                for sel in [
                    "button[data-automation-id='bottom-navigation-next-button']",
                    "button:has-text('Save and Continue')",
                    "button:has-text('Next')",
                    "button:has-text('Continue')",
                ]:
                    btn = page.locator(sel)
                    if await btn.count() > 0:
                        try:
                            await btn.first.click(force=True)
                            clicked = True
                            print(f"   Clicked: {sel}")
                            break
                        except:
                            try:
                                await btn.first.evaluate("el => el.click()")
                                clicked = True
                                print(f"   JS-clicked: {sel}")
                                break
                            except:
                                pass
                
                if not clicked:
                    # Try the click_filter pattern
                    filters = page.locator("div[data-automation-id='click_filter']")
                    fcount = await filters.count()
                    for i in range(fcount):
                        label = await filters.nth(i).evaluate("el => el.getAttribute('aria-label') || ''")
                        if 'save' in label.lower() or 'continue' in label.lower() or 'next' in label.lower():
                            await filters.nth(i).click(force=True)
                            clicked = True
                            print(f"   Clicked click_filter: {label}")
                            break
                
                if not clicked:
                    print("   ⚠️ Could not find Next/Continue button!")
                
                await asyncio.sleep(5)
                
                # Check for validation errors
                errors = page.locator("[data-automation-id='errorMessage'], .error, div[role='alert']")
                if await errors.count() > 0:
                    for i in range(await errors.count()):
                        err = await errors.nth(i).inner_text()
                        if err.strip():
                            print(f"   ⚠️ Validation error: {err}")

        await ss(page, "final")
        print("\n✅ Script complete!")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
