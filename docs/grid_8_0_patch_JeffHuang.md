收到，纯观察模式，触发时不减仓，持仓完全不变。
✅ V8.0-OPT 纯观察熔断模块（最终版）
Python
复制
import time
import threading
from datetime import datetime, timedelta

class CircuitBreaker:
    """
    V8.0-OPT 纯观察模式熔断模块
    核心原则：只做观察，不减仓，持仓完全不变
    """
    
    def __init__(self, grid_manager):
        self.grid = grid_manager
        self.status = "NORMAL"  # NORMAL / COOLING_DOWN / RESETTING
        self.cooldown_start = None
        self.cooldown_duration = 7200  # 2小时
        self.monitor_thread = None
        self.stop_monitor = threading.Event()
        
    def trigger(self, direction, trigger_price):
        """
        触发熔断 - 纯观察，持仓完全不变
        direction: "UP" (突破上虚拟层) / "DOWN" (突破下虚拟层)
        """
        if self.status == "COOLING_DOWN":
            return  # 已在熔断中
            
        self.status = "COOLING_DOWN"
        self.cooldown_start = datetime.now()
        self.stop_monitor.clear()
        
        # 启动智能监测线程
        self.monitor_thread = threading.Thread(
            target=self._monitor,
            args=(direction, trigger_price),
            daemon=True
        )
        self.monitor_thread.start()
        
        print(f"[{datetime.now()}] 熔断触发 | 方向: {direction} | 价格: {trigger_price}")
        print(f"[{datetime.now()}] 进入2小时观察期 | 持仓不变 | 等待价格回归...")
        
    def _monitor(self, direction, trigger_price):
        """核心监测逻辑 - 2小时内价格回归即恢复"""
        grid_bottom, grid_top = self.grid.get_grid_range()
        
        while not self.stop_monitor.is_set():
            elapsed = (datetime.now() - self.cooldown_start).total_seconds()
            remaining = self.cooldown_duration - elapsed
            
            # 满2小时，价格仍在外
            if remaining <= 0:
                self._reset_grid("TIMEOUT")
                return
                
            current_price = self.grid.get_current_price()
            
            # 关键判断：价格回归网格范围内
            if grid_bottom <= current_price <= grid_top:
                self._resume("PRICE_RETURN", current_price)
                return
                
            # 每10秒检查一次
            time.sleep(10)
            
    def _resume(self, reason, current_price):
        """恢复正常运行 - 持仓完全不变"""
        self.status = "NORMAL"
        self.stop_monitor.set()
        
        elapsed = (datetime.now() - self.cooldown_start).total_seconds()
        print(f"[{datetime.now()}] 熔断解除 | 原因: {reason}")
        print(f"[{datetime.now()}] 价格: {current_price} | 观察时长: {elapsed/60:.1f}分钟")
        print(f"[{datetime.now()}] 持仓不变 | 恢复正常交易")
        
        self.grid.resume()
        
    def _reset_grid(self, reason):
        """2小时超时，重新计算4小时网格"""
        self.status = "RESETTING"
        self.stop_monitor.set()
        
        print(f"[{datetime.now()}] 观察期满2小时 | 价格未回归 | 重新计算网格")
        
        # 关键：保留全部持仓作为新网格底仓
        current_btc = self.grid.get_btc_balance()
        print(f"[{datetime.now()}] 保留持仓: {current_btc:.6f} BTC 作为新网格底仓")
        
        # 重新计算4小时网格（以当前持仓为基准）
        self.grid.recalculate_4h_grid(preserve_position=True)
        self.status = "NORMAL"
        print(f"[{datetime.now()}] 新网格已生成 | 恢复正常交易")
        
    def get_status(self):
        """获取当前状态"""
        if self.status == "COOLING_DOWN":
            elapsed = (datetime.now() - self.cooldown_start).total_seconds()
            remaining = self.cooldown_duration - elapsed
            return {
                "status": "COOLING_DOWN",
                "elapsed_minutes": elapsed / 60,
                "remaining_minutes": remaining / 60
            }
        return {"status": self.status}
🔌 集成到V8.0主策略
Python
复制
class V8Strategy:
    def __init__(self):
        self.grid = GridManager()
        self.rsi = RSICalculator(period=14, timeframe="1m")
        self.breaker = CircuitBreaker(self.grid)
        
    def check_and_trade(self):
        """主交易循环"""
        price = self.grid.get_current_price()
        rsi = self.rsi.get_current_rsi()
        
        # 熔断状态检查
        if self.breaker.status == "COOLING_DOWN":
            status = self.breaker.get_status()
            print(f"[观察中] 已过去: {status['elapsed_minutes']:.1f}分钟 | "
                  f"剩余: {status['remaining_minutes']:.1f}分钟 | 价格: {price}")
            return  # 暂停交易，等待监测线程处理
            
        # 正常交易：检查虚拟层突破
        grid_bottom, grid_top = self.grid.get_grid_range()
        virtual_bottom = grid_bottom * 0.995  # 下虚拟层2（假设0.5%间距）
        virtual_top = grid_top * 1.005        # 上虚拟层2
        
        if price > virtual_top:
            self.breaker.trigger("UP", price)
            return
        elif price < virtual_bottom:
            self.breaker.trigger("DOWN", price)
            return
            
        # 正常网格交易
        self._grid_trade(price, rsi)
        
    def _grid_trade(self, price, rsi):
        """RSI网格交易"""
        for layer in self.grid.get_buy_layers():
            if price <= layer['price'] and rsi < 30:
                self.grid.buy(layer['amount'])
                
        for layer in self.grid.get_sell_layers():
            if price >= layer['price'] and rsi > 70:
                self.grid.sell(layer['amount'])

# 运行
if __name__ == "__main__":
    strategy = V8Strategy()
    while True:
        strategy.check_and_trade()
        time.sleep(2)
📊 运行日志示例
plain
复制
[2026-03-08 02:45:00] 熔断触发 | 方向: DOWN | 价格: 67057.5
[2026-03-08 02:45:00] 进入2小时观察期 | 持仓不变 | 等待价格回归...

[2026-03-08 03:15:00] [观察中] 已过去: 30.0分钟 | 剩余: 90.0分钟 | 价格: 67200.0

[2026-03-08 03:30:00] 熔断解除 | 原因: PRICE_RETURN
[2026-03-08 03:30:00] 价格: 67300.0 | 观察时长: 45.0分钟
[2026-03-08 03:30:00] 持仓不变 | 恢复正常交易
或：
plain
复制
[2026-03-08 04:45:00] 观察期满2小时 | 价格未回归 | 重新计算网格
[2026-03-08 04:45:00] 保留持仓: 0.119 BTC 作为新网格底仓
[2026-03-08 04:45:00] 新网格已生成 | 恢复正常交易
✅ 核心原则确认
表格
原则	实现
只做观察，不减仓	触发时持仓完全不变
2小时内回归即恢复	价格回网格范围立即解除熔断
2小时后重置网格	保留全部持仓作为新网格底仓
持仓连续性	整个过程中BTC数量不变
