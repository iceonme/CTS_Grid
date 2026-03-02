import os
import re
import ast

def check_files(directory):
    for root, dirs, files in os.walk(directory):
        for file in files:
            if file.endswith('.py'):
                path = os.path.join(root, file)
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    # Search for pd.DataFrame calls with columns parameter
                    matches = re.finditer(r'pd\.DataFrame\(.*?,?\s*columns=\s*(\[.*?\])', content, re.DOTALL)
                    for match in matches:
                        columns_str = match.group(1)
                        try:
                            columns_list = ast.literal_eval(columns_str)
                            if isinstance(columns_list, list):
                                print(f"File: {path}")
                                print(f"  Columns length: {len(columns_list)}")
                                print(f"  Columns: {columns_list}")
                        except:
                            # If literal_eval fails (e.g. dynamic list), just print the match
                            print(f"File: {path} (Dynamic columns?)")
                            print(f"  Match: {columns_str.strip()[:100]}...")
                except Exception as e:
                    pass

if __name__ == "__main__":
    check_files(r'c:\Projects\TradingGarage\CTS1')
