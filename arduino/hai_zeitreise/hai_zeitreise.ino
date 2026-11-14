// Hai-Zeitreise: 109 shark species on 8 WS2812B strands (S1..S8 on pins 2..9).
//
// Each strand runs across under the 16 rails (P01..P16) and lights up to 17
// gaps (gap 1 = left, at plate S-L, where Din enters). Every species sits at
// its habitat depth, S1 at the top down to S8 in the deep sea.
//
// Cycle
//   Self-test   once after power-up: S1 shows 1 LED, S2 2 LEDs ... S8 8 LEDs.
//   Rest        REST_MS: all species in their Red List colour at BASE_LEVEL
//               (with MIT_ZEITREISE 1 the 4 stocks rest at their latest status).
//   Act "Wer verschwindet" (ACT_MS, 26 s): the 46 threatened species blink
//               three times, then go dark tier by tier, CR (red) -> EN
//               (orange) -> VU (yellow). Only the 63 blue species remain for
//               a moment, then all return. A thought experiment based on the
//               Red List, not a forecast.
//   Then back to rest.
//
// Optional (MIT_ZEITREISE 1, off since 13.11.: not visible on the object)
//   Time travel after the act, run 1 ("catch as 2017-2019") and run 2 ("catch at F_MSY"),
//               1970 -> 2030, one year per YEAR_MS. The other species dim
//               over FADE_MS at the start of each run; the 4 stocks follow
//               SSB/SSBMSY of that year:
//                 below MSY      -> pulses
//                 forecast years -> flickers
//                 no data        -> faint glow
//   Then back to rest.
//
// Remote mode (screen next to the model, web/ in this project)
//   Chrome on the MacBook sends one checked line every 250 ms over USB
//   (115200 baud): R rest, S <led> one species blinks, Y <scen> <year>,
//   A <ms> act at that moment, X back to the own loop. Each line ends in
//   *HH (XOR checksum, see the remote parser block). The board answers
//   "remote <line>" when the command changes and "err <line>" on bad input.
//   No valid line for 5 s -> "remote timeout", the own loop above resumes.
//
// Data (do not edit by hand, regenerate and run scripts/pruefe_led_daten.py):
//   zeitreihe.h          from scripts/build_zeitreihe_led.py
//   acht_straenge_map.h  from modell/led_reihen_modell.py
// Library: FastLED (Arduino Library Manager). Boards: UNO R3 and UNO R4 WiFi.
//
// Wiring, check BEFORE the first power-up
//   1. Measure the PSU output with a multimeter: 5.0 to 5.2 V. Lookalike
//      supplies exist with 12 V, which destroys the strips.
//   2. Connect PSU GND and Arduino GND.
//   3. One 330 to 470 Ohm resistor in each data line (pins 2..9), close to
//      the strip. One 1000 uF capacitor across +5 V / GND at the feed point.
//   4. Strips get power from the PSU, never through the Arduino 5 V pin.
//
// Hardware checklist after upload
//   - Self-test: S1..S8 light up in this order with 1..8 LEDs. A strand in
//     the wrong place means its data wire sits on the wrong pin.
//   - Set KALIBRIERUNG to 1, upload, open Serial Monitor (115200 baud,
//     line ending "Newline"). Each species slot lights in its colour; check
//     that the slots sit in the gaps. If not, fix with g1/g17 (see below),
//     paste the printed lines into the calibration block, set KALIBRIERUNG
//     back to 0.
//   - Watch one full cycle (30 s rest + 26 s act): the threatened species
//     blink, then red, orange and yellow go dark one after the other.
//   - After 10 minutes PSU and cables are at most hand-warm.

#include <FastLED.h>
#include "zeitreihe.h"
#include "acht_straenge_map.h"

