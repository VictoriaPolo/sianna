"""
Lanzador local del panel SIANNA.

La implementación real del backend vive en landing/api/index.py (para que
Vercel la despliegue como función serverless junto con la landing page).
Este archivo solo la reutiliza para correr todo localmente con:

    pip install -r requirements.txt
    python app.py

Luego abrir http://127.0.0.1:5050/panel en el navegador.
"""

import os
import sys

from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))

sys.path.insert(0, os.path.join(BASE_DIR, "landing", "api"))
from index import app  # noqa: E402

if __name__ == "__main__":
    print("SIANNA web -> http://127.0.0.1:5050/panel")
    app.run(host="127.0.0.1", port=5050, debug=False, threaded=True)
