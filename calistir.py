#!/usr/bin/env python3
"""SEO Denetim Aracini baslatir ve tarayicida acar.

Kullanim:
    py calistir.py                 # http://127.0.0.1:5000 adresinde acilir
    py calistir.py --port 5050     # baska bir kapi numarasi
    py calistir.py --acma          # tarayiciyi kendiliginden acma

Gereksinim: pip install -r requirements.txt
"""
import argparse
import sys
import threading
import webbrowser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from seo_app.web import uygulama


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=5000)
    ap.add_argument("--host", default="127.0.0.1", help="varsayilan olarak yalnizca bu bilgisayardan erisilir")
    ap.add_argument("--acma", action="store_true", help="tarayiciyi kendiliginden acma")
    args = ap.parse_args()

    adres = "http://" + ("127.0.0.1" if args.host in ("0.0.0.0", "::") else args.host) + ":" + str(args.port)
    print("SEO Denetim Araci calisiyor:", adres)
    print("Durdurmak icin Ctrl+C")
    if not args.acma:
        threading.Timer(1.0, lambda: webbrowser.open(adres)).start()
    uygulama.run(host=args.host, port=args.port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