// ===== configuration ========================================================
#ifndef KALIBRIERUNG
#define KALIBRIERUNG 0      // 1 = calibration mode via Serial Monitor
#endif
#ifndef MIT_JAHRESPANEL
#define MIT_JAHRESPANEL 0   // 1 = 16x16 WS2812B panel shows the year
#endif
#ifndef MIT_ZEITREISE
#define MIT_ZEITREISE 0     // 1 = time travel of the 4 stocks after the act
#endif
// #define PIN_SENSOR 12    // optional presence sensor (HIGH = someone there)

// Data pins of S1..S8. FastLED needs them as compile-time constants; setup()
// checks them against STRIP_PINS from acht_straenge_map.h.
#define PIN_S1 2
#define PIN_S2 3
#define PIN_S3 4
#define PIN_S4 5
#define PIN_S5 6
#define PIN_S6 7
#define PIN_S7 8
#define PIN_S8 9

// Addressed pixels per strand: 17 gaps plus overhang at the strip end.
// Lower to 20 if RAM on the UNO R3 runs short.
const uint8_t PIXELS_PER_STRIP = 24;

const uint16_t PSU_MA = 5000;          // current limit, protects thin feed wires
const uint8_t MASTER_BRIGHTNESS = 116;  // 45 % of 255 (166 dimmed by another 30 %), all levels scale with it
const uint32_t REST_MS = 30000;        // rest phase between the acts
const uint16_t YEAR_MS = 900;          // 61 years -> about 55 s per run
const uint16_t FADE_MS = 1000;         // other species dim at the start of a run
const uint8_t BASE_LEVEL = 220;        // all species in rest and act (0-255)
const uint8_t RUN_LEVEL = 25;          // species without a series, during a run
const uint8_t GLOW_LEVEL = 12;         // stock with no data for that year
const uint16_t SELFTEST_STEP_MS = 350;

// Two-point calibration per strand (S1..S8): pixel index on the strip that
// sits under gap 1 and under gap 17. Default 0 and 16 = strip starts exactly
// at gap 1 with the planned LED pitch. A reversed strip has GAP1 > GAP17.
uint8_t GAP1_INDEX[N_STRIPS] = {0, 0, 0, 0, 0, 0, 0, 0};
uint8_t GAP17_INDEX[N_STRIPS] = {16, 16, 16, 16, 16, 16, 16, 16};

#if MIT_JAHRESPANEL
#define PIN_MATRIX 10
#define MATRIX_W 16
#define MATRIX_H 16
#define MATRIX_SERPENTINE 1  // 1 if every second row runs backwards
#define MATRIX_FLIP_X 0      // 1 if the digits appear mirrored
#define MATRIX_FLIP_Y 0      // 1 if the digits appear upside down
#endif
// ============================================================================

// ---- act timeline (pure) -------------------------------------------------------
// Act "Wer verschwindet", times in ms since the act started. Tier 0 = not
// threatened (blue), 1 = VU (yellow), 2 = EN (orange), 3 = CR (red).
// Plain C++ without Arduino calls, so the host test can compile this block.
const uint32_t ACT_BLINK_HALF = 500;   // blink: 0.5 s off, 0.5 s on, three times
const uint32_t ACT_BLINK_MS = 3000;
const uint32_t ACT_CR_OFF = 5000;      // CR fades out from ACT_BLINK_MS to here
const uint32_t ACT_CR_PAUSE = 7000;    // EN starts fading here
const uint32_t ACT_EN_OFF = 10000;
const uint32_t ACT_EN_PAUSE = 12000;   // VU starts fading here
const uint32_t ACT_VU_OFF = 15000;     // from here only the blue species remain
const uint32_t ACT_RETURN = 23000;     // all threatened species fade back in
const uint32_t ACT_MS = 26000;         // end of the act

// Smooth 0..255 -> 0..255 curve (ease in and out, quadratic).
uint8_t easeQuad(uint8_t x) {
  if (x < 128) return (uint8_t)((2u * x * x) / 255u);
  uint16_t r = 255u - x;
  return (uint8_t)(255u - (2u * r * r) / 255u);
}

