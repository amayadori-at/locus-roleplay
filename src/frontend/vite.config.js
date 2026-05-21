import { svelte } from "@sveltejs/vite-plugin-svelte";
import { defineConfig } from "vite";

const backendUrl = process.env.LOCUS_BACKEND_URL || "http://127.0.0.1:8787";

export default defineConfig({
  plugins: [svelte()],
  server: {
    port: 5173,
    proxy: {
      "/api": backendUrl
    }
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes("node_modules/@xyflow")) return "vendor-xyflow";
          if (id.includes("node_modules")) return "vendor";
        }
      }
    }
  }
});
