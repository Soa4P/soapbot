/**
 * Two overlapping reloads used to settle in whatever order the network returned them.
 *
 * The visible symptom was a panel showing the *older* snapshot after pressing refresh,
 * or — worse — correct data with a red error banner on top, because a stale rejection
 * landed after a fresh success. These tests pin the ordering rules, not the markup:
 * only the newest request may write data, write an error, or clear the spinner.
 */
import { mount } from '@vue/test-utils'
import { defineComponent } from 'vue'
import { describe, expect, it, vi } from 'vitest'

import { ApiError } from '@/api/client'
import { useAsync } from './useAsync'

interface Deferred<T> {
  promise: Promise<T>
  resolve: (value: T) => void
  reject: (reason: unknown) => void
}

function deferred<T>(): Deferred<T> {
  let resolve!: (value: T) => void
  let reject!: (reason: unknown) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

/** `useAsync` registers `onMounted`, so it has to run inside a real component. */
function mountHook(loader: () => Promise<string>) {
  let hook!: ReturnType<typeof useAsync<string>>
  const wrapper = mount(
    defineComponent({
      setup() {
        hook = useAsync(loader)
        return () => null
      },
    }),
  )
  return { hook, wrapper }
}

/** Build a loader that hands out one deferred per call, in order. */
function queuedLoader(queue: Deferred<string>[]) {
  return vi.fn(() => {
    const next = queue.shift()
    if (!next) throw new Error('loader called more times than the test queued')
    return next.promise
  })
}

describe('useAsync request sequencing', () => {
  it('keeps the newest result when an older request settles later', async () => {
    const first = deferred<string>()
    const second = deferred<string>()
    const loader = queuedLoader([first, second])
    const { hook } = mountHook(loader)

    // Mount already fired one request; this is the second, i.e. the newest.
    const newest = hook.reload()
    expect(loader).toHaveBeenCalledTimes(2)

    second.resolve('new')
    await newest
    first.resolve('old')
    await Promise.resolve()

    expect(hook.data.value).toBe('new')
  })

  it('does not let a stale failure overwrite a fresh success', async () => {
    const first = deferred<string>()
    const second = deferred<string>()
    const loader = queuedLoader([first, second])
    const { hook } = mountHook(loader)

    const newest = hook.reload()
    second.resolve('fresh')
    await newest

    first.reject(new ApiError(500, 'boom'))
    await Promise.resolve()

    expect(hook.data.value).toBe('fresh')
    expect(hook.error.value).toBe('')
  })

  it('keeps the spinner on until the newest request settles', async () => {
    const first = deferred<string>()
    const second = deferred<string>()
    const loader = queuedLoader([first, second])
    const { hook } = mountHook(loader)

    const newest = hook.reload()
    expect(hook.loading.value).toBe(true)

    // The older request finishing first must not hide that one is still outstanding.
    first.resolve('old')
    await Promise.resolve()
    expect(hook.loading.value).toBe(true)

    second.resolve('new')
    await newest
    expect(hook.loading.value).toBe(false)
  })

  it('reports the failure of the newest request', async () => {
    const only = deferred<string>()
    const loader = queuedLoader([only])
    const { hook } = mountHook(loader)

    only.reject(new ApiError(503, 'not initialised'))
    await Promise.resolve()

    expect(hook.error.value).toBe('not initialised')
    expect(hook.loading.value).toBe(false)
  })
})