// 255 before start, 0 after end, eased in between.
uint8_t fadeOut(uint32_t t, uint32_t start, uint32_t end) {
  if (t <= start) return 255;
  if (t >= end) return 0;
  return 255 - easeQuad((uint8_t)((t - start) * 255u / (end - start)));
}

// Brightness factor (0..255) of a tier at time t in the act.
uint8_t actLevel(uint8_t tier, uint32_t t) {
  if (tier == 0 || t >= ACT_MS) return 255;
  if (t < ACT_BLINK_MS) return ((t / ACT_BLINK_HALF) % 2) ? 255 : 0;
  if (t >= ACT_RETURN) return easeQuad((uint8_t)((t - ACT_RETURN) * 255u / (ACT_MS - ACT_RETURN)));
  if (tier == 3) return fadeOut(t, ACT_BLINK_MS, ACT_CR_OFF);
  if (tier == 2) return fadeOut(t, ACT_CR_PAUSE, ACT_EN_OFF);
  return fadeOut(t, ACT_EN_PAUSE, ACT_VU_OFF);
}

// 0 blink, 1 CR, 2 EN, 3 VU, 4 only blue left, 5 return.
uint8_t actPhase(uint32_t t) {
  if (t < ACT_BLINK_MS) return 0;
  if (t < ACT_CR_PAUSE) return 1;
  if (t < ACT_EN_PAUSE) return 2;
  if (t < ACT_VU_OFF) return 3;
  if (t < ACT_RETURN) return 4;
  return 5;
}
// ---- end act timeline ----------------------------------------------------------

static_assert(PIXELS_PER_STRIP >= 17, "a strand needs at least 17 pixels");

#if MIT_JAHRESPANEL && defined(__AVR__)
// Measured with FastLED 3.10.9: 8 strands use 1299 of 2048 bytes RAM on the
// UNO R3, the panel needs 768 more. Use an UNO R4 for the panel.
#error "MIT_JAHRESPANEL needs an UNO R4: not enough RAM on the UNO R3"
#endif

const uint8_t N_GAPS = 17;
const uint8_t STRIP_PIN_LIST[N_STRIPS] = {PIN_S1, PIN_S2, PIN_S3, PIN_S4,
                                          PIN_S5, PIN_S6, PIN_S7, PIN_S8};

CRGB strips[N_STRIPS][PIXELS_PER_STRIP];

// ---- species -> pixel -------------------------------------------------------

// Pixel index on strand s for model gap position p (0..16), or -1 if the
// calibration pushes it off the strip.
int16_t pixelIndex(uint8_t s, uint8_t p) {
  int16_t g1 = GAP1_INDEX[s];
  int16_t v = (int16_t)p * ((int16_t)GAP17_INDEX[s] - g1);
  int16_t idx = g1 + (v >= 0 ? v + 8 : v - 8) / 16;  // round to nearest
  return (idx >= 0 && idx < PIXELS_PER_STRIP) ? idx : -1;
}

void setSpecies(uint8_t ledIndex, CRGB color) {
  uint8_t s = pgm_read_byte(&LED_STRIP_OF[ledIndex]);
  uint8_t p = pgm_read_byte(&LED_PIXEL_OF[ledIndex]);
  if (s >= N_STRIPS) return;
  int16_t idx = pixelIndex(s, p);
  if (idx >= 0) strips[s][idx] = color;
}

CRGB redListColor(uint8_t ledIndex, uint8_t level) {
  CRGB c = CRGB(pgm_read_dword(&LED_COLOR[ledIndex]));
  c.nscale8_video(level);
  return c;
}

void clearStrips() {
  for (uint8_t s = 0; s < N_STRIPS; s++) fill_solid(strips[s], PIXELS_PER_STRIP, CRGB::Black);
}

void drawBase(uint8_t level) {
  clearStrips();
  for (uint8_t i = 0; i < N_LED; i++) setSpecies(i, redListColor(i, level));
}

