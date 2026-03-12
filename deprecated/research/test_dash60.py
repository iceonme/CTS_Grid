
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dashboard.server_60 import create_dashboard_60
import time

try:
    print("Testing Dashboard 60 startup...")
    dashboard = create_dashboard_60(port=5160) # Use a different port for test
    dashboard.start_background()
    time.sleep(5)
    print("Dashboard 60 should be running on 5160")
except Exception as e:
    print(f"Error starting dashboard: {e}")
    import traceback
    traceback.print_exc()
