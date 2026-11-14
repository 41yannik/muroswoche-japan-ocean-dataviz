// Prints actLevel/actPhase from the sketch, so the TypeScript port can be compared 1:1.
// Regenerate after changing the act in hai_zeitreise.ino (from web/src/lib/fixtures):
//   sed -n '/---- act timeline (pure)/,/---- end act timeline/p' \
//       ../../../../arduino/hai_zeitreise/hai_zeitreise.ino > akt_block.inc
//   c++ -std=c++17 -o /tmp/akt_dump akt_dump.cpp && /tmp/akt_dump && mv akt_tabelle.json akt_sketch.json
#include <cstdint>
#include <cstdio>
#include "akt_block.inc"
int main() {
  int q[][2] = {{3, 0}, {3, 500}, {3, 3001}, {3, 4000}, {3, 5000}, {2, 6000}, {1, 15000}, {0, 15000}, {1, 23000}, {1, 26000}};
  for (auto &p : q) printf("actLevel(%d,%d)=%d\n", p[0], p[1], actLevel(p[0], p[1]));
  int ph[] = {2999, 3000, 14999, 22999, 23000};
  for (int t : ph) printf("actPhase(%d)=%d\n", t, actPhase(t));
  // full table for the TS comparison: every 10 ms, all tiers
  FILE *f = fopen("akt_tabelle.json", "w");
  fprintf(f, "[");
  for (uint32_t t = 0; t <= 26000; t += 10) {
    fprintf(f, "%s[%u,%u,%u,%u]", t ? "," : "", actLevel(0, t), actLevel(1, t), actLevel(2, t), actLevel(3, t));
  }
  fprintf(f, "]\n");
  fclose(f);
}
