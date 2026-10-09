"""Local relay that lets the bundled rclone reach the internet on Android.

rclone is a plain Linux binary there. Android has no /etc/resolv.conf, so rclone's own DNS
lookups fail. rclone honours HTTPS_PROXY/HTTP_PROXY, so it hands every connection to this
relay instead, and Python resolves the host name through Android's normal resolver.
Only clients that know the random password (i.e. our rclone) may use it.
"""
import base64
import secrets
import socket
import threading

MAX_HEAD = 64 * 1024


def start():
    """Start the relay on a random loopback port; returns the proxy URL to put in HTTPS_PROXY."""
    password = secrets.token_urlsafe(24)
    expected = "Basic " + base64.b64encode(f"rclone:{password}".encode()).decode()
    listener = socket.create_server(("127.0.0.1", 0))
    threading.Thread(target=_accept_loop, args=(listener, expected), name="netproxy", daemon=True).start()
    return f"http://rclone:{password}@127.0.0.1:{listener.getsockname()[1]}"


def _accept_loop(listener, expected):
    while True:
        client, _ = listener.accept()
        threading.Thread(target=_handle, args=(client, expected), daemon=True).start()


def _read_head(sock):
    data = b""
    while b"\r\n\r\n" not in data:
        chunk = sock.recv(16384)
        if not chunk or len(data) > MAX_HEAD:
            return None, b""
        data += chunk
    head, _, rest = data.partition(b"\r\n\r\n")
    return head.decode("latin-1").split("\r\n"), rest


def _handle(client, expected):
    upstream = None
    try:
        lines, rest = _read_head(client)
        if not lines:
            return
        method, target, version = lines[0].split(" ", 2)
        headers = [line for line in lines[1:] if line]
        auth = next((line.split(":", 1)[1].strip() for line in headers if line.lower().startswith("proxy-authorization:")), "")
        if not secrets.compare_digest(auth, expected):
            client.sendall(b"HTTP/1.1 407 Proxy Authentication Required\r\nProxy-Authenticate: Basic\r\nContent-Length: 0\r\n\r\n")
            return
        if method.upper() == "CONNECT":  # HTTPS: blind TLS tunnel
            host, _, port = target.rpartition(":")
            upstream = socket.create_connection((host.strip("[]"), int(port)), timeout=30)
            upstream.settimeout(None)
            client.sendall(b"HTTP/1.1 200 Connection established\r\n\r\n")
            if rest:
                upstream.sendall(rest)
            _pipe(client, upstream)
            return
        # Plain HTTP (e.g. MEGA's transfer servers): one request per connection.
        if not target.startswith("http://"):
            client.sendall(b"HTTP/1.1 400 Bad Request\r\nContent-Length: 0\r\n\r\n")
            return
        authority, _, path = target[len("http://"):].partition("/")
        host, _, port = authority.rpartition(":") if authority.rsplit(":", 1)[-1].isdigit() else (authority, "", "80")
        keep = [h for h in headers if h.split(":", 1)[0].strip().lower() not in ("proxy-authorization", "proxy-connection", "connection")]
        request = "\r\n".join([f"{method} /{path} {version}", *keep, "Connection: close", "", ""]).encode("latin-1")
        upstream = socket.create_connection((host.strip("[]"), int(port)), timeout=30)
        upstream.settimeout(None)
        upstream.sendall(request + rest)
        relay = threading.Thread(target=_forward, args=(client, upstream), daemon=True)
        relay.start()  # request body, if any
        response, body = _read_head(upstream)
        if not response:
            return
        response = [response[0], *[h for h in response[1:] if h.split(":", 1)[0].strip().lower() != "connection"], "Connection: close"]
        client.sendall(("\r\n".join(response) + "\r\n\r\n").encode("latin-1") + body)
        _forward(upstream, client)
    except (OSError, ValueError):
        try:
            client.sendall(b"HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
        except OSError:
            pass
    finally:
        for sock in (client, upstream):
            if sock is not None:
                try:
                    sock.close()
                except OSError:
                    pass


def _forward(source, destination):
    try:
        while True:
            data = source.recv(65536)
            if not data:
                break
            destination.sendall(data)
    except OSError:
        pass
    finally:
        try:
            destination.shutdown(socket.SHUT_WR)
        except OSError:
            pass


def _pipe(a, b):
    other = threading.Thread(target=_forward, args=(b, a), daemon=True)
    other.start()
    _forward(a, b)
    other.join()
