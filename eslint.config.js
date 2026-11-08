// ESLint flat config for every TypeScript package (Section 9.1):
// typescript-eslint strict-type-checked plus react-hooks; formatting is Prettier's job.
import js from "@eslint/js";
import reactHooks from "eslint-plugin-react-hooks";
import globals from "globals";
import tseslint from "typescript-eslint";

export default tseslint.config(
  {
    ignores: [
      "**/node_modules/**",
      "**/dist/**",
      "**/out/**",
      "**/release/**",
      "**/coverage/**",
      ".venv/**",
      "packages/ts/protocol/src/generated/**",
    ],
  },
  js.configs.recommended,
  ...tseslint.configs.strictTypeChecked,
  {
    languageOptions: {
      parserOptions: {
        projectService: true,
        tsconfigRootDir: import.meta.dirname,
      },
    },
    rules: {
      "@typescript-eslint/no-explicit-any": "error",
      "@typescript-eslint/restrict-template-expressions": ["error", { allowNumber: true }],
      "@typescript-eslint/no-unused-vars": ["error", { argsIgnorePattern: "^_", varsIgnorePattern: "^_" }],
    },
  },
  {
    files: ["apps/desktop/src/renderer/**/*.{ts,tsx}", "packages/ts/ui-kit/**/*.{ts,tsx}"],
    plugins: { "react-hooks": reactHooks },
    languageOptions: { globals: globals.browser },
    rules: reactHooks.configs.recommended.rules,
  },
  {
    files: ["apps/desktop/src/main/**/*.ts", "apps/desktop/src/preload/**/*.ts", "**/*.config.{js,ts}"],
    languageOptions: { globals: globals.node },
  },
  {
    files: ["**/*.js"],
    ...tseslint.configs.disableTypeChecked,
  },
);
