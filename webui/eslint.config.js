// Deliberately narrow. This is not a style linter — Prettier and vue-tsc already cover
// formatting and types. It exists for the class of bug that shipped twice this month:
// an error swallowed by an empty `catch`, and a template key that resolved to its own
// name because the locale file had no entry. Both are invisible at compile time and
// both reached the person using the panel.
import js from '@eslint/js'
import pluginVue from 'eslint-plugin-vue'
import globals from 'globals'
import tseslint from 'typescript-eslint'

/**
 * `no-empty` is not enough: it deliberately ignores a block that contains only a
 * comment. Every silent failure in this panel looked exactly like that —
 *
 *     } catch {
 *       /* clipboard needs a secure context *\/
 *     }
 *
 * — so the comment made the block "non-empty" to ESLint while the error was still
 * discarded. This rule counts statements instead of characters.
 *
 * Two ways to satisfy it, and both require saying something out loud:
 *   1. put a statement in the block (recover, return a fallback, rethrow);
 *   2. or start the comment with `fallback:` / `degraded:` / `ignored:` — an explicit
 *      declaration that doing nothing here is the intended behaviour. Grep for that
 *      prefix and you get an audit list of every place the panel swallows an error.
 */
const JUSTIFIED = /^\s*(fallback|degraded|ignored)\s*:/i

const localPlugin = {
  rules: {
    'no-silent-catch': {
      meta: {
        type: 'problem',
        docs: { description: 'a catch that neither recovers nor reports the failure' },
        schema: [],
        messages: {
          silent:
            'A catch block must do something: recover, fall back, or surface the reason. If doing nothing is correct, start the comment with `fallback:`, `degraded:` or `ignored:` so the decision is visible.',
        },
      },
      create(context) {
        return {
          CatchClause(node) {
            if (node.body.body.length > 0) return
            const comments = context.sourceCode.getCommentsInside(node.body)
            if (comments.some((comment) => JUSTIFIED.test(comment.value))) return
            context.report({ node, messageId: 'silent' })
          },
        }
      },
    },
  },
}

export default [
  {
    ignores: ['dist/**', 'node_modules/**'],
  },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  ...pluginVue.configs['flat/recommended'],
  {
    files: ['**/*.{ts,vue}'],
    languageOptions: {
      ecmaVersion: 'latest',
      sourceType: 'module',
      globals: { ...globals.browser },
      parserOptions: {
        parser: tseslint.parser,
      },
    },
    plugins: { local: localPlugin },
    rules: {
      // The rule this file exists for.
      'local/no-silent-catch': 'error',
      'no-empty': ['error', { allowEmptyCatch: false }],
      // `any` is the API boundary's current shape (`request<any>` on a dozen routes).
      // Replacing it with precise types is its own task; turning it into a build error
      // now would bury the two rules above under 79 unrelated failures.
      '@typescript-eslint/no-explicit-any': 'off',
      'no-void': 'off',
      '@typescript-eslint/no-floating-promises': 'off',
      // Vue templates use single-word component names in this codebase; not a defect.
      'vue/multi-word-component-names': 'off',
      // Formatting is Prettier's job; enabling these produces noise that hides the two
      // rules above, which are the reason this file exists.
      'vue/max-attributes-per-line': 'off',
      'vue/singleline-html-element-content-newline': 'off',
      'vue/html-self-closing': 'off',
      'vue/html-indent': 'off',
      'vue/html-closing-bracket-newline': 'off',
      'vue/attributes-order': 'off',
      'vue/first-attribute-linebreak': 'off',
      'vue/multiline-html-element-content-newline': 'off',
    },
  },
  {
    files: ['scripts/**/*.mjs'],
    languageOptions: { globals: { ...globals.node } },
  },
]