uint8_t atLeast(uint8_t v, uint8_t lo) { return v < lo ? lo : v; }

// ---- optional year panel ------------------------------------------------------
#if MIT_JAHRESPANEL
CRGB matrix[MATRIX_W * MATRIX_H];

const uint8_t DIGITS[10][5] PROGMEM = {
  {7, 5, 5, 5, 7}, {2, 6, 2, 2, 7}, {7, 1, 7, 4, 7}, {7, 1, 7, 1, 7}, {5, 5, 7, 1, 1},
  {7, 4, 7, 1, 7}, {7, 4, 7, 5, 7}, {7, 1, 1, 1, 1}, {7, 5, 7, 5, 7}, {7, 5, 7, 1, 7},
};

uint16_t xy(uint8_t x, uint8_t y) {
  if (MATRIX_FLIP_X) x = MATRIX_W - 1 - x;
  if (MATRIX_FLIP_Y) y = MATRIX_H - 1 - y;
  if (MATRIX_SERPENTINE && (y & 1)) return y * MATRIX_W + (MATRIX_W - 1 - x);
  return y * MATRIX_W + x;
}

void clearPanel() { fill_solid(matrix, MATRIX_W * MATRIX_H, CRGB::Black); }

void drawYear(uint16_t year, CRGB color) {
  clearPanel();
  uint8_t d[4] = {(uint8_t)(year / 1000), (uint8_t)(year / 100 % 10),
                  (uint8_t)(year / 10 % 10), (uint8_t)(year % 10)};
  for (uint8_t i = 0; i < 4; i++) {
    uint8_t x0 = i * 4;  // 3 columns + 1 gap, last digit ends at column 14
    for (uint8_t row = 0; row < 5; row++) {
      uint8_t bits = pgm_read_byte(&DIGITS[d[i]][row]);
      for (uint8_t col = 0; col < 3; col++) {
        if (bits & (4 >> col)) matrix[xy(x0 + col, 5 + row)] = color;
      }
    }
  }
}
#endif

// ---- setup --------------------------------------------------------------------

void checkPins() {
  for (uint8_t s = 0; s < N_STRIPS; s++) {
    if (STRIP_PIN_LIST[s] != STRIP_PINS[s]) {
      Serial.print(F("WARNING: S"));
      Serial.print(s + 1);
      Serial.print(F(" on pin "));
      Serial.print(STRIP_PIN_LIST[s]);
      Serial.print(F(", model plan says pin "));
      Serial.println(STRIP_PINS[s]);
    }
  }
}

void selfTest() {
  for (uint8_t s = 0; s < N_STRIPS; s++) {
    clearStrips();
    for (uint8_t k = 0; k <= s; k++) strips[s][k] = CRGB(60, 60, 60);
    FastLED.show();
    delay(SELFTEST_STEP_MS);
  }
  clearStrips();
  FastLED.show();
}

#if KALIBRIERUNG
void calibrationSetup();
void calibrationLoop();
#else
void normalLoop();
#endif

void setup() {
  Serial.begin(115200);
  FastLED.addLeds<WS2812B, PIN_S1, GRB>(strips[0], PIXELS_PER_STRIP);
  FastLED.addLeds<WS2812B, PIN_S2, GRB>(strips[1], PIXELS_PER_STRIP);
  FastLED.addLeds<WS2812B, PIN_S3, GRB>(strips[2], PIXELS_PER_STRIP);
  FastLED.addLeds<WS2812B, PIN_S4, GRB>(strips[3], PIXELS_PER_STRIP);
  FastLED.addLeds<WS2812B, PIN_S5, GRB>(strips[4], PIXELS_PER_STRIP);
  FastLED.addLeds<WS2812B, PIN_S6, GRB>(strips[5], PIXELS_PER_STRIP);
  FastLED.addLeds<WS2812B, PIN_S7, GRB>(strips[6], PIXELS_PER_STRIP);
  FastLED.addLeds<WS2812B, PIN_S8, GRB>(strips[7], PIXELS_PER_STRIP);
#if MIT_JAHRESPANEL
  FastLED.addLeds<WS2812B, PIN_MATRIX, GRB>(matrix, MATRIX_W * MATRIX_H);
#endif
  FastLED.setMaxPowerInVoltsAndMilliamps(5, PSU_MA);
  FastLED.setBrightness(MASTER_BRIGHTNESS);
#ifdef PIN_SENSOR
  pinMode(PIN_SENSOR, INPUT);
#endif
  FastLED.clear(true);
  checkPins();
  selfTest();
#if KALIBRIERUNG
  calibrationSetup();
#else
  Serial.println(F("hai_zeitreise ready"));
#endif
}

