import js from "@eslint/js";
import jsxA11y from "eslint-plugin-jsx-a11y";
import reactHooks from "eslint-plugin-react-hooks";
import globals from "globals";
import tseslint from "typescript-eslint";
import shared from "../../eslint.config.mjs";

export default tseslint.config(
  ...shared,
  { ignores: ["dist", "demo-dist", "coverage", "playwright-report", "test-results", "demo/public"] },
  js.configs.recommended,
  ...tseslint.configs.strictTypeChecked,
  {
    languageOptions: {
      globals: { ...globals.browser },
      parserOptions: { projectService: { allowDefaultProject: ["*.mjs"] }, tsconfigRootDir: import.meta.dirname },
    },
    plugins: { "react-hooks": reactHooks, "jsx-a11y": jsxA11y },
    rules: {
      ...reactHooks.configs.recommended.rules,
      ...jsxA11y.flatConfigs.strict.rules,
      "@typescript-eslint/restrict-template-expressions": ["error", { allowNumber: true }],
      "@typescript-eslint/no-unnecessary-condition": "error",
      "@typescript-eslint/consistent-type-imports": "error",
      eqeqeq: "error",
      "no-console": ["error", { allow: ["warn", "error"] }],
    },
  },
  {
    files: ["**/*.test.{ts,tsx}", "e2e/**", "scripts/**", "*.config.*"],
    languageOptions: { globals: { ...globals.node } },
    rules: { "@typescript-eslint/no-non-null-assertion": "off" },
  },
  { files: ["*.mjs", "scripts/**"], ...tseslint.configs.disableTypeChecked },
  { files: ["scripts/**"], languageOptions: { globals: { ...globals.node } }, rules: { "no-console": "off" } },
);
