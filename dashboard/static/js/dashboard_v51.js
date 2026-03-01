/**
 * 智能网格交易系统 5.1 核心前端逻辑
 * 版本: v0301-refactor
 */

// 全局变量容器 (避免污染全局作用域的最佳实践，但此处为了保持与原 HTML 逻辑兼容性，暂沿用全局变量)
let mainChart = null;
let rsiChart = null;
let macdChart = null;
let equityChart = null;
let candleSeries = null;
let rsiSeries = null;
let macdHistSeries = null;
let macdMacdSeries = null;
let macdSignalSeries = null;
let equitySeries = null;

let latestStrategyInfo = null;
let isConnected = false;
let reconnectAttempts = 0;
let currentStrategyId = 'grid_v51';
let currentSlotStatus = 'stopped';
let candleDataBuffer = [];
let lastCandleTime = null;
let rsiStartTime = null;
let lastRsiUpdateTime = null;
let lastMacdUpdateTime = null;
let initialBalanceForChart = null;
let equityStartTime = null;
let lastEquityUpdateTime = null;

// 标记缓存
let globalTradeMarkers = [];
let globalPivotMarkers = [];
let tradePaginationState = {
    allTrades: [],
    currentPage: 1,
    pageSize: 20,
    totalPages: 1
};

// 工具函数
function fmtPct(v) {
    if (v === undefined || v === null || Number.isNaN(Number(v))) return '--';
    return `${(Number(v) * 100).toFixed(2)}%`;
}
function fmtVal(v) {
    if (v === undefined || v === null) return '--';
    if (typeof v === 'boolean') return v ? '开启' : '关闭';
    if (typeof v === 'number') return Number.isInteger(v) ? `${v}` : `${v.toFixed(4)}`;
    return `${v}`;
}

