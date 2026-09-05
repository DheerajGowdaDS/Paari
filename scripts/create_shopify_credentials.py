"""Automate Shopify Admin custom app creation using Playwright.

Launches a browser window. The user logs into Shopify manually.
Then this script automates:
1. Creating a custom app
2. Configuring Admin API scopes
3. Installing the app
4. Extracting the access token and client secret
"""

from __future__ import annotations

import asyncio
import sys
import time

STORE_DOMAIN = "paari-demo-store.myshopify.com"


async def main() -> None:
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        # Launch headed browser so the user can log in
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()

        # Navigate to Shopify admin
        print(f"Opening Shopify admin for {STORE_DOMAIN}...")
        await page.goto(f"https://{STORE_DOMAIN}/admin")
        print("Please log in to the Shopify admin.")
        print("After logging in, press Enter in this terminal to continue...")
        await asyncio.get_event_loop().run_in_executor(None, input)

        # Navigate to app development page
        print("Navigating to app development settings...")
        await page.goto(f"https://{STORE_DOMAIN}/admin/settings/apps/development")
        await page.wait_for_load_state("networkidle")
        time.sleep(2)

        # Check if we need to allow custom app development
        allow_btn = page.locator("text=Allow custom app development")
        if await allow_btn.count() > 0:
            print("Allowing custom app development...")
            await allow_btn.click()
            await page.wait_for_load_state("networkidle")
            # Confirm
            confirm_btn = page.locator("button:has-text('Allow')")
            if await confirm_btn.count() > 0:
                await confirm_btn.click()
                await page.wait_for_load_state("networkidle")
            time.sleep(2)

        # Create a new app
        print("Creating 'Paari' app...")
        create_btn = page.locator("text=Create an app")
        if await create_btn.count() > 0:
            await create_btn.click()
            await page.wait_for_load_state("networkidle")
            time.sleep(1)

            # Fill app name
            name_input = page.locator("input[name='app']")
            if await name_input.count() > 0:
                await name_input.fill("Paari")
            else:
                # Try other selectors
                name_input = page.locator("input[type='text']").first
                await name_input.fill("Paari")

            # Click Create
            create_app_btn = page.locator("button:has-text('Create app')")
            if await create_app_btn.count() > 0:
                await create_app_btn.click()
                await page.wait_for_load_state("networkidle")
                time.sleep(3)

        # Navigate to Configuration tab
        print("Configuring Admin API scopes...")
        config_tab = page.locator("text=Configuration")
        if await config_tab.count() > 0:
            await config_tab.click()
            await page.wait_for_load_state("networkidle")
            time.sleep(2)

        # Find Admin API integration and click Configure
        configure_btn = page.locator("text=Configure").first
        if await configure_btn.count() > 0:
            await configure_btn.click()
            await page.wait_for_load_state("networkidle")
            time.sleep(2)

        # Select the required scopes
        scopes = [
            "read_products",
            "read_inventory",
            "read_orders",
            "write_orders",
            "write_draft_orders",
        ]
        for scope in scopes:
            checkbox = page.locator(f"text={scope}").locator("..").locator("input[type='checkbox']")
            if await checkbox.count() > 0:
                if not await checkbox.is_checked():
                    await checkbox.click()
                    print(f"  Enabled: {scope}")
            else:
                # Try alternative selector
                checkbox = page.locator(f"[data-scope='{scope}']")
                if await checkbox.count() > 0 and not await checkbox.is_checked():
                    await checkbox.click()
                    print(f"  Enabled: {scope}")

        # Save
        save_btn = page.locator("button:has-text('Save')")
        if await save_btn.count() > 0:
            await save_btn.click()
            await page.wait_for_load_state("networkidle")
            time.sleep(2)
            print("Saved API scopes.")

        # Navigate to API credentials tab
        print("Installing app to get credentials...")
        creds_tab = page.locator("text=API credentials")
        if await creds_tab.count() > 0:
            await creds_tab.click()
            await page.wait_for_load_state("networkidle")
            time.sleep(2)

        # Install app
        install_btn = page.locator("button:has-text('Install app')")
        if await install_btn.count() > 0:
            await install_btn.click()
            await page.wait_for_load_state("networkidle")
            time.sleep(2)

            # Confirm install
            install_confirm = page.locator("button:has-text('Install')")
            if await install_confirm.count() > 0:
                await install_confirm.click()
                await page.wait_for_load_state("networkidle")
                time.sleep(3)

        # Extract the access token
        print("\nLooking for credentials on the page...")
        page_text = await page.inner_text("body")

        # Find shpat_ token
        import re
        shpat_match = re.search(r"shpat_[a-zA-Z0-9]+", page_text)
        if shpat_match:
            token = shpat_match.group(0)
            print(f"\n✅ Admin API Access Token: {token}")
        else:
            print("\n❌ Could not find shpat_ token on the page.")
            print("Please look at the browser window and copy the token manually.")

        # Find client secret
        secret_match = re.search(r"Client secret[:\s]+([a-f0-9]{32})", page_text, re.IGNORECASE)
        if secret_match:
            secret = secret_match.group(1)
            print(f"✅ Client Secret: {secret}")
        else:
            print("❌ Could not find client secret on the page.")
            print("Please look at the browser window and copy it manually.")

        print("\nPress Enter to close the browser...")
        await asyncio.get_event_loop().run_in_executor(None, input)
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
