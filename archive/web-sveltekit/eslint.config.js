import js from "@eslint/js";
import svelte from "eslint-plugin-svelte";
import globals from "globals";
import ts from "typescript-eslint";
import svelteConfig from "./svelte.config.js";

const layer = (name) => [`$lib/${name}`, `$lib/${name}/**`];
const FRAMEWORKS = ["svelte", "svelte/**", "leaflet", "leaflet.*", "@sveltejs/**"];

function boundary(files, banned, extra = []) {
  return {
    files,
    ignores: ["**/*.test.ts"],
    rules: {
      "no-restricted-imports": [
        "error",
        {
          patterns: [
            { group: ["../**"], message: "Import across folders through $lib so the layer rules can see it." },
            ...banned.map((name) => ({ group: layer(name), message: `This layer must not depend on ${name}.` })),
            ...(extra.length ? [{ group: extra, message: "Domain and application stay framework free." }] : []),
          ],
        },
      ],
    },
  };
}

export default ts.config(
  { ignores: ["build/", ".svelte-kit/", "node_modules/"] },
  js.configs.recommended,
  ...ts.configs.recommended,
  ...svelte.configs.recommended,
  {
    languageOptions: { globals: { ...globals.browser } },
    // Keying the existing lists would change how Svelte reuses their DOM nodes.
    rules: { "svelte/require-each-key": "off" },
  },
  {
    files: ["**/*.svelte", "**/*.svelte.ts"],
    languageOptions: {
      parserOptions: { projectService: true, extraFileExtensions: [".svelte"], parser: ts.parser, svelteConfig },
    },
  },
  boundary(["src/lib/domain/**"], ["application", "adapters", "ui", "app"], FRAMEWORKS),
  boundary(["src/lib/application/**"], ["adapters", "ui", "app"], FRAMEWORKS),
  boundary(["src/lib/adapters/**"], ["ui", "app"]),
  boundary(["src/lib/ui/**"], ["adapters", "app"]),
);
