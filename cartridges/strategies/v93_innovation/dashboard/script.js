/**
 * V9.3 Innovation Dashboard Script
 * 负责 K 线渲染、3+2 网格线绘制、指标更新及 Socket.IO 通信
 */

// --- 1. 全局变量与配置 ---
const strategyId = window.STRATEGY_ID;
const socket = io();

let mainChart, mainSeries, rsiChart, rsiSeries, pnlChart, pnlSeries;
let gridLines = []; // 存储当前网格线对象 { price, line }

const chartOptions = {
    layout: { background: { color: '#111827' }, textColor: '#94a3b8' },
    grid: { vertLines: { color: '#1e293b' }, horzLines: { color: '#1e293b' } },
    crosshair: { mode: 0 },
    timeScale: { borderColor: '#1e293b', timeVisible: true, secondsVisible: false }
};

// --- 2. 初始化图表 ---
function initCharts() {
    // 主图 (Price + Grids)
    mainChart = LightweightCharts.createChart(document.getElementById('tv-chart-main'), {
        ...chartOptions,
        handleScroll: true, handleScale: true
    });
    mainSeries = mainChart.addCandlestickSeries({
        upColor: '#00d084', downColor: '#ff4757', borderVisible: false, wickVisible: true
    });

    // RSI 指标图
    rsiChart = LightweightCharts.createChart(document.getElementById('tv-chart-rsi'), {
        ...chartOptions,
        timeScale: { visible: false }
    });
    rsiSeries = rsiChart.addLineSeries({ color: '#00d4ff', lineWidth: 2 });
    // RSI 阈值水平线
    rsiChart.addLineSeries({ color: 'rgba(255, 71, 87, 0.3)', lineWidth: 1, lineStyle: 2 }).setData([{time:0, value:25}, {time:2000000000, value:25}]);
    rsiChart.addLineSeries({ color: 'rgba(0, 208, 132, 0.3)', lineWidth: 1, lineStyle: 2 }).setData([{time:0, value:85}, {time:2000000000, value:85}]);

    // PNL 曲线图
    pnlChart = LightweightCharts.createChart(document.getElementById('tv-chart-equity'), chartOptions);
    pnlSeries = pnlChart.addLineSeries({ 
        color: '#00d4ff', lineWidth: 3,
        lineType: 2 // Curved
    });

    window.addEventListener('resize', () => {
        mainChart.resize(document.getElementById('tv-chart-main').clientWidth, 440);
        rsiChart.resize(document.getElementById('tv-chart-rsi').clientWidth, 100);
        pnlChart.resize(document.getElementById('tv-chart-equity').clientWidth, 160);
    });
}

// --- 3. 更新网格线渲染 ---
function updateGridLines(prices) {
    // prices [VH, P3, P2, P1, P0, VL]
    if (!prices || prices.length < 6) return;

    // 清空旧线
    gridLines.forEach(l => mainSeries.removePriceLine(l));
    gridLines = [];

    const colors = ['rgba(255, 71, 87, 0.5)', '#f59e0b', '#f59e0b', '#a855f7', '#a855f7', 'rgba(168, 85, 247, 0.5)'];
    const titles = ['VH', 'P3', 'P2', 'P1', 'P0', 'VL'];

    prices.forEach((p, i) => {
        const line = mainSeries.createPriceLine({
            price: p,
            color: colors[i],
            lineWidth: i === 0 || i === 5 ? 1 : 2,
            lineStyle: i === 0 || i === 5 ? 2 : 0,
            axisLabelVisible: true,
            title: titles[i],
        });
        gridLines.push(line);
    });
}

// --- 4. Socket.IO 通信逻辑 ---
socket.on('connect', () => {
    document.getElementById('statusDot').className = 'status-dot connected';
    document.getElementById('statusText').innerText = '已连接';
    socket.emit('join', { strategy_id: strategyId });
});