void loop() {
#if KALIBRIERUNG
  calibrationLoop();
#else
  normalLoop();
#endif
}

// ---- normal operation -----------------------------------------------------------
#if !KALIBRIERUNG

enum State { REST, ACT, RUN };
State state = REST;
uint8_t scenario = 0;
uint32_t stateStart = 0;
int16_t lastYearIndex = -1;
int8_t lastActPhase = -1;

// Red List tier from the colour: 3 CR (red), 2 EN (orange), 1 VU (yellow), 0 blue.
uint8_t tierOf(uint8_t ledIndex) {
  uint32_t c = pgm_read_dword(&LED_COLOR[ledIndex]);
  if (c == 0xFF0000) return 3;
  if (c == 0xFF5000) return 2;
  if (c == 0xFFC000) return 1;
  return 0;
}

bool presence() {
#ifdef PIN_SENSOR
  return digitalRead(PIN_SENSOR) == HIGH;
#else
  return false;
#endif
}

void showRest() {
  drawBase(BASE_LEVEL);
#if MIT_ZEITREISE
  // with the time travel the 4 stocks rest at their own level
  for (uint8_t s = 0; s < N_STOCK; s++) {
    uint8_t i = STOCK_LED_ID[s] - 1;
    setSpecies(i, redListColor(i, REST_BRIGHT[s]));
  }
#endif
#if MIT_JAHRESPANEL
  clearPanel();
#endif
}

// Act "Wer verschwindet", t = ms since the act started
void showAct(uint32_t t) {
  clearStrips();
  for (uint8_t i = 0; i < N_LED; i++) {
    setSpecies(i, redListColor(i, scale8(BASE_LEVEL, actLevel(tierOf(i), t))));
  }
#if MIT_JAHRESPANEL
  clearPanel();
#endif
  int8_t phase = actPhase(t);
  if (phase != lastActPhase) {
    lastActPhase = phase;
    static const char* const NAMES[] = {"blink", "CR", "EN", "VU", "hold", "return"};
    Serial.print(F("act "));
    Serial.println(NAMES[phase]);
  }
}

// t = ms since the start of this run (also used by the remote command Y)
void showYear(uint8_t yearIndex, uint32_t t, uint32_t now) {
  uint8_t others = RUN_LEVEL;
  if (t < FADE_MS) others = BASE_LEVEL - (uint32_t)(BASE_LEVEL - RUN_LEVEL) * t / FADE_MS;
  drawBase(others);

  bool forecastYear = false;
  for (uint8_t s = 0; s < N_STOCK; s++) {
    uint8_t i = STOCK_LED_ID[s] - 1;
    uint8_t level = pgm_read_byte(&BRIGHT[scenario][s][yearIndex]);
    uint8_t flags = pgm_read_byte(&FLAGS[scenario][s][yearIndex]);
    // flags: bit0 data, bit1 forecast, bit2 below MSY, bit3 model bridge (not shown)
    if (!(flags & 1)) {
      level = GLOW_LEVEL;
    } else {
      if (flags & 4) level = scale8(level, 120 + scale8(sin8(now / 4), 135));  // pulse
      if (flags & 2) {
        forecastYear = true;
        level = qadd8(scale8(level, 200), random8(level / 3 + 1));               // flicker
      }
    }
    setSpecies(i, redListColor(i, atLeast(level, GLOW_LEVEL)));
  }

#if MIT_JAHRESPANEL
  CRGB digits = CRGB(200, 200, 200);
  if (forecastYear) digits = scenario == 0 ? CRGB(255, 40, 40) : CRGB(255, 120, 0);
  drawYear(YEAR_FIRST + yearIndex, digits);
#endif

  if (yearIndex != lastYearIndex) {
    lastYearIndex = yearIndex;
    Serial.print(F("run "));
    Serial.print(scenario + 1);
    Serial.print(F(" year "));
    Serial.print(YEAR_FIRST + yearIndex);
    Serial.println(forecastYear ? F(" forecast") : F(""));
  }
}

