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
      // R28: the orval-emitted fetch client (src/api/generated/fSPDraftAPI.ts)
      // bypasses customFetch (CSRF, problem+json). It is dead code — never import
      // it; go through the api layer instead.
      'no-restricted-imports': [
        'error',
        {
          paths: [
            {
              name: '@/api/generated/fSPDraftAPI',
              message:
                'Не импортируйте сгенерированный fetch-клиент — используйте customFetch из @/api/client (R28).',
            },
          ],
          patterns: [
            {
              group: ['**/generated/fSPDraftAPI', '**/fSPDraftAPI'],
              message:
                'Не импортируйте сгенерированный fetch-клиент — используйте customFetch из @/api/client (R28).',
            },
          ],
        },
      ],
    },
  },
)
