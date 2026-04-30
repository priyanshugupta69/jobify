#!/usr/bin/env python3
"""Apply to ISS STOXX - properly fill all Step 1 fields using correct IDs."""

import asyncio
import json
from pathlib import Path
from playwright.async_api import async_playwright

JOB_URL = "https://issgovernance.wd1.myworkdayjobs.com/ISScareers/job/Mumbai-India/Software-Engineer--Python--Database-_JR_9501"
EMAIL = "priyanshuraja456@gmail.com"
PASSWORD = "ApKing3AkhGNUx!1"
RESUME = "/home/ubuntu/.openclaw/media/inbound/PriyanshuGuptaCV---aca58e11-0bd7-4ddd-a16e-98b2159de749.pdf"
SCREENSHOTS = Path("/home/ubuntu/.openclaw/workspace/job_pipeline/screenshots")
SCREENSHOTS.mkdir(exist_ok=True)

step_num = [0]

async def ss(page, name):
    step_num[0] += 1
    path = SCREENSHOTS / f"iss3_{step_num[0]:02d}_{name}.png"
    await page.screenshot(path=str(path), full_page=True)
    print(f"📸 {path}")

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 1200},
            user_agent="Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        page.set_default_timeout(15000)

        # === SIGN IN ===
        print("=== SIGNING IN ===")
        await page.goto(JOB_URL, wait_until="networkidle", timeout=60000)
        await asyncio.sleep(2)
        
        try:
            await page.locator("button:has-text('Accept Cookies')").first.click(timeout=3000)
        except:
            pass

        # Sign In
        await page.locator("button[data-automation-id='utilityButtonSignIn']").first.click(force=True)
        await asyncio.sleep(2)
        await page.locator("input[data-automation-id='email']").first.fill(EMAIL)
        await page.locator("input[type='password']").first.fill(PASSWORD)
        await asyncio.sleep(1)
        await page.locator("div[data-automation-id='click_filter'][aria-label='Sign In']").first.click(force=True)
        await asyncio.sleep(5)
        print(f"Signed in. URL: {page.url}")
        await ss(page, "signed_in")

        # === START APPLICATION ===
        print("\n=== STARTING APPLICATION ===")
        await page.locator("a:has-text('Apply'), button:has-text('Apply')").first.click()
        await asyncio.sleep(3)
        
        # Click "Apply Manually" (since no previous application exists)
        manual = page.locator("button:has-text('Apply Manually'), a:has-text('Apply Manually')")
        if await manual.count() > 0:
            await manual.first.click(force=True)
            print("Clicked 'Apply Manually'")
        else:
            # Try autofill with resume
            autofill = page.locator("button:has-text('Autofill with Resume')")
            if await autofill.count() > 0:
                await autofill.first.click(force=True)
                print("Clicked 'Autofill with Resume'")
        
        await asyncio.sleep(5)
        await ss(page, "form_start")

        # === STEP 1: MY INFORMATION ===
        print("\n=== STEP 1: MY INFORMATION ===")
        
        # 1. "How Did You Hear About Us?" - Workday multi-select dropdown
        # Click on the dropdown to open it, then select an option
        print("Filling 'How Did You Hear About Us?'...")
        source_input = page.locator("#source--source")
        await source_input.click()
        await asyncio.sleep(1)
        # Type to search
        await source_input.fill("Career")
        await asyncio.sleep(2)
        # Click the first option in the dropdown
        option = page.locator("[id^='source--source-option-']").first
        if await option.count() > 0:
            await option.click()
            print("   Selected source option")
        else:
            # Try clicking any visible option
            options = page.locator("[role='option'], li[role='option']")
            if await options.count() > 0:
                await options.first.click()
                print("   Selected first dropdown option")
            else:
                # Try just pressing Enter
                await page.keyboard.press("Enter")
                print("   Pressed Enter on source")
        await asyncio.sleep(1)
        
        # 2. "Previously worked?" - Click "No" radio
        print("Selecting 'No' for previously worked...")
        # Use value-based selector since IDs are dynamic
        no_radio = page.locator("input[type='radio'][name='candidateIsPreviousWorker'][value='false']")
        if await no_radio.count() > 0:
            await no_radio.first.click(force=True)
            print("   Clicked No radio")
        else:
            # Try clicking the label
            no_label = page.locator("label:has-text('No')")
            if await no_label.count() > 0:
                await no_label.first.click(force=True)
                print("   Clicked No label")
            else:
                # JS click
                await page.evaluate("""() => {
                    const radios = document.querySelectorAll('input[type=radio]');
                    for (const r of radios) {
                        if (r.value === 'false' && r.name.includes('previousWorker')) {
                            r.click();
                            r.dispatchEvent(new Event('change', {bubbles: true}));
                            return true;
                        }
                    }
                    // Try by index - the second radio is usually No
                    const allRadios = [...document.querySelectorAll('input[type=radio]')];
                    if (allRadios.length >= 2) {
                        allRadios[1].click();
                        allRadios[1].dispatchEvent(new Event('change', {bubbles: true}));
                    }
                }""")
                print("   JS-clicked No radio")
        await asyncio.sleep(1)
        
        # 3. Legal Name
        print("Filling name...")
        await page.locator("#name--legalName--firstName").fill("Priyanshu")
        await page.locator("#name--legalName--lastName").fill("Gupta")
        
        # 4. Address
        print("Filling address...")
        await page.locator("#address--addressLine1").fill("Mumbai")
        await page.locator("#address--city").fill("Mumbai")
        await page.locator("#address--postalCode").fill("400001")
        
        # 5. Phone - need to select Device Type dropdown first
        print("Filling phone...")
        # Phone Device Type - this is likely a Workday dropdown
        # Look for the select/dropdown for device type
        device_type = page.locator("select[id*='deviceType'], button[id*='deviceType'], [data-automation-id*='deviceType']")
        if await device_type.count() > 0:
            try:
                await device_type.first.click()
                await asyncio.sleep(1)
            except:
                pass
        else:
            # It might be a custom dropdown - look for it by label text
            # Try to find all dropdowns/selects on the page
            print("   Looking for Phone Device Type dropdown...")
            dropdowns = page.locator("button[aria-haspopup='listbox'], [role='listbox'], select")
            dd_count = await dropdowns.count()
            print(f"   Found {dd_count} dropdowns")
            for i in range(dd_count):
                dd = dropdowns.nth(i)
                text = await dd.inner_text()
                attrs = await dd.evaluate("el => ({id: el.id, aid: el.getAttribute('data-automation-id'), label: el.getAttribute('aria-label')})")
                print(f"   Dropdown {i}: text='{text[:50]}' attrs={attrs}")
        
        # Phone number
        await page.locator("#phoneNumber--phoneNumber").fill("7590082188")
        
        await ss(page, "step1_filled")
        
        # Now let's dump the full page HTML to understand the Phone Device Type widget
        print("\nDumping Phone Device Type area HTML...")
        phone_section_html = await page.evaluate("""() => {
            // Find elements containing 'Phone Device Type'
            const labels = document.querySelectorAll('label, span, div');
            for (const el of labels) {
                if (el.textContent.includes('Phone Device Type')) {
                    return el.parentElement.parentElement.innerHTML.substring(0, 2000);
                }
            }
            return 'Phone Device Type not found in labels';
        }""")
        print(f"Phone Device Type HTML: {phone_section_html[:1000]}")
        
        # Also get "How Did You Hear" status
        source_status = await page.evaluate("""() => {
            const el = document.querySelector('#source--source');
            if (el) return {value: el.value, parentHTML: el.parentElement.innerHTML.substring(0, 500)};
            return 'not found';
        }""")
        print(f"\nSource field status: {source_status}")
        
        # Try clicking Save and Continue to see what errors remain
        print("\nClicking Save and Continue...")
        await page.locator("button:has-text('Save and Continue')").first.click(force=True)
        await asyncio.sleep(3)
        await ss(page, "step1_after_save")
        
        # Check for errors
        text = await page.inner_text("body")
        if "Error" in text:
            # Extract error messages
            errors = []
            for line in text.split('\n'):
                if line.strip().startswith('Error-') or 'is required' in line:
                    errors.append(line.strip())
            print(f"\nRemaining errors: {errors}")
        
        # Check current step
        if "step 2" in text.lower() or "my experience" in text.lower():
            print("\n✅ Advanced to Step 2!")
        else:
            print("\n❌ Still on Step 1")
        
        # Print first 2000 chars
        print(f"\nPage: {text[:2000]}")
        
        await ss(page, "current_state")
        await browser.close()
        print("\nDone!")

if __name__ == "__main__":
    asyncio.run(main())
