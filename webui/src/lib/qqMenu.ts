/**
 * Shared shapes for the QQ menu editor.
 *
 * The tree is edited through an injected reactive array + numeric path rather than by
 * passing nodes down as props: props are one-way, and a recursive editor that mutates
 * them is a form that silently edits a copy. See `QqMenuItem.vue`.
 */
import type { InjectionKey, Ref } from 'vue'

export interface MenuNode {
  name: string
  type: 'send' | 'link' | 'menu'
  reply?: string
  url?: string
  children?: MenuNode[]
}

export const QQ_MENU_KEY: InjectionKey<Ref<MenuNode[]>> = Symbol('qq-menu')

/** The node at ``path``, e.g. ``[2, 0]`` = first child of the third top-level item. */
export function nodeAt(items: MenuNode[], path: number[]): MenuNode {
  let node = items[path[0]!]!
  for (const index of path.slice(1)) {
    node = node.children![index]!
  }
  return node
}

/** Remove the node at ``path``; the root array is spliced when the path has one step. */
export function removeAt(items: MenuNode[], path: number[]): void {
  if (path.length === 1) {
    items.splice(path[0]!, 1)
    return
  }
  const parent = nodeAt(items, path.slice(0, -1))
  parent.children?.splice(path[path.length - 1]!, 1)
}
