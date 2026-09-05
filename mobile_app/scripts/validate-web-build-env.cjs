const requiredNames = [
  'EXPO_PUBLIC_FIREBASE_API_KEY',
  'EXPO_PUBLIC_FIREBASE_AUTH_DOMAIN',
  'EXPO_PUBLIC_FIREBASE_PROJECT_ID',
  'EXPO_PUBLIC_FIREBASE_STORAGE_BUCKET',
  'EXPO_PUBLIC_FIREBASE_MESSAGING_SENDER_ID',
  'EXPO_PUBLIC_FIREBASE_APP_ID',
];

const missing = requiredNames.filter((name) => !process.env[name]?.trim());
if (missing.length > 0) {
  throw new Error(`Configuracao Firebase incompleta para o build: ${missing.join(', ')}.`);
}
if (process.env.EXPO_PUBLIC_TRQ_BEC_API_URL !== 'https://api.liberrotas.com.br') {
  throw new Error('O build Web de producao exige a URL HTTPS oficial da API.');
}
// Informa apenas o resultado: valores de configuracao nao devem aparecer no log.
console.log('Configuracao publica do build Web validada.');
