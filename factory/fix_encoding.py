import os
import sys
import argparse

# 解决 Windows 控制台中文乱码问题
if sys.platform.startswith('win'):
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

def fix_mojibake(text):
    """
    尝试修复乱码：将被错误识别为 UTF-8 的字节流还原。
    """
    # 尝试整体转换（适用于全文件乱码）
    try:
        # 使用 gb18030 比较稳健，涵盖更多字节组合
        candidate = text.encode('gb18030').decode('utf-8')
        # 启发式判断：如果转换后乱码明显减少，则认为成功
        if is_mojibake_likely(text) and not is_mojibake_likely(candidate):
            return candidate
    except:
        pass

    # 尝试逐段修复（适用于混合文本）
    result = ""
    i = 0
    while i < len(text):
        match_found = False
        # 尝试不同长度的乱码块 (2, 3, 4, 6 字符通常对应 1 或 2 个 UTF-8 中文字符)
        for length in [6, 4, 3, 2]:
            chunk = text[i:i+length]
            if len(chunk) < 2: continue
            try:
                # 尝试还原回原始字节。如果包含 € 等特殊字符，尝试 cp1252/latin-1
                try:
                    raw_bytes = chunk.encode('gb18030')
                except UnicodeEncodeError:
                    # 针对包含 € 等无法在 gb18030 中直接编码回原始单字节的情况
                    raw_bytes = chunk.encode('cp1252', errors='replace')
                
                decoded = raw_bytes.decode('utf-8')
                # 简单验证：解码出的内容不应包含明显的乱码特征，且应该是可读的中文字符
                if any('\u4e00' <= c <= '\u9fff' for c in decoded):
                    result += decoded
                    i += length
                    match_found = True
                    break
            except:
                continue
        
        if not match_found:
            result += text[i]
            i += 1
    return result

def is_mojibake_likely(text):
    """
    启发式检查：如果文本中包含常见的乱码特征字符，则认为可能存在乱码。
    """
    # 增加更多顽固乱码标志
    markers = ['策略', '鈹', '馃', '锔', '执行', '鍔ㄦ€佺綉鏍', '重构鐗', '交易系统']
    for marker in markers:
        if marker in text:
            return True
    return False

def process_file(filepath, dry_run=False):
    try:
        # 尝试以带 BOM 的 UTF-8 读ȡ
        with open(filepath, 'r', encoding='utf-8-sig', errors='ignore') as f:
            content = f.read()
        
        if not is_mojibake_likely(content):
            # print(f"  [Skip] {filepath} looks normal.")
            return False

        fixed_content = fix_mojibake(content)
        
        if fixed_content == content:
            return False

        if dry_run:
            print(f"  [Dry-run] Would fix: {filepath}")
        else:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(fixed_content)
            print(f"  [Fixed] {filepath}")
        return True
    except Exception as e:
        print(f"  [Error] Failed to process {filepath}: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description="ATS 乱码修复工具 (Mojibake Fixer)")
    parser.add_argument("path", nargs="?", default=".", help="文件或Ŀ¼路径 (Ĭ认当ǰĿ¼)")
    parser.add_argument("--dry-run", action="store_true", help="ֻ显示将要修复的文件，不执行写入")
    parser.add_argument("--recursive", "-r", action="store_true", help="递归扫描子Ŀ¼")
    parser.add_argument("--ext", default=".md,.py,.txt", help="包含的文件扩展名 (逗号分隔)")
    
    args = parser.parse_args()
    
    extensions = tuple(args.ext.split(','))
    target_path = args.path
    
    print(f"开ʼɨ描: {os.path.abspath(target_path)}")
    
    count = 0
    if os.path.isfile(target_path):
        if process_file(target_path, args.dry_run):
            count += 1
    elif os.path.isdir(target_path):
        if args.recursive:
            for root, dirs, files in os.walk(target_path):
                # 排除һЩ不需Ҫɨ描的Ŀ¼
                if any(x in root for x in ['.git', '__pycache__', '.gemini', 'node_modules']):
                    continue
                for file in files:
                    if file.endswith(extensions):
                        full_path = os.path.join(root, file)
                        if process_file(full_path, args.dry_run):
                            count += 1
        else:
            for file in os.listdir(target_path):
                if file.endswith(extensions):
                    full_path = os.path.join(target_path, file)
                    if process_file(full_path, args.dry_run):
                        count += 1
    
    print(f"\n修复完成。总计处理文件数: {count}")

if __name__ == "__main__":
    main()
