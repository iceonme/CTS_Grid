import asyncio
from playwright.async_api import async_playwright
import time
import os

async def capture():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1920, "height": 1080})
        print("访问 http://localhost:5000/5.1 ...")
        await page.goto("http://localhost:5000/5.1")
        
        # 等待数据加载和渲染
        print("等待 10 秒渲染图表数据...")
        await asyncio.sleep(10)
        
        # 截图保存到 artifacts 目录以便 walkthrough 引用
        save_path = r"C:\Users\iceon\.gemini\antigravity\brain\810a1895-1764-4a03-891b-6861ca87a225\dashboard_5_1_snapshot.png"
        await page.screenshot(path=save_path)
        print(f"截图已保存到: {save_path}")
        
        await browser.close()

if __name__ == '__main__':
    asyncio.run(capture())
