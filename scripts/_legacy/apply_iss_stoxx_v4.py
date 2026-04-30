#!/usr/bin/env python3
"""ISS STOXX application - fix the 3 remaining Step 1 fields, then complete all steps."""

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
sn = [0]

async def ss(page, name):
    sn[0] += 1
    path = SCREENSHOTS / f"iss4_{sn[0]:02d}_{name}.png"
    await page.screenshot(path=str(path), full_page=True)
    print(f"📸 {path}")

async def workday_select_dropdown(page, button_id, option_text):
    """Select an option from a Workday custom dropdown by button ID."""
    btn = page.locator(f"#{button_id}")
    await btn.click()
    await asyncio.sleep(1)
    # Find the option in the opened listbox
    option = page.locator(f"[role='option']:has-text('{option_text}'), li:has-text('{option_text}')")
    if await option.count() > 0:
        await option.first.click()
        print(f"   Selected '{option_text}' from #{button_id}")
        return True
    # Fallback: click first non-empty option
    options = page.locator("[role='option']")
    count = await options.count()
    for i in range(count):
        txt = await options.nth(i).inner_text()
        if txt.strip() and txt.strip() != "Select One":
            await options.nth(i).click()
            print(f"   Selected '{txt.strip()}' from #{button_id}")
            return True
    return False

