#!/usr/bin/env python3
"""
Simulate FlatToFlatEngine with real Sierra Chart DTC data from Sim1 account.
This script connects to Sierra Chart, fetches fills, and replays them through
the engine logic to identify why trades are not detected.
"""
import json, time, hashlib, base64, os, struct, socket
from datetime import datetime

# ── DTC WebSocket client (raw socket, manual WS frames) ──

def ws_handshake(sock, host, port):
    key = base64.b64encode(os.urandom(16)).decode()
    req = (f"GET / HTTP/1.1\r\nHost: {host}:{port}\r\n"
           "Upgrade: websocket\r\nConnection: Upgrade\r\n"
           f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n")
    sock.sendall(req.encode())
    resp = b''
    while b'\r\n\r\n' not in resp:
        resp += sock.recv(4096)
    return b'101' in resp

def ws_send(sock, data):
    payload = json.dumps(data, separators=(',', ':')).encode()
    mask = os.urandom(4)
    masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
    hdr = b'\x81'
    L = len(payload)
    if L < 126: hdr += bytes([0x80 | L])
    elif L < 65536: hdr += bytes([0x80 | 126]) + struct.pack('>H', L)
    else: hdr += bytes([0x80 | 127]) + struct.pack('>Q', L)
    sock.sendall(hdr + mask + masked)

def ws_recv_all(sock, timeout=10):
    sock.settimeout(timeout)
    buf = b''
    msgs = []
    while True:
        try:
            chunk = sock.recv(65536)
            if not chunk: break
            buf += chunk
        except socket.timeout: break
        except: break
        while len(buf) >= 2:
            op = buf[0] & 0x0F
            msk = bool(buf[1] & 0x80)
            L = buf[1] & 0x7F
            off = 2
            if L == 126:
                if len(buf) < off + 2: break
                L = struct.unpack('>H', buf[off:off+2])[0]; off += 2
            elif L == 127:
                if len(buf) < off + 8: break
                L = struct.unpack('>Q', buf[off:off+8])[0]; off += 8
            if msk:
                if len(buf) < off + 4: break
                mask = buf[off:off+4]; off += 4
            else:
                mask = None
            if len(buf) < off + L: break
            payload = buf[off:off+L]
            if mask: payload = bytes(b ^ mask[i%4] for i, b in enumerate(payload))
            buf = buf[off+L:]
            if op == 1:
                for part in payload.decode('utf-8', errors='replace').split('\x00'):
                    if part.strip():
                        try: msgs.append(json.loads(part))
                        except: pass
    return msgs

# ── FUT_MAP for price normalization ──
FUT_MAP = {
    'MES': {'tickSize': 0.25, 'currencyPerTick': 1.25, 'divisor': 100},
    'MNQ': {'tickSize': 0.25, 'currencyPerTick': 0.25, 'divisor': 100},
    'ES':  {'tickSize': 0.25, 'currencyPerTick': 12.50, 'divisor': 100},
    'NQ':  {'tickSize': 0.25, 'currencyPerTick': 5.00, 'divisor': 100},
    'MYM': {'tickSize': 1.00, 'currencyPerTick': 0.50, 'divisor': 100},
    'YM':  {'tickSize': 1.00, 'currencyPerTick': 5.00, 'divisor': 100},
    'M2K': {'tickSize': 0.10, 'currencyPerTick': 0.20, 'divisor': 100},
    'MCL': {'tickSize': 0.01, 'currencyPerTick': 1.00, 'divisor': 1000},
    'RTY': {'tickSize': 0.10, 'currencyPerTick': 5.00, 'divisor': 100},
}

def get_meta(sym):
    base = sym.rstrip('0123456789').rstrip('.')
    for k in ['MES','MNQ','ES','NQ','MYM','YM','M2K','MCL','RTY']:
        if base.startswith(k): return FUT_MAP[k]
    return {'tickSize': 0.25, 'currencyPerTick': 1.25, 'divisor': 100}

def normalize_price(sym, raw):
    m = get_meta(sym)
    d = m['divisor']
    return raw / d if d else raw

def price_to_currency(sym, points):
    m = get_meta(sym)
    ticks = points / m['tickSize']
    return ticks * m['currencyPerTick']

def side_from(bs):
    return 1 if bs == 1 else -1 if bs == 2 else 0

# ── FlatToFlatEngine (Python port of JS code) ──
class FlatToFlatEngine:
    def __init__(self):
        self.open_trades = {}  # symbol → trade dict
        self.closed_trades = []
        self._net_pos = {}     # symbol → cumulative net position
    
    def apply_fill(self, symbol, side, qty, price, time_ms, commission=0, pos_after=None):
        if not symbol or not side or not qty or not price or not time_ms:
            return {'closedTrades': [], 'realizedPnl': 0}
        
        result = {'closedTrades': [], 'realizedPnl': 0}
        remaining = qty
        
        # PositionQuantity logic (same as JS)
        if pos_after is not None:
            is_flat = (pos_after == 0)
            self._net_pos[symbol] = pos_after
        else:
            prev = self._net_pos.get(symbol, 0)
            self._net_pos[symbol] = prev + side * qty
            is_flat = (self._net_pos[symbol] == 0)
        
        # Case 1: No open trade
        if symbol not in self.open_trades:
            if is_flat:
                return result  # inherited fill, ignore
            self.open_trades[symbol] = {
                'side': side, 'avgEntry': price, 'totalQty': remaining,
                'openTime': time_ms, 'totalCommission': commission, 'scaleOuts': []
            }
            return result
        
        trade = self.open_trades[symbol]
        
        # Case 2: Same direction (scale-in)
        if trade['side'] == side:
            new_total = trade['totalQty'] + remaining
            trade['avgEntry'] = (trade['avgEntry'] * trade['totalQty'] + price * remaining) / new_total
            trade['totalQty'] = new_total
            trade['totalCommission'] += commission
            
            if is_flat:
                total_pnl_pts = (price - trade['avgEntry']) * trade['side'] * trade['totalQty']
                total_pnl = price_to_currency(symbol, total_pnl_pts) - commission
                ct = {
                    'symbol': symbol, 'side': trade['side'], 'qty': trade['totalQty'],
                    'openTime': trade['openTime'], 'closeTime': time_ms,
                    'entry': trade['avgEntry'], 'exit': price,
                    'pnl': total_pnl
                }
                result['closedTrades'].append(ct)
                self.closed_trades.append(ct)
                del self.open_trades[symbol]
            return result
        
        # Case 3: Opposite direction (scale-out / reversal)
        while remaining > 0 and trade and trade['totalQty'] > 0:
            closed_qty = min(remaining, trade['totalQty'])
            pnl_pts = (price - trade['avgEntry']) * trade['side'] * closed_qty
            pnl_currency = price_to_currency(symbol, pnl_pts)
            comm_portion = (closed_qty / qty) * commission
            net_pnl = pnl_currency - comm_portion
            
            trade['totalQty'] -= closed_qty
            remaining -= closed_qty
            trade['scaleOuts'].append({'qty': closed_qty, 'price': price, 'timeMs': time_ms, 'pnl': net_pnl})
            
            if trade['totalQty'] <= 0:
                total_qty = sum(so['qty'] for so in trade['scaleOuts'])
                avg_exit = sum(so['price'] * so['qty'] for so in trade['scaleOuts']) / total_qty if total_qty else price
                total_pnl = sum(so['pnl'] for so in trade['scaleOuts'])
                close_time = trade['scaleOuts'][-1]['timeMs'] if trade['scaleOuts'] else time_ms
                
                ct = {
                    'symbol': symbol, 'side': trade['side'], 'qty': total_qty,
                    'openTime': trade['openTime'], 'closeTime': close_time,
                    'entry': trade['avgEntry'], 'exit': avg_exit,
                    'pnl': total_pnl
                }
                result['closedTrades'].append(ct)
                self.closed_trades.append(ct)
                del self.open_trades[symbol]
                trade = None
                
                if is_flat:
                    remaining = 0
                elif remaining > 0:
                    self.open_trades[symbol] = {
                        'side': side, 'avgEntry': price, 'totalQty': remaining,
                        'openTime': time_ms, 'totalCommission': commission * (remaining / qty),
                        'scaleOuts': []
                    }
                    remaining = 0
        
        return result

# ── Main ──
def main():
    host = '127.0.0.1'
    port = 11099
    
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(10)
    sock.connect((host, port))
    
    if not ws_handshake(sock, host, port):
        print("Handshake failed"); return
    
    # LOGON
    ws_send(sock, {"Type":1,"ProtocolVersion":8,"Username":"","Password":"",
                   "TradeAccount":"Sim1","Hostname":"debug","ClientName":"JTWJ-debug"})
    time.sleep(1)
    msgs = ws_recv_all(sock, 5)
    logon = [m for m in msgs if m.get('Type') == 2]
    
    if not logon or logon[0].get('Result') != 1:
        print(f"LOGON failed: {logon}"); sock.close(); return
    
    print("LOGON OK")
    uses_multi = logon[0].get('UsesMultiplePositionsPerSymbolAndTradeAccount', 0)
    print(f"UsesMultiplePositions={uses_multi}")
    
    # Request fills - last 7 days
    now_sec = int(time.time())
    ws_send(sock, {"Type":303,"TradeAccount":"Sim1","RequestID":42,
                   "StartDateTime":now_sec - 7*86400})
    
    fills = []
    no_fills = False
    start = time.time()
    while time.time() - start < 15:
        new_msgs = ws_recv_all(sock, 5)
        for m in new_msgs:
            if m.get('Type') == 304:
                if m.get('NoOrderFills'):
                    no_fills = True
                else:
                    fills.append(m)
        if no_fills: break
    
    print(f"\nFills received: {len(fills)}")
    
    # Sort by DateTime
    fills.sort(key=lambda f: float(f.get('DateTime', 0)))
    
    # Replay through FlatToFlatEngine
    engine = FlatToFlatEngine()
    closed_count = 0
    
    print(f"\n{'#':>3} {'Symbol':10s} {'Side':4s} {'Qty':>5} {'Price':>10} {'OC':>5} {'PosQty':>7} {'NetPos':>7} {'Trades':>6} {'Action'}")
    print("─" * 85)
    
    for i, f in enumerate(fills):
        sym = f.get('Symbol', '?')
        bs = f.get('BuySell', 0)
        qty = f.get('Quantity', 0)
        raw_price = f.get('Price', 0)
        oc = f.get('OpenClose', '?')
        pq_raw = f.get('PositionQuantity')
        dt_raw = f.get('DateTime', 0)
        comm = f.get('Commission', 0) or 0
        eid = f.get('UniqueExecutionID', '')
        
        side = side_from(bs)
        price = normalize_price(sym, raw_price) if raw_price else 0
        
        # Parse timestamp
        ts = float(dt_raw) if dt_raw else 0
        if ts > 1e12: ts = ts / 1000
        elif ts > 1e9: ts = ts * 1000
        ts = int(ts)
        
        # PositionQuantity: None if absent
        pos_qty = pq_raw if (pq_raw is not None and pq_raw != '') else None
        
        oc_str = 'OPEN' if oc == 1 else 'CLOSE' if oc == 2 else f'OC{oc}'
        side_str = 'Buy' if side == 1 else 'Sell' if side == -1 else '???'
        pq_str = str(pq_raw) if pq_raw is not None else '---'
        net_before = engine._net_pos.get(sym, 0)
        
        r = engine.apply_fill(sym, side, qty, price, ts, comm, pos_qty)
        n_closed = len(r['closedTrades'])
        closed_count += n_closed
        
        net_after = engine._net_pos.get(sym, 0)
        
        # Determine action description
        action = ''
        if n_closed > 0:
            for ct in r['closedTrades']:
                action += f"CLOSED {ct['side']:+d}qty={ct['qty']}@{ct['entry']:.2f}→{ct['exit']:.2f} PnL=${ct['pnl']:.2f}"
        elif sym in engine.open_trades and engine.open_trades[sym]['side'] == side:
            action = f"scale-in → avg={engine.open_trades[sym]['avgEntry']:.2f}"
        elif sym not in engine.open_trades and pos_qty is None and net_after == 0:
            action = "IGNORED (flat, no trade open)"
        elif sym not in engine.open_trades:
            action = f"NEW TRADE {side:+d}"
        else:
            action = f"scale-out, remaining={engine.open_trades[sym]['totalQty']}" if sym in engine.open_trades else "CLOSE+REV"
        
        dt_str = datetime.fromtimestamp(ts/1000).strftime('%m/%d %H:%M') if ts > 0 else '?'
        print(f"{i+1:3d} {sym:10s} {side_str:4s} {qty:5d} {price:10.2f} {oc_str:>5s} {pq_str:>7s} {net_after:7.0f} {closed_count:6d} {action}")
    
    print(f"\n{'='*85}")
    print(f"TOTAL TRADES CLOSED: {len(engine.closed_trades)}")
    print(f"OPEN TRADES: {len(engine.open_trades)}")
    
    for sym, t in engine.open_trades.items():
        s_str = 'Buy' if t['side'] == 1 else 'Sell'
        print(f"  STILL OPEN: {sym} {s_str} qty={t['totalQty']} @ avg={t['avgEntry']:.2f}")
    
    # Show all closed trades
    if engine.closed_trades:
        print(f"\nCLOSED TRADES DETAIL:")
        total_pnl = 0
        for i, t in enumerate(engine.closed_trades):
            s_str = 'Buy' if t['side'] == 1 else 'Sell'
            dt_open = datetime.fromtimestamp(t['openTime']/1000).strftime('%m/%d %H:%M')
            dt_close = datetime.fromtimestamp(t['closeTime']/1000).strftime('%m/%d %H:%M')
            print(f"  [{i+1}] {t['symbol']} {s_str} qty={t['qty']} entry={t['entry']:.2f} exit={t['exit']:.2f} PnL=${t['pnl']:.2f} ({dt_open}→{dt_close})")
            total_pnl += t['pnl']
        print(f"\n  TOTAL PnL: ${total_pnl:.2f}")
    
    sock.close()

if __name__ == '__main__':
    main()