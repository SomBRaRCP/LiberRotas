/**
 * Configuração de análise estática criada pelo Expo SDK 56.
 *
 * O preset flat do Expo reúne regras adequadas para React, React Native e
 * TypeScript. A pasta dist é ignorada porque contém artefatos gerados e não
 * código-fonte mantido pela equipe.
 * Referência: https://docs.expo.dev/guides/using-eslint/
 */
const { defineConfig } = require('eslint/config');
const expoConfig = require("eslint-config-expo/flat");

module.exports = defineConfig([
  expoConfig,
  {
    ignores: ["dist/*"],
  }
]);
