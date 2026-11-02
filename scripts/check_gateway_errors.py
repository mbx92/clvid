"""Check a disposable Caddy container using --network none and infra/Caddyfile.

Usage: python scripts/check_gateway_errors.py <isolated-container-name>
The temporary HTTP client shares that container's isolated network namespace;
the running application and its requests are never interrupted.
"""
import subprocess
import sys

CHECK = r'''
import json
import urllib.error
import urllib.request

for method, path in (("GET", "/api/v1/health/ready"), ("POST", "/api/v1/projects/test/process"), ("GET", "/login")):
    request = urllib.request.Request("http://127.0.0.1:8080"+path, method=method,
                                     data=b"" if method == "POST" else None)
    try:
        urllib.request.urlopen(request, timeout=15)
    except urllib.error.HTTPError as response:
        body = response.read()
        assert response.code == 503, response.code
        assert response.headers["Retry-After"] == "5"
        if path.startswith("/api/"):
            assert response.headers["Content-Type"] == "application/json"
            assert response.headers["Cache-Control"] == "no-store"
            error = json.loads(body)
            assert error["code"] == "SERVICE_UNAVAILABLE"
            assert "status pekerjaan" in error["message"]
        else:
            assert "Aplikasi sementara belum tersedia" in body.decode()
        assert not any(text in body for text in (b"api:8000", b"dial tcp", b"Bad Gateway"))
        print(f"PASS {method} {path}: friendly 503, Retry-After, no internal diagnostics", flush=True)
    else:
        raise AssertionError("An unreachable upstream must not return success")
'''

subprocess.run(["docker", "run", "--rm", "-i", "--network", f"container:{sys.argv[1]}",
                "clipper-backend:local", "python", "-"], input=CHECK, text=True, check=True, timeout=60)
