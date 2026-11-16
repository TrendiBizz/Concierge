import socket, uuid
host = "152.42.239.240"
msg = ("OPTIONS sip:probe@%s SIP/2.0\r\nVia: SIP/2.0/UDP 0.0.0.0:5099;branch=z9hG4bK%s\r\nMax-Forwards: 70\r\n"
       "From: <sip:probe@example.invalid>;tag=%s\r\nTo: <sip:probe@%s>\r\nCall-ID: %s@probe\r\nCSeq: 1 OPTIONS\r\nContent-Length: 0\r\n\r\n"
       % (host, uuid.uuid4().hex[:8], uuid.uuid4().hex[:6], host, uuid.uuid4().hex))
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.settimeout(4)
s.sendto(msg.encode(), (host, 5060))
try:
    data, _ = s.recvfrom(2048); print("ANSWERED (SIP port is OPEN to the internet):", data[:60])
except socket.timeout:
    print("no answer (dropped)")
