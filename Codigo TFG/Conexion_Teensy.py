import serial
import serial.tools.list_ports
import time

# Variable global para mantener una sola conexión
_ser_teensy = None
_PORT = "COM4"  # Cambia según el caso

# ======================= Conexión =======================

def conectar_teensy(baud=115200, timeout=0.2):
    """
    Establece o reutiliza la conexión única con el Teensy.
    Retorna el objeto serial si está disponible.
    """
    global _ser_teensy

    # Si ya hay conexión abierta, reutilizar
    if _ser_teensy and _ser_teensy.is_open:
        #print("[Teensy] Conexión existente reutilizada.")
        return _ser_teensy

    # Buscar y abrir puerto
    try:
        _ser_teensy = serial.Serial(_PORT, baudrate=baud, timeout=timeout)
        time.sleep(0.5)
        #print(f"[Teensy] Conectado en {_PORT}")
        return _ser_teensy
    except serial.SerialException as e:
        #print(f"[Teensy] Error al conectar: {e}")
        _ser_teensy = None
        return None


# ======================= Configuración =======================

def configurar_teensy(ser, resorte, tipo):
    """
    Envía configuración inicial (resorte y modo).
    """
    if ser is None:
        #print("[Teensy] No hay conexión activa.")
        return

    try:
        resorte = str(resorte).strip()
        tipo = tipo.strip().upper()
        if not resorte.isdigit():
            print("[Teensy] Valor de resorte inválido.")
            return
        if tipo not in ("E", "F"):
            print("[Teensy] Tipo inválido (usar 'E' o 'F').")
            return

        ser.flushInput()
        ser.flushOutput()
        time.sleep(0.1)
        ser.write(f"{resorte}\n".encode("utf-8"))
        time.sleep(0.1)
        ser.write(f"{tipo}\n".encode("utf-8"))
        time.sleep(0.1)

        print(f"[Teensy] Configurado → Resorte {resorte}, Tipo {tipo}")

    except Exception as e:
        print(f"[Teensy] Error al configurar: {e}")


# ======================= Lectura =======================

def leer_teensy_linea(ser):
    """
    Lee una línea del Teensy y devuelve (angulo, fuerza) o None.
    """
    if ser is None:
        return None
    try:
        line = ser.readline().decode("utf-8").strip()
        if not line:
            return None
        parts = line.split(",")
        if len(parts) >= 2:
            ang = float(parts[0])
            fuerza = float(parts[1])
            return ang, fuerza
    except Exception:
        pass
    return None


# ======================= Cierre =======================

def cerrar_teensy():
    """
    Cierra la conexión si está abierta.
    """
    global _ser_teensy
    if _ser_teensy and _ser_teensy.is_open:
        try:
            _ser_teensy.close()
            print("[Teensy] Conexión cerrada correctamente.")
        except Exception as e:
            print(f"[Teensy] Error al cerrar: {e}")
    _ser_teensy = None


# ======================= Prueba directa =======================

if __name__ == "__main__":
    ser = conectar_teensy()
    if ser:
        configurar_teensy(ser, 1, "F")
        try:
            while True:
                data = leer_teensy_linea(ser)
                if data:
                    print(f"Ángulo: {data[0]:.2f}, Fuerza: {data[1]:.2f}")
                time.sleep(0.1)
        except KeyboardInterrupt:
            cerrar_teensy()