function formatNumber(num, decimals = 2) {
    if (num === undefined || num === null) return '--';
    return num.toLocaleString('zh-CN', { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
}

function convertTime(timestamp) {
    if (timestamp === undefined || timestamp === null) return null;
    let ms;
    if (typeof timestamp === 'number') {
        ms = timestamp > 1e12 ? timestamp : timestamp * 1000;
    } else if (typeof timestamp === 'string') {
        const ts = /Z$|[+-]\d{2}:?\d{2}$/.test(timestamp) ? timestamp : `${timestamp}Z`;
        const date = new Date(ts);
        ms = date.getTime();
    } else {
        return null;
    }
    const seconds = Math.floor(ms / 1000);
    // LightweightCharts 默认展示为 UTC，我们需要根据本地时区调整
    const localOffset = new Date().getTimezoneOffset() * 60;
    return seconds - localOffset;
}

function convertAndValidateCandle(c) {
    if (!c || typeof c !== 'object') return null;
    const required = ['t', 'o', 'h', 'l', 'c'];
    for (const key of required) {
        if (c[key] === undefined || c[key] === null) return null;
    }
    const time = convertTime(c.t);
    if (!time) return null;
    const open = parseFloat(c.o);
    const high = parseFloat(c.h);
    const low = parseFloat(c.l);
    const close = parseFloat(c.c);
    if (!Number.isFinite(open) || !Number.isFinite(high) || !Number.isFinite(low) || !Number.isFinite(close)) return null;
    if (high < low || high < 0 || low < 0) return null;
    return { time, open, high, low, close };
}

function prepareBatchData(dataList) {
    if (!Array.isArray(dataList) || dataList.length === 0) return [];
    const batch = [];
    const seen = new Set();
    for (const item of dataList) {
        if (!item) continue;
        const ts = convertTime(item.t);
        if (!ts || seen.has(ts)) continue;
        seen.add(ts);
        if (item.v === undefined || item.v === null) {
            batch.push({ time: ts });
        } else {
            batch.push({ time: ts, value: parseFloat(item.v) });
        }
    }
    return batch.sort((a, b) => a.time - b.time);
}

// 图表逻辑
function initCharts() {
    mainChart = LightweightCharts.createChart(document.getElementById('tv-chart-main'), {
        layout: { background: { color: 'transparent' }, textColor: '#94a3b8', fontFamily: "'Noto Sans SC', sans-serif" },
        grid: { vertLines: { color: 'rgba(255, 255, 255, 0.03)' }, horzLines: { color: 'rgba(255, 255, 255, 0.03)' } },
        crosshair: { mode: LightweightCharts.CrosshairMode.Normal, vertLine: { color: '#00d4ff' }, horzLine: { color: '#00d4ff' } },
        rightPriceScale: { borderColor: 'rgba(255, 255, 255, 0.1)', mode: LightweightCharts.PriceScaleMode.Normal, scaleMargins: { top: 0.1, bottom: 0.1 }, minimumWidth: 72 },
        timeScale: { borderColor: 'rgba(255, 255, 255, 0.1)', timeVisible: true, shiftVisibleRangeOnNewBar: true, rightBarStaysOnScroll: true },
        handleScroll: { vertTouchDrag: false },
    });

    candleSeries = mainChart.addCandlestickSeries({ upColor: '#00d084', downColor: '#ff4757', borderUpColor: '#00d084', borderDownColor: '#ff4757', wickUpColor: '#00d084', wickDownColor: '#ff4757' });
    window.gridLines = [];

    rsiChart = LightweightCharts.createChart(document.getElementById('tv-chart-rsi'), {
        layout: { background: { color: 'transparent' }, textColor: '#94a3b8', fontFamily: "'Noto Sans SC', sans-serif" },
        grid: { vertLines: { color: 'rgba(255, 255, 255, 0.03)' }, horzLines: { color: 'rgba(255, 255, 255, 0.03)' } },
        crosshair: { mode: LightweightCharts.CrosshairMode.Magnet, vertLine: { color: '#00d4ff' }, horzLine: { color: '#00d4ff' } },
        rightPriceScale: { borderColor: 'rgba(255, 255, 255, 0.1)', scaleMargins: { top: 0.1, bottom: 0.1 }, minimumWidth: 72 },
        timeScale: { visible: false },
    });
    rsiSeries = rsiChart.addLineSeries({ color: '#a855f7', lineWidth: 2, title: 'RSI' });

    macdChart = LightweightCharts.createChart(document.getElementById('tv-chart-macd'), {
        layout: { background: { color: 'transparent' }, textColor: '#94a3b8', fontFamily: "'Noto Sans SC', sans-serif" },
        grid: { vertLines: { color: 'rgba(255, 255, 255, 0.03)' }, horzLines: { color: 'rgba(255, 255, 255, 0.03)' } },
        crosshair: { mode: LightweightCharts.CrosshairMode.Magnet, vertLine: { color: '#00d4ff' } },
        rightPriceScale: { borderColor: 'rgba(255, 255, 255, 0.1)', autoScale: true, scaleMargins: { top: 0.1, bottom: 0.1 }, visible: true, minimumWidth: 72 },
        timeScale: { visible: false },
    });
    macdHistSeries = macdChart.addHistogramSeries({ color: '#26a69a', priceFormat: { type: 'volume' }, priceScaleId: 'right' });
    macdMacdSeries = macdChart.addLineSeries({ color: '#2962FF', lineWidth: 1, title: 'MACD', priceScaleId: 'right' });
    macdSignalSeries = macdChart.addLineSeries({ color: '#FF6D00', lineWidth: 1, title: 'Signal', priceScaleId: 'right' });
    macdHistSeries.createPriceLine({ price: 0, color: 'rgba(255, 255, 255, 0.2)', lineWidth: 1, lineStyle: LightweightCharts.LineStyle.Solid, axisLabelVisible: false });

    equityChart = LightweightCharts.createChart(document.getElementById('tv-chart-equity'), {
        layout: { background: { color: 'transparent' }, textColor: '#94a3b8', fontFamily: "'Noto Sans SC', sans-serif" },
        grid: { vertLines: { color: 'rgba(255, 255, 255, 0.03)' }, horzLines: { color: 'rgba(255, 255, 255, 0.03)' } },
        crosshair: { mode: LightweightCharts.CrosshairMode.Magnet, vertLine: { color: '#00d4ff' } },
        rightPriceScale: { borderColor: 'rgba(255, 255, 255, 0.1)', scaleMargins: { top: 0.1, bottom: 0.1 }, minimumWidth: 72 },
        timeScale: { visible: false },
    });
    equitySeries = equityChart.addLineSeries({ color: '#f59e0b', lineWidth: 2, title: '总资产' });

    function syncCharts(sourceChart) {
        const logicalRange = sourceChart.timeScale().getVisibleLogicalRange();
        if (logicalRange) {
            [mainChart, rsiChart, macdChart, equityChart].forEach(c => {
                if (c !== sourceChart) c.timeScale().setVisibleLogicalRange(logicalRange);
            });
        }
    }
    [mainChart, rsiChart, macdChart, equityChart].forEach(c => {
        c.timeScale().subscribeVisibleTimeRangeChange(() => syncCharts(c));
    });

    const resizeObserver = new ResizeObserver(() => {
        [mainChart, rsiChart, macdChart, equityChart].forEach(c => {
            const container = c.chartElement().parentElement;
            if (container) c.applyOptions({ width: container.clientWidth });
        });
    });
    resizeObserver.observe(document.getElementById('tv-chart-main'));
}

function updateMACD(macdData, timestamp) {
    if (!macdHistSeries || !timestamp || !macdData) return;
    const time = convertTime(timestamp);
    if (!time) return;
    if (lastMacdUpdateTime !== null && time < lastMacdUpdateTime) return;
    try {
        const hist = (macdData.macdhist === null || macdData.macdhist === undefined) ? null : parseFloat(macdData.macdhist);
        const macdLine = (macdData.macd === null || macdData.macd === undefined) ? null : parseFloat(macdData.macd);
        const signalLine = (macdData.macdsignal === null || macdData.macdsignal === undefined) ? null : parseFloat(macdData.macdsignal);

        if (hist === null) macdHistSeries.update({ time }); else macdHistSeries.update({ time, value: hist, color: hist > 0 ? '#26a69a' : '#ef5350' });
        if (macdLine === null) macdMacdSeries.update({ time }); else macdMacdSeries.update({ time, value: macdLine });
        if (signalLine === null) macdSignalSeries.update({ time }); else macdSignalSeries.update({ time, value: signalLine });
        lastMacdUpdateTime = time;
    } catch (err) { console.error('[Chart] MACD Update Error:', err); }
}

function updateRSI(rsiValue, timestamp) {
    if (!rsiSeries || !timestamp) return;
    const time = convertTime(timestamp);
    if (!time) return;
    if (lastRsiUpdateTime !== null && time < lastRsiUpdateTime) return;
    if (rsiStartTime === null && rsiValue !== null) {
        rsiStartTime = time;
        if (!window.rsiLinesDrawn) {
            rsiSeries.createPriceLine({ price: 70, color: '#ff4757', lineWidth: 1, lineStyle: LightweightCharts.LineStyle.Dashed, title: '超买(70)' });
            rsiSeries.createPriceLine({ price: 30, color: '#00d084', lineWidth: 1, lineStyle: LightweightCharts.LineStyle.Dashed, title: '超卖(30)' });
            window.rsiLinesDrawn = true;
        }
    }
    const val = (rsiValue === null || rsiValue === undefined) ? null : parseFloat(rsiValue);
    rsiSeries.update(val === null ? { time } : { time, value: val });
    lastRsiUpdateTime = time;
}

function updateEquity(totalValue, timestamp) {
    if (!equitySeries || !timestamp) return;
    const time = convertTime(timestamp);
    if (!time) return;
    if (lastEquityUpdateTime !== null && time < lastEquityUpdateTime) return;
    if (equityStartTime === null && totalValue !== null) {
        equityStartTime = time;
        if (!window.equityLineDrawn && initialBalanceForChart !== null) {
            equitySeries.createPriceLine({ price: parseFloat(initialBalanceForChart), color: '#64748b', lineWidth: 1, lineStyle: LightweightCharts.LineStyle.Dashed, title: '初始资金' });
            window.equityLineDrawn = true;
        }
    }
    const val = (totalValue === null || totalValue === undefined) ? null : parseFloat(totalValue);
    equitySeries.update(val === null ? { time } : { time, value: val });
    lastEquityUpdateTime = time;
}

function updateChart(data, tradeHistory) {
    if (!candleSeries) return;
    const candles = Array.isArray(data) ? data : [data].filter(x => x);
    if (candles.length === 0 && (!tradeHistory || tradeHistory.length === 0)) return;
    const tvData = candles.map(c => convertAndValidateCandle(c)).filter(x => x);
    if (tvData.length === 0) return;
    try {
        if (Array.isArray(data) && data.length > 1) {
            candleDataBuffer = tvData.sort((a, b) => a.time - b.time).slice(-500);
            candleSeries.setData(candleDataBuffer);
            if (candleDataBuffer.length > 0) lastCandleTime = candleDataBuffer[candleDataBuffer.length - 1].time;
            if (window.isInitializingCharts) { mainChart.timeScale().fitContent(); window.isInitializingCharts = false; }
        } else {
            const lastCandle = tvData[tvData.length - 1];
            upsertCandle(candleDataBuffer, lastCandle);
            candleSeries.update(lastCandle);
            lastCandleTime = lastCandle.time;
        }
    } catch (err) { console.error('[Chart] Candle Update Error:', err); }
    if (tradeHistory) updateTradeMarkers(tradeHistory);
}

function upsertCandle(buffer, candle) {
    if (!buffer || buffer.length === 0) { buffer.push(candle); return; }
    const last = buffer[buffer.length - 1];
    if (candle.time > last.time) { buffer.push(candle); }
    else if (candle.time === last.time) { buffer[buffer.length - 1] = candle; }
    else {
        const idx = buffer.findIndex(x => x.time === candle.time);
        if (idx >= 0) buffer[idx] = candle; else { buffer.push(candle); buffer.sort((a, b) => a.time - b.time); }
    }
    if (buffer.length > 500) buffer.splice(0, buffer.length - 500);
}

function updateTradeMarkers(tradeHistory) {
    if (!candleSeries || !Array.isArray(tradeHistory)) return;
    globalTradeMarkers = tradeHistory.map(trade => {
        const time = convertTime(trade.time);
        const price = parseFloat(trade.price);
        if (!time || isNaN(price)) return null;
        return {
            time, position: trade.type === 'BUY' ? 'belowBar' : 'aboveBar',
            color: trade.type === 'BUY' ? '#00d084' : '#ff4757',
            shape: trade.type === 'BUY' ? 'arrowUp' : 'arrowDown',
            text: trade.type === 'BUY' ? `买入` : `卖出`,
            size: 1.5,
            id: `trade_${trade.time}_${trade.id || ''}`
        };
    }).filter(x => x);
    refreshMarkers();
}

function updatePivotMarkers(pivots) {
    if (!pivots) return;
    const ph = pivots.pivots_high || [];
    const pl = pivots.pivots_low || [];
    globalPivotMarkers = [];
    ph.forEach(p => {
        const t = convertTime(p.time);
        if (t) globalPivotMarkers.push({ time: t, position: 'aboveBar', color: '#f59e0b', shape: 'circle', text: '阻力', size: 0.8, id: `pivot_h_${p.time}` });
    });
    pl.forEach(p => {
        const t = convertTime(p.time);
        if (t) globalPivotMarkers.push({ time: t, position: 'belowBar', color: '#a855f7', shape: 'circle', text: '支撑', size: 0.8, id: `pivot_l_${p.time}` });
    });
    refreshMarkers();
}

function refreshMarkers() {
    if (!candleSeries) return;
    // 合并并去重 (基于 time 和 id)
    const all = [...globalTradeMarkers, ...globalPivotMarkers].sort((a, b) => a.time - b.time);
    candleSeries.setMarkers(all);
}

function drawGridLines(gridLower, gridUpper, gridLevels) {
    if (!candleSeries || !gridLevels || gridLevels < 2) return;

    // 决定哪些标签需要显示 (保留 3-5 个)
    const showIndices = new Set();
    showIndices.add(0); // 下界
    showIndices.add(gridLevels - 1); // 上界
    if (gridLevels > 2) showIndices.add(Math.floor(gridLevels / 2)); // 中间
    if (gridLevels > 6) {
        showIndices.add(Math.floor(gridLevels / 4));
        showIndices.add(Math.floor(3 * gridLevels / 4));
    }

    if (!window.gridLines || window.gridLines.length !== gridLevels) {
        if (window.gridLines) window.gridLines.forEach(l => candleSeries.removePriceLine(l));
        window.gridLines = [];
        const colors = ['#00d084', '#a855f7', '#ff4757'];
        for (let i = 0; i < gridLevels; i++) {
            const color = i === 0 ? colors[0] : (i === gridLevels - 1 ? colors[2] : colors[1]);
            const isLabelVisible = showIndices.has(i);
            window.gridLines.push(candleSeries.createPriceLine({
                price: gridLower,
                color,
                lineWidth: 1,
                lineStyle: LightweightCharts.LineStyle.Dashed,
                axisLabelVisible: isLabelVisible,
                title: i === 0 ? '网格下界' : (i === gridLevels - 1 ? '网格上界' : (isLabelVisible ? `网格${i}` : ''))
            }));
        }
    }
    const step = (gridUpper - gridLower) / (gridLevels - 1);
    for (let i = 0; i < gridLevels; i++) window.gridLines[i].applyOptions({ price: gridLower + step * i });
}

// UI 业务逻辑
function formatLocalTime(timeStr) {
    if (!timeStr) return '--:--:--';
    try {
        const ts = (typeof timeStr === 'string' && !(/Z$|[+\-]\d{2}:?\d{2}$/.test(timeStr))) ? `${timeStr}Z` : timeStr;
        return new Date(ts).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });
    } catch (e) { return '--:--:--'; }
}

