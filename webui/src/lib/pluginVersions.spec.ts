import { describe, expect, it } from 'vitest'

import { blockKey, versionKey } from './pluginVersions'

describe('versionKey', () => {
  it('treats the two- and three-component spellings as one release', () => {
    expect(versionKey('1.0')).toBe('1.0.0')
    expect(versionKey('1.0.0')).toBe('1.0.0')
    expect(versionKey('2.3.4')).toBe('2.3.4')
  })

  it('keeps a pre-release tag attached', () => {
    expect(versionKey('1.2b1')).toBe('1.2.0b1')
    expect(versionKey('1.2.3rc1')).toBe('?1.2.3rc1') // same as the backend grammar
  })

  it('strips surrounding whitespace, including a trailing newline', () => {
    expect(versionKey('1.2.3\n')).toBe('1.2.3')
    expect(versionKey('  1.2  ')).toBe('1.2.0')
  })

  it('never lets junk collide with a real release and never throws', () => {
    expect(versionKey('')).not.toBe(versionKey('0.0.0'))
    expect(versionKey('1.0.0; rm -rf /')).toMatch(/^\?/)
    expect(versionKey('not a version')).toBe('?not a version')
  })
})

describe('blockKey', () => {
  it('matches the backend key for the versions the index actually lists', () => {
    expect(blockKey('weather', '1.0')).toBe('weather@1.0.0')
    expect(blockKey('weather', '1.0.0')).toBe('weather@1.0.0')
  })

  it('normalises the name the way the manifest grammar does', () => {
    expect(blockKey('Demo', '1.2.3')).toBe(blockKey('demo', '1.2.3'))
    expect(blockKey('  Demo ', '1.2')).toBe('demo@1.2.0')
  })
})
