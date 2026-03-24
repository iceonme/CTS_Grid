import json
from datetime import datetime
import os

def test_serialization():
    # Simulate the data structure causing the error
    data = {
        "strategy_state": {
            "grid_config": {
                "created_at": datetime.now(),
                "some_list": [1, 2, 3]
            },
            "slots": [
                {"ts": datetime.now(), "price": 50000}
            ]
        },
        "slot_metadata": {
            "last_save_time": datetime.now().isoformat()
        }
    }
    
    test_file = "test_state.json"
    
    print("Testing serialization with default=str...")
    try:
        with open(test_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False, default=str)
        print("Serialization successful!")
    except Exception as e:
        print(f"Serialization failed: {e}")
        return False

    print("\nReading back and verifying...")
    try:
        with open(test_file, 'r', encoding='utf-8') as f:
            loaded = json.load(f)
        
        created_at_str = loaded["strategy_state"]["grid_config"]["created_at"]
        print(f"Loaded created_at: {created_at_str} (Type: {type(created_at_str)})")
        
        # Test parsing back
        parsed_dt = datetime.fromisoformat(created_at_str)
        print(f"Parsed back to datetime: {parsed_dt}")
        
        os.remove(test_file)
        print("\nCleanup done. Test PASSED!")
        return True
    except Exception as e:
        print(f"Verification failed: {e}")
        return False

if __name__ == "__main__":
    test_serialization()
