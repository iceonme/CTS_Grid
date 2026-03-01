import requests
import socket
import os
import sys

def check_connection(url):
    print(f"Testing connection to {url}...")
    try:
        response = requests.get(url, timeout=5)
        print(f"  [OK] Status Code: {response.status_code}")
        return True
    except Exception as e:
        print(f"  [FAILED] Error: {e}")
        return False

def check_dns(hostname):
    print(f"Resolving DNS for {hostname}...")
    try:
        ip = socket.gethostbyname(hostname)
        print(f"  [OK] IP: {ip}")
        return ip
    except Exception as e:
        print(f"  [FAILED] Error: {e}")
        return None

def main():
    print("=== OKX Connectivity Diagnostic ===\n")
    
    # Check Environment Variables
    print("Checking Proxy Environment Variables:")
    print(f"  HTTP_PROXY: {os.environ.get('HTTP_PROXY')}")
    print(f"  HTTPS_PROXY: {os.environ.get('HTTPS_PROXY')}")
    print(f"  ALL_PROXY: {os.environ.get('ALL_PROXY')}\n")

    targets = [
        "https://www.baidu.com",
        "https://www.google.com",
        "https://www.okx.com/api/v5/market/candles?instId=BTC-USDT&limit=1"
    ]

    for target in targets:
        domain = target.split("//")[-1].split("/")[0].split("?")[0]
        check_dns(domain)
        check_connection(target)
        print("-" * 40)

    print("\nSuggestions:")
    print("1. If Baidu works but OKX/Google fails, you likely need a proxy (VPN).")
    print("2. If everything fails, check your local network connection.")
    print("3. In PowerShell, try setting your proxy before running:")
    print('   $env:HTTP_PROXY = "http://127.0.0.1:xxxx"')
    print('   $env:HTTPS_PROXY = "http://127.0.0.1:xxxx"')
    print("   (replace xxxx with your proxy port, e.g., 7890 for Clash)")

if __name__ == "__main__":
    main()
