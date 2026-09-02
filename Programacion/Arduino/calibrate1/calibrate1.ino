#include <ESP32Servo.h>

// Crear objetos Servo
Servo thumb;   // Pulgar
Servo ind;   // Índice
Servo middle;  // Medio
Servo ring;    // Anular
Servo pinky;   // Meñique

// Variables de calibración para cada dedo (posición inicial: mano abierta)
int thumb_open_pos = 0;   // Posición abierta del pulgar (ajusta según sea necesario)
int index_open_pos = 0;   // Posición abierta del índice
int middle_open_pos = 0;  // Posición abierta del medio
int ring_open_pos = 180;    // Posición abierta del anular
int pinky_open_pos = 180;   // Posición abierta del meñique

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

  // Calibración: Mover los servos a la posición inicial (mano abierta)
  thumb.write(thumb_open_pos);
  ind.write(index_open_pos);
  middle.write(middle_open_pos);
  ring.write(ring_open_pos);
  pinky.write(pinky_open_pos);

  // Mensaje para indicar que la calibración ha terminado
  Serial.begin(9600);
  Serial.println("Calibración completa: Mano en posición abierta.");
}

void loop() {
  // El loop puede quedarse vacío para este caso de calibración
}
