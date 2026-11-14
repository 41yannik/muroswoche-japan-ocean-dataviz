// The two Node APIs ablauf.test.ts uses to read the sketch. Declared here so the
// type check passes without pulling in @types/node for a browser project.
declare module "node:fs" {
  export function readFileSync(path: string, encoding: "utf8"): string;
}
declare module "node:url" {
  export function fileURLToPath(url: string | URL): string;
}
