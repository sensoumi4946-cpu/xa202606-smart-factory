// Smoke tests for build configuration.

import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

function repoFile(relativePath: string): string {
  return readFileSync(
    fileURLToPath(new URL(`../../${relativePath}`, import.meta.url)),
    'utf-8',
  )
}

const pkg = JSON.parse(repoFile('package.json')) as {
  name: string
  scripts: Record<string, string>
  dependencies: Record<string, string>
  devDependencies: Record<string, string>
}

describe('package.json', () => {
  it('is the dashboard package', () => {
    expect(pkg.name).toBe('smart-factory-dashboard')
  })

  it('exposes the scripts CI depends on', () => {
    expect(pkg.scripts.dev).toBeDefined()
    expect(pkg.scripts.build).toBeDefined()
    expect(pkg.scripts.test).toBeDefined()
  })

  it('typechecks as part of the build', () => {
    // `vite build` alone would ship a bundle with type errors in it.
    expect(pkg.scripts.build).toContain('vue-tsc')
  })

  it('depends on vue and echarts', () => {
    expect(pkg.dependencies.vue).toBeDefined()
    expect(pkg.dependencies.echarts).toBeDefined()
  })

  it('keeps test tooling out of production dependencies', () => {
    expect(pkg.dependencies.vitest).toBeUndefined()
    expect(pkg.devDependencies.vitest).toBeDefined()
  })
})

describe('index.html', () => {
  const html = repoFile('index.html')

  it('mounts the app', () => {
    expect(html).toContain('id="app"')
  })

  it('loads the entry module', () => {
    expect(html).toContain('/src/main.ts')
  })

  it('declares a charset', () => {
    expect(html.toLowerCase()).toContain('charset')
  })
})