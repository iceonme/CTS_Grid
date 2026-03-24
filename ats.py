import os
import sys
import argparse
from datetime import datetime

# 解决 Windows 控制台中文乱码问题
if sys.platform.startswith('win'):
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import asyncio

# 核心导入
from console.runner.skill_loader import SkillLoader
from console.runner.ats_engine import ATSEngine, StrategySlot
from console.dashboard.server import DashboardServer

# 默认三支柱配置 (Tri-Pillar)
DEFAULT_FEED = "cartridges/datafeeds/okx-feed"
DEFAULT_EXECUTOR = "cartridges/executors/paper-executor"

async def async_start_run(args):
    """异步启动交易控制台"""
    skill_name = args.skill
    if not skill_name.startswith("cartridges"):
        skill_path = os.path.join("cartridges", "strategies", skill_name)
    else:
        skill_path = skill_name

    print(f"🚀 ATS 控制台启动 (Async) | 模式: {args.mode.upper()} | 端口: {args.port}", flush=True)
    
    loader = SkillLoader()
    
    # 1. 加载组件 (Skills)
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 正在以微服务模式载入组件...", flush=True)
    try:
        feed, _, _ = loader.load(args.datafeed)
        executor, _, _ = loader.load(args.executor)
        strategy, meta, config = loader.load(skill_path)
    except Exception as e:
        print(f"❌ 组件加载失败: {e}")
        return

    slot_id = meta.get("name", "strategy")
    display_name = meta.get("name", "Strategy")
    initial_balance = config.get("initial_balance", config.get("params", {}).get("initial_balance", 10000))

    # 2. 初始化运行基座 (ATS Engine)
    runner = ATSEngine()
    
    # 3. 注册槽位
    slot = StrategySlot(
        slot_id=slot_id,
        display_name=display_name,
        feed=feed,
        strategy=strategy,
        executor=executor
    )
    runner.add_slot(slot)

    # 4. 仪表盘处理 (TODO: 将 Dashboard 适配为事件监听器)
    if not args.no_dashboard:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 🌍 Dashboard 暂未完全适配事件总线，跳过 UI 绑定", flush=True)

    # 5. 启动运行
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 🚀 全系统供电准备就绪...", flush=True)
    try:
        await runner.run()
    except KeyboardInterrupt:
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 👋 正在安全关闭...", flush=True)
        await runner.stop()

def main():
    parser = argparse.ArgumentParser(
        description="ATS (Agentic Trading System) Control Plane (Async Edition)",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    subparsers = parser.add_subparsers(dest="command", help="子命令")
    
    run_parser = subparsers.add_parser("run", help="启动交易策略运行器")
    run_parser.add_argument("skill", help="策略名称 (如 grid-v60) 或完整路径")
    run_parser.add_argument("--datafeed", default=DEFAULT_FEED, help="DataFeed Skill 路径")
    run_parser.add_argument("--executor", default=DEFAULT_EXECUTOR, help="Executor Skill 路径")
    run_parser.add_argument("--port", type=int, default=5066, help="Dashboard 端口")
    run_parser.add_argument("--mode", default="paper", choices=["paper", "live"], help="运行模式")
    run_parser.add_argument("--no-dashboard", action="store_true", help="禁用 Dashboard 反馈界面")

    args = parser.parse_args()
    
    if args.command == "run":
        try:
            asyncio.run(async_start_run(args))
        except KeyboardInterrupt:
            pass
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
