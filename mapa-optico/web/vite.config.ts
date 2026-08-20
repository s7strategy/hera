import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
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
