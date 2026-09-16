"""
gestureRecognition.py — SIANNA
================================
Captura video, detecta la mano con MediaPipe (handDetector), envía el estado
de los 5 dedos al ESP32 por puerto serial, y reporta métricas en vivo al
panel web (webapp/app.py) a través de metrics_client.py:

    - Estado de dedos y gesto reconocido en cada frame (para la vista "En vivo")
    - Latencia de procesamiento y FPS (para "Tiempos de respuesta")
    - Repeticiones por gesto, contadas por transición estable (para "Repeticiones")
    - Pruebas de precisión guiadas gesto por gesto (para "Precisión"),
      activables con la tecla 't' mientras corre el script.

Controles durante la ejecución (con la ventana de video en foco):
    q   -> salir
    t   -> iniciar una prueba de precisión guiada
    (durante una prueba) n -> saltar la repetición actual   |   ESC -> cancelar la prueba

Antes de ejecutar:
    1) Deja corriendo el panel web:  cd ../WebApp && python app.py
    2) Ajusta SERIAL_PORT abajo al puerto COM de tu ESP32.
    3) pip install -r requeriments.txt  (y additionally: pip install requests)
"""

import random
import time
from collections import deque

import cv2
import numpy as np
import serial  # pip install pyserial

import handDetector as hand
from metrics_client import MetricsClient

# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------
SERIAL_PORT = "COM3"
BAUD_RATE = 9600
CAMERA_INDEX = 0
SIANNA_API_URL = "http://127.0.0.1:5050"

STABILIZE_WINDOW = 5        # nº de frames recientes usados para votar el gesto estable
STABILIZE_THRESHOLD = 3     # mayoría mínima para considerar el gesto estable (ceil(N/2)+1)
EVENT_LOG_EVERY_N_FRAMES = 3  # para no saturar la base de datos, se registra 1 de cada N frames
                               # (las transiciones de gesto SIEMPRE se registran, sin importar esto)

ACCURACY_TEST_REPS_PER_GESTURE = 5
ACCURACY_TEST_TIMEOUT_S = 5.0

# Mapeo estado-de-dedos -> nombre de gesto. fingers = [pulgar, indice, medio, anular, meñique]
# 1 = extendido/abierto, 0 = flexionado/cerrado. Ajusta o agrega combinaciones según necesites.
GESTURES = {
    (1, 1, 1, 1, 1): "mano_abierta",
    (0, 0, 0, 0, 0): "puno_cerrado",
    (0, 1, 0, 0, 0): "senalar",
    (1, 0, 0, 0, 0): "pulgar_arriba",
    (0, 1, 1, 0, 0): "paz",
    (0, 1, 0, 0, 1): "rock",
}
UNKNOWN_GESTURE = "gesto_no_reconocido"
FINGERS_BY_GESTURE = {name: fingers for fingers, name in GESTURES.items()}


def frame_brightness(img):
    """Brillo promedio del frame (escala de grises, 0-255). El panel web lo
    agrupa en Baja/Media/Alta para relacionar precisión con condición de luz."""
    return float(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).mean())


def classify_gesture(fingers):
    return GESTURES.get(tuple(fingers), UNKNOWN_GESTURE)


def stable_vote(buffer):
    """Devuelve (gesto_mas_frecuente, cuenta) sobre el buffer de predicciones recientes."""
    if not buffer:
        return None, 0
    counts = {}
    for g in buffer:
        counts[g] = counts.get(g, 0) + 1
    best_gesture = max(counts, key=counts.get)
    return best_gesture, counts[best_gesture]


def connect_serial():
    try:
        conn = serial.Serial(SERIAL_PORT, BAUD_RATE)
        time.sleep(2)  # dar tiempo al ESP32 para reiniciar tras abrir el puerto
        print(f"[gestureRecognition] Conectado al ESP32 en {SERIAL_PORT}.")
        return conn
    except Exception as exc:  # noqa: BLE001 - queremos seguir sin hardware si falla
        print(
            f"[gestureRecognition] No se pudo abrir el puerto serial {SERIAL_PORT} ({exc}). "
            "El script seguirá corriendo sin enviar comandos al ESP32."
        )
        return None


def draw_overlay(img, lines):
    y = 30
    for line in lines:
        cv2.putText(img, line, (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 0, 0), 4, cv2.LINE_AA)
        cv2.putText(img, line, (10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 255), 1, cv2.LINE_AA)
        y += 26


