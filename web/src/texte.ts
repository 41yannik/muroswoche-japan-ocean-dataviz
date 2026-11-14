// All screen texts, English and Japanese. Edit here; no code change needed.
// The Japanese is a draft: a native speaker should proofread it before the exhibition.

export interface Zweisprachig {
  en: string;
  ja: string;
}

/** The vertical title is the Japanese name of the bay; the Latin name stands beside it. */
export const TITEL: Zweisprachig = { ja: "相模湾", en: "Sagami Bay" };
export const UNTERTITEL: Zweisprachig = { en: "109 shark species", ja: "サメ109種" };

/** the word under the depth number */
export const TIEFE: Zweisprachig = { en: "depth", ja: "水深" };

/** the act: the counter, its unit and one line */
export const ARTEN: Zweisprachig = { en: "species", ja: "種" };
export const AKT: Zweisprachig = {
  en: "A thought experiment: the threatened species vanish, tier by tier.",
  ja: "思考実験：危険度の高い順に種が消えたら",
};

/** Index = tier: 0 not threatened, 1 VU, 2 EN, 3 CR (IUCN Red List). */
export const STUFE: Zweisprachig[] = [
  { en: "Not threatened", ja: "低い" },
  { en: "Vulnerable", ja: "危急" },
  { en: "Endangered", ja: "危機" },
  { en: "Critically endangered", ja: "深刻な危機" },
];

export const STATUS = {
  connected: "Model connected",
  connecting: "Connecting to the model",
  disconnected: "Model not connected",
  unsupported: "Open this page in Chrome to drive the model",
  button: "Connect model",
};

export const QUELLEN = "Sources: IUCN Red List, FishBase, OBIS, SRTM15+, JAMSTEC";
