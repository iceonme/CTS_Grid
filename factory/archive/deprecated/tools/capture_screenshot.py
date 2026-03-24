import asyncio
from playwright.async_api import async_playwright
import time
import os

async def capture():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1920, "height": 1080})
        print("璁块棶 http://localhost:5000/5.1 ...")
        await page.goto("http://localhost:5000/5.1")
        
        # 绛夊緟鏁版嵁鍔犺浇鍜屾覆鏌?
        print("绛夊緟 10 绉掓覆鏌撳浘琛ㄦ暟鎹?..")
        await asyncio.sleep(10)
        
        # 鎴浘淇濆瓨鍒?artifacts 鐩綍浠ヤ究 walkthrough 寮曠敤
        save_path = r"C:\Users\iceon\.gemini\antigravity\brain\810a1895-1764-4a03-891b-6861ca87a225\dashboard_5_1_snapshot.png"
        await page.screenshot(path=save_path)
        print(f"鎴浘宸蹭繚瀛樺埌: {save_path}")
        
        await browser.close()

if __name__ == '__main__':
    asyncio.run(capture())
