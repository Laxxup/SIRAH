// =====================================================
// SIRAH OJOS - Seguidor de cara horizontal + parpadeo
// =====================================================
//
// Loop automatico UNICAMENTE el parpadeo natural (~6s).
// El ojo horizontal SOLO se mueve por comandos serial "X".
// Sin cara -> se recentra y se queda quieto (parpadeando).
//
// Protocolo serial (115200 baud, lineas con \n):
//   X <0-100>   posicion horizontal (0=izq, 50=centro, 100=der)
//   CENTER      volver al centro
//   BLINK       disparar un parpadeo ahora
//   READY       responde "OK <posX> BLINK=<0|1>"
// =====================================================

#include <ESP32Servo.h>

const int PIN_X   = 25;
const int PIN_PII = 33;
const int PIN_PSI = 23;

const int X_LEFT   = 14;
const int X_CENTER = 55;
const int X_RIGHT  = 90;

const int PII_OPEN  = 90;
const int PII_CLOSE = 30;
const int PSI_OPEN  = 105;
const int PSI_CLOSE = 155;

Servo servoX;
Servo servoPII;
Servo servoPSI;

float limitar01(float x) {
  if (x < 0.0f) return 0.0f;
  if (x > 1.0f) return 1.0f;
  return x;
}

float suavizar(float t) {
  t = limitar01(t);
  return t * t * (3.0f - 2.0f * t);
}

bool vencido(unsigned long ahora, unsigned long objetivo) {
  return (long)(ahora - objetivo) >= 0;
}

// =====================================================
// OJO HORIZONTAL
// =====================================================

int posX = X_CENTER;
int inicioX  = X_CENTER;
int destinoX = X_CENTER;
bool moviendoX = false;
unsigned long inicioMovimientoX = 0;
unsigned long duracionMovimientoX = 200;

void activarX() {
  if (!servoX.attached()) {
    servoX.setPeriodHertz(50);
    servoX.attach(PIN_X, 500, 2400);
    servoX.write(posX);
  }
}

void apagarX() {
  if (servoX.attached()) servoX.detach();
  moviendoX = false;
}

void moverOjoX(int pos100) {
  int destino = map(pos100, 0, 100, X_LEFT, X_RIGHT);
  destino = constrain(destino, X_LEFT, X_RIGHT);

  if (moviendoX) {
    destinoX = destino;
    return;
  }
  if (destino == posX) return;

  inicioX = posX;
  destinoX = destino;
  duracionMovimientoX = 200;
  inicioMovimientoX = millis();
  activarX();
  moviendoX = true;
}

void recentrarOjo() {
  if (!moviendoX && posX == X_CENTER) return;
  if (!moviendoX) {
    inicioX = posX;
    destinoX = X_CENTER;
    duracionMovimientoX = 220;
    inicioMovimientoX = millis();
    activarX();
    moviendoX = true;
  } else {
    destinoX = X_CENTER;
  }
}

void actualizarOjos() {
  if (!moviendoX) return;

  unsigned long ahora = millis();
  float progreso = (float)(ahora - inicioMovimientoX) / duracionMovimientoX;
  progreso = limitar01(progreso);
  float p = suavizar(progreso);
  int nuevaPos = round(inicioX + (destinoX - inicioX) * p);

  if (nuevaPos != posX) {
    posX = nuevaPos;
    servoX.write(posX);
  }

  if (progreso >= 1.0f) {
    posX = destinoX;
    servoX.write(posX);
    apagarX();
  }
}

// =====================================================
// PARPADEO (unico loop automatico)
// =====================================================

enum EstadoBlink { BLINK_IDLE, BLINK_CERRANDO, BLINK_CERRADO, BLINK_ABRIENDO };

EstadoBlink estadoBlink = BLINK_IDLE;
unsigned long inicioBlink = 0;
unsigned long siguienteBlink = 0;

const unsigned long BLINK_CIERRE_MS = 95;
const unsigned long BLINK_CERRADO_MS = 45;
const unsigned long BLINK_ABRIR_MS   = 135;