function renderTradeList() {
    const container = document.getElementById('tradeList');
    if (!container) return;
    const { allTrades, currentPage, pageSize } = tradePaginationState;
    tradePaginationState.totalPages = Math.ceil(allTrades.length / pageSize) || 1;
    const pageTrades = allTrades.slice((currentPage - 1) * pageSize, currentPage * pageSize);
    container.innerHTML = pageTrades.length ? '' : '<div class="empty-state">暂无交易记录</div>';
    document.getElementById('tradePagination').style.display = pageTrades.length ? 'flex' : 'none';
    pageTrades.forEach(trade => {
        const item = document.createElement('div');
        item.className = `trade-item ${trade.type.toLowerCase()}`;
        const amountText = (trade.quote_amount > 0 ? trade.quote_amount : (trade.price * trade.size));
        item.innerHTML = `<div class="trade-icon">${trade.type === 'BUY' ? '买' : '卖'}</div><div class="trade-info"><div class="trade-type">${trade.type === 'BUY' ? '买入' : '卖出'} BTC</div><div style="font-size:12px;color:#888;">${trade.size.toFixed(6)} BTC @ $${trade.price.toFixed(2)}</div><div class="trade-time">${formatLocalTime(trade.time)}</div></div><div class="trade-price" style="color:${trade.type === 'BUY' ? 'var(--loss)' : 'var(--profit)'}">${trade.type === 'BUY' ? '-' : '+'}${amountText.toFixed(2)} USDT</div>`;
        container.appendChild(item);
    });
    document.getElementById('tradeCount').textContent = `${allTrades.length} 笔`;
    const info = document.getElementById('tradePageInfo');
    if (info) info.textContent = `第 ${currentPage}/${tradePaginationState.totalPages} 页 (共 ${allTrades.length} 笔)`;
    document.getElementById('prevTradePage').disabled = currentPage <= 1;
    document.getElementById('nextTradePage').disabled = currentPage >= tradePaginationState.totalPages;
}

