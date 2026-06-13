import { vitePreprocess } from "@sveltejs/vite-plugin-svelte";

export default {
  preprocess: vitePreprocess(),
  vitePlugin: {
    // Force runes mode for project components so legacy syntax fails the
    // build; node_modules (lucide-svelte, @xyflow/svelte) keep their own mode.
    dynamicCompileOptions({ filename }) {
      if (!filename.includes("node_modules")) {
        return { runes: true };
      }
    }
  }
};
