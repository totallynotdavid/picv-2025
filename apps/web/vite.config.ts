import { mdsvex } from "mdsvex";
import tailwindcss from "@tailwindcss/vite";
import adapterAuto from "@sveltejs/adapter-auto";
import adapterNode from "@sveltejs/adapter-node";
import { sveltekit } from "@sveltejs/kit/vite";
import { defineConfig } from "vite";

const adapter = process.env.ADAPTER === "node" ? adapterNode() : adapterAuto();

export default defineConfig({
  plugins: [
    tailwindcss(),
    sveltekit({
      compilerOptions: {
        // Enable runes for project files, not for dependencies.
        runes: ({ filename }) =>
          filename.split(/[/\\]/).includes("node_modules") ? undefined : true,
      },

      adapter,
      preprocess: [mdsvex({ extensions: [".svx", ".md"] })],
      extensions: [".svelte", ".svx", ".md"],
      typescript: {
        config: (config) => ({
          ...config,
          include: [...config.include, "../drizzle.config.ts"],
        }),
      },
    }),
  ],
});
