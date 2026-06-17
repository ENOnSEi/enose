import threading

import serial

estado = "inicio"
running = True


def menu():
    global estado, running

    while running:
        print("\n--- MENU ---")
        print("1 - Base")
        print("2 - Medicion")
        print("3 - Salir")

        op = input("Selecciona: ")

        if op == "1":
            estado = "base"
        elif op == "2":
            estado = "medicion"
        elif op == "3":
            running = False
            break


def main():
    global running

    ser = serial.Serial("/dev/ttyACM0", 9600, timeout=1)

    with open("data1.csv", "w") as f:
        # cabecera CSV
        f.write("data,v20,v11,v02,v00,estado\n")

        while running:
            line = ser.readline().decode(errors="ignore").strip()

            if not line:
                continue

            # añade estado al CSV
            line_csv = f"{line},{estado}"

            print(line_csv)
            f.write(line_csv + "\n")
            f.flush()

    ser.close()


if __name__ == "__main__":
    t = threading.Thread(target=menu, daemon=True)
    t.start()

    main()
