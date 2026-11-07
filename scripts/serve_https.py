#!/usr/bin/env python3
"""Serve a folder over HTTPS using a certificate + private key.

Usage:
  python3 serve_https.py --dir ./site --port 8443 --cert cert.pem --key key.pem
"""
import argparse
import functools
import http.server
import ssl

p = argparse.ArgumentParser(description="Tiny static HTTPS server")
p.add_argument("--dir", default=".", help="folder to serve")
p.add_argument("--port", type=int, default=8443)
p.add_argument("--bind", default="0.0.0.0")
p.add_argument("--cert", required=True, help="certificate (fullchain.pem or cert.pem)")
p.add_argument("--key", required=True, help="private key (privkey.pem or key.pem)")
a = p.parse_args()

handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=a.dir)
httpd = http.server.ThreadingHTTPServer((a.bind, a.port), handler)
ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
ctx.minimum_version = ssl.TLSVersion.TLSv1_2
ctx.load_cert_chain(a.cert, a.key)
httpd.socket = ctx.wrap_socket(httpd.socket, server_side=True)
print(f"Serving {a.dir} on https://{a.bind}:{a.port}  (Ctrl+C to stop)")
try:
    httpd.serve_forever()
except KeyboardInterrupt:
    print("\nStopped.")
