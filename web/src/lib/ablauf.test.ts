import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import arten from "../data/arten.json";
import tabelle from "./fixtures/akt_sketch.json";
import {
  ACT,
  CH1_FAHRT_MS,
  CH1_INTRO_MS,
  CH1_MS,
  CH1_STATION_MS,
  CH2_MS,
  LOOP_MS,
  OBEN_M,
  STATIONEN,
  actLevel,
  actPhase,
  befehl,
  zeile,
  zustand,
} from "./ablauf";

const SKETCH = fileURLToPath(
  new URL("../../../arduino/hai_zeitreise/hai_zeitreise.ino", import.meta.url),
);
const TIER_NUM = { LC: 0, VU: 1, EN: 2, CR: 3 } as const;

describe("act timeline matches the sketch", () => {
  const src = readFileSync(SKETCH, "utf8");
  const block = src.slice(src.indexOf("// ---- act timeline (pure)"), src.indexOf("// ---- end act timeline"));

  it("uses the same ACT_* constants", () => {
    const found: Record<string, number> = {};
    for (const m of block.matchAll(/const uint32_t (ACT_\w+) = (\d+);/g)) found[m[1]] = Number(m[2]);
    expect(Object.keys(found).length).toBe(9);
    expect(found).toEqual({
      ACT_BLINK_HALF: ACT.BLINK_HALF,
      ACT_BLINK_MS: ACT.BLINK_MS,
      ACT_CR_OFF: ACT.CR_OFF,
      ACT_CR_PAUSE: ACT.CR_PAUSE,
      ACT_EN_OFF: ACT.EN_OFF,
      ACT_EN_PAUSE: ACT.EN_PAUSE,
      ACT_VU_OFF: ACT.VU_OFF,
      ACT_RETURN: ACT.RETURN,
      ACT_MS: ACT.MS,
    });
  });

  it("reproduces actLevel of the sketch for every 10 ms and every tier", () => {
    // fixtures/akt_sketch.json is printed by fixtures/akt_dump.cpp, compiled against
    // the sketch block (see the comment at the top of that file).
    expect(tabelle.length).toBe(ACT.MS / 10 + 1);
    tabelle.forEach((row, i) => {
      for (let tier = 0; tier < 4; tier++) expect(actLevel(tier, i * 10)).toBe(row[tier]);
    });
    expect(actPhase(2999)).toBe(0);
    expect(actPhase(3000)).toBe(1);
    expect(actPhase(14999)).toBe(3);
    expect(actPhase(22999)).toBe(4);
    expect(actPhase(23000)).toBe(5);
  });

  it("is monotonic within each fade, as in the sketch", () => {
    for (const [tier, a, b] of [[3, 3000, 5000], [2, 7000, 10000], [1, 12000, 15000]] as const) {
      let prev = 256;
      for (let t = a; t <= b; t += 10) {
        const v = actLevel(tier, t);
        expect(v).toBeLessThanOrEqual(prev);
        prev = v;
      }
      expect(prev).toBe(0);
    }
  });
});

