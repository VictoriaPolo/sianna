#include <ESP32Servo.h>
// Crear objetos Servo
Servo thumb;
Servo ind;
Servo middle;
Servo ring;
Servo pinky;

// Variables de calibración de apertura y cierre para cada dedo
int thumb_open_pos = 0, thumb_close_pos = 110;
int index_open_pos = 0, index_close_pos = 180;
int middle_open_pos = 0, middle_close_pos = 150;
int ring_open_pos = 180, ring_close_pos = 20;
int pinky_open_pos = 180, pinky_close_pos = 20;

// Pines de conexión de los servos a la placa
int thumb_pin = 27;
int index_pin = 26;
int middle_pin = 25;
int ring_pin = 33;
int pinky_pin = 32;

// Variable para almacenar los datos recibidos
String data = "";
int fingers[5] = {0, 0, 0, 0, 0}; // Array para almacenar el estado de cada dedo

void setup() {
  
  // Asignar los pines a los objetos Servo
  thumb.attach(thumb_pin);
  ind.attach(index_pin);
  middle.attach(middle_pin);
  ring.attach(ring_pin);
  pinky.attach(pinky_pin);
  
  // Configurar el puerto serial
  Serial.begin(9600);
  
  // Inicialmente, abrir la mano
  openHand();
}
void loop() {
  
  // Verificar si hay datos disponibles en el puerto serial
  if (Serial.available() > 0) {
    
    // Leer la línea de datos entrantes
    data = Serial.readStringUntil('\n');
    
    // Dividir los datos recibidos en un array
    parseData(data);
    
    // Controlar los dedos de acuerdo con los datos recibidos
    controlFingers();

    // Confirmar por serial que el comando ya fue aplicado a los servos
    // (usado desde Python para medir la latencia de la etapa "servo").
    Serial.println("ACK");
  }
  
  // Esperar un pequeño tiempo para evitar saturar el puerto serial
  delay(100);
}

// Función para analizar los datos recibidos
void parseData(String inputData) {
  
  // Separar los datos por comas y almacenarlos en el array fingers
  int index = 0;
  int start = 0;
  int commaIndex = inputData.indexOf(',');
  
  while (commaIndex >= 0 && index < 5) {
    fingers[index] = inputData.substring(start, commaIndex).toInt();
    start = commaIndex + 1;
    commaIndex = inputData.indexOf(',', start);
    index++;
  }
  
  // Último dato (sin coma al final)
  if (index < 5) {
    fingers[index] = inputData.substring(start).toInt();
  }
}

// Función para controlar los dedos según los datos recibidos
void controlFingers() {
  
  // Controlar el pulgar
  if (fingers[0] == 1) {
    thumb.write(thumb_open_pos); // Pulgar abierto
  } else {
    thumb.write(thumb_close_pos); // Pulgar cerrado
  }
  
  // Controlar el índice
  if (fingers[1] == 1) {
    ind.write(index_open_pos); // Índice abierto
  } else {
    ind.write(index_close_pos); // Índice cerrado
  }
  
  // Controlar el dedo medio
  if (fingers[2] == 1) {
    middle.write(middle_open_pos); // Medio abierto
  } else {
    middle.write(middle_close_pos); // Medio cerrado
  }
  
  // Controlar el anular
  if (fingers[3] == 1) {
    ring.write(ring_open_pos); // Anular abierto
  } else {
    ring.write(ring_close_pos); // Anular cerrado
  }
  
  // Controlar el meñique
  if (fingers[4] == 1) {
    pinky.write(pinky_open_pos); // Meñique abierto
  } else {
    pinky.write(pinky_close_pos); // Meñique cerrado
  }
}

// Función para abrir todos los dedos
void openHand() {
  
  thumb.write(thumb_open_pos);
  ind.write(index_open_pos);
  middle.write(middle_open_pos);
  ring.write(ring_open_pos);
  pinky.write(pinky_open_pos);
  
}

// Función para cerrar todos los dedos
void closeHand() {
  
  thumb.write(thumb_close_pos);
  ind.write(index_close_pos);
  middle.write(middle_close_pos);
  ring.write(ring_close_pos);
  pinky.write(pinky_close_pos);
  
}
