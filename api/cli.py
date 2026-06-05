#!/usr/bin/env python3
import json
import sys
import urllib.error
import urllib.parse
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


def do_start(name: str | None = None) -> dict:
    if name is None:
        name = input("Nombre de la medición: ").strip()
        if not name:
            print("El nombre no puede estar vacío.", file=sys.stderr)
            sys.exit(1)
    return req("POST", f"/serial/start?{urllib.parse.urlencode({'name': name})}")


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
            result = do_start()
            print(f"Iniciado: id={result['measurement_set_id']} nombre='{result['name']}'")
        elif op == "4":
            req("POST", "/serial/stop")
            print("Detenido")
        elif op == "5":
            print_status(req("GET", "/serial/status"))
        elif op == "6":
            break


if __name__ == "__main__":
    if len(sys.argv) == 1:
        menu()
        sys.exit(0)

    cmd = sys.argv[1]

    if cmd == "start":
        name = sys.argv[2] if len(sys.argv) > 2 else None
        result = do_start(name)
        print(f"Iniciado: id={result['measurement_set_id']} nombre='{result['name']}'")
    elif cmd == "stop":
        req("POST", "/serial/stop")
        print("Detenido")
    elif cmd == "base":
        req("PUT", "/serial/estado/base")
        print("Estado → base")
    elif cmd == "medicion":
        req("PUT", "/serial/estado/medicion")
        print("Estado → medicion")
    elif cmd == "status":
        print_status(req("GET", "/serial/status"))
    else:
        print(f"Uso: {sys.argv[0]} [start [nombre] | stop | base | medicion | status]")
        sys.exit(1)
