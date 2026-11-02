import ipaddress
import socket
import sys
from urllib.parse import urlsplit, urlunsplit
from .process import MediaError


def public_address(address):
    try:
        ip = ipaddress.ip_address(address)
        if isinstance(ip, ipaddress.IPv6Address) and (ip.ipv4_mapped or ip.sixtofour or ip.teredo
                or ip in ipaddress.ip_network("64:ff9b::/96") or ip in ipaddress.ip_network("64:ff9b:1::/48")):
            return False
        return ip.is_global and not (ip.is_multicast or ip.is_reserved or ip.is_unspecified)
    except ValueError:
        return False


def validate_url(url):
    try:
        if any(ord(c) < 33 for c in url) or "\\" in url:
            raise ValueError()
        parsed = urlsplit(url)
        host = (parsed.hostname or "").rstrip(".").lower()
        if (parsed.scheme not in ("http", "https") or not host or parsed.username is not None or parsed.password is not None
                or parsed.port not in (None, 80, 443) or host == "localhost"
                or host.endswith((".localhost", ".internal", ".local")) or "." not in host and ":" not in host):
            raise ValueError()
        try:
            ipaddress.ip_address(host)
        except ValueError:
            pass
        else:
            if not public_address(host):
                raise ValueError()
        return urlunsplit(parsed._replace(fragment=""))
    except (ValueError, TypeError):
        raise MediaError("invalid_url", "Gunakan URL HTTP/HTTPS publik tanpa kredensial atau port khusus.") from None


def install_network_guard():
    original = socket.getaddrinfo
    def guarded(host, port, *args, **kwargs):
        if port not in (80, 443, "80", "443", "http", "https"):
            raise PermissionError("Port jaringan dibatasi.")
        records = original(host, port, *args, **kwargs)
        if not records or any(not public_address(row[4][0]) for row in records):
            raise PermissionError("Alamat jaringan privat diblokir.")
        return records
    socket.getaddrinfo = guarded
    def audit(event, args):
        if event in ("socket.connect", "socket.sendto"):
            address = args[1] if event == "socket.connect" else args[2]
            if not isinstance(address, tuple) or len(address) < 2:
                raise PermissionError("Hanya jaringan HTTP publik diperbolehkan.")
            host, port = address[:2]
            if port not in (80, 443):
                raise PermissionError("Port jaringan dibatasi.")
            try:
                ipaddress.ip_address(host)
            except ValueError:
                # Do not allow a second OS-level resolution after validation.
                # urllib/yt-dlp use getaddrinfo then connect to literal IPs.
                raise PermissionError("Koneksi harus memakai alamat IP yang telah diperiksa.")
            if not public_address(host):
                raise PermissionError("Alamat jaringan privat diblokir.")
    sys.addaudithook(audit)
