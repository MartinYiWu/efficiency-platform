import js from '@eslint/js';
import eslintConfigPrettier from 'eslint-config-prettier';
import vue from 'eslint-plugin-vue';
import globals from 'globals';
import tseslint from 'typescript-eslint';

export default tseslint.config(
  {
    ignores: [
      'dist',
      'coverage',
      'playwright-report',
      'test-results',
      'test-results-*',
      '.local-acceptance',
    ],
  },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  ...vue.configs['flat/recommended'],
  {
    files: ['scripts/**/*.mjs', 'e2e/**/*.mjs'],
    languageOptions: { globals: globals.node },
  },
  {
    files: ['**/*.{ts,vue}'],
    languageOptions: {
      globals: { ...globals.browser, ...globals.node },
      parserOptions: { parser: tseslint.parser },
    },
    rules: { 'no-irregular-whitespace': 'off', 'vue/multi-word-component-names': 'off' },
  },
  eslintConfigPrettier,
);
