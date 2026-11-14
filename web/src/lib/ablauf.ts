// The loop of the screen: one pure function of time. The screen and the LED
// commands both read from zustand(t), so they cannot drift apart.
import arten from "../data/arten.json";

// Act "Wer verschwindet", copied 1:1 from the act timeline block in
// arduino/hai_zeitreise/hai_zeitreise.ino (ablauf.test.ts checks both).
export const ACT = {
  BLINK_HALF: 500,
  BLINK_MS: 3000,
  CR_OFF: 5000,
  CR_PAUSE: 7000,
  EN_OFF: 10000,
  EN_PAUSE: 12000,
  VU_OFF: 15000,
  RETURN: 23000,
  MS: 26000,
} as const;

// Chapter 1, the descent: the camera starts above the sea, then sinks along the slope
// and stops at one real species per depth band (LED numbers, shallow to deep):
// scalloped hammerhead, goblin shark, kitefin shark, Japanese velvet dogfish,
// frilled shark, smalleye pygmy shark, leafscale gulper shark.
export const STATIONEN = [3, 53, 71, 90, 96, 106, 109] as const;
export const CH1_INTRO_MS = 4000;
/** time per station; the first CH1_FAHRT_MS of it the camera travels down */
export const CH1_STATION_MS = 7000;
export const CH1_FAHRT_MS = 2500;
export const CH1_MS = CH1_INTRO_MS + STATIONEN.length * CH1_STATION_MS;

// Chapter 2: the act "Wer verschwindet".
export const CH2_MS = ACT.MS;
export const LOOP_MS = CH1_MS + CH2_MS;

/** camera depth in metres: above the water (negative) at the start, wide view in the act */
export const OBEN_M = -60;
export const AKT_TIEFE_M = 700;
/** the depth scale on screen runs from the surface to this depth (m), just below the deepest species */
export const SKALA_M = 1300;

const STATION_TIEFE = STATIONEN.map((led) => {
  const a = arten.find((x) => x.led === led);
  if (!a) throw new Error(`station LED ${led} is not in arten.json`);
  return a.depth_m;
});

/** a camera pose: a station index, above the sea, or the wide view of the act */
export type Blickpunkt = number | "oben" | "akt";

function tiefeVon(b: Blickpunkt): number {
  if (b === "oben") return OBEN_M;
  if (b === "akt") return AKT_TIEFE_M;
  return STATION_TIEFE[b];
}

const smooth = (f: number): number => f * f * (3 - 2 * f);

// Number of species per tier, index = tier (0 not threatened, 1 VU, 2 EN, 3 CR).
export const TIER_COUNT = [63, 23, 19, 4] as const;

const easeQuad = (x: number): number => {
  if (x < 128) return Math.floor((2 * x * x) / 255);
  const r = 255 - x;
  return 255 - Math.floor((2 * r * r) / 255);
};

const fadeOut = (t: number, start: number, end: number): number => {
  if (t <= start) return 255;
  if (t >= end) return 0;
  return 255 - easeQuad(Math.floor(((t - start) * 255) / (end - start)));
};

/** Brightness factor 0..255 of a tier at time t (ms) in the act, as actLevel() in the sketch. */
export function actLevel(tier: number, t: number): number {
  if (tier === 0 || t >= ACT.MS) return 255;
  if (t < ACT.BLINK_MS) return Math.floor(t / ACT.BLINK_HALF) % 2 ? 255 : 0;
  if (t >= ACT.RETURN) return easeQuad(Math.floor(((t - ACT.RETURN) * 255) / (ACT.MS - ACT.RETURN)));
  if (tier === 3) return fadeOut(t, ACT.BLINK_MS, ACT.CR_OFF);
  if (tier === 2) return fadeOut(t, ACT.CR_PAUSE, ACT.EN_OFF);
  return fadeOut(t, ACT.EN_PAUSE, ACT.VU_OFF);
}

