#!/usr/bin/env python3
"""Connect to Sierra Chart DTC, fetch fills for Sim1, and trace what the app should see."""
import socket, json, time, struct, os, base64, hashlib

def ws_handshake(sock, host, port):
    """Perform WebSocket handshake manually."""
    key = base64.b64encode(os.urandom(16)).decode()
    req = (
        f"GET / HTTP/1.1\r\n"
        f"Host: {host}:{port}\r\n"
        "Upgrade: websocket\r\n"
        "Connection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {key}\r\n"
        "Sec-WebSocket-Version: 13\r\n\r\n"
    )
    sock.sendall(req.encode())
    resp = b''
    while b'\r\n\r\n' not in resp:
        resp += sock.recv(4096)
    if b'101' not in resp:
        raise Exception("WebSocket handshake failed")

def ws_send(sock, data):
    """Send a text WebSocket frame."""
    payload = json.dumps(data, separators=(',', ':')).encode()
    mask = os.urandom(4)
    masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
    header = b'\x81'  # FIN + text opcode
    length = len(payload)
    if length < 126:
        header += bytes([0x80 | length])
    elif length < 65536:
        header += bytes([0x80 | 126]) + struct.pack('>H', length)
    else:
        header += bytes([0x80 | 127]) + struct.pack('>Q', length)
    sock.sendall(header + mask + masked)

def ws_recv(sock, timeout=10):
    """Receive WebSocket frames and return parsed JSON messages."""
    sock.settimeout(timeout)
    messages = []
    buf = b''
    
    while True:
        try:
            chunk = sock.recv(65536)
            if not chunk:
                break
            buf += chunk
        except socket.timeout:
            break
        except:
            break
        
        while len(buf) >= 2:
            # Parse frame header
            opcode = buf[0] & 0x0F
            masked = bool(buf[1] & 0x80)
            length = buf[1] & 0x7F
            offset = 2
            
            if length == 126:
                if len(buf) < offset + 2:
                    break
                length = struct.unpack('>H', buf[offset:offset+2])[0]
                offset += 2
            elif length == 127:
                if len(buf) < offset + 8:
                    break
                length = struct.unpack('>Q', buf[offset:offset+8])[0]
                offset += 8
            
            if masked:
                if len(buf) < offset + 4:
                    break
                mask = buf[offset:offset+4]
                offset += 4
            
            if len(buf) < offset + length:
                break
            
            payload = buf[offset:offset+length]
            if masked:
                payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
            
            buf = buf[offset+length:]
            
            if opcode == 1:  # Text frame
                text = payload.decode('utf-8', errors='replace')
                for part in text.split('\x00'):
                    part = part.strip()
                    if part:
                        try:
                            messages.append(json.loads(part))
                        except json.JSONDecodeError:
                            pass
            elif opcode == 8:  # Close
                return messages
            elif opcode == 9:  # Ping
                ws_send(sock, {"Type": 3})  # Pong as heartbeat
    
    return messages