function updateControlButtons(status) {
    currentSlotStatus = status;
    const startBtn = document.getElementById('startBtn'), pauseBtn = document.getElementById('pauseBtn');
    if (!startBtn || !pauseBtn) return;
    startBtn.disabled = status === 'running'; startBtn.style.opacity = status === 'running' ? '0.4' : '1';
    pauseBtn.disabled = status !== 'running'; pauseBtn.style.opacity = status !== 'running' ? '0.4' : '1';
}

function renderStrategyDoc(strategyData) {
    const box = document.getElementById('strategyDocContent');
    const params = strategyData?.params;
    const metadata = strategyData?.param_metadata || {};
    if (!params) { box.innerHTML = `<div class="strategy-block"><p>等待策略参数同步...</p></div>`; return; }

    // 1. 核心判别逻辑部分
    const logicHtml = `
        <div style="background: rgba(0,212,255,0.03); border: 1px solid rgba(0,212,255,0.1); border-radius: 8px; padding: 18px; margin-bottom: 24px;">
            <h5 style="margin: 0 0 12px 0; color: var(--primary); font-size: 16px;">🧠 策略核心判别逻辑</h5>
            <ul style="margin: 0; padding-left: 20px; font-size: 14px; color: var(--text-secondary); line-height: 1.7;">
                <li><strong>趋势判别：</strong>使用 MACD (12,26,9) 柱状图斜率判断 5 级市场状态（强牛至强熊）。</li>
                <li><strong>入场择时：</strong>基于自适应 RSI (14) 识别超买超卖，强牛市网格上移，强熊市网格下移。</li>
                <li><strong>网格执行：</strong>结合 ATR 波动率动态计算网格上下边界及间距，实现自适应网格。</li>
                <li><strong>多维风控：</strong>包含 RSI 高位禁买、移动止盈（基于指标背离）、黑天鹅检测及冷却期机制。</li>
            </ul>
        </div>
    `;

    // 2. 将参数渲染为 2 列网格布局
    const gridHtml = Object.entries(params).map(([k, v]) => {
        const meta = metadata[k] || { label: k, desc: '暂无说明', default: '--' };
        let displayVal = v;
        if (typeof v === 'boolean') displayVal = v ? 'true' : 'false';
        return `
            <div class="param-item" style="padding: 18px; background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.05); border-radius: 10px; display: flex; flex-direction: column; gap: 12px;">
                <div style="display: flex; justify-content: space-between; align-items: flex-start;">
                    <div class="param-name" style="flex: 1; padding-right: 12px;">
                        <div style="font-weight: bold; color: var(--text-primary); font-size: 17px; margin-bottom: 4px;">${meta.label}</div>
                        <div style="font-weight: normal; color: #475569; font-size: 13px; font-family: monospace;">${k}</div>
                    </div>
                    <div style="display: flex; flex-direction: column; align-items: flex-end; gap: 6px;">
                        <input type="text" class="param-input" id="input-${k}" data-key="${k}" value="${displayVal}" 
                               style="width: 85px; text-align: right; background: #0f172a; border: 1px solid #334155; color: var(--primary); padding: 5px 10px; border-radius: 6px; font-size: 15px; font-family: monospace; transition: all 0.3s;">
                        <div style="font-size: 12px; color: #10b981;">
                            <span style="color: #475569;">默认:</span>
                            <span style="cursor: pointer; text-decoration: underline dotted; font-weight: bold; padding: 2px 4px; background: rgba(16,185,129,0.1); border-radius: 3px;" 
                                  title="点击恢复默认值"
                                  onclick="const el=document.getElementById('input-${k}'); el.value='${meta.default}'; el.focus(); el.style.boxShadow='0 0 12px var(--primary)'; setTimeout(()=>el.style.boxShadow='', 600);">
                                ${meta.default}
                            </span>
                        </div>
                    </div>
                </div>
                <div style="font-size: 14px; color: var(--text-secondary); line-height: 1.6; border-top: 1px solid rgba(255,255,255,0.03); padding-top: 10px; min-height: 3em;">
                    ${meta.desc}
                </div>
            </div>`;
    }).join('');

    box.innerHTML = `
        <div class="strategy-block">
            ${logicHtml}
            <h4 style="margin-bottom: 20px; color: var(--text-primary); border-left: 4px solid var(--primary); padding-left: 12px; font-size: 18px;">策略参数配置</h4>
            <div class="param-list" style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 15px;">${gridHtml}</div>
            <div style="margin-top:24px; padding: 15px; background: rgba(0,212,255,0.05); border: 1px dashed var(--primary); border-radius: 8px; font-size:14px; color: var(--text-primary); line-height: 1.6;">
                <strong>💡 操作提示：</strong><br>
                1. 修改数值后，点击页面下方的“<strong>保存并应用</strong>”按钮。<br>
                2. 点击绿色的“<strong>默认值</strong>”数字可快速恢复初始配置。<br>
                3. 修改核心周期参数（MACD/RSI/ATR）会重置指标引擎。
            </div>
        </div>`;
}

