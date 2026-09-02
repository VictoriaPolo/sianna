#include <ESP32Servo.h>

// Crear objetos Servo
Servo thumb;   // Pulgar
Servo ind;   // Índice
Servo middle;  // Medio
Servo ring;    // Anular
Servo pinky;   // Meñique

// Variables de calibración de apertura para cada dedo (mano abierta)
int thumb_open_pos = 0;   
int index_open_pos = 0;   
int middle_open_pos = 0;  
int ring_open_pos = 180;    
int pinky_open_pos = 180;   

// Pines de conexión de los servos a la placa
int thumb_pin = 27;
int index_pin = 26;
int middle_pin = 25;
int ring_pin = 33;
int pinky_pin = 32;

void setup() {
  // Asignar los pines a los objetos Servo
  thumb.attach(thumb_pin);
  ind.attach(index_pin);
  middle.attach(middle_pin);
  ring.attach(ring_pin);
  pinky.attach(pinky_pin);

  // Colocar los servos en la posición de apertura inicial (mano abierta)
  thumb.write(thumb_open_pos);
  ind.write(index_open_pos);
  middle.write(middle_open_pos);
  ring.write(ring_open_pos);
  pinky.write(pinky_open_pos);

  // Iniciar la comunicación serial
  Serial.begin(9600);
  Serial.println("Mano en posición abierta.");
  Serial.println("Ingrese el número del dedo (1-5) seguido del ángulo de cierre (0-180), separado por una coma. Ejemplo: 1,90");
}

void loop() {
  // Verificar si hay datos disponibles en el puerto serial
  if (Serial.available() > 0) {
    // Leer la entrada desde el puerto serial
    String input = Serial.readStringUntil('\n');

    // Dividir la entrada en dedo y ángulo (separado por coma)
    int commaIndex = input.indexOf(',');
    
    if (commaIndex > 0) {
      int finger = input.substring(0, commaIndex).toInt();
      int angle = input.substring(commaIndex + 1).toInt();

      // Validar si el dedo está entre 1 y 5, y el ángulo entre 0 y 180
      if (finger >= 1 && finger <= 5 && angle >= 0 && angle <= 180) {
        moveFinger(finger, angle);
        Serial.print("Moviendo dedo ");
        Serial.print(finger);
        Serial.print(" a ");
        Serial.print(angle);
        Serial.println(" grados.");
      } else {
        Serial.println("Error: dedo debe estar entre 1-5 y el ángulo entre 0-180.");
      }
    } else {
      Serial.println("Error: formato incorrecto. Use: dedo,angulo (ej: 1,90).");
    }
  }
}

// Función para mover el dedo especificado al ángulo dado
void moveFinger(int finger, int angle) {
  switch (finger) {
    case 1:
      thumb.write(angle);
      break;
    case 2:
      ind.write(angle);
      break;
    case 3:
      middle.write(angle);
      break;
    case 4:
      ring.write(angle);
      break;
    case 5:
      pinky.write(angle);
      break;
    default:
      Serial.println("Error: dedo no válido.");
      break;
  }
}