async def workday_multiselect(page, input_id, search_text):
    """Select from a Workday multi-select (search + click option)."""
    inp = page.locator(f"#{input_id}")
    await inp.click()
    await asyncio.sleep(1)
    await inp.fill("")
    await asyncio.sleep(0.5)
    await inp.fill(search_text)
    await asyncio.sleep(2)
    
    # Click the matching option
    options = page.locator("[role='option']")
    count = await options.count()
    print(f"   Multi-select options visible: {count}")
    for i in range(count):
        txt = await options.nth(i).inner_text()
        print(f"   Option {i}: '{txt.strip()}'")
        if search_text.lower() in txt.lower():
            await options.nth(i).click()
            print(f"   ✓ Selected '{txt.strip()}'")
            return True
    
    # Just click the first one
    if count > 0:
        await options.first.click()
        txt = await options.first.inner_text()
        print(f"   ✓ Selected first: '{txt.strip()}'")
        return True
    return False

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
        await page.locator("button[data-automation-id='utilityButtonSignIn']").first.click(force=True)
        await asyncio.sleep(2)
        await page.locator("input[data-automation-id='email']").first.fill(EMAIL)
        await page.locator("input[type='password']").first.fill(PASSWORD)
        await asyncio.sleep(1)
        await page.locator("div[data-automation-id='click_filter'][aria-label='Sign In']").first.click(force=True)
        await asyncio.sleep(5)
        print(f"Signed in ✓")

        # === START APPLICATION ===
        print("\n=== STARTING APPLICATION ===")
        await page.locator("a:has-text('Apply'), button:has-text('Apply')").first.click()
        await asyncio.sleep(3)
        await ss(page, "apply_popup")
        
        # Try various popup options
        for btn_text in ["Apply Manually", "Use My Last Application", "Autofill with Resume"]:
            btn = page.locator(f"button:has-text('{btn_text}'), a:has-text('{btn_text}')")
            if await btn.count() > 0:
                await btn.first.click(force=True)
                print(f"Clicked '{btn_text}' ✓")
                break
        else:
            # Maybe already on the form - check if there's a file input or popup closed
            print("No popup button found, might be on form already")
        
        await asyncio.sleep(5)
        await ss(page, "form_loaded")

        # === STEP 1: MY INFORMATION ===
        print("\n=== STEP 1: MY INFORMATION ===")
        
        # 1. "How Did You Hear About Us?" - Workday multi-select
        print("\n1. How Did You Hear About Us?")
        # Clear and search - need to click the input, clear, type, wait, click option
        source_inp = page.locator("#source--source")
        await source_inp.click()
        await asyncio.sleep(1)
        await source_inp.fill("")
        await asyncio.sleep(1)
        
        # Get all available options
        options = page.locator("[role='option']")
        opt_count = await options.count()
        print(f"   Available options: {opt_count}")
        for i in range(min(opt_count, 10)):
            txt = await options.nth(i).inner_text()
            print(f"   [{i}] {txt.strip()}")
        
        if opt_count > 0:
            # Try to find "Career Site" or "Company Website" or just pick first
            selected = False
            for keyword in ["Career", "Website", "Online", "Internet"]:
                for i in range(opt_count):
                    txt = await options.nth(i).inner_text()
                    if keyword.lower() in txt.lower():
                        await options.nth(i).click()
                        print(f"   ✓ Selected: {txt.strip()}")
                        selected = True
                        break
                if selected:
                    break
            if not selected:
                await options.first.click()
                txt = await options.first.inner_text()
                print(f"   ✓ Selected first: {txt.strip()}")
        
        await asyncio.sleep(1)
        # Click elsewhere to close dropdown
        await page.locator("body").click(position={"x": 10, "y": 10})
        await asyncio.sleep(1)
        
        # 2. "Previously worked?" - Need to use Workday's custom radio
        print("\n2. Previously worked? → No")
        # The radio buttons have dynamic IDs. Use label text approach.
        # In Workday, clicking the label text should work
        await page.evaluate("""() => {
            // Find all radio inputs
            const radios = document.querySelectorAll('input[type="radio"]');
            for (const radio of radios) {
                // Get the associated label
                const label = radio.closest('label') || document.querySelector('label[for="' + radio.id + '"]');
                if (label && label.textContent.trim() === 'No') {
                    radio.checked = true;
                    radio.dispatchEvent(new Event('change', { bubbles: true }));
                    radio.dispatchEvent(new Event('click', { bubbles: true }));
                    // Also try clicking the label
                    label.click();
                    return 'clicked No';
                }
            }
            // Fallback: click the second radio (No is usually second)
            if (radios.length >= 2) {
                radios[1].checked = true;
                radios[1].dispatchEvent(new Event('change', { bubbles: true }));
                radios[1].click();
                return 'clicked second radio';
            }
            return 'no radios found';
        }""")
        await asyncio.sleep(1)
        
        # Also try Playwright click on label
        no_labels = page.locator("label")
        label_count = await no_labels.count()
        for i in range(label_count):
            txt = await no_labels.nth(i).inner_text()
            if txt.strip() == "No":
                await no_labels.nth(i).click(force=True)
                print("   ✓ Clicked 'No' label")
                break
        await asyncio.sleep(1)
        
        # 3. Legal Name
        print("\n3. Name")
        await page.locator("#name--legalName--firstName").fill("Priyanshu")
        await page.locator("#name--legalName--lastName").fill("Gupta")
        print("   ✓ Priyanshu Gupta")
        
        # 4. Address
        print("\n4. Address")
        await page.locator("#address--addressLine1").fill("Mumbai")
        await page.locator("#address--city").fill("Mumbai")
        await page.locator("#address--postalCode").fill("400001")
        print("   ✓ Mumbai, 400001")
        
        # 5. Phone Device Type - custom Workday dropdown
        print("\n5. Phone Device Type")
        phone_type_btn = page.locator("#phoneNumber--phoneType")
        await phone_type_btn.click()
        await asyncio.sleep(1)
        
        # Look for Mobile option
        options = page.locator("[role='option'], [role='listbox'] li")
        opt_count = await options.count()
        print(f"   Phone type options: {opt_count}")
        for i in range(min(opt_count, 10)):
            txt = await options.nth(i).inner_text()
            print(f"   [{i}] {txt.strip()}")
        
        selected = False
        for keyword in ["Mobile", "Cell", "Home", "Work"]:
            for i in range(opt_count):
                txt = await options.nth(i).inner_text()
                if keyword.lower() in txt.lower():
                    await options.nth(i).click()
                    print(f"   ✓ Selected: {txt.strip()}")
                    selected = True
                    break
            if selected:
                break
        if not selected and opt_count > 0:
            await options.first.click()
            print("   ✓ Selected first option")
        
        await asyncio.sleep(1)
        
        # 6. Phone Number
        print("\n6. Phone Number")
        await page.locator("#phoneNumber--phoneNumber").fill("7590082188")
        print("   ✓ 7590082188")
        
        await ss(page, "step1_complete")
        
        # === SAVE AND CONTINUE ===
        print("\n=== Saving Step 1 ===")
        await page.locator("button:has-text('Save and Continue')").first.click(force=True)
        await asyncio.sleep(5)
        await ss(page, "after_step1_save")
        
        # Check if we moved to step 2
        text = await page.inner_text("body")
        
        # Check for remaining errors
        if "Error-" in text:
            errors = [l.strip() for l in text.split('\n') if l.strip().startswith('Error-')]
            print(f"   Remaining errors: {errors}")
            print(f"\n   Page snippet: {text[:1500]}")
        
        if "My Experience" in text and "current step 2" in text:
            print("\n✅ STEP 1 COMPLETE - On Step 2 now!")
        elif "current step 1" in text:
            print("\n❌ Still on Step 1 - errors need fixing")
            # Let's get more detail about what's wrong
            await ss(page, "step1_errors")
            await browser.close()
            return
        
        # === STEP 2: MY EXPERIENCE ===
        print("\n=== STEP 2: MY EXPERIENCE ===")
        await asyncio.sleep(2)
        
        # Check for resume upload
        file_input = page.locator("input[type='file']")
        if await file_input.count() > 0:
            await file_input.first.set_input_files(RESUME)
            print("   ✓ Resume uploaded")
            await asyncio.sleep(5)
        
        # Dump fields
        text = await page.inner_text("body")
        print(f"   Page: {text[:2000]}")
        await ss(page, "step2")
        
        # Save and continue
        await page.locator("button:has-text('Save and Continue')").first.click(force=True)
        await asyncio.sleep(5)
        await ss(page, "after_step2")
        
        text = await page.inner_text("body")
        
        # === STEP 3: APPLICATION QUESTIONS ===
        if "Application Questions" in text or "step 3" in text:
            print("\n=== STEP 3: APPLICATION QUESTIONS ===")
            print(f"   Page: {text[:2000]}")
            await ss(page, "step3")
            
            # Fill any text fields/textareas
            textareas = page.locator("textarea:visible")
            ta_count = await textareas.count()
            for i in range(ta_count):
                ta = textareas.nth(i)
                val = await ta.input_value()
                if not val:
                    await ta.fill("N/A")
            
            # Handle any dropdowns
            # Save and continue
            await page.locator("button:has-text('Save and Continue')").first.click(force=True)
            await asyncio.sleep(5)
            text = await page.inner_text("body")
        
        # === STEP 4: VOLUNTARY DISCLOSURES ===
        if "Voluntary" in text or "step 4" in text:
            print("\n=== STEP 4: VOLUNTARY DISCLOSURES ===")
            await ss(page, "step4")
            await page.locator("button:has-text('Save and Continue')").first.click(force=True)
            await asyncio.sleep(5)
            text = await page.inner_text("body")
        
        # === STEP 5: REVIEW & SUBMIT ===
        if "Review" in text or "step 5" in text:
            print("\n=== STEP 5: REVIEW & SUBMIT ===")
            await ss(page, "step5_review")
            print(f"   Page: {text[:3000]}")
            
            submit = page.locator("button:has-text('Submit')")
            if await submit.count() > 0:
                print("   🚀 SUBMITTING!")
                await submit.first.click(force=True)
                await asyncio.sleep(5)
                text = await page.inner_text("body")
                await ss(page, "submitted")
                
                if any(w in text.lower() for w in ["thank", "submitted", "success", "received"]):
                    print("\n   ✅✅✅ APPLICATION SUBMITTED SUCCESSFULLY! ✅✅✅")
                else:
                    print(f"   Post-submit: {text[:1000]}")
        
        await ss(page, "final")
        await browser.close()
        print("\n=== DONE ===")

if __name__ == "__main__":
    asyncio.run(main())
