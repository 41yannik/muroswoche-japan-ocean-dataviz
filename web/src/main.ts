// One clock drives everything: zustand(t) decides the scene, the texts and the LED command.
import { befehl, SKALA_M, zustand, type Zustand } from "./lib/ablauf";
import { Modell, type Status } from "./lib/seriell";
import { ARTEN, STUFE_FARBE, STUFE_INDEX } from "./szene/haie";
import { baueSzene } from "./szene/szene";
import { STATUS } from "./texte";

/** Below this camera depth the water is dark enough for light text (m). */
const HELL_BIS_M = 200;
const TINTE = { hell: "#27221f", dunkel: "#f3efe8" };
/** the shadow behind the text, in the opposite tone of the ink (see global.css) */
const HALO = { hell: "rgb(243 239 232 / 0.45)", dunkel: "rgb(25 34 54 / 0.6)" };
/** a tapped shark keeps its name and its LED this long (ms) */
const GEWAEHLT_MS = 6000;
/** a pointer that moves less than this between down and up is a tap, not a drag (CSS px) */
const TAP_PX = 8;
/** the name stands this far below the centre of its shark (CSS px) */
const ABSTAND = 64;
/** the depth number needs this much room on the right edge (CSS px) */
const SKALA_BREITE = 560;

const $ = (id: string) => {
  const el = document.getElementById(id);
  if (!el) throw new Error(`#${id} missing`);
  return el;
};

/** Writes text only when it changed, so the DOM stays quiet at 60 fps. */
function setText(el: HTMLElement, text: string) {
  if (el.textContent !== text) el.textContent = text;
}

function setOpacity(el: HTMLElement, an: boolean) {
  const v = an ? "1" : "0";
  if (el.style.opacity !== v) el.style.opacity = v;
}

export function start(): void {
  // ?t=<seconds> starts the loop at that point; with ?halt the clock stands still there (screenshots)
  const params = new URLSearchParams(location.search);
  const offset = Number(params.get("t") ?? 0) * 1000 || 0;
  const halt = params.has("halt");
  const t0 = performance.now() - offset;

  const canvas = $("szene") as HTMLCanvasElement;
  const szene = baueSzene(canvas);
  window.addEventListener("resize", () => szene.resize());

  const modell = new Modell(zeigeStatus);
  const knopf = $("verbinden");
  knopf.addEventListener("click", () => void modell.verbinden());
  zeigeStatus(modell.status);
  void modell.start();

  function zeigeStatus(s: Status) {
    setText($("status-text"), STATUS[s]);
    const punkt = $("status-punkt");
    // filled when the model listens, a ring when it does not
    punkt.style.background = s === "connected" || s === "connecting" ? "currentColor" : "transparent";
    punkt.style.opacity = s === "connecting" ? "0.5" : "1";
    // without a model the button says it all; the status line would repeat it
    knopf.classList.toggle("hidden", s !== "disconnected");
    $("status-text").classList.toggle("hidden", s === "disconnected");
  }

  // ---- a tap on a shark during the descent shows its name and lights its LED
  let z: Zustand = zustand(offset);
  let gewaehlt: number | null = null;
  let gewaehltBis = 0;
  let unten: { x: number; y: number } | null = null;
  canvas.addEventListener("pointerdown", (e) => (unten = { x: e.clientX, y: e.clientY }));
  canvas.addEventListener("pointerup", (e) => {
    if (!unten) return;
    const weg = Math.hypot(e.clientX - unten.x, e.clientY - unten.y);
    unten = null;
    if (weg > TAP_PX || z.kapitel !== 1) return;
    const led = szene.waehle(e.clientX, e.clientY);
    if (led !== null) {
      gewaehlt = led;
      gewaehltBis = performance.now() + GEWAEHLT_MS;
    }
  });

  const root = document.documentElement;
  const skala = $("skala");
  const marke = $("marke");
  const zahlBlock = $("zahl-block");
  const art = $("art");
  const akt = $("akt");
  let tinte = "";
  let nameLed: number | null = null;

  function overlay(gewaehlt: number | null) {
    const tief = z.tiefe > HELL_BIS_M;
    const t = tief ? TINTE.dunkel : TINTE.hell;
    if (t !== tinte) {
      root.style.setProperty("--ink", (tinte = t));
      root.style.setProperty("--halo", tief ? HALO.dunkel : HALO.hell);
    }

    // depth: the marker runs down the scale, the number hangs below it at the top and
    // stands above it at the bottom, so it never leaves the screen
    const imAkt = z.kapitel === 2 && z.akt !== null && z.akt.phase < 5;
    setOpacity(skala, !imAkt);
    setOpacity(akt, imAkt);
    const tiefe = Math.max(z.tiefe, 0);
    const f = Math.min(tiefe / SKALA_M, 1);
    marke.style.top = `${(f * 100).toFixed(2)}%`;
    zahlBlock.style.transform = `translateY(-${(f * 100).toFixed(2)}%)`;
    setText($("tiefe-zahl"), Math.round(tiefe).toLocaleString("en-US"));
    setText($("zaehler"), String(z.zaehler));

    // the name appears once the camera has arrived at the station
    const led = gewaehlt ?? (z.kapitel === 1 && z.blick.f >= 1 ? z.featured : null);
    setOpacity(art, led !== null);
    if (led !== null && led !== nameLed) {
      nameLed = led;
      const a = ARTEN[led - 1];
      const ja = $("art-ja");
      // one species has no Japanese name in the data; it shows its scientific name instead
      setText(ja, a.name_ja || a.species);
      ja.lang = a.name_ja ? "ja" : "la";
      ja.style.fontStyle = a.name_ja ? "normal" : "italic";
      setText($("art-en"), a.name_en);
      $("art-punkt").style.background = STUFE_FARBE[STUFE_INDEX[a.tier]];
    }
    if (nameLed !== null) setzeName(nameLed);
  }

  function setzeName(led: number) {
    const p = szene.bildschirm(led);
    if (!p) {
      art.style.visibility = "hidden";
      return;
    }
    art.style.visibility = "visible";
    const w = art.offsetWidth;
    const h = art.offsetHeight;
    // centred under the shark, which swims across the view, kept clear of the depth scale
    const x = Math.min(Math.max(p.x - w / 2, 56), window.innerWidth - SKALA_BREITE - w);
    const y = Math.min(Math.max(p.y + ABSTAND, 160), window.innerHeight - 120 - h);
    art.style.transform = `translate(${x.toFixed(1)}px, ${y.toFixed(1)}px)`;
  }

  function frame(now: number) {
    const t = halt ? offset : now - t0;
    z = zustand(t);
    if (gewaehlt !== null && (performance.now() > gewaehltBis || z.kapitel !== 1)) gewaehlt = null;
    szene.render(t / 1000, z, gewaehlt);
    overlay(gewaehlt);
    modell.senden(gewaehlt !== null ? `S ${gewaehlt}` : befehl(z));
    requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);
}