void activarParpados() {
  if (!servoPII.attached()) {
    servoPII.setPeriodHertz(50);
    servoPII.attach(PIN_PII, 500, 2400);
  }
  if (!servoPSI.attached()) {
    servoPSI.setPeriodHertz(50);
    servoPSI.attach(PIN_PSI, 500, 2400);
  }
  servoPII.write(PII_OPEN);
  servoPSI.write(PSI_OPEN);
}

void apagarParpados() {
  if (servoPII.attached()) servoPII.detach();
  if (servoPSI.attached()) servoPSI.detach();
}

void iniciarBlink() {
  if (estadoBlink != BLINK_IDLE) return;
  activarParpados();
  inicioBlink = millis();
  estadoBlink = BLINK_CERRANDO;
}

void actualizarBlink() {
  unsigned long ahora = millis();

  if (estadoBlink == BLINK_IDLE) return;

  if (estadoBlink == BLINK_CERRANDO) {
    float progreso = (float)(ahora - inicioBlink) / BLINK_CIERRE_MS;
    float p = limitar01(progreso) * (3.0f - 2.0f * limitar01(progreso));
    int pii = round(PII_OPEN + (PII_CLOSE - PII_OPEN) * p);
    int psi = round(PSI_OPEN + (PSI_CLOSE - PSI_OPEN) * p);
    servoPII.write(pii);
    servoPSI.write(psi);
    if (progreso >= 1.0f) {
      servoPII.write(PII_CLOSE);
      servoPSI.write(PSI_CLOSE);
      estadoBlink = BLINK_CERRADO;
      inicioBlink = ahora;
    }
    return;
  }

  if (estadoBlink == BLINK_CERRADO) {
    if (ahora - inicioBlink >= BLINK_CERRADO_MS) {
      estadoBlink = BLINK_ABRIENDO;
      inicioBlink = ahora;
    }
    return;
  }

  if (estadoBlink == BLINK_ABRIENDO) {
    float progreso = (float)(ahora - inicioBlink) / BLINK_ABRIR_MS;
    float p = limitar01(progreso) * (3.0f - 2.0f * limitar01(progreso));
    int pii = round(PII_CLOSE + (PII_OPEN - PII_CLOSE) * p);
    int psi = round(PSI_CLOSE + (PSI_OPEN - PSI_CLOSE) * p);
    servoPII.write(pii);
    servoPSI.write(psi);
    if (progreso >= 1.0f) {
      servoPII.write(PII_OPEN);
      servoPSI.write(PSI_OPEN);
      estadoBlink = BLINK_IDLE;
      apagarParpados();
      siguienteBlink = ahora + 6000;
    }
  }
}

// =====================================================
// PARSER SERIAL
// =====================================================

String entrada;

void procesarSerial() {
  while (Serial.available()) {
    char c = (char)Serial.read();
    if (c == '\n' || c == '\r') {
      if (entrada.length() > 0) {
        entrada.trim();
        if (entrada.startsWith("X ")) {
          int pct = constrain(entrada.substring(2).toInt(), 0, 100);
          moverOjoX(pct);
        } else if (entrada == "CENTER") {
          recentrarOjo();
        } else if (entrada == "BLINK") {
          iniciarBlink();
        } else if (entrada == "READY") {
          Serial.print("OK ");
          Serial.print(posX);
          Serial.print(" BLINK=");
          Serial.println(estadoBlink == BLINK_IDLE ? 0 : 1);
        }
        entrada = "";
      }
    } else {
      entrada += c;
    }
  }
}

// =====================================================
// SETUP
// =====================================================

void setup() {
  Serial.begin(115200);
  delay(500);
  randomSeed(micros());

  posX = X_CENTER;
  siguienteBlink = millis() + 6000;

  Serial.println("==============================");
  Serial.println(" SIRAH OJOS v2");
  Serial.println(" solo parpadeo auto; sigue la cara por X 0-100");
  Serial.println("==============================");
}

// =====================================================
// LOOP (solo parpadeo es automatico)
// =====================================================

void loop() {
  unsigned long ahora = millis();

  procesarSerial();
  actualizarOjos();
  actualizarBlink();

  if (estadoBlink == BLINK_IDLE && vencido(ahora, siguienteBlink)) {
    iniciarBlink();
  }
}
