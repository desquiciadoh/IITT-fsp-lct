import js from '@eslint/js'
import globals from 'globals'
import tseslint from 'typescript-eslint'
import reactHooks from 'eslint-plugin-react-hooks'

export default tseslint.config(
  {
    ignores: [
      'dist/',
      'openapi/',
      'src/api/generated/',
      'node_modules/',
      '.vite/',
      'public/',
      'playwright-report/',
      'test-results/',
    ],
  },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ['scripts/**/*.mjs'],
    languageOptions: { globals: globals.node },
  },
  {
    files: ['*.config.{js,ts}', 'vite.config.ts'],
    languageOptions: { globals: { ...globals.node, ...globals.browser } },
  },
  {
    files: ['e2e/**/*.ts'],
    languageOptions: { globals: globals.node },
  },
  {
    files: ['**/*.{ts,tsx}'],
    languageOptions: {
      ecmaVersion: 2022,
      globals: globals.browser,
    },
    plugins: { 'react-hooks': reactHooks },
    rules: {
      'react-hooks/rules-of-hooks': 'error',
      'react-hooks/exhaustive-deps': 'warn',
      '@typescript-eslint/no-unused-vars': [
        'error',
        { argsIgnorePattern: '^_', varsIgnorePattern: '^_' },
      ],
      // R28: orval's `client: 'fetch'` still emits a full client we never use.
      // The app calls the API through the hand-written hooks in `src/api/*.ts`
      // (customFetch adds CSRF and translates problem+json), so block the
      // generated client instead of deleting it from the `api:gen` output.
      'no-restricted-imports': [
        'error',
        {
          paths: [
            {
              name: '@/api/generated/fSPDraftAPI',
              message: 'Use the hooks in src/api/*.ts (customFetch adds CSRF and parses problem+json).',
            },
          ],
        },
      ],
    },
  },
)
