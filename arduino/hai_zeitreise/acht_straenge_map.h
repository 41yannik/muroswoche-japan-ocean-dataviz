// Automatisch generiert von modell/led_reihen_modell.py
// 8 WS2812B LED-Straenge (S1..S8) an 8 Arduino-Pins (Pin 2..9), je 17 aktive Luecken (0..16).
#pragma once
#include <Arduino.h>

const uint8_t N_STRIPS = 8;
const uint8_t LEDS_PER_STRIP = 24; // mind. 17 im Modell + Ueberhang am Streifenende
const uint8_t STRIP_PINS[N_STRIPS] = {2, 3, 4, 5, 6, 7, 8, 9};

// Zuordnung fuer jede Haiart (Index = led_id - 1, fuer led_id 1..109):
// LED_STRIP_OF[i] = Strang 0..7 (S1..S8), LED_PIXEL_OF[i] = LED-Position 0..16 (Luecke 1..17)
const uint8_t LED_STRIP_OF[109] PROGMEM = {
  0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
  1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1,
  1, 1, 1, 2, 2, 2, 2, 2, 2, 2, 2, 2,
  2, 2, 2, 2, 2, 2, 3, 3, 3, 3, 3, 3,
  3, 3, 3, 3, 3, 3, 3, 3, 3, 4, 4, 4,
  4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4,
  4, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5, 5,
  5, 5, 5, 6, 6, 6, 6, 6, 6, 6, 6, 6,
  6, 6, 6, 7, 7, 7, 7, 7, 7, 7, 7, 7,
  7,
};

const uint8_t LED_PIXEL_OF[109] PROGMEM = {
  8, 0, 16, 4, 12, 2, 6, 10, 14, 7, 9, 1,
  3, 15, 5, 10, 12, 7, 16, 11, 8, 2, 6, 9,
  14, 13, 1, 3, 9, 15, 5, 13, 11, 7, 6, 0,
  2, 12, 10, 14, 4, 8, 16, 8, 5, 0, 11, 13,
  3, 15, 9, 7, 4, 12, 1, 6, 14, 10, 15, 3,
  8, 0, 12, 11, 5, 7, 2, 14, 9, 6, 13, 4,
  16, 9, 12, 8, 0, 3, 5, 7, 14, 10, 16, 13,
  11, 1, 4, 8, 6, 15, 10, 12, 0, 2, 7, 4,
  14, 16, 9, 11, 1, 5, 15, 8, 3, 12, 6, 7,
  9,
};
