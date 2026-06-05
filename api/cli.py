#!/usr/bin/env python3
import json
import sys
import urllib.error
import urllib.request

BASE = "http://localhost:8000"


def req(method: str, path: str) -> dict:
    r = urllib.request.Request(f"{BASE}{path}", method=method)
    try:
        with urllib.request.urlopen(r) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        print(f"Error {e.code}: {e.read().decode()}", file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"No se puede conectar a la API en {BASE}: {e.reason}", file=sys.stderr)
        sys.exit(1)


def print_status(s: dict) -> None:
    icon = "▶" if s["running"] else "■"
    print(f"{icon} running={s['running']}  estado={s['estado']}  total={s['readings_total']}")


def menu() -> None:
    print_status(req("GET", "/serial/status"))
    while True:
        print("\n--- MENU ---")
        print("1 - Base")
        print("2 - Medicion")
        print("3 - Start")
        print("4 - Stop")
        print("5 - Status")
        print("6 - Salir")
        op = input("Selecciona: ").strip()
        if op == "1":
            req("PUT", "/serial/estado/base")
            print("Estado → base")
        elif op == "2":
            req("PUT", "/serial/estado/medicion")
            print("Estado → medicion")
        elif op == "3":
            print(req("POST", "/serial/start"))
        elif op == "4":
            req("POST", "/serial/stop")
            print("Detenido")
        elif op == "5":
            print_status(req("GET", "/serial/status"))
        elif op == "6":
            break


COMMANDS = {
    "base": lambda: req("PUT", "/serial/estado/base"),
    "medicion": lambda: req("PUT", "/serial/estado/medicion"),
    "start": lambda: req("POST", "/serial/start"),
    "stop": lambda: req("POST", "/serial/stop"),
    "status": lambda: print_status(req("GET", "/serial/status")) or {},
}

if __name__ == "__main__":
    if len(sys.argv) == 1:
        menu()
    elif sys.argv[1] in COMMANDS:
        result = COMMANDS[sys.argv[1]]()
        if result:
            print(result)
    else:
        print(f"Uso: {sys.argv[0]} [{'|'.join(COMMANDS)}]")
        sys.exit(1)
