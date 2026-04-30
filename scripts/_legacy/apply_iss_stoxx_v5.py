#!/usr/bin/env python3
"""ISS STOXX v5 - Fix the last 2 stubborn fields with proper Workday widget interaction."""

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
    path = SCREENSHOTS / f"iss5_{sn[0]:02d}_{name}.png"
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
        except: pass
        await page.locator("button[data-automation-id='utilityButtonSignIn']").first.click(force=True)
        await asyncio.sleep(2)
        await page.locator("input[data-automation-id='email']").first.fill(EMAIL)
        await page.locator("input[type='password']").first.fill(PASSWORD)
        await asyncio.sleep(1)
        await page.locator("div[data-automation-id='click_filter'][aria-label='Sign In']").first.click(force=True)
        await asyncio.sleep(5)
        print("Signed in ✓")

        # === START APPLICATION ===
        print("\n=== STARTING APPLICATION ===")
        await page.locator("a:has-text('Apply'), button:has-text('Apply')").first.click()
        await asyncio.sleep(3)
        for btn_text in ["Apply Manually", "Use My Last Application", "Autofill with Resume"]:
            btn = page.locator(f"button:has-text('{btn_text}')")
            if await btn.count() > 0:
                await btn.first.click(force=True)
                print(f"Clicked '{btn_text}' ✓")
                break
        await asyncio.sleep(5)
        await ss(page, "form_loaded")

        # === STEP 1: MY INFORMATION ===
        print("\n=== STEP 1: MY INFORMATION ===")
        
        # --- 1. "How Did You Hear About Us?" ---
        # This is a Workday multi-select widget. The issue before was that [role='option'] 
        # was matching options from OTHER dropdowns on the page.
        # We need to scope to the correct dropdown container.
        print("\n1. How Did You Hear About Us?")
        
        # First, scroll to top to make sure source field is in view
        await page.evaluate("window.scrollTo(0, 0)")
        await asyncio.sleep(1)
        
        # Click the source search input to open its dropdown
        source = page.locator("#source--source")
        await source.scroll_into_view_if_needed()
        await asyncio.sleep(1)
        await source.click()
        await asyncio.sleep(1)
        
        # Type "Career" to filter
        await source.fill("Career")
        await asyncio.sleep(2)
        await ss(page, "source_dropdown")
        
        # Now find the dropdown that's associated with this input
        # Workday uses data-automation-id="activeListContainer" for the active dropdown
        # But let's be more specific - look for the option nearest to the source input
        
        # Use JavaScript to find and click the correct option
        result = await page.evaluate("""() => {
            // Find the source input
            const input = document.querySelector('#source--source');
            if (!input) return 'no input found';
            
            // Navigate up to find the multi-select container
            let container = input.closest('[data-automation-id="multiSelectContainer"], [data-automation-id="formField-source"]');
            if (!container) {
                // Try going up a few levels
                container = input.parentElement?.parentElement?.parentElement?.parentElement;
            }
            
            if (!container) return 'no container found';
            
            // Find options within or near this container
            const options = container.querySelectorAll('[role="option"], li');
            const result = [];
            for (const opt of options) {
                result.push(opt.textContent.trim());
            }
            
            // If no options in container, look for the global active list
            if (options.length === 0) {
                const activeList = document.querySelector('[data-automation-id="activeListContainer"]');
                if (activeList) {
                    const activeOptions = activeList.querySelectorAll('[role="option"], li');
                    for (const opt of activeOptions) {
                        const text = opt.textContent.trim();
                        result.push(text);
                        if (text.toLowerCase().includes('career')) {
                            opt.click();
                            return 'CLICKED: ' + text;
                        }
                    }
                }
            } else {
                // Click the Career option
                for (const opt of options) {
                    if (opt.textContent.toLowerCase().includes('career')) {
                        opt.click();
                        return 'CLICKED: ' + opt.textContent.trim();
                    }
                }
                // Click first option as fallback
                if (options.length > 0) {
                    options[0].click();
                    return 'CLICKED FIRST: ' + options[0].textContent.trim();
                }
            }
            
            return 'options found: ' + JSON.stringify(result);
        }""")
        print(f"   Source result: {result}")
        await asyncio.sleep(1)
        
        # If the above didn't work, try pressing ArrowDown + Enter
        if "CLICKED" not in str(result):
            await source.press("ArrowDown")
            await asyncio.sleep(500)
            await source.press("Enter")
            print("   Tried ArrowDown + Enter")
        
        # Click elsewhere to close
        await page.keyboard.press("Escape")
        await asyncio.sleep(1)
        
        # Check if selection registered
        selected_items = await page.evaluate("""() => {
            const container = document.querySelector('#source--source')?.closest('[data-automation-id="multiSelectContainer"]');
            if (!container) return 'no container';
            // Look for selected pills/tags
            const pills = container.querySelectorAll('[data-automation-id="selectedItem"], [data-automation-id="promptSelectionLabel"]');
            return Array.from(pills).map(p => p.textContent.trim());
        }""")
        print(f"   Selected items: {selected_items}")
        
        await ss(page, "after_source_select")
        
        # --- 2. "Previously worked?" ---
        print("\n2. Previously worked? → No")
        
        # Workday custom radio buttons need special handling
        # They use div wrappers that capture events, not standard radio inputs
        result = await page.evaluate("""() => {
            // Method 1: Find by label text and trigger React-compatible events
            const labels = document.querySelectorAll('label');
            for (const label of labels) {
                if (label.textContent.trim() === 'No') {
                    const input = label.querySelector('input[type="radio"]') || 
                                  document.querySelector('#' + label.getAttribute('for'));
                    if (input) {
                        // Set the value
                        const nativeInputValueSetter = Object.getOwnPropertyDescriptor(
                            window.HTMLInputElement.prototype, 'checked'
                        ).set;
                        nativeInputValueSetter.call(input, true);
                        
                        // Dispatch events that React listens to
                        input.dispatchEvent(new Event('input', { bubbles: true }));
                        input.dispatchEvent(new Event('change', { bubbles: true }));
                        input.dispatchEvent(new MouseEvent('click', { bubbles: true }));
                        
                        return 'set via React setter + events';
                    }
                    // Try clicking the label itself
                    label.click();
                    return 'clicked label';
                }
            }
            
            // Method 2: Find radio by value
            const radios = document.querySelectorAll('input[type="radio"][value="false"]');
            for (const radio of radios) {
                radio.click();
                return 'clicked radio value=false';
            }
            
            return 'not found';
        }""")
        print(f"   Radio result: {result}")
        
        # Also try direct Playwright interaction with the label
        # Workday wraps radios in divs with click handlers
        try:
            # Find the "No" text near a radio and click its container
            no_container = page.locator("label:has(input[type='radio'][value='false'])")
            if await no_container.count() > 0:
                await no_container.first.click(force=True)
                print("   Clicked No container via Playwright")
            else:
                # Try clicking the label text "No"
                all_text = page.locator("text=No")
                count = await all_text.count()
                for i in range(count):
                    parent = all_text.nth(i).locator("..")
                    tag = await parent.evaluate("el => el.tagName")
                    if tag == "LABEL":
                        await all_text.nth(i).click(force=True)
                        print(f"   Clicked 'No' text element {i}")
                        break
        except Exception as e:
            print(f"   Playwright click error: {e}")
        
        await asyncio.sleep(1)
        
        # Verify radio state
        radio_state = await page.evaluate("""() => {
            const radios = document.querySelectorAll('input[type="radio"]');
            return Array.from(radios).map(r => ({
                name: r.name, value: r.value, checked: r.checked, 
                id: r.id, labelText: r.closest('label')?.textContent?.trim()
            }));
        }""")
        print(f"   Radio states: {radio_state}")
        
        await ss(page, "after_radio")
        
        # --- 3-6: Other fields (already working) ---
        print("\n3-6. Filling other fields...")
        await page.locator("#name--legalName--firstName").fill("Priyanshu")
        await page.locator("#name--legalName--lastName").fill("Gupta")
        await page.locator("#address--addressLine1").fill("Mumbai")
        await page.locator("#address--city").fill("Mumbai")
        await page.locator("#address--postalCode").fill("400001")
        
        # Phone Device Type
        await page.locator("#phoneNumber--phoneType").click()
        await asyncio.sleep(1)
        mobile_opt = page.locator("[role='option']:has-text('Mobile')")
        if await mobile_opt.count() > 0:
            await mobile_opt.first.click()
        await asyncio.sleep(1)
        
        await page.locator("#phoneNumber--phoneNumber").fill("7590082188")
        print("   All other fields filled ✓")
        
        await ss(page, "all_fields_done")
        
        # === SAVE STEP 1 ===
        print("\n=== Saving Step 1 ===")
        await page.locator("button:has-text('Save and Continue')").first.click(force=True)
        await asyncio.sleep(5)
        await ss(page, "after_save")
        
        text = await page.inner_text("body")
        errors = [l.strip() for l in text.split('\n') if l.strip().startswith('Error-')]
        if errors:
            print(f"   Errors: {errors}")
        
        if "current step 2" in text or ("My Experience" in text and "current step" in text and "1 of 5" not in text):
            print("   ✅ STEP 1 COMPLETE!")
        elif "current step 1" in text:
            print("   ❌ Still on Step 1")
            # Last resort: try to use JavaScript to submit the form data
            print("\n   Trying JS form manipulation...")
            
            # For "How Did You Hear" - try simulating the Workday multiselect properly
            await page.evaluate("""() => {
                // Find and click the source search box
                const sourceInput = document.querySelector('#source--source');
                if (sourceInput) {
                    sourceInput.focus();
                    sourceInput.click();
                }
            }""")
            await asyncio.sleep(2)
            
            # Now use keyboard to navigate
            await page.locator("#source--source").fill("")
            await asyncio.sleep(1)
            await page.locator("#source--source").type("Career Sites", delay=100)
            await asyncio.sleep(2)
            await page.keyboard.press("ArrowDown")
            await asyncio.sleep(500)
            await page.keyboard.press("Enter")
            await asyncio.sleep(1)
            
            # Check selection
            sel_check = await page.evaluate("""() => {
                const el = document.querySelector('#source--source');
                const parent = el?.parentElement;
                return parent?.innerHTML?.substring(0, 500);
            }""")
            print(f"   Source parent HTML: {sel_check}")
            
            await ss(page, "retry_source")
            
            # Try save again
            await page.locator("button:has-text('Save and Continue')").first.click(force=True)
            await asyncio.sleep(5)
            text = await page.inner_text("body")
            errors = [l.strip() for l in text.split('\n') if l.strip().startswith('Error-')]
            print(f"   Errors after retry: {errors}")
            await ss(page, "after_retry_save")
            
            if errors:
                print(f"\n   Page: {text[:2000]}")
        
        # Continue with remaining steps if we made it past step 1
        current_text = await page.inner_text("body")
        
        # === STEP 2+ ===
        for step_name in ["My Experience", "Application Questions", "Voluntary Disclosures", "Review"]:
            if step_name.lower() not in current_text.lower():
                continue
            print(f"\n=== {step_name.upper()} ===")
            await ss(page, step_name.replace(" ", "_").lower())
            
            if step_name == "My Experience":
                # Upload resume if there's a file input
                file_input = page.locator("input[type='file']")
                if await file_input.count() > 0:
                    await file_input.first.set_input_files(RESUME)
                    print("   ✓ Resume uploaded")
                    await asyncio.sleep(5)
            
            elif step_name == "Review":
                submit = page.locator("button:has-text('Submit')")
                if await submit.count() > 0:
                    print("   🚀 SUBMITTING!")
                    await submit.first.click(force=True)
                    await asyncio.sleep(5)
                    final_text = await page.inner_text("body")
                    if any(w in final_text.lower() for w in ["thank", "submitted", "success"]):
                        print("   ✅✅✅ APPLICATION SUBMITTED! ✅✅✅")
                    else:
                        print(f"   Post-submit: {final_text[:500]}")
                    await ss(page, "submitted")
                    break
            
            # Save and Continue
            save_btn = page.locator("button:has-text('Save and Continue')")
            if await save_btn.count() > 0:
                await save_btn.first.click(force=True)
                await asyncio.sleep(5)
            
            current_text = await page.inner_text("body")
        
        await ss(page, "final")
        await browser.close()
        print("\n=== DONE ===")

if __name__ == "__main__":
    asyncio.run(main())