// Socket 事件
socket.on('connect', () => { isConnected = true; reconnectAttempts = 0; document.getElementById('statusDot').className = 'status-dot connected'; document.getElementById('statusText').textContent = '已连接'; });
socket.on('disconnect', () => { isConnected = false; document.getElementById('statusDot').className = 'status-dot disconnected'; document.getElementById('statusText').textContent = '已断开'; });
socket.on('strategies_list', () => { socket.emit('join', { strategy_id: currentStrategyId }); });
socket.on('reset_ui', (data) => {
    const isSoft = data && data.soft;
    console.log(`[SocketIO] 执行重置信号: sid=${currentStrategyId}, soft=${isSoft}`);

    // 1. 物理清空账户相关数据 (内存与 UI)
    tradePaginationState.allTrades = [];
    tradePaginationState.currentPage = 1;
    renderTradeList();
    globalTradeMarkers = [];

    // 2. 重置权益资产 (无论软硬都清空，因为资金重置了)
    if (window.equitySeries) window.equitySeries.setData([]);
    window.equityLineDrawn = false;
    lastEquityUpdateTime = null;

    // 3. 只有全量重置才清空行情
    if (!isSoft) {
        console.log('[SocketIO] 执行全量硬重置 - 清空行情历史');
        if (window.candleSeries) window.candleSeries.setData([]);
        if (window.rsiSeries) window.rsiSeries.setData([]);
        if (window.macdMacdSeries) window.macdMacdSeries.setData([]);
        if (window.macdSignalSeries) window.macdSignalSeries.setData([]);
        if (window.macdHistSeries) window.macdHistSeries.setData([]);

        // 移除 markers 和网格线
        candleSeries?.setMarkers([]);
        globalPivotMarkers = [];
        if (window.gridLines && window.candleSeries) {
            window.gridLines.forEach(l => window.candleSeries.removePriceLine(l));
            window.gridLines = [];
        }
        window.rsiLinesDrawn = false;
        lastCandleTime = lastRsiUpdateTime = lastMacdUpdateTime = null;
    } else {
        console.log('[SocketIO] 执行软重置 - 行情数据已保留');
        // 软重置也要清除图表上的成交标记，因为 trades 没了
        candleSeries?.setMarkers([]);
    }

    // 4. 重置账户 UI 面板数值
    const resetFields = [
        'totalValue', 'pnlRate', 'cashValue', 'positionSize',
        'positionAvgPrice', 'positionUnrealizedPnl', 'positionLayers',
        'signalText', 'macdTrend', 'atrVal', 'marketRegime'
    ];
    resetFields.forEach(id => {
        const el = document.getElementById(id);
        if (!el) return;
        if (id === 'pnlRate') el.textContent = '0.00%';
        else if (id === 'positionLayers') el.textContent = '0 层';
        else if (id === 'signalText') el.textContent = '等待重启...';
        else el.textContent = '--';
    });

    updateControlButtons('stopped');
});

