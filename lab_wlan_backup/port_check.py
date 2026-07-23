# -*- coding: utf-8 -*-
"""Definitive check: are eNSP console ports 2000-2008 open on 127.0.0.1?"""
import socket
for p in range(2000, 2009):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(2)
    try:
        s.connect(('127.0.0.1', p))
        print(f"port {p}: OPEN")
    except (ConnectionRefusedError, OSError) as e:
        print(f"port {p}: CLOSED ({e})")
    finally:
        s.close()
