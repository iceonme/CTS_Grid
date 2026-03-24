import os
import sys
import argparse
from datetime import datetime

# 解决 Windows 控制台中文乱码问题
if sys.platform.startswith('win'):
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# 核心导入
from console.runner.skill_loader import SkillLoader
from console.runner.multi_strategy_runner import MultiStrategyRunner
from console.dashboard.server import DashboardServer

# 默认桥接组件
DEFAULT_FEED = "cartridges/bridge/datafeeds/okx-feed"
DEFAULT_EXECUTOR = "cartridges/bridge/executors/paper-executor"

def start_run(args):
    """处理 'run' 子命令，启动交易控制台"""
    skill_name = args.skill
    # 路径自动补全
    if not skill_name.startswith("cartridges"):
        skill_path = os.path.join("cartridges", "strategies", skill_name)
    else:
        skill_path = skill_name

    print(f"🚀 ATS 控制台启动 | 模式: {args.mode.upper()} | 端口: {args.port}", flush=True)
    
    loader = SkillLoader()
    
    # 1. 加载桥接组件 (Bridge Skills)
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 正在载入桥接层...", flush=True)
    try:
        feed, _, _ = loader.load(args.datafeed)
        executor, _, _ = loader.load(args.executor)
    except Exception as e:
        print(f"❌ 桥接组件加载失败: {e}")
        sys.exit(1)

    # 2. 加载策略卡带 (Strategy Skill)
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 正在载入策略: {skill_path}", flush=True)
    try:
        strategy, meta, config = loader.load(skill_path)
    except Exception as e:
        print(f"❌ 策略加载失败: {e}")
        sys.exit(1)

    slot_id = meta.get("name", "strategy")

    # 3. 初始化运行器
    dashboard = None if args.no_dashboard else DashboardServer(port=args.port)
    
    # 核心：注册 Skill 专属看板
    if dashboard:
        abs_skill_path = os.path.abspath(skill_path)
        dashboard.register_skill_dashboard(slot_id, abs_skill_path)

    runner = MultiStrategyRunner(dashboard)
    
    # 启动 Dashboard 后台服务 (解决 127.0.0.1 拒绝访问问题)
    if dashboard:
        # 核心修复：将 Dashboard 的控制指令绑定到 Runner
        dashboard.on_control_callback = runner.on_control_handle
        
        dashboard.start_background()
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 🌍 Dashboard 服务已在后台启动: http://127.0.0.1:{args.port}", flush=True)
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 💡 提示: 现已支持页面控制（暂停/重置/保存参数）", flush=True)
    else:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 💡 模式: 纯命令行 (Dashboard 已禁用)", flush=True)
    
    # 将策略与执行器绑定并加入运行轨道
    from console.runner.multi_strategy_runner import StrategySlot
    
    # 核心修正：确保 top-level symbol 被注入到 params 以确保策略实例化正确
    strategy_params = config.get("params", {}).copy()
    if "symbol" in config and "symbol" not in strategy_params:
        strategy_params["symbol"] = config["symbol"]
        
    slot_id = meta.get("name", "strategy")
    display_name = meta.get("name", "Strategy")
    
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 🧩 槽位注册: ID={slot_id} | 交易对={strategy_params.get('symbol', 'BTC-USDT')}", flush=True)

    slot = StrategySlot(
        slot_id=slot_id,
        display_name=display_name,
        strategy=strategy,
        executor=executor,
        initial_balance=config.get("initial_balance", config.get("params", {}).get("initial_balance", 10000))
    )
    runner.add_slot(slot)

    # 4. 预热与运行
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 🛠️ 正在进行策略预热...", flush=True)
    runner.perform_warmup(feed)
    
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 🚀 ATS 已就绪，开始巡航...", flush=True)
    try:
        runner.start_all()
        for data in feed.stream():
            runner.on_bar(data)
    except KeyboardInterrupt:
        print(f"\n[{datetime.now().strftime('%H:%M:%S')}] 👋 正在安全关闭...", flush=True)
        runner.stop()

def main():
    parser = argparse.ArgumentParser(
        description="ATS (Agentic Trading System) Control Plane",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:
  python ats.py run grid-v60
  python ats.py run grid-v60 --mode paper --port 5001
        """
    )
    
    subparsers = parser.add_subparsers(dest="command", help="子命令")
    
    # 'run' 子命令: 启动控制台
    run_parser = subparsers.add_parser("run", help="启动交易策略运行器")
    run_parser.add_argument("skill", help="策略名称 (如 grid-v60) 或完整路径")
    run_parser.add_argument("--datafeed", default=DEFAULT_FEED, help="DataFeed Skill 路径")
    run_parser.add_argument("--executor", default=DEFAULT_EXECUTOR, help="Executor Skill 路径")
    run_parser.add_argument("--port", type=int, default=5066, help="Dashboard 端口")
    run_parser.add_argument("--mode", default="paper", choices=["paper", "live"], help="运行模式")
    run_parser.add_argument("--no-dashboard", action="store_true", help="禁用 Dashboard 反馈界面")
    run_parser.set_defaults(func=start_run)

    args = parser.parse_args()
    
    if hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
