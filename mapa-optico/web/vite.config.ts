import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Onde o app fica pendurado no dominio. Na raiz (Vercel dedicado, vite dev) e
// "/"; publicado como subpasta do site da HERA e "/mapa/". O build le de
// APP_BASE para o mesmo codigo servir os dois sem gambiarra de caminho.
const base = process.env.APP_BASE || "/";

export default defineConfig({
  base,
  plugins: [react()],
  build: {
    outDir: "dist",
    sourcemap: false,
    rollupOptions: {
      output: {
        // maplibre e supabase mudam pouco: chunk separado para o cache do
        // navegador nao ser invalidado a cada ajuste da interface.
        manualChunks: {
          maplibre: ["maplibre-gl"],
          supabase: ["@supabase/supabase-js"],
        },
      },
    },
  },
  server: { port: 5173 },
});
