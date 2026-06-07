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


def do_start(name: str | None = None, n_repetitions: int | None = None) -> dict:
    if name is None:
        name = input("Nombre de la muestra: ").strip()
        if not name:
            print("El nombre no puede estar vacío.", file=sys.stderr)
            sys.exit(1)
    if n_repetitions is None:
        raw = input("Número de repeticiones: ").strip()
        try:
            n_repetitions = int(raw)
        except ValueError:
            print("El número de repeticiones debe ser un entero.", file=sys.stderr)
            sys.exit(1)
    params = urllib.parse.urlencode({"name": name, "n_repetitions": n_repetitions})
    return req("POST", f"/serial/start?{params}")


def menu() -> None:
    print_status(req("GET", "/serial/status"))
    while True:
        print("\n--- MENU ---")
        print("1 - Start")
        print("2 - Stop")
        print("3 - Status")
        print("4 - [test] Base")
        print("5 - [test] Medicion")
        print("6 - [test] Cooldown")
        print("7 - Salir")
        op = input("Selecciona: ").strip()
        if op == "1":
            result = do_start()
            print(f"Iniciado: sample_id={result['sample_id']} nombre='{result['name']}' reps={result['n_repetitions']}")
        elif op == "2":
            req("POST", "/serial/stop")
            print("Detenido")
        elif op == "3":
            print_status(req("GET", "/serial/status"))
        elif op == "4":
            req("PUT", "/serial/estado/base")
            print("Estado → base")
        elif op == "5":
            req("PUT", "/serial/estado/medicion")
            print("Estado → medicion")
        elif op == "6":
            req("PUT", "/serial/estado/cooldown")
            print("Estado → cooldown")
        elif op == "7":
            break


if __name__ == "__main__":
    if len(sys.argv) == 1:
        menu()
        sys.exit(0)

    cmd = sys.argv[1]

    if cmd == "start":
        name = sys.argv[2] if len(sys.argv) > 2 else None
        n_reps = int(sys.argv[3]) if len(sys.argv) > 3 else None
        result = do_start(name, n_reps)
        print(f"Iniciado: sample_id={result['sample_id']} nombre='{result['name']}' reps={result['n_repetitions']}")
    elif cmd == "stop":
        req("POST", "/serial/stop")
        print("Detenido")
    elif cmd == "status":
        print_status(req("GET", "/serial/status"))
    elif cmd in ("base", "medicion", "cooldown"):
        req("PUT", f"/serial/estado/{cmd}")
        print(f"Estado → {cmd}")
    else:
        print(f"Uso: {sys.argv[0]} [start [nombre] [repeticiones] | stop | status | base | medicion | cooldown]")
        sys.exit(1)