#if MIT_ZEITREISE
void startRun(uint8_t scen, uint32_t now) {
  state = RUN;
  scenario = scen;
  stateStart = now;
  lastYearIndex = -1;
}
#endif  // MIT_ZEITREISE

void startRest(uint32_t now) {
  state = REST;
  stateStart = now;
  Serial.println(F("rest"));
}

void startAct(uint32_t now) {
  state = ACT;
  stateStart = now;
  lastActPhase = -1;
}

// ---- remote mode: the screen next to the model leads ------------------------------

// ---- remote parser (pure) --------------------------------------------------------
// One line from the screen (web/src/lib/seriell.ts): <payload>*HH, where HH is the
// XOR of all payload characters in uppercase hex, as in NMEA. The checksum catches
// bytes lost while FastLED.show() blocks interrupts ("S 53" arriving as "S 3").
//   R            rest view
//   S <led>      species 1..N_LED blinks, all others dim
//   Y <s> <year> scenario s (0 status quo, 1 F_MSY), year YEAR_FIRST..YEAR_LAST
//   A <ms>       act "Wer verschwindet" at ms 0..ACT_MS-1
//   X            leave remote mode
// Checked on the host by arduino/host_test/run.sh.
struct RemoteCmd {
  char kind;
  uint32_t a;
  uint32_t b;
};

int8_t hexDigit(char c) {
  if (c >= '0' && c <= '9') return c - '0';
  if (c >= 'A' && c <= 'F') return c - 'A' + 10;
  return -1;
}

// One space, then 1 to 6 digits.
bool readUint(const char*& p, uint32_t& out) {
  if (*p != ' ') return false;
  p++;
  uint8_t n = 0;
  out = 0;
  while (*p >= '0' && *p <= '9') {
    if (++n > 6) return false;
    out = out * 10 + (uint32_t)(*p - '0');
    p++;
  }
  return n > 0;
}

// Cuts the line at '*' once the checksum matches, so an error print shows the payload.
// Plain references instead of RemoteCmd&: the Arduino IDE puts generated prototypes
// above the struct, so a struct parameter would not compile.
bool parseRemote(char* line, char& kind, uint32_t& a, uint32_t& b) {
  uint8_t x = 0;
  char* star = line;
  while (*star && *star != '*') x ^= (uint8_t)*star++;
  if (*star != '*' || star == line) return false;
  int8_t hi = hexDigit(star[1]);
  int8_t lo = hexDigit(hi < 0 ? '\0' : star[2]);
  if (hi < 0 || lo < 0 || star[3] != '\0' || (uint8_t)(hi * 16 + lo) != x) return false;
  *star = '\0';

  RemoteCmd c = {line[0], 0, 0};
  const char* p = line + 1;
  bool ok;
  switch (c.kind) {
    case 'R':
    case 'X':
      ok = true;
      break;
    case 'S':
      ok = readUint(p, c.a) && c.a >= 1 && c.a <= N_LED;
      break;
    case 'Y':
      ok = readUint(p, c.a) && c.a < N_SCEN && readUint(p, c.b) && c.b >= YEAR_FIRST && c.b <= YEAR_LAST;
      break;
    case 'A':
      ok = readUint(p, c.a) && c.a < ACT_MS;
      break;
    default:
      ok = false;
  }
  if (!ok || *p != '\0') return false;
  kind = c.kind;
  a = c.a;
  b = c.b;
  return true;
}
// ---- end remote parser -----------------------------------------------------------

