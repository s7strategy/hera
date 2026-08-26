import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Onde o app fica pendurado no dominio. Na raiz (Vercel dedicado, vite dev) e
// "/"; publicado como subpasta do site da HERA e "/mapa/". O build le de
// APP_BASE para o mesmo codigo servir os dois sem gambiarra de caminho.
const base = process.env.APP_BASE || "/";

// Build de arquivo unico: um chunk so. Com code splitting o modulo de entrada
// `import`a os chunks vizinhos, e um HTML que inlina so as tags <script> do
// index continua dependendo desses arquivos — o "arquivo unico" abria em
// branco, com erro de CORS, ao ser aberto direto do disco.
const arquivoUnico = process.env.APP_BUNDLE_UNICO === "1";

export default defineConfig({
  base,
  plugins: [react()],
  build: {
    outDir: "dist",
    sourcemap: false,
    rollupOptions: {
      output: arquivoUnico
        ? { inlineDynamicImports: true }
        : {
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