def run_accuracy_test(cap, detector, serial_conn, metrics):
    """Prueba de precisión guiada: pide gestos en orden aleatorio y mide si el
    sistema los reconoce correctamente y en cuánto tiempo (respuesta)."""
    test_gestures = list(GESTURES.values())
    plan = test_gestures * ACCURACY_TEST_REPS_PER_GESTURE
    random.shuffle(plan)

    print(f"[gestureRecognition] Iniciando prueba de precisión: {len(plan)} repeticiones.")
    metrics.set_test_status(True, prompt="Preparando prueba...")

    results = {"correctas": 0, "incorrectas": 0, "timeouts": 0}
    aborted = False

    for idx, expected in enumerate(plan, start=1):
        buffer = deque(maxlen=STABILIZE_WINDOW)
        start_time = time.time()
        stable_gesture = None
        timed_out = False

        metrics.set_test_status(True, prompt=f"Haz: {expected}  ({idx}/{len(plan)})")

        while True:
            elapsed = time.time() - start_time
            ret, img = cap.read()
            if not ret:
                continue

            img = detector.findHands(img)
            lmList, _ = detector.findPosition(img)
            raw_gesture = None
            if len(lmList) != 0:
                fingers = detector.fingersUp()
                raw_gesture = classify_gesture(fingers)
                buffer.append(raw_gesture)

            candidate, votes = stable_vote(buffer)
            if candidate is not None and votes >= STABILIZE_THRESHOLD:
                stable_gesture = candidate

            remaining = max(0.0, ACCURACY_TEST_TIMEOUT_S - elapsed)
            draw_overlay(img, [
                f"PRUEBA DE PRECISION  ({idx}/{len(plan)})",
                f"Haz el gesto: {expected}",
                f"Tiempo restante: {remaining:0.1f}s   [n] saltar  [ESC] cancelar",
            ])
            cv2.imshow("Image", img)
            key = cv2.waitKey(1) & 0xFF

            if stable_gesture is not None:
                break
            if elapsed >= ACCURACY_TEST_TIMEOUT_S:
                timed_out = True
                break
            if key == 27:  # ESC
                aborted = True
                break
            if key == ord("n"):
                timed_out = True
                break

        response_time_ms = (time.time() - start_time) * 1000.0
        correct = (stable_gesture == expected) and not timed_out
        brightness = frame_brightness(img)
        expected_fingers = list(FINGERS_BY_GESTURE[expected])
        detected_fingers = (
            list(FINGERS_BY_GESTURE[stable_gesture])
            if stable_gesture in FINGERS_BY_GESTURE
            else None
        )

        if aborted:
            print("[gestureRecognition] Prueba de precisión cancelada por el usuario.")
            break

        metrics.log_accuracy_test(
            expected_gesture=expected,
            detected_gesture=stable_gesture,
            correct=correct,
            response_time_ms=None if timed_out and stable_gesture is None else response_time_ms,
            timed_out=timed_out,
            brightness=brightness,
            expected_fingers=expected_fingers,
            detected_fingers=detected_fingers,
        )

        if correct:
            results["correctas"] += 1
            feedback, color = "Correcto", (0, 200, 0)
        elif timed_out:
            results["timeouts"] += 1
            feedback, color = "Tiempo agotado", (0, 165, 255)
        else:
            results["incorrectas"] += 1
            feedback, color = f"Detectado: {stable_gesture}", (0, 0, 255)

        ret, img = cap.read()
        if ret:
            draw_overlay(img, [f"Esperado: {expected}", feedback])
            cv2.imshow("Image", img)
        cv2.waitKey(600)

    metrics.set_test_status(False)
    total = sum(results.values())
    print(
        f"[gestureRecognition] Prueba finalizada: {results['correctas']}/{total} correctas, "
        f"{results['incorrectas']} incorrectas, {results['timeouts']} con tiempo agotado."
    )


