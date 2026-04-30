#!/usr/bin/env python3
"""ISS STOXX v6 - Robust popup + form handling."""

import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

JOB_URL = "https://issgovernance.wd1.myworkdayjobs.com/ISScareers/job/Mumbai-India/Software-Engineer--Python--Database-_JR_9501"
EMAIL = "priyanshuraja456@gmail.com"
PASSWORD = "ApKing3AkhGNUx!1"
RESUME = "/home/ubuntu/.openclaw/media/inbound/PriyanshuGuptaCV---aca58e11-0bd7-4ddd-a16e-98b2159de749.pdf"
SCREENSHOTS = Path("/home/ubuntu/.openclaw/workspace/job_pipeline/screenshots")
SCREENSHOTS.mkdir(exist_ok=True)
sn = [0]

async def ss(page, name):
    sn[0] += 1
    path = SCREENSHOTS / f"iss6_{sn[0]:02d}_{name}.png"
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
        page.set_default_timeout(20000)

        # === SIGN IN ===
        print("=== SIGNING IN ===")
        await page.goto(JOB_URL, wait_until="networkidle", timeout=60000)
        await asyncio.sleep(3)
        try:
            await page.locator("button:has-text('Accept Cookies')").first.click(timeout=3000)
            await asyncio.sleep(1)
        except: pass
        
        await page.locator("button[data-automation-id='utilityButtonSignIn']").first.click(force=True)
        await asyncio.sleep(3)
        await page.locator("input[data-automation-id='email']").first.fill(EMAIL)
        await page.locator("input[type='password']").first.fill(PASSWORD)
        await asyncio.sleep(1)
        await page.locator("div[data-automation-id='click_filter'][aria-label='Sign In']").first.click(force=True)
        await asyncio.sleep(6)
        print("Signed in ✓")

        # === CLICK APPLY ===
        print("\n=== CLICKING APPLY ===")
        apply_btn = page.locator("a:has-text('Apply'), button:has-text('Apply')")
        await apply_btn.first.click()
        await asyncio.sleep(4)
        await ss(page, "popup")
        
        # === HANDLE POPUP ===
        # The popup uses Workday's glass overlay. Need to click buttons inside it.
        # Let's find all clickable elements in the popup
        popup_html = await page.evaluate("""() => {
            const popup = document.querySelector('[data-automation-id="wd-popup-glass"]');
            if (popup) {
                // Get all buttons/links in popup
                const clickables = popup.querySelectorAll('button, a, [role="button"], [data-automation-id]');
                return Array.from(clickables).map(el => ({
                    tag: el.tagName,
                    text: el.textContent.trim().substring(0, 50),
                    aid: el.getAttribute('data-automation-id'),
                    role: el.getAttribute('role'),
                    href: el.getAttribute('href')
                }));
            }
            return 'no popup found';
        }""")
        print(f"Popup elements: {popup_html}")
        
        # Click "Apply Manually" - use JavaScript to bypass overlay issues
        result = await page.evaluate("""() => {
            const popup = document.querySelector('[data-automation-id="wd-popup-glass"]') || document;
            const elements = popup.querySelectorAll('button, a, [role="button"], div[data-automation-id="click_filter"]');
            for (const el of elements) {
                const text = el.textContent.trim();
                if (text === 'Apply Manually') {
                    el.click();
                    return 'clicked Apply Manually';
                }
            }
            // Try "Autofill with Resume"
            for (const el of elements) {
                const text = el.textContent.trim();
                if (text.includes('Autofill with Resume')) {
                    el.click();
                    return 'clicked Autofill with Resume';
                }
            }
            // Try anything with "Apply"
            for (const el of elements) {
                const text = el.textContent.trim();
                if (text.includes('Apply') && !text.includes('LinkedIn') && text !== 'Apply') {
                    el.click();
                    return 'clicked: ' + text;
                }
            }
            return 'no matching button';
        }""")
        print(f"Popup click: {result}")
        await asyncio.sleep(6)
        await ss(page, "after_popup")
        
        # Verify we're on the form
        text = await page.inner_text("body")
        if "My Information" not in text:
            print("Not on form yet. Page text:")
            print(text[:500])
            # Maybe the popup is still there or we need to wait
            # Try again with a different approach
            await page.evaluate("""() => {
                // Force close any popup
                const glass = document.querySelector('[data-automation-id="wd-popup-glass"]');
                if (glass) glass.remove();
            }""")
            await asyncio.sleep(2)
        
        # Check again
        text = await page.inner_text("body")
        if "My Information" not in text:
            print("Still not on form. Trying to navigate directly...")
            # Maybe we need to go to the apply URL directly
            await ss(page, "not_on_form")
            # Let's try a different URL pattern
            await page.goto(JOB_URL + "/apply", wait_until="networkidle", timeout=30000)
            await asyncio.sleep(5)
            text = await page.inner_text("body")
        
        print(f"\nCurrent page (first 500): {text[:500]}")
        await ss(page, "current_state")
        
        if "My Information" not in text:
            print("\n❌ Could not reach form. Aborting.")
            await browser.close()
            return
        
        # === NOW FILL STEP 1 ===
        print("\n=== STEP 1: MY INFORMATION ===")
        
        # Wait for fields to be ready
        await page.wait_for_selector("#name--legalName--firstName", timeout=10000)
        
        # 1. HOW DID YOU HEAR - Workday multiselect
        print("\n1. Source dropdown")
        source = page.locator("#source--source")
        if await source.count() > 0:
            await source.click()
            await asyncio.sleep(1)
            # Clear and type
            await source.fill("")
            await asyncio.sleep(1)
            
            # Get the active list container content
            active_list = await page.evaluate("""() => {
                const lists = document.querySelectorAll('[data-automation-id="activeListContainer"]');
                for (const list of lists) {
                    const items = list.querySelectorAll('[role="option"]');
                    if (items.length > 0) {
                        return Array.from(items).map(i => ({text: i.textContent.trim(), id: i.id}));
                    }
                }
                return [];
            }""")
            print(f"   Active list: {active_list}")
            
            # Type to filter
            await source.fill("Career")
            await asyncio.sleep(2)
            
            # Click the Career Sites option via JS on the correct list
            clicked = await page.evaluate("""() => {
                const lists = document.querySelectorAll('[data-automation-id="activeListContainer"]');
                for (const list of lists) {
                    const items = list.querySelectorAll('[role="option"]');
                    for (const item of items) {
                        if (item.textContent.includes('Career')) {
                            item.click();
                            return 'clicked: ' + item.textContent.trim();
                        }
                    }
                    // Click first if no career match
                    if (items.length > 0) {
                        items[0].click();
                        return 'clicked first: ' + items[0].textContent.trim();
                    }
                }
                // Fallback: try any visible option with "Career" text
                const allOpts = document.querySelectorAll('[role="option"]');
                for (const opt of allOpts) {
                    if (opt.textContent.includes('Career')) {
                        opt.click();
                        return 'global clicked: ' + opt.textContent.trim();
                    }
                }
                return 'nothing clicked';
            }""")
            print(f"   Result: {clicked}")
            await asyncio.sleep(1)
            await page.keyboard.press("Escape")
            await asyncio.sleep(1)
        
        # Check if source has a selection now
        source_val = await page.evaluate("""() => {
            // Look for pill/tag indicating selection
            const source = document.querySelector('#source--source');
            const container = source?.closest('.css-g3k79h, [data-uxi-widget-type]')?.parentElement;
            if (container) {
                const pills = container.querySelectorAll('[data-automation-id="selectedItem"], [data-automation-id="promptSelectionLabel"]');
                if (pills.length > 0) return Array.from(pills).map(p => p.textContent.trim());
            }
            // Check the label below the input that shows "X items selected"
            const labels = document.querySelectorAll('*');
            for (const el of labels) {
                if (el.textContent.includes('items selected') || el.textContent.includes('item selected')) {
                    return el.textContent.trim();
                }
            }
            return 'unknown';
        }""")
        print(f"   Source selection: {source_val}")
        
        # 2. PREVIOUSLY WORKED - Radio
        print("\n2. Previously worked → No")
        # Click the label "No" that is near the radio input
        clicked = await page.evaluate("""() => {
            const labels = document.querySelectorAll('label');
            for (const label of labels) {
                if (label.textContent.trim() === 'No') {
                    const radio = label.querySelector('input[type="radio"]');
                    if (radio) {
                        // Simulate a full user click
                        label.dispatchEvent(new MouseEvent('mousedown', {bubbles: true}));
                        label.dispatchEvent(new MouseEvent('mouseup', {bubbles: true}));
                        label.dispatchEvent(new MouseEvent('click', {bubbles: true}));
                        if (radio) {
                            radio.dispatchEvent(new MouseEvent('click', {bubbles: true}));
                        }
                        return 'dispatched events on No label, radio checked: ' + radio.checked;
                    }
                }
            }
            return 'No label not found';
        }""")
        print(f"   Result: {clicked}")
        
        # Playwright click as backup
        no_label = page.locator("label:has-text('No'):near(input[type='radio'])")
        if await no_label.count() > 0:
            try:
                await no_label.first.click()
                print("   Also Playwright-clicked No label")
            except:
                pass
        
        await asyncio.sleep(1)
        
        # 3-6. Other fields
        print("\n3-6. Other fields...")
        await page.locator("#name--legalName--firstName").fill("Priyanshu")
        await page.locator("#name--legalName--lastName").fill("Gupta")
        await page.locator("#address--addressLine1").fill("Mumbai")
        await page.locator("#address--city").fill("Mumbai")
        await page.locator("#address--postalCode").fill("400001")
        
        # Phone Device Type
        await page.locator("#phoneNumber--phoneType").click()
        await asyncio.sleep(1)
        await page.evaluate("""() => {
            const opts = document.querySelectorAll('[role="option"]');
            for (const opt of opts) {
                if (opt.textContent.trim() === 'Mobile') {
                    opt.click();
                    return;
                }
            }
        }""")
        await asyncio.sleep(1)
        
        await page.locator("#phoneNumber--phoneNumber").fill("7590082188")
        print("   Done ✓")
        
        await ss(page, "step1_filled")
        
        # === SAVE ===
        print("\n=== SAVING STEP 1 ===")
        await page.locator("button:has-text('Save and Continue')").first.click(force=True)
        await asyncio.sleep(5)
        await ss(page, "after_save1")
        
        text = await page.inner_text("body")
        errors = [l.strip() for l in text.split('\n') if l.strip().startswith('Error-')]
        print(f"Errors: {errors}")
        
        if "current step 2" in text:
            print("\n✅ STEP 1 COMPLETE!")
        else:
            print(f"\nStill on step 1. First 2000 chars:")
            print(text[:2000])
        
        # === REMAINING STEPS ===
        for step_num in range(2, 6):
            text = await page.inner_text("body")
            if f"current step {step_num}" not in text:
                continue
            
            print(f"\n=== STEP {step_num} ===")
            await ss(page, f"step{step_num}")
            
            if step_num == 2:  # My Experience
                file_input = page.locator("input[type='file']")
                if await file_input.count() > 0:
                    await file_input.first.set_input_files(RESUME)
                    print("   Resume uploaded ✓")
                    await asyncio.sleep(5)
            
            if step_num == 5:  # Review
                submit = page.locator("button:has-text('Submit')")
                if await submit.count() > 0:
                    print("   🚀 SUBMITTING!")
                    await submit.first.click(force=True)
                    await asyncio.sleep(5)
                    final = await page.inner_text("body")
                    await ss(page, "submitted")
                    if any(w in final.lower() for w in ["thank", "submitted", "success"]):
                        print("   ✅✅✅ APPLICATION SUBMITTED! ✅✅✅")
                    else:
                        print(f"   Post-submit: {final[:500]}")
                    break
            
            # Save and Continue
            save = page.locator("button:has-text('Save and Continue')")
            if await save.count() > 0:
                await save.first.click(force=True)
                await asyncio.sleep(5)
        
        await ss(page, "final")
        await browser.close()
        print("\n=== DONE ===")

if __name__ == "__main__":
    asyncio.run(main())
