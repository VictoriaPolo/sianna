# SIANNA · Panel web de seguimiento

Panel local que se conecta con `gestureRecognition.py` para graficar en vivo
los movimientos de la mano y guardar en una base de datos (SQLite) las
métricas del proyecto:

- **Precisión** del reconocimiento de gestos (pruebas guiadas gesto por gesto).
- **Tiempos de respuesta** (latencia por frame y por prueba de precisión).
- **Número de repeticiones por gesto**.
- **Vista en vivo** del estado de los 5 dedos, gesto actual, FPS y latencia.

Todo corre en tu computador (no requiere internet, salvo la primera vez que
instales las librerías) y los datos quedan guardados en `webapp/sianna.db`.

## 1. Instalar dependencias

Backend web (una sola vez):

```
cd WebApp
pip install -r requirements.txt
```

Script de Python del reconocimiento de gestos (una sola vez, además de lo que
ya tenías instalado según `Programacion/Python/requeriments.txt`):

```
pip install requests
```

## 2. Arrancar el panel web

```
cd WebApp
python app.py
```

Verás `SIANNA web -> http://127.0.0.1:5050`. Abre esa dirección en tu
navegador y déjala abierta — se actualiza sola.

## 3. Arrancar el reconocimiento de gestos

En **otra** terminal (deja corriendo la del panel web):

```
cd Programacion/Python
python gestureRecognition.py
```

Antes de correrlo, revisa en la parte de arriba del archivo:

- `SERIAL_PORT = "COM3"` → cámbialo al puerto COM donde esté conectado tu ESP32
  (si no lo conectas, el script sigue funcionando igual, solo no mueve los
  servos — útil para probar el panel sin tener la mano armada).
- `CAMERA_INDEX = 0` → cámbialo si usas otra cámara.

Con la ventana de video en foco:

- **`q`** → salir.
- **`t`** → iniciar una prueba de precisión guiada (te pide cada gesto varias
  veces, en orden aleatorio, y mide si lo detectaste bien y en cuánto tiempo).
  Durante la prueba: **`n`** salta la repetición actual, **`ESC`** la cancela.

Apenas lo inicias, se crea una sesión nueva y el panel web pasa a mostrar
"Conectado". Todo lo que veas en la ventana de OpenCV (gesto, FPS, latencia)
se refleja también en la pestaña **En vivo** de la web.

## 4. Qué gestos reconoce

Definidos en `GESTURES` dentro de `gestureRecognition.py` (edítalo para
agregar o cambiar gestos — cada uno es una combinación de los 5 dedos
`[pulgar, índice, medio, anular, meñique]`, `1` = abierto, `0` = cerrado):

| Gesto | Dedos |
|---|---|
| mano_abierta | 1,1,1,1,1 |
| puno_cerrado | 0,0,0,0,0 |
| senalar | 0,1,0,0,0 |
| pulgar_arriba | 1,0,0,0,0 |
| paz | 0,1,1,0,0 |
| rock | 0,1,0,0,1 |

Cualquier otra combinación se registra como `gesto_no_reconocido`.

## 5. Estructura

```
WebApp/
  app.py              backend Flask + API REST + base de datos SQLite
  requirements.txt
  static/
    index.html        la página web (gráficas con Chart.js, sin dependencias externas)
    vendor/chart.umd.js
  sianna.db           se crea sola al primer arranque (no se sube a git)
  README.md

Programacion/Python/
  gestureRecognition.py  loop principal (cámara -> gestos -> ESP32), ahora también
                         reporta métricas al panel web
  metrics_client.py      cliente HTTP que envía los datos al panel (nuevo)
  handDetector.py        sin cambios
```

## 6. Base de datos

`webapp/sianna.db` (SQLite) tiene tres tablas:

- `sessions` — cada vez que corres `gestureRecognition.py` se crea una sesión.
- `gesture_events` — un registro por frame procesado (gesto, dedos, latencia,
  fps), usado para "Tiempos de respuesta" y "Repeticiones" (las repeticiones
  cuentan solo las transiciones a un gesto estable, no cada frame).
- `accuracy_tests` — un registro por repetición dentro de una prueba de
  precisión (`t`), con el gesto esperado, el detectado, si fue correcto y el
  tiempo de respuesta.

Puedes abrir `sianna.db` con cualquier visor de SQLite (por ejemplo DB Browser
for SQLite) si quieres exportar los datos para el informe del proyecto.

## 7. Si algo no conecta

- La web muestra "Desconectado" si no ha recibido datos en los últimos 2
  segundos — es normal si `gestureRecognition.py` no está corriendo.
- Si `gestureRecognition.py` no encuentra el panel web (`http://127.0.0.1:5050`),
  imprime una advertencia en la consola pero sigue funcionando con la cámara y
  el ESP32 con total normalidad; solo no queda nada guardado.
- Si el puerto 5050 ya está en uso en tu computador, cambia el puerto al final
  de `app.py` (`app.run(..., port=5050)`) y en `SIANNA_API_URL` dentro de
  `gestureRecognition.py`.
