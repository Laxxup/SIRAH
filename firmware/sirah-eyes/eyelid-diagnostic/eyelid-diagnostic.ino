#include <Wire.h>
#include <Adafruit_PWMServoDriver.h>

Adafruit_PWMServoDriver pca = Adafruit_PWMServoDriver(0x40);

// --- ASIGNACIÓN DE CANALES ---
const uint8_t CH_OJO_X   = 0;
const uint8_t CH_OJO_Y   = 1;
const uint8_t CH_SUP_DER = 2;
const uint8_t CH_INF_DER = 3;
const uint8_t CH_SUP_IZQ = 4;
const uint8_t CH_INF_IZQ = 5;

// --- NUEVO RANGO DE LÍMITES CALIBRADOS ---
// Ojo X
const int X_CENTRO = 90;
const int X_DER    = 50;
const int X_IZQ    = 140;

// Ojo Y
const int Y_CENTRO = 70;
const int Y_ARRIBA = 110;
const int Y_ABAJO  = 60;

// Párpado Derecho Superior
const int SUP_DER_ABRIR  = 100;
const int SUP_DER_CERRAR = 80;

// Párpado Derecho Inferior
const int INF_DER_ABRIR  = 20;
const int INF_DER_CERRAR = 90;

// Párpado Izquierdo Superior
const int SUP_IZQ_ABRIR  = 105;
const int SUP_IZQ_CERRAR = 150;

// Párpado Izquierdo Inferior
const int INF_IZQ_ABRIR  = 130;
const int INF_IZQ_CERRAR = 70;

// --- CONFIGURACIÓN DE PULSOS PWM ---
const int SERVO_MIN_PULSE = 125; 
const int SERVO_MAX_PULSE = 575; 

// --- TIMERS NO BLOQUEANTES ---
unsigned long ultimoParpadeo = 0;
unsigned long tiempoParpadeo = 3000;

unsigned long ultimoMovimiento = 0;
unsigned long tiempoMovimiento = 2000;

void setServoAngle(uint8_t channel, int angle) {
  angle = constrain(angle, 0, 180);
  int pulse = map(angle, 0, 180, SERVO_MIN_PULSE, SERVO_MAX_PULSE);
  pca.setPWM(channel, 0, pulse);
}

void abrirOjos() {
  setServoAngle(CH_SUP_DER, SUP_DER_ABRIR);
  setServoAngle(CH_INF_DER, INF_DER_ABRIR);
  setServoAngle(CH_SUP_IZQ, SUP_IZQ_ABRIR);
  setServoAngle(CH_INF_IZQ, INF_IZQ_ABRIR);
}

void cerrarOjos() {
  setServoAngle(CH_SUP_DER, SUP_DER_CERRAR);
  setServoAngle(CH_INF_DER, INF_DER_CERRAR);
  setServoAngle(CH_SUP_IZQ, SUP_IZQ_CERRAR);
  setServoAngle(CH_INF_IZQ, INF_IZQ_CERRAR);
}

void parpadear() {
  cerrarOjos();
  delay(120);
  abrirOjos();
}

void moverOjos(int x, int y) {
  x = constrain(x, X_DER, X_IZQ);
  y = constrain(y, Y_ABAJO, Y_ARRIBA);
  
  setServoAngle(CH_OJO_X, x);
  setServoAngle(CH_OJO_Y, y);
}

void setup() {
  Wire.begin();
  pca.begin();
  pca.setPWMFreq(50);

  delay(100);

  // Inicialización: Centrado y abierto
  moverOjos(X_CENTRO, Y_CENTRO);
  abrirOjos();
}

void loop() {
  unsigned long ahora = millis();

  // Rutina de Parpadeo
  if (ahora - ultimoParpadeo >= tiempoParpadeo) {
    parpadear();
    ultimoParpadeo = ahora;
    tiempoParpadeo = random(2000, 6000);
  }

  // Rutina de Movimiento Ocular
  if (ahora - ultimoMovimiento >= tiempoMovimiento) {
    if (random(0, 10) < 3) {
      moverOjos(X_CENTRO, Y_CENTRO);
    } else {
      int nuevoX = random(X_DER, X_IZQ + 1);
      int nuevoY = random(Y_ABAJO, Y_ARRIBA + 1);
      moverOjos(nuevoX, nuevoY);
    }

    ultimoMovimiento = ahora;
    tiempoMovimiento = random(1200, 3500);
  }
}