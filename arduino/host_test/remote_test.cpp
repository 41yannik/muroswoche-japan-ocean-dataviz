// Host test for the remote parser in hai_zeitreise.ino (block between
// "---- remote parser (pure)" and "---- end remote parser").
// Run from the project root:  bash arduino/host_test/run.sh
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <string>

// Values the sketch takes from zeitreihe.h and the act timeline block.
const uint8_t N_LED = 109;
const uint8_t N_SCEN = 2;
const uint16_t YEAR_FIRST = 1970;
const uint16_t YEAR_LAST = 2030;
const uint32_t ACT_MS = 26000;

#include "remote_block.inc"

static int failures = 0;
static int checks = 0;

// Appends *HH, computed here independently of the sketch.
static std::string framed(const char* payload) {
  uint8_t x = 0;
  for (const char* p = payload; *p; p++) x ^= (uint8_t)*p;
  char tail[4];
  snprintf(tail, sizeof tail, "*%02X", x);
  return std::string(payload) + tail;
}

static void expectOk(const std::string& line, char kind, uint32_t a, uint32_t b) {
  checks++;
  char buf[32];
  snprintf(buf, sizeof buf, "%s", line.c_str());
  RemoteCmd c = {0, 0, 0};
  bool ok = parseRemote(buf, c.kind, c.a, c.b);
  if (!ok || c.kind != kind || c.a != a || c.b != b) {
    failures++;
    printf("FAIL accept %-14s -> ok=%d kind=%c a=%u b=%u\n", line.c_str(), ok, c.kind ? c.kind : '?', c.a, c.b);
  }
}

static void expectBad(const std::string& line) {
  checks++;
  char buf[32];
  snprintf(buf, sizeof buf, "%s", line.c_str());
  RemoteCmd c = {0, 0, 0};
  if (parseRemote(buf, c.kind, c.a, c.b)) {
    failures++;
    printf("FAIL reject %-14s -> accepted kind=%c a=%u\n", line.c_str(), c.kind, c.a);
  }
}

int main() {
  // literal checksums, worked out by hand: R = 0x52, X = 0x58, "S 53" = 0x75
  expectOk("R*52", 'R', 0, 0);
  expectOk("X*58", 'X', 0, 0);
  expectOk("S 53*75", 'S', 53, 0);

  expectOk(framed("S 1"), 'S', 1, 0);
  expectOk(framed("S 109"), 'S', 109, 0);
  expectOk(framed("Y 0 1970"), 'Y', 0, 1970);
  expectOk(framed("Y 1 2030"), 'Y', 1, 2030);
  expectOk(framed("A 0"), 'A', 0, 0);
  expectOk(framed("A 25999"), 'A', 25999, 0);

  // checksum missing, wrong, lowercase, short or long
  expectBad("R");
  expectBad("R*53");
  expectBad("S 53*76");
  expectBad("R*5");
  expectBad("R*522");
  expectBad("*00");
  expectBad("");
  expectOk("S 9*4A", 'S', 9, 0);   // "S 9" = 0x4A
  expectBad("S 9*4a");             // the page always sends uppercase hex

  // a byte lost on the wire: "S 53" arrives as "S 3" with the old checksum
  expectBad("S 3*75");
  expectBad("Y 0 197*" + framed("Y 0 1970").substr(9));

  // out of range
  expectBad(framed("S 0"));
  expectBad(framed("S 110"));
  expectBad(framed("Y 2 2000"));
  expectBad(framed("Y 0 1969"));
  expectBad(framed("Y 0 2031"));
  expectBad(framed("A 26000"));
  expectBad(framed("S 1234567"));

  // malformed
  expectBad(framed("R 1"));
  expectBad(framed("X 0"));
  expectBad(framed("S"));
  expectBad(framed("S53"));
  expectBad(framed("S 53 1"));
  expectBad(framed("S 5x"));
  expectBad(framed("Y 0"));
  expectBad(framed("A"));
  expectBad(framed("Q 1"));
  expectBad(framed("r"));

  printf("%d checks, %d failures\n", checks, failures);
  return failures ? 1 : 0;
}