socket.on('strategy_status_changed', (data) => {
    console.log('[SocketIO] 策略状态变更:', data);
    if (data.status) updateControlButtons(data.status);
});

socket.on('history_update', (data) => {
    if (data.history_candles) updateChart(data.history_candles, []);
    if (data.history_rsi && rsiSeries) rsiSeries.setData(prepareBatchData(data.history_rsi));
    if (data.history_equity && equitySeries) equitySeries.setData(prepareBatchData(data.history_equity));
    if (data.history_macd) {
        const batch = data.history_macd;
        const macdData = [], signalData = [], histData = [];
        batch.forEach(item => {
            const time = convertTime(item.time);
            if (!time) return;
            // null 值作为留白占位（只push {time}），保持数据点数量与K线一致
            // 这样 syncCharts 的 LogicalRange 才能正确对齐
            macdData.push(item.macd !== null && item.macd !== undefined ? { time, value: item.macd } : { time });
            signalData.push(item.macdsignal !== null && item.macdsignal !== undefined ? { time, value: item.macdsignal } : { time });
            if (item.macdhist !== null && item.macdhist !== undefined) {
                histData.push({ time, value: item.macdhist, color: item.macdhist > 0 ? '#26a69a' : '#ef5350' });
            } else {
                histData.push({ time });
            }
        });
        if (macdMacdSeries) macdMacdSeries.setData(macdData);
        if (macdSignalSeries) macdSignalSeries.setData(signalData);
        if (macdHistSeries) macdHistSeries.setData(histData);
    }
});