def main():
    metrics = MetricsClient(base_url=SIANNA_API_URL)
    metrics.start_session(notes="Sesión desde gestureRecognition.py")

    cap = cv2.VideoCapture(CAMERA_INDEX)
    detector = hand.handDetector()
    serial_conn = connect_serial()

    stable_buffer = deque(maxlen=STABILIZE_WINDOW)
    last_stable_gesture = None
    p_time = 0.0
    frame_counter = 0
    last_sent_fingers = None
    pending_ack_since = None  # timestamp del último comando serial aún sin ACK del ESP32

    print("[gestureRecognition] Controles: [q] salir   [t] iniciar prueba de precision")

    try:
        while True:
            frame_start = time.time()
            ret, img = cap.read()
            if not ret:
                continue
            t_captura = time.time()

            img = detector.findHands(img)
            lmList, bbox = detector.findPosition(img)
            t_mediapipe = time.time()

            hand_detected = len(lmList) != 0
            gesture_name = None
            fingers = None

            if hand_detected:
                fingers = detector.fingersUp()
                gesture_name = classify_gesture(fingers)
                stable_buffer.append(gesture_name)
            t_inferencia = time.time()

            serial_ms = None
            servo_ms = None
            servo_angles = None
            if serial_conn is not None:
                # ¿Llegó la confirmación (ACK) del último comando enviado al ESP32?
                # Se revisa sin bloquear para no frenar la captura de video.
                if pending_ack_since is not None and serial_conn.in_waiting > 0:
                    ack_line = serial_conn.readline().decode(errors="ignore").strip()
                    servo_ms = (time.time() - pending_ack_since) * 1000.0
                    pending_ack_since = None
                    # El ESP32 devuelve "ACK,<pulgar>,<indice>,<medio>,<anular>,<meñique>"
                    # con el ángulo (0-180) que acaba de aplicar a cada servo, según su
                    # calibración de apertura/cierre. No es un sensor de posición: es el
                    # ángulo objetivo, no el que el servo llegó a alcanzar realmente.
                    if ack_line.startswith("ACK,"):
                        try:
                            servo_angles = [int(v) for v in ack_line.split(",")[1:6]]
                        except ValueError:
                            servo_angles = None

                # Solo se reenvía cuando el estado de los dedos cambia: evita saturar
                # el puerto serial y permite emparejar cada envío con su propio ACK.
                if hand_detected and fingers != last_sent_fingers:
                    t_serial0 = time.time()
                    serial_conn.write(
                        (
                            f"{fingers[0]},{fingers[1]},{fingers[2]},{fingers[3]},{fingers[4]}\n"
                        ).encode()
                    )
                    serial_ms = (time.time() - t_serial0) * 1000.0
                    pending_ack_since = time.time()
                    last_sent_fingers = list(fingers)

            c_time = time.time()
            fps = 1.0 / (c_time - p_time) if p_time else 0.0
            p_time = c_time
            latency_ms = (c_time - frame_start) * 1000.0
            captura_ms = (t_captura - frame_start) * 1000.0
            mediapipe_ms = (t_mediapipe - t_captura) * 1000.0
            inferencia_ms = (t_inferencia - t_mediapipe) * 1000.0

            candidate, votes = stable_vote(stable_buffer) if hand_detected else (None, 0)
            stable_gesture = candidate if votes >= STABILIZE_THRESHOLD else last_stable_gesture
            is_transition = hand_detected and stable_gesture is not None and stable_gesture != last_stable_gesture
            if is_transition:
                last_stable_gesture = stable_gesture

            frame_counter += 1
            should_log = is_transition or (frame_counter % EVENT_LOG_EVERY_N_FRAMES == 0)
            if should_log:
                metrics.log_event(
                    gesture_name=gesture_name or UNKNOWN_GESTURE if hand_detected else "sin_mano",
                    fingers=fingers or [],
                    latency_ms=latency_ms,
                    fps=fps,
                    hand_detected=hand_detected,
                    is_transition=is_transition,
                    captura_ms=captura_ms,
                    mediapipe_ms=mediapipe_ms,
                    inferencia_ms=inferencia_ms,
                    serial_ms=serial_ms,
                    servo_ms=servo_ms,
                    servo_angles=servo_angles,
                )

            draw_overlay(img, [
                f"Gesto: {gesture_name or '-'}" if hand_detected else "Mano no detectada",
                f"FPS: {fps:0.1f}   Latencia: {latency_ms:0.1f} ms",
                "[q] salir   [t] prueba de precision",
            ])
            cv2.imshow("Image", img)

            key = cv2.waitKey(10) & 0xFF
            if key == ord("q"):
                break
            if key == ord("t"):
                run_accuracy_test(cap, detector, serial_conn, metrics)
                p_time = time.time()
    finally:
        metrics.end_session()
        metrics.close()
        if serial_conn is not None:
            serial_conn.close()
        cap.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
