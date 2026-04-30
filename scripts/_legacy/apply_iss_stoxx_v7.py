#!/usr/bin/env python3
"""ISS STOXX v7 - Navigate directly to apply URL, wait for form, use keyboard for Workday widgets."""

import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

APPLY_URL = "https://issgovernance.wd1.myworkdayjobs.com/en-US/ISScareers/job/Mumbai%2C-India/Software-Engineer--Python--Database-_JR_9501/apply/applyManually"
EMAIL = "priyanshuraja456@gmail.com"
PASSWORD = "ApKing3AkhGNUx!1"
RESUME = "/home/ubuntu/.openclaw/media/inbound/PriyanshuGuptaCV---aca58e11-0bd7-4ddd-a16e-98b2159de749.pdf"
SCREENSHOTS = Path("/home/ubuntu/.openclaw/workspace/job_pipeline/screenshots")
SCREENSHOTS.mkdir(exist_ok=True)
sn = [0]

async def ss(page, name):
    sn[0] += 1
    path = SCREENSHOTS / f"iss7_{sn[0]:02d}_{name}.png"
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

        # === SIGN IN FIRST (go to main page, sign in, then navigate to apply) ===
        print("=== SIGNING IN ===")
        await page.goto("https://issgovernance.wd1.myworkdayjobs.com/ISScareers", wait_until="networkidle", timeout=60000)
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
        
        # === NAVIGATE TO APPLY PAGE DIRECTLY ===
        print("\n=== NAVIGATING TO APPLICATION FORM ===")
        await page.goto(APPLY_URL, wait_until="networkidle", timeout=60000)
        await asyncio.sleep(5)
        
        # Wait for the form to render
        try:
            await page.wait_for_selector("#name--legalName--firstName", timeout=15000)
            print("Form loaded ✓")
        except:
            print("Form fields not found, waiting more...")
            await asyncio.sleep(5)
            # Scroll to trigger lazy load
            await page.evaluate("window.scrollTo(0, 500)")
            await asyncio.sleep(3)
        
        await ss(page, "form_loaded")
        
        # Dump all visible interactive elements for debugging
        fields_info = await page.evaluate("""() => {
            const inputs = document.querySelectorAll('input, select, button[aria-haspopup], [role="listbox"]');
            return Array.from(inputs).filter(el => el.offsetParent !== null).map(el => ({
                tag: el.tagName,
                type: el.type,
                id: el.id,
                name: el.name,
                aid: el.getAttribute('data-automation-id'),
                label: el.getAttribute('aria-label'),
                value: el.value?.substring(0, 30),
                checked: el.checked
            }));
        }""")
        print(f"\nAll visible fields ({len(fields_info)}):")
        for f in fields_info:
            print(f"  {f}")
        
        # === FILL STEP 1 ===
        print("\n=== FILLING STEP 1 ===")
        
        # --- 1. "How Did You Hear About Us?" multi-select ---
        print("\n1. HOW DID YOU HEAR ABOUT US")
        source = page.locator("#source--source")
        if await source.count() > 0:
            # Click to focus and open dropdown
            await source.click()
            await asyncio.sleep(1)
            
            # Clear any existing text
            await page.keyboard.press("Control+A")
            await page.keyboard.press("Backspace")
            await asyncio.sleep(1)
            
            # Type search term
            await page.keyboard.type("Career", delay=100)
            await asyncio.sleep(2)
            
            await ss(page, "source_typing")
            
            # Use keyboard to select: ArrowDown then Enter
            await page.keyboard.press("ArrowDown")
            await asyncio.sleep(500)
            await page.keyboard.press("Enter")
            await asyncio.sleep(1)
            
            # Check if selected
            sel = await page.evaluate("""() => {
                const container = document.querySelector('#source--source')?.parentElement?.parentElement;
                return container?.textContent?.substring(0, 200);
            }""")
            print(f"   After select: {sel}")
            
            # Tab out to close
            await page.keyboard.press("Tab")
            await asyncio.sleep(1)
        else:
            print("   Source input not found!")
        
        # --- 2. "Previously worked?" radio ---
        print("\n2. PREVIOUSLY WORKED → No")
        
        # Try using Playwright's check() method which handles React better
        radios = page.locator("input[type='radio']")
        count = await radios.count()
        print(f"   Found {count} radio inputs")
        for i in range(count):
            r = radios.nth(i)
            attrs = await r.evaluate("el => ({id: el.id, name: el.name, value: el.value, checked: el.checked})")
            print(f"   Radio {i}: {attrs}")
            if attrs.get('value') == 'false':
                # Use check() instead of click()
                try:
                    await r.check(force=True)
                    print(f"   ✓ Checked radio {i} (value=false)")
                except Exception as e:
                    print(f"   check() failed: {e}")
                    # Try JS with full event simulation
                    await r.evaluate("""el => {
                        el.checked = true;
                        el.dispatchEvent(new Event('input', {bubbles: true}));
                        el.dispatchEvent(new Event('change', {bubbles: true}));
                        // React 16/17 trick
                        const tracker = el._valueTracker;
                        if (tracker) tracker.setValue('true');
                        el.dispatchEvent(new Event('input', {bubbles: true}));
                    }""")
                    print("   Used React valueTracker hack")
        
        # Also try clicking the label container
        await page.evaluate("""() => {
            const labels = document.querySelectorAll('label');
            for (const label of labels) {
                if (label.textContent.trim() === 'No') {
                    // Simulate real mouse events
                    const rect = label.getBoundingClientRect();
                    const events = ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click'];
                    for (const type of events) {
                        label.dispatchEvent(new MouseEvent(type, {
                            bubbles: true, cancelable: true, view: window,
                            clientX: rect.left + rect.width/2,
                            clientY: rect.top + rect.height/2
                        }));
                    }
                    return 'dispatched full mouse events on No label';
                }
            }
        }""")
        print("   Dispatched full mouse events on No label")
        await asyncio.sleep(1)
        
        # Verify
        radio_states = await page.evaluate("""() => {
            return Array.from(document.querySelectorAll('input[type="radio"]')).map(r => ({
                id: r.id, value: r.value, checked: r.checked, name: r.name
            }));
        }""")
        print(f"   Radio states after: {radio_states}")
        
        # --- 3. Name ---
        print("\n3. NAME")
        await page.locator("#name--legalName--firstName").fill("Priyanshu")
        await page.locator("#name--legalName--lastName").fill("Gupta")
        print("   ✓ Priyanshu Gupta")
        
        # --- 4. Address ---
        print("\n4. ADDRESS")
        await page.locator("#address--addressLine1").fill("Mumbai")
        await page.locator("#address--city").fill("Mumbai")
        await page.locator("#address--postalCode").fill("400001")
        print("   ✓ Mumbai")
        
        # --- 5. Phone Device Type ---
        print("\n5. PHONE DEVICE TYPE")
        phone_type = page.locator("#phoneNumber--phoneType")
        if await phone_type.count() > 0:
            await phone_type.click()
            await asyncio.sleep(1)
            # Use keyboard to navigate
            await page.keyboard.press("ArrowDown")  # Skip "Select One"
            await page.keyboard.press("ArrowDown")  # Skip another if needed
            await asyncio.sleep(500)
            
            # Try to find Mobile specifically
            result = await page.evaluate("""() => {
                const opts = document.querySelectorAll('[role="option"]');
                for (const opt of opts) {
                    if (opt.textContent.trim() === 'Mobile') {
                        opt.click();
                        return 'clicked Mobile';
                    }
                }
                return 'Mobile not found, opts: ' + Array.from(opts).map(o => o.textContent.trim()).join(', ');
            }""")
            print(f"   {result}")
            await asyncio.sleep(1)
        
        # --- 6. Phone Number ---
        print("\n6. PHONE NUMBER")
        await page.locator("#phoneNumber--phoneNumber").fill("7590082188")
        print("   ✓ 7590082188")
        
        await ss(page, "all_filled")
        
        # === SAVE STEP 1 ===
        print("\n=== SAVING STEP 1 ===")
        await page.locator("button:has-text('Save and Continue')").first.click(force=True)
        await asyncio.sleep(5)
        await ss(page, "after_save1")
        
        text = await page.inner_text("body")
        errors = [l.strip() for l in text.split('\n') if l.strip().startswith('Error-')]
        
        if errors:
            print(f"\n❌ Remaining errors: {errors}")
            
            # LAST RESORT: Try using page.goto to the Autofill URL instead
            # Autofill with Resume might handle these fields differently
            print("\n   Trying Autofill with Resume approach...")
            autofill_url = "https://issgovernance.wd1.myworkdayjobs.com/en-US/ISScareers/job/Mumbai%2C-India/Software-Engineer--Python--Database-_JR_9501/apply/autofillWithResume"
            await page.goto(autofill_url, wait_until="networkidle", timeout=30000)
            await asyncio.sleep(5)
            await ss(page, "autofill_page")
            
            text = await page.inner_text("body")
            print(f"   Autofill page: {text[:500]}")
            
            # Upload resume if there's a file input
            file_input = page.locator("input[type='file']")
            if await file_input.count() > 0:
                await file_input.first.set_input_files(RESUME)
                print("   Resume uploaded for autofill!")
                await asyncio.sleep(10)
                await ss(page, "after_autofill")
                text = await page.inner_text("body")
                print(f"   After autofill: {text[:1000]}")
        else:
            print("\n✅ STEP 1 COMPLETE!")
        
        # Continue with remaining steps
        for step_num in range(2, 6):
            text = await page.inner_text("body")
            if f"current step {step_num}" not in text:
                if step_num == 2 and "My Experience" in text:
                    pass  # ok
                else:
                    continue
            
            print(f"\n=== STEP {step_num} ===")
            print(f"   Page: {text[:1000]}")
            await ss(page, f"step{step_num}")
            
            if step_num == 2:
                file_input = page.locator("input[type='file']")
                if await file_input.count() > 0:
                    await file_input.first.set_input_files(RESUME)
                    print("   Resume uploaded ✓")
                    await asyncio.sleep(5)
            
            if step_num == 5:
                submit = page.locator("button:has-text('Submit')")
                if await submit.count() > 0:
                    await submit.first.click(force=True)
                    await asyncio.sleep(5)
                    final = await page.inner_text("body")
                    await ss(page, "submitted")
                    print(f"   Result: {final[:500]}")
                    if any(w in final.lower() for w in ["thank", "submitted", "success"]):
                        print("   ✅✅✅ APPLICATION SUBMITTED! ✅✅✅")
                    break
            
            save = page.locator("button:has-text('Save and Continue')")
            if await save.count() > 0:
                await save.first.click(force=True)
                await asyncio.sleep(5)
        
        await ss(page, "final")
        await browser.close()
        print("\n=== DONE ===")

if __name__ == "__main__":
    asyncio.run(main())