/** 0 blink, 1 CR, 2 EN, 3 VU, 4 only blue left, 5 return; as actPhase() in the sketch. */
export function actPhase(t: number): number {
  if (t < ACT.BLINK_MS) return 0;
  if (t < ACT.CR_PAUSE) return 1;
  if (t < ACT.EN_PAUSE) return 2;
  if (t < ACT.VU_OFF) return 3;
  if (t < ACT.RETURN) return 4;
  return 5;
}

export interface Zustand {
  kapitel: 1 | 2;
  /** ms since the start of the chapter */
  tKapitel: number;
  /** chapter 1: LED number of the featured species, null during the intro */
  featured: number | null;
  /** chapter 1: index into STATIONEN and progress 0..1 within that station */
  featuredIndex: number;
  featuredProgress: number;
  /** the camera moves from one pose to the next, f = 0..1 (linear; tiefe is eased) */
  blick: { von: Blickpunkt; nach: Blickpunkt; f: number };
  /** camera depth in metres (negative above the water) */
  tiefe: number;
  /** chapter 2: act phase and brightness factor per tier */
  akt: { phase: number; t: number; level: [number, number, number, number] } | null;
  /** chapter 2: number of species still visible */
  zaehler: number;
}

export function zustand(tLoop: number): Zustand {
  const t = ((tLoop % LOOP_MS) + LOOP_MS) % LOOP_MS;
  const z: Zustand = {
    kapitel: 1, tKapitel: t, featured: null, featuredIndex: -1, featuredProgress: 0,
    blick: { von: "oben", nach: "oben", f: 1 }, tiefe: OBEN_M, akt: null, zaehler: 109,
  };
  if (t < CH1_MS) {
    if (t >= CH1_INTRO_MS) {
      const k = (t - CH1_INTRO_MS) / CH1_STATION_MS;
      const i = Math.floor(k);
      const tk = t - CH1_INTRO_MS - i * CH1_STATION_MS;
      z.featuredIndex = i;
      z.featuredProgress = k - i;
      z.featured = STATIONEN[i];
      z.blick = { von: i === 0 ? "oben" : i - 1, nach: i, f: Math.min(tk / CH1_FAHRT_MS, 1) };
    }
  } else {
    const tk = t - CH1_MS;
    const level = [0, 1, 2, 3].map((tier) => actLevel(tier, tk)) as [number, number, number, number];
    const phase = actPhase(tk);
    z.kapitel = 2;
    z.tKapitel = tk;
    z.akt = { phase, t: tk, level };
    // During the blink and the return all species count as present.
    z.zaehler = phase === 0 || phase === 5
      ? 109
      : TIER_COUNT.reduce((sum, n, tier) => sum + (level[tier] > 0 ? n : 0), 0);
    if (tk < ACT.BLINK_MS) z.blick = { von: STATIONEN.length - 1, nach: "akt", f: tk / ACT.BLINK_MS };
    else if (tk < ACT.RETURN) z.blick = { von: "akt", nach: "akt", f: 1 };
    else z.blick = { von: "akt", nach: "oben", f: (tk - ACT.RETURN) / (ACT.MS - ACT.RETURN) };
  }
  const { von, nach, f } = z.blick;
  z.tiefe = tiefeVon(von) + (tiefeVon(nach) - tiefeVon(von)) * smooth(f);
  return z;
}

/**
 * Line command for the model (see the remote mode in hai_zeitreise.ino):
 * R rest, S <led> highlight one species, A <ms> act at ms. The sketch also knows
 * Y <scenario> <year>; the screen no longer sends it.
 */
export function befehl(z: Zustand): string {
  if (z.kapitel === 1) return z.featured === null ? "R" : `S ${z.featured}`;
  return `A ${z.tKapitel}`;
}

/** The line as sent over USB: command, '*', XOR of its characters as two uppercase hex digits, '\n'. */
export function zeile(cmd: string): string {
  let x = 0;
  for (let i = 0; i < cmd.length; i++) x ^= cmd.charCodeAt(i);
  return `${cmd}*${x.toString(16).toUpperCase().padStart(2, "0")}\n`;
}
