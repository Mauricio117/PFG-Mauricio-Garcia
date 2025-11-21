// ------------------- CONFIGURACIÓN -------------------
struct Resorte {
  float L0;          // Longitud efectiva inicial (m)
  float constante;   // Constante K (N/m)
};

// Datos de los resortes: {L0, K}
Resorte resortes[3] = {
  {0.045, 428.3},  // Resorte 1 
  {0.046, 595.6},  // Resorte 2 
  {0.04, 12146.8}   // Resorte 3 
};


// ------------------- VARIABLES -------------------
int resorte_sel = 0;   // 0 = sin resorte
char modo_sel = 'E';   // 'E' = Extensión, 'F' = Flexión

float angulo = 0.0;
float fuerza = 0.0;


// ============================================================
//                  FUNCIONES AUXILIARES
// ============================================================

// Leer potenciómetro y convertirlo a ángulo (°)
float leerPotenciometro(char modo) {
  int lectura = analogRead(A10); // Potenciómetro
  float pot_val = (lectura / 1023.0) * 10000.0;  // Escalado a rango
  float ang_calc = 0;

  if (modo == 'E') {
    // Ecuación de extensión (ajustar tras calibración)
    ang_calc = (0.0274 * pot_val - 138.472);
  } else {
    // Ecuación de flexión (simétrica)
    ang_calc = -(0.0274 * pot_val - 138.472);
  }

  return ang_calc;  // Devuelve ángulo en grados
}



// ============================================================
//           CÁLCULO DE FUERZA SEGÚN GEOMETRÍA REAL
// ============================================================

float calcularFuerza(float angulo, int sel, char modo) {
  if (sel == 0)
    return 0; // Sin resorte seleccionado

  // ---------- PARÁMETROS GEOMÉTRICOS ----------
  const float a = 0.081;  // Distancia punto fijo (m)
  const float r = 0.026;  // Radio brazo móvil (m)
  const float L0_geom = fabs(a - r); // Longitud inicial (posición 0°)

  // ---------- SELECCIÓN DE RESORTE ----------
  Resorte res = resortes[sel - 1];

  // Conversión a radianes
  float theta = angulo * PI / 180.0;

  // ---------- CÁLCULO DE LONGITUD Y DEFORMACIÓN ----------
  float L = sqrt(pow(r * cos(theta) - a, 2) + pow(r * sin(theta), 2));  // Longitud actual
  float deltaL = L - L0_geom;   // Deformación (m)

  if (deltaL < 0)
    deltaL = 0;  // El resorte no empuja si está comprimido

  // ---------- FUERZA DEL RESORTE ----------
  float F = res.constante * deltaL;  // N

  return F;  // Devuelve fuerza en Newtons
}



// ============================================================
//                     SETUP Y LOOP
// ============================================================

void setup() {
  Serial.begin(115200);
  delay(500);
  Serial.println("Teensy listo. Esperando comandos...");
}



void loop() {
  // ---------- LECTURA DE COMANDOS DESDE PC ----------
  if (Serial.available()) {
    char c = Serial.read();

    // Seleccionar resorte (0–3)
    if (c >= '0' && c <= '3') {
      resorte_sel = c - '0';
      Serial.print("Resorte seleccionado: ");
      Serial.println(resorte_sel);
    }

    // Seleccionar modo ('E' o 'F')
    else if (c == 'E' || c == 'F') {
      modo_sel = c;
      Serial.print("Modo: ");
      Serial.println(modo_sel == 'E' ? "Extensión" : "Flexión");
    }
  }

  // ---------- LECTURA DE ÁNGULO ----------
  angulo = leerPotenciometro(modo_sel);

  // ---------- CÁLCULO DE FUERZA ----------
  fuerza = calcularFuerza(angulo, resorte_sel, modo_sel);

  // ---------- ENVÍO DE DATOS ----------
  Serial.print(angulo, 2);
  Serial.print(",");
  Serial.println(fuerza, 3);

  delay(100);  // Frecuencia ~10 Hz
}
