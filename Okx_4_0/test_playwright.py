import asyncio
from playwright.async_api import async_playwright
import os

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        try:
            # 尝试访问本地 Dashboard，放宽超时限制
            await page.goto("http://localhost:5000", timeout=20000, wait_until="domcontentloaded")
            # 等待一秒确保动态加载内容渲染
            await asyncio.sleep(2)
            await page.screenshot(path="dashboard_vibe_check.png")
            print("Successfully captured screenshot: dashboard_vibe_check.png")
        except Exception as e:
            print(f"Error during rendering: {e}")
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