def main():
    host = '127.0.0.1'
    port = 11099
    
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(10)
    sock.connect((host, port))
    
    ws_handshake(sock, host, port)
    print("WebSocket connected")
    
    # LOGON
    ws_send(sock, {
        "Type": 1,
        "ProtocolVersion": 8,
        "Username": "",
        "Password": "",
        "TradeAccount": "Sim1",
        "Hostname": "debug",
        "ClientName": "debug"
    })
    
    time.sleep(1)
    msgs = ws_recv(sock, timeout=5)
    logon = [m for m in msgs if m.get('Type') == 2]
    
    if not logon:
        print("No LOGON_RESPONSE received!")
        sock.close()
        return
    
    result = logon[0].get('Result', -1)
    print(f"LOGON: Result={result}")
    if result != 1:
        print(f"LOGON FAILED: {logon[0]}")
        sock.close()
        return
    
    # Request fills for Sim1 - last 7 days
    now_sec = int(time.time())
    ws_send(sock, {"Type": 303, "TradeAccount": "Sim1", "StartDateTime": now_sec - 7 * 86400})
    
    # Wait for fills
    all_fills = []
    no_fills = False
    start = time.time()
    while time.time() - start < 15:
        new_msgs = ws_recv(sock, timeout=5)
        for m in new_msgs:
            if m.get('Type') == 304:
                if m.get('NoOrderFills'):
                    no_fills = True
                    print("Server says: NoOrderFills")
                else:
                    all_fills.append(m)
            elif m.get('Type') == 3:
                pass  # heartbeat
        if no_fills:
            break
        if all_fills and time.time() - start > 5:
            # Got some fills, wait a bit more for remaining
            continue
    
    print(f"\nTotal fills: {len(all_fills)}")
    
    from datetime import datetime
    
    # Group fills by day
    by_day = {}
    for f in all_fills:
        dt = f.get('DateTime', 0)
        try:
            ts = float(dt)
            if ts > 1e12:
                ts = ts / 1000
            day = datetime.fromtimestamp(ts).strftime('%Y-%m-%d')
        except:
            day = 'unknown'
        by_day.setdefault(day, []).append(f)
    
    # Sort fills by DateTime
    all_fills.sort(key=lambda f: float(f.get('DateTime', 0)))
    
    # Today's fills detailed
    today = datetime.now().strftime('%Y-%m-%d')
    today_fills = [f for f in all_fills if day == today for day in [None]]
    
    print(f"\nFills by day:")
    for day in sorted(by_day.keys()):
        count = len(by_day[day])
        # Check OpenClose distribution
        opens = sum(1 for f in by_day[day] if f.get('OpenClose') == 1)
        closes = sum(1 for f in by_day[day] if f.get('OpenClose') == 2)
        has_pq = sum(1 for f in by_day[day] if 'PositionQuantity' in f and f['PositionQuantity'] is not None)
        print(f"  {day}: {count} fills (Open={opens}, Close={closes}, hasPosQty={has_pq})")
    
    # Today's fills with full detail
    today_key = datetime.now().strftime('%Y-%m-%d')
    today_fills = by_day.get(today_key, [])
    
    if today_fills:
        print(f"\n=== TODAY'S FILLS ({today_key}) ===")
        for i, f in enumerate(today_fills):
            bs = f.get('BuySell', '?')
            qty = f.get('Quantity', 0)
            price = f.get('Price', 0)
            oc = f.get('OpenClose', '?')
            pq = f.get('PositionQuantity', 'NONE')
            dt = f.get('DateTime', 0)
            eid = f.get('UniqueExecutionID', 'NONE')
            sym = f.get('Symbol', '?')
            comm = f.get('Commission', 'NONE')
            
            side = 'Buy' if bs == 1 else 'Sell' if bs == 2 else f'BS={bs}'
            oc_str = 'OPEN' if oc == 1 else 'CLOSE' if oc == 2 else f'OC={oc}'
            
            try:
                ts = float(dt)
                if ts > 1e12:
                    ts = ts / 1000
                dt_str = datetime.fromtimestamp(ts).strftime('%H:%M:%S')
            except:
                dt_str = str(dt)
            
            norm_price = price / 100 if isinstance(price, (int, float)) and price > 10000 else price
            pq_display = pq if pq != 'NONE' else '---'
            
            print(f"  [{i+1:2d}] {sym:10s} {side:4s} qty={qty:>4} @ {norm_price:>10.2f}  {oc_str:6s}  posAfter={str(pq_display):>6s}  {dt_str}  comm={comm}")
    else:
        print(f"\nNo fills found for today ({today_key})")
        # Show most recent fills instead
        if all_fills:
            recent = sorted(all_fills, key=lambda f: float(f.get('DateTime', 0)), reverse=True)[:10]
            print(f"\nMost recent 10 fills:")
            for i, f in enumerate(recent):
                bs = f.get('BuySell', '?')
                qty = f.get('Quantity', 0)
                price = f.get('Price', 0)
                oc = f.get('OpenClose', '?')
                pq = f.get('PositionQuantity', 'NONE')
                dt = f.get('DateTime', 0)
                sym = f.get('Symbol', '?')
                side = 'Buy' if bs == 1 else 'Sell' if bs == 2 else f'BS={bs}'
                oc_str = 'OPEN' if oc == 1 else 'CLOSE' if oc == 2 else f'OC={oc}'
                try:
                    ts = float(dt)
                    if ts > 1e12:
                        ts = ts / 1000
                    dt_str = datetime.fromtimestamp(ts).strftime('%m/%d %H:%M:%S')
                except:
                    dt_str = str(dt)
                norm_price = price / 100 if isinstance(price, (int, float)) and price > 10000 else price
                pq_display = pq if pq != 'NONE' else '---'
                print(f"  [{i+1:2d}] {sym:10s} {side:4s} qty={qty:>4} @ {norm_price:>10.2f}  {oc_str:6s}  posAfter={str(pq_display):>6s}  {dt_str}")
    
    sock.close()

if __name__ == '__main__':
    main()