const uint32_t REMOTE_TIMEOUT_MS = 5000;  // no valid line for this long -> own loop
const uint8_t SPOT_DIM = 40;              // other species while one is shown (S)
const uint16_t SPOT_BLINK_MS = 400;       // the shown species: 400 ms bright, 400 ms dim

bool remote = false;
RemoteCmd remoteCmd = {'R', 0, 0};
uint32_t remoteAt = 0;     // millis() of the last valid line
uint32_t remoteSince = 0;  // millis() when the current command (kind and argument) began
uint32_t actBase = 0;      // A: act time = millis() - actBase, renewed by every line
char remoteBuf[24];
uint8_t remoteLen = 0;
bool remoteOverflow = false;

void handleRemoteLine(char* line, uint32_t now) {
  RemoteCmd c;
  if (!parseRemote(line, c.kind, c.a, c.b)) {
    Serial.print(F("err "));
    Serial.println(line);
    return;
  }
  if (c.kind == 'X') {
    Serial.println(F("remote off"));
    if (remote) {
      remote = false;
      startRest(now);
    }
    return;
  }
  // The heartbeat repeats the same command every 250 ms; only a change restarts it.
  // A carries the act clock, so its argument changes on every line by design.
  bool changed = !remote || c.kind != remoteCmd.kind ||
                 (c.kind != 'A' && (c.a != remoteCmd.a || c.b != remoteCmd.b));
  remote = true;
  remoteAt = now;
  remoteCmd = c;
  if (c.kind == 'A') actBase = now - c.a;
  if (changed) {
    remoteSince = now;
    lastActPhase = -1;
    lastYearIndex = -1;
    Serial.print(F("remote "));
    Serial.println(line);
  }
}

void readSerial(uint32_t now) {
  while (Serial.available() > 0) {
    char ch = (char)Serial.read();
    if (ch == '\r') continue;
    if (ch == '\n') {
      if (remoteOverflow) {
        Serial.println(F("err line too long"));
      } else if (remoteLen > 0) {
        remoteBuf[remoteLen] = '\0';
        handleRemoteLine(remoteBuf, now);
      }
      remoteLen = 0;
      remoteOverflow = false;
    } else if (remoteLen < sizeof(remoteBuf) - 1) {
      remoteBuf[remoteLen++] = ch;
    } else {
      remoteOverflow = true;
    }
  }
}

void showRemote(uint32_t now) {
  uint32_t t = now - remoteSince;
  switch (remoteCmd.kind) {
    case 'S': {
      drawBase(SPOT_DIM);
      uint8_t i = remoteCmd.a - 1;
      setSpecies(i, redListColor(i, (t / SPOT_BLINK_MS) % 2 ? SPOT_DIM : 255));
#if MIT_JAHRESPANEL
      clearPanel();
#endif
      break;
    }
    case 'Y':
      scenario = remoteCmd.a;
      showYear(remoteCmd.b - YEAR_FIRST, t, now);
      break;
    case 'A':
      showAct(now - actBase);
      break;
    default:
      showRest();
  }
}

