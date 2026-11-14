import { defineConfig } from "astro/config";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  server: { host: "127.0.0.1", port: 4321 },
  // the toolbar is dev-only chrome; off so the exhibition preview stays clean
  devToolbar: { enabled: false },
  vite: { plugins: [tailwindcss()] },
});