socket.on('update', (data) => {
    if (!data) return;
    const ts = data.timestamp || (data.candle ? data.candle.t : null);

    // 1. 更新账户与基础资产 (右侧面板)
    const updateElement = (id, value, fallback = '--') => {
        const el = document.getElementById(id);
        if (el) el.textContent = value !== undefined && value !== null ? value : fallback;
    };

    // 价格与权益
    const currentSymbol = (latestStrategyInfo && latestStrategyInfo.params) ? latestStrategyInfo.params.symbol : (Object.keys(data.prices || {})[0] || 'BTC-USDT');
    const btcPrice = (data.prices && data.prices[currentSymbol]) || (data.prices && data.prices['BTC-USDT']) || (data.prices && data.prices['BTC-USDT-SWAP']) || null;
    if (btcPrice) updateElement('btcPrice', btcPrice.toLocaleString());

    if (data.total_value !== undefined) updateElement('totalValue', data.total_value.toLocaleString() + ' USDT');
    if (data.cash !== undefined) updateElement('cashValue', data.cash.toLocaleString());

    if (data.pnl_pct !== undefined) {
        const pnlEl = document.getElementById('pnlRate');
        if (pnlEl) {
            pnlEl.textContent = (data.pnl_pct >= 0 ? '+' : '') + data.pnl_pct.toFixed(2) + '%';
            pnlEl.style.color = data.pnl_pct >= 0 ? 'var(--profit)' : 'var(--loss)';
        }
    }

    // 2. 更新策略状态 (左侧面板)
    if (data.strategy) {
        latestStrategyInfo = data.strategy;
        const s = data.strategy;

        // 核心信号
        const signalBox = document.getElementById('tradeSignalBox');
        if (signalBox) {
            updateElement('signalText', s.signal_text || '等待数据...');
            updateElement('signalStrengthVal', `强度: ${s.signal_strength || s.signal_strength_val || '--'}`);
            signalBox.classList.remove('buy', 'sell');
            if (s.signal_color === 'buy') signalBox.classList.add('buy');
            else if (s.signal_color === 'sell') signalBox.classList.add('sell');
        }

        // 趋势与分析
        updateElement('macdTrend', s.macd_trend);
        updateElement('atrVal', s.current_atr ? s.current_atr.toFixed(1) : '--');
        updateElement('marketRegime', s.market_regime || '--');

        // 指标
        updateElement('rsiVal', s.current_rsi !== undefined ? s.current_rsi.toFixed(2) : '--');
        if (s.rsi_oversold && s.rsi_overbought) {
            updateElement('rsiThresholds', `${s.rsi_oversold.toFixed(1)} / ${s.rsi_overbought.toFixed(1)}`);
        }

        // 网格部署
        if (s.grid_lower && s.grid_upper) {
            updateElement('gridRange', `${s.grid_lower.toFixed(1)} - ${s.grid_upper.toFixed(1)}`);
        }
        updateElement('positionLayers', s.position_count !== undefined ? `${s.position_count} 层` : '--');

        // 波段参考
        const pivotBox = document.getElementById('pivotInfo');
        if (pivotBox && s.pivots) {
            const ph = s.pivots.pivots_high || [];
            const pl = s.pivots.pivots_low || [];
            if (ph.length > 0 || pl.length > 0) {
                let html = '<div style="margin-bottom:6px;border-bottom:1px solid rgba(255,255,255,0.05);padding-bottom:2px;">波段参考 (Top 3)</div>';
                html += '<div style="display:flex;justify-content:space-between;gap:8px;">';
                html += `<div style="flex:1;"><div style="color:var(--loss);margin-bottom:2px;">阻力 (高)</div>${ph.slice(0, 3).map(p => `<div>$${p.price.toFixed(1)}</div>`).join('')}</div>`;
                html += `<div style="flex:1;"><div style="color:var(--profit);margin-bottom:2px;">支撑 (低)</div>${pl.slice(0, 3).map(p => `<div>$${p.price.toFixed(1)}</div>`).join('')}</div>`;
                html += '</div>';
                pivotBox.innerHTML = html;
            } else {
                pivotBox.innerHTML = '<div style="color:var(--text-secondary);font-size:10px;">计算波段中...</div>';
            }
        }

        // 持仓详情逻辑 (多来源兼容)
        const activeSymbol = (s.params && s.params.symbol) ? s.params.symbol : 'BTC-USDT';
        const posSize = (data.positions && data.positions[activeSymbol]) ? data.positions[activeSymbol].size : (s.position_size || 0);
        updateElement('positionSize', parseFloat(posSize).toFixed(4));

        const posAvg = (data.positions && data.positions[activeSymbol]) ? data.positions[activeSymbol].avg_price : (s.position_avg_price || 0);
        updateElement('positionAvgPrice', posAvg > 0 ? posAvg.toLocaleString() : '--');

        const posPnl = (data.positions && data.positions[activeSymbol]) ? data.positions[activeSymbol].unrealized_pnl : (s.position_unrealized_pnl || 0);
        const pnlDetailEl = document.getElementById('positionUnrealizedPnl');
        if (pnlDetailEl) {
            pnlDetailEl.textContent = posPnl !== 0 ? (posPnl > 0 ? '+' : '') + posPnl.toFixed(2) : '--';
            pnlDetailEl.style.color = posPnl > 0 ? 'var(--profit)' : (posPnl < 0 ? 'var(--loss)' : 'var(--text-primary)');
        }

        // 图表标记与网格线
        if (ts) {
            updatePivotMarkers(s.pivots);
            updateMACD({ macd: s.macd, macdsignal: s.macdsignal, macdhist: s.macdhist }, ts);
            if (s.grid_lines) drawGridLines(s.grid_lines[0], s.grid_lines[s.grid_lines.length - 1], s.grid_lines.length);
        }
    }

    // 3. 图表曲线更新
    if (ts) {
        if (data.rsi !== undefined) updateRSI(data.rsi, ts);
        if (data.total_value !== undefined) updateEquity(data.total_value, ts);
        if (data.candle) updateChart(data.candle, data.trade_history);
    }

    // 4. 其他 UI 状态
    if (data.slot_status) {
        updateControlButtons(data.slot_status.is_running && !data.slot_status.is_paused ? 'running' : (data.slot_status.is_paused ? 'paused' : 'stopped'));
    }
    if (data.trade_history) {
        tradePaginationState.allTrades = data.trade_history.slice().reverse();
        renderTradeList();
    }
    if (data.trade) {
        tradePaginationState.allTrades.unshift(data.trade);
        renderTradeList();
    }
});