void normalLoop() {
  static bool started = false;
  uint32_t now = millis();
  if (!started) {
    started = true;
    startRest(now);
  }

  readSerial(now);
  if (remote && now - remoteAt >= REMOTE_TIMEOUT_MS) {
    remote = false;
    Serial.println(F("remote timeout"));
    startRest(now);
  }
  if (remote) {
    showRemote(now);
    FastLED.show();
    delay(20);
    return;
  }

  uint32_t t = now - stateStart;

  if (state == REST) {
    if (t >= REST_MS || presence()) {
      startAct(now);
      t = 0;
    }
  } else if (state == ACT) {
    if (t >= ACT_MS) {
#if MIT_ZEITREISE
      startRun(0, now);
      t = 0;
#else
      startRest(now);
#endif
    }
  }
#if MIT_ZEITREISE
  else if (t / YEAR_MS >= N_YEARS) {
    if (scenario + 1 < N_SCEN) {
      startRun(scenario + 1, now);
      t = 0;
    } else {
      startRest(now);
    }
  }
#endif

  if (state == REST) showRest();
  else if (state == ACT) showAct(t);
#if MIT_ZEITREISE
  else showYear(t / YEAR_MS, t, now);
#endif
  FastLED.show();
  delay(20);
}

#endif  // !KALIBRIERUNG

// ---- calibration mode -------------------------------------------------------------
#if KALIBRIERUNG

// Commands in the Serial Monitor (line ending "Newline"):
//   g1 <strand 1-8> <index>   pixel index under gap 1 of that strand
//   g17 <strand 1-8> <index>  pixel index under gap 17 of that strand
//   p                         print the calibration lines again
// Display: pixel 0 green, every 5th pixel dim white (to count along the
// strip), every species slot in its Red List colour.

char lineBuf[24];
uint8_t lineLen = 0;

void printArray(const __FlashStringHelper *name, const uint8_t *a) {
  Serial.print(F("uint8_t "));
  Serial.print(name);
  Serial.print(F("[N_STRIPS] = {"));
  for (uint8_t s = 0; s < N_STRIPS; s++) {
    Serial.print(a[s]);
    if (s + 1 < N_STRIPS) Serial.print(F(", "));
  }
  Serial.println(F("};"));
}

void printCalibration() {
  Serial.println(F("--- paste into the calibration block ---"));
  printArray(F("GAP1_INDEX"), GAP1_INDEX);
  printArray(F("GAP17_INDEX"), GAP17_INDEX);
}

void drawCalibration() {
  clearStrips();
  for (uint8_t s = 0; s < N_STRIPS; s++) {
    strips[s][0] = CRGB(0, 60, 0);
    for (uint8_t k = 5; k < PIXELS_PER_STRIP; k += 5) strips[s][k] = CRGB(25, 25, 25);
  }
  for (uint8_t i = 0; i < N_LED; i++) setSpecies(i, redListColor(i, 160));
#if MIT_JAHRESPANEL
  clearPanel();
#endif
  FastLED.show();
}

void handleLine(char *line) {
  char cmd[4] = {0};
  int strand = 0, index = -1;
  int n = sscanf(line, "%3s %d %d", cmd, &strand, &index);
  if (n >= 1 && strcmp(cmd, "p") == 0) {
    printCalibration();
    return;
  }
  bool isG1 = strcmp(cmd, "g1") == 0;
  bool isG17 = strcmp(cmd, "g17") == 0;
  if (n != 3 || !(isG1 || isG17) || strand < 1 || strand > N_STRIPS ||
      index < 0 || index >= PIXELS_PER_STRIP) {
    Serial.println(F("? use: g1 <strand 1-8> <index 0-23> | g17 <strand> <index> | p"));
    return;
  }
  if (isG1) GAP1_INDEX[strand - 1] = index;
  else GAP17_INDEX[strand - 1] = index;
  drawCalibration();
  printCalibration();
}

void calibrationSetup() {
  Serial.println(F("hai_zeitreise CALIBRATION"));
  Serial.println(F("g1 <strand 1-8> <index>, g17 <strand 1-8> <index>, p"));
  drawCalibration();
  printCalibration();
}

void calibrationLoop() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\r') continue;
    if (c == '\n') {
      lineBuf[lineLen] = 0;
      if (lineLen) handleLine(lineBuf);
      lineLen = 0;
    } else if (lineLen < sizeof(lineBuf) - 1) {
      lineBuf[lineLen++] = c;
    }
  }
}

#endif  // KALIBRIERUNG
