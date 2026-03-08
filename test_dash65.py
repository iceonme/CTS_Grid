
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dashboard_65.server_65 import create_dashboard_65
import time

try:
    print("Testing Dashboard 65 startup...")
    dashboard = create_dashboard_65(port=5065) # Use 5065 for V6.5A
    dashboard.start_background()
    time.sleep(5)
    print("Dashboard 65 should be running on 5065")
except Exception as e:
    print(f"Error starting dashboard: {e}")
    import traceback
    traceback.print_exc()