// 初始化
document.addEventListener('DOMContentLoaded', () => {
    initCharts();
    document.getElementById('startBtn').onclick = () => socket.emit('start_strategy', { strategy_id: currentStrategyId });
    document.getElementById('pauseBtn').onclick = () => socket.emit('pause_strategy', { strategy_id: currentStrategyId });
    document.getElementById('resetBtn').onclick = () => document.getElementById('resetConfirmModal').style.display = 'flex';
    document.getElementById('confirmResetAction').onclick = () => { socket.emit('reset_strategy', { strategy_id: currentStrategyId }); document.getElementById('resetConfirmModal').style.display = 'none'; };
    document.getElementById('cancelReset').onclick = () => document.getElementById('resetConfirmModal').style.display = 'none';
    document.getElementById('openStrategyDocBtn').onclick = () => { renderStrategyDoc(latestStrategyInfo); document.getElementById('strategyDocModal').classList.add('show'); };
    document.getElementById('closeStrategyDocBtn').onclick = () => document.getElementById('strategyDocModal').classList.remove('show');
    document.getElementById('prevTradePage').onclick = () => { if (tradePaginationState.currentPage > 1) { tradePaginationState.currentPage--; renderTradeList(); } };
    document.getElementById('nextTradePage').onclick = () => { if (tradePaginationState.currentPage < tradePaginationState.totalPages) { tradePaginationState.currentPage++; renderTradeList(); } };

    // 保存参数逻辑
    document.getElementById('saveParamsBtn').onclick = () => {
        const inputs = document.querySelectorAll('.param-input');
        const newParams = {};
        inputs.forEach(input => {
            const key = input.getAttribute('data-key');
            let val = input.value.trim();
            // 基础类型转换尝试
            if (val.toLowerCase() === 'true') val = true;
            else if (val.toLowerCase() === 'false') val = false;
            else if (!isNaN(val) && val !== '') val = parseFloat(val);
            newParams[key] = val;
        });

        console.log('[Dashboard] 发送参数更新请求:', newParams);
        socket.emit('save_strategy_params', {
            strategy_id: currentStrategyId,
            params: newParams
        });

        // 提示并关闭弹窗
        alert('参数已提交保存请求，请留意终端反馈');
        document.getElementById('strategyDocModal').classList.remove('show');
    };
});
