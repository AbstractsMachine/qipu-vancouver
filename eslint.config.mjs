// Shared ESLint flat config for the JavaScript and TypeScript in packages/. A package imports it and adds its own rules.
export default [
  {
    ignores: ["**/node_modules/**", "**/dist/**", "**/build/**", "**/coverage/**"],
  },
  {
    files: ["**/*.{js,mjs,ts,tsx}"],
    languageOptions: { ecmaVersion: 2023, sourceType: "module" },
    rules: {
      "no-unused-vars": "error",
      "no-undef": "error",
      eqeqeq: "error",
      "prefer-const": "error",
    },
  },
];