describe("zustand(t)", () => {
  const depth = (led: number) => arten.find((a) => a.led === led)!.depth_m;

  it("runs the descent, then the act, in a loop of about 80 seconds", () => {
    expect(LOOP_MS).toBe(CH1_MS + CH2_MS);
    expect(CH2_MS).toBe(ACT.MS);
    expect(CH1_MS).toBe(CH1_INTRO_MS + STATIONEN.length * CH1_STATION_MS);
    expect(LOOP_MS).toBeGreaterThan(70_000);
    expect(LOOP_MS).toBeLessThan(90_000);
    expect(zustand(0).kapitel).toBe(1);
    expect(zustand(CH1_MS - 1).kapitel).toBe(1);
    expect(zustand(CH1_MS).kapitel).toBe(2);
    expect(zustand(LOOP_MS).kapitel).toBe(1);
    expect(zustand(LOOP_MS + 5).tKapitel).toBe(5);
    for (let t = 0; t < LOOP_MS; t += 100) expect([1, 2]).toContain(zustand(t).kapitel);
  });

  it("stops at seven stations from the shallows to the deepest species", () => {
    expect(STATIONEN.length).toBe(7);
    for (let i = 1; i < STATIONEN.length; i++) expect(depth(STATIONEN[i])).toBeGreaterThan(depth(STATIONEN[i - 1]));
    expect(depth(STATIONEN[0])).toBeLessThan(50);
    expect(depth(STATIONEN[STATIONEN.length - 1])).toBe(Math.max(...arten.map((a) => a.depth_m)));
    // every 200 m band down to 800 m and below 1,000 m has a stop
    const baender = new Set(STATIONEN.map((l) => Math.floor(depth(l) / 200)));
    for (const b of [0, 1, 2, 3, 5, 6]) expect(baender.has(b)).toBe(true);
    expect(new Set(STATIONEN.map((l) => arten.find((a) => a.led === l)!.tier)).size).toBeGreaterThanOrEqual(3);
    const seen: number[] = [];
    for (let t = 0; t < CH1_MS; t += 100) {
      const f = zustand(t).featured;
      if (f !== null && seen[seen.length - 1] !== f) seen.push(f);
    }
    expect(seen).toEqual([...STATIONEN]);
    expect(zustand(0).featured).toBeNull();
  });

  it("the camera depth starts above the sea, holds at each station's depth and only goes down", () => {
    expect(zustand(0).tiefe).toBe(OBEN_M);
    expect(OBEN_M).toBeLessThan(0);
    STATIONEN.forEach((led, i) => {
      const halt = CH1_INTRO_MS + i * CH1_STATION_MS + CH1_FAHRT_MS;
      for (const t of [halt, halt + 1000, CH1_INTRO_MS + (i + 1) * CH1_STATION_MS - 1]) {
        expect(zustand(t).tiefe).toBeCloseTo(depth(led), 6);
        expect(zustand(t).blick.f).toBe(1);
      }
    });
    let prev = -Infinity;
    for (let t = 0; t < CH1_MS; t += 20) {
      const d = zustand(t).tiefe;
      expect(d).toBeGreaterThanOrEqual(prev - 1e-9);
      prev = d;
    }
  });

  it("the camera depth is continuous over the whole loop, also where the loop closes", () => {
    let prev = zustand(LOOP_MS - 10).tiefe;
    for (let t = 0; t <= LOOP_MS; t += 10) {
      const d = zustand(t).tiefe;
      expect(Math.abs(d - prev)).toBeLessThan(15);
      prev = d;
    }
    expect(zustand(LOOP_MS - 1).tiefe).toBeCloseTo(OBEN_M, 0);
  });

  it("chapter 2 is the act and counts 109, 105, 86, 63, then 109 again", () => {
    const start = CH1_MS;
    expect(zustand(start).akt!.phase).toBe(0);
    expect(zustand(start + 1000).zaehler).toBe(109);
    expect(zustand(start + ACT.CR_OFF).zaehler).toBe(105);
    expect(zustand(start + ACT.EN_OFF).zaehler).toBe(86);
    expect(zustand(start + ACT.VU_OFF).zaehler).toBe(63);
    expect(zustand(start + ACT.RETURN - 1).zaehler).toBe(63);
    expect(zustand(start + ACT.RETURN + 1).zaehler).toBe(109);
    const z = zustand(start + 4000).akt!;
    expect(z.level).toEqual([255, 255, 255, actLevel(3, 4000)]);
  });

  it("tier counts in the data match the counter", () => {
    const n = (t: keyof typeof TIER_NUM) => arten.filter((a) => a.tier === t).length;
    expect([n("CR"), n("EN"), n("VU"), n("LC")]).toEqual([4, 19, 23, 63]);
  });
});

describe("befehl(z) for the model", () => {
  it("sends one command per state and never the year command", () => {
    expect(befehl(zustand(0))).toBe("R");
    const f = STATIONEN[0];
    expect(befehl(zustand(CH1_INTRO_MS))).toBe(`S ${f}`);
    expect(befehl(zustand(CH1_MS - 1))).toBe(`S ${STATIONEN[STATIONEN.length - 1]}`);
    expect(befehl(zustand(CH1_MS + 1234))).toBe("A 1234");
    for (let t = 0; t < LOOP_MS; t += 50) expect(befehl(zustand(t))).not.toMatch(/^Y/);
  });

  it("frames each line with the XOR checksum the sketch expects", () => {
    // same literals as arduino/host_test/remote_test.cpp
    expect(zeile("R")).toBe("R*52\n");
    expect(zeile("X")).toBe("X*58\n");
    expect(zeile("S 53")).toBe("S 53*75\n");
    expect(zeile("S 9")).toBe("S 9*4A\n");
    expect(zeile("S 1")).toBe("S 1*42\n");
    // every command of a full loop stays ASCII and inside the sketch's 24-byte buffer
    for (let t = 0; t < LOOP_MS; t += 50) {
      const l = zeile(befehl(zustand(t)));
      expect(l).toMatch(/^[A-Z][ 0-9]*\*[0-9A-F]{2}\n$/);
      expect(l.length - 1).toBeLessThan(24);
    }
  });
});
