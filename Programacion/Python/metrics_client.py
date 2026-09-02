"""
metrics_client.py
==================
Cliente ligero que usa gestureRecognition.py para enviar datos al panel web
de SIANNA (servidor Flask en http://127.0.0.1:5050 por defecto).

Diseñado para no interrumpir jamás el bucle principal de captura de video:
  - Si el servidor web no está corriendo, los métodos simplemente no hacen
    nada (no lanzan excepciones).
  - Los eventos se envían en un hilo aparte con una cola, para no bloquear
    la cámara ni el envío serial al ESP32 esperando la respuesta HTTP.

Uso típico dentro de gestureRecognition.py:

    from metrics_client import MetricsClient

    metrics = MetricsClient()
    metrics.start_session(notes="Prueba con iluminación de laboratorio")
    ...
    metrics.log_event(gesture_name, fingers, latency_ms, fps, hand_detected, is_transition)
    ...
    metrics.log_accuracy_test(expected, detected, correct, response_time_ms, timed_out)
    ...
    metrics.end_session()
"""

import queue
import threading

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None
    print(
        "[metrics_client] Advertencia: falta el paquete 'requests'. "
        "Instala con: pip install requests"
    )


class MetricsClient:
    def __init__(self, base_url="http://127.0.0.1:5050", enabled=True, timeout=1.5):
        self.base_url = base_url.rstrip("/")
        self.enabled = enabled and requests is not None
        self.timeout = timeout
        self.session_id = None

        self._queue = queue.Queue()
        self._stop = False
        if self.enabled:
            self._thread = threading.Thread(target=self._worker, daemon=True)
            self._thread.start()

    # -- infraestructura interna -------------------------------------------------

    def _worker(self):
        while not self._stop:
            try:
                path, payload = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue
            self._post(path, payload)

    def _post(self, path, payload, timeout=None):
        if not self.enabled:
            return None
        try:
            r = requests.post(
                f"{self.base_url}{path}", json=payload, timeout=timeout or self.timeout
            )
            return r
        except requests.exceptions.RequestException:
            # El panel web no está corriendo o no responde: seguimos sin él.
            return None

    def is_server_reachable(self):
        if not self.enabled:
            return False
        try:
            r = requests.get(f"{self.base_url}/api/health", timeout=1.0)
            return r.ok
        except requests.exceptions.RequestException:
            return False

    # -- sesiones -----------------------------------------------------------------

    def start_session(self, notes=""):
        """Crea una sesión nueva en la base de datos. Se hace de forma síncrona
        (una sola vez, al inicio del script) porque necesitamos el session_id
        antes de poder registrar cualquier evento."""
        if not self.enabled:
            return None
        r = self._post("/api/sessions", {"notes": notes}, timeout=3.0)
        if r is not None and r.ok:
            self.session_id = r.json().get("id")
            print(f"[metrics_client] Sesión #{self.session_id} iniciada en el panel web.")
        else:
            print(
                "[metrics_client] No se pudo conectar con el panel web "
                f"({self.base_url}). ¿Está corriendo 'python app.py'? "
                "El script seguirá funcionando sin registrar métricas."
            )
        return self.session_id

    def end_session(self):
        if not self.enabled or not self.session_id:
            return
        self._post(f"/api/sessions/{self.session_id}/end", {}, timeout=2.0)

    # -- eventos (cada frame / cada gesto estable) --------------------------------

    def log_event(
        self,
        gesture_name,
        fingers,
        latency_ms=None,
        fps=None,
        hand_detected=True,
        is_transition=False,
        captura_ms=None,
        mediapipe_ms=None,
        inferencia_ms=None,
        serial_ms=None,
        servo_ms=None,
    ):
        if not self.enabled or not self.session_id:
            return
        self._queue.put(
            (
                "/api/events",
                {
                    "session_id": self.session_id,
                    "gesture_name": gesture_name,
                    "fingers": list(fingers) if fingers is not None else [],
                    "latency_ms": latency_ms,
                    "fps": fps,
                    "hand_detected": bool(hand_detected),
                    "is_transition": bool(is_transition),
                    "captura_ms": captura_ms,
                    "mediapipe_ms": mediapipe_ms,
                    "inferencia_ms": inferencia_ms,
                    "serial_ms": serial_ms,
                    "servo_ms": servo_ms,
                },
            )
        )

    # -- pruebas de precisión ------------------------------------------------------

    def log_accuracy_test(
        self, expected_gesture, detected_gesture, correct, response_time_ms, timed_out=False
    ):
        if not self.enabled or not self.session_id:
            return
        self._queue.put(
            (
                "/api/accuracy_tests",
                {
                    "session_id": self.session_id,
                    "expected_gesture": expected_gesture,
                    "detected_gesture": detected_gesture,
                    "correct": bool(correct),
                    "response_time_ms": response_time_ms,
                    "timed_out": bool(timed_out),
                },
            )
        )

    def set_test_status(self, active, prompt=None):
        """Le avisa a la web si hay una prueba de precisión en curso (opcional,
        solo para mostrar un aviso en el panel en vivo)."""
        if not self.enabled:
            return
        self._post("/api/live/test", {"active": active, "prompt": prompt}, timeout=1.0)

    def close(self):
        self._stop = True