socket.on('update', (data) => {
    if (!data) return;

    // A. 市场数据更新
    if (data.market_data) {
        const d = data.market_data;
        // 统一为 Unix 秒数
        let tsValue = d.timestamp;
        if (typeof tsValue === 'string') {
            tsValue = Math.floor(new Date(tsValue).getTime() / 1000);
        } else if (tsValue > 2000000000) { // 可能是毫秒
            tsValue = Math.floor(tsValue / 1000);
        }
        
        const bar = {
            time: tsValue,
            open: d.open, high: d.high, low: d.low, close: d.close
        };
        mainSeries.update(bar);
        document.getElementById('ethPrice').innerText = d.close.toFixed(2);
    }

    // B. 账户与策略状态更新 (来自 get_status)
    const strategy = data.strategy || {};
    if (strategy.rsi) {
        document.getElementById('rsiVal').innerText = strategy.rsi;
        rsiSeries.update({
            time: Math.floor(Date.now() / 1000),
            value: strategy.rsi
        });
    }

    if (strategy.grid_prices) {
        updateGridLines(strategy.grid_prices);
    }

    if (strategy.layer !== undefined) {
        document.getElementById('currentLayer').innerText = strategy.layer ?? 'Out';
    }

    if (strategy.trend !== undefined) {
        const trendMap = { '1': '看多 ▲', '-1': '看空 ▼', '0': '震荡 ●' };
        document.getElementById('trendText').innerText = trendMap[strategy.trend] || '--';
    }

    if (strategy.leverage) {
        document.getElementById('leverageVal').innerText = strategy.leverage + 'x';
    }

    // C. 账户资金与持仓
    if (data.total_value) {
        document.getElementById('totalValue').innerText = data.total_value.toFixed(2);
        const baseline = 5000.0; // V93 初始本金
        const pnl = ((data.total_value - baseline) / baseline * 100).toFixed(2);
        const pnlEl = document.getElementById('pnlRate');
        pnlEl.innerText = pnl + '%';
        pnlEl.className = 'pnl-value ' + (pnl >= 0 ? 'text-profit' : 'text-loss');
        
        pnlSeries.update({
            time: Math.floor(Date.now() / 1000),
            value: data.total_value
        });
    }

    if (data.cash !== undefined) document.getElementById('cashValue').innerText = data.cash.toFixed(2);
    
    // 持仓详情
    const pos = (data.positions || {})[strategy.symbol] || { size: 0, avg_price: 0 };
    document.getElementById('longPosSize').innerText = pos.size > 0 ? pos.size.toFixed(3) : '0';
    document.getElementById('shortPosSize').innerText = pos.size < 0 ? Math.abs(pos.size).toFixed(3) : '0';
    document.getElementById('positionAvgPrice').innerText = pos.avg_price.toFixed(2);
});

socket.on('history_update', (data) => {
    if (!data) return;
    
    // A. K 线历史 (Main Chart)
    if (data.history_candles) {
        const bars = data.history_candles.map(d => {
            let tsValue = d.time || d.timestamp;
            if (typeof tsValue === 'string') {
                tsValue = Math.floor(new Date(tsValue).getTime() / 1000);
            } else if (tsValue > 2000000000) { // 可能是毫秒
                tsValue = Math.floor(tsValue / 1000);
            }
            return {
                time: tsValue,
                open: d.open, high: d.high, low: d.low, close: d.close
            };
        });
        mainSeries.setData(bars);
    }

    // B. RSI 历史 (RSI Chart)
    if (data.history_rsi) {
        rsiSeries.setData(data.history_rsi);
    }

    // C. 资产历史 (PNL Chart)
    if (data.history_equity) {
        pnlSeries.setData(data.history_equity);
    }
});

// --- 5. 交互处理 ---
document.getElementById('resetBtn').onclick = () => {
    document.getElementById('resetConfirmModal').classList.add('show');
};

document.getElementById('cancelReset').onclick = () => {
    document.getElementById('resetConfirmModal').classList.remove('show');
};

document.getElementById('confirmResetAction').onclick = () => {
    socket.emit('reset_strategy', { strategy_id: strategyId });
    document.getElementById('resetConfirmModal').classList.remove('show');
};

// 启动
initCharts();
