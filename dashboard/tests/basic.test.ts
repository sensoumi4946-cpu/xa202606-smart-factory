import { describe, it, expect } from 'vitest'

describe('dashboard smoke test', () => {
  it('should have a valid package.json', async () => {
    const pkg = await import('../package.json')
    expect(pkg.name).toBe('smart-factory-dashboard')
    expect(pkg.dependencies.vue).toBeDefined()
  })

  it('should have index.html with correct title', async () => {
    const html = await import('fs').then(fs => fs.readFileSync('index.html', 'utf-8'))
    expect(html).toContain('XA-202606')
    expect(html).toContain('<title>')
    expect(html).toContain('id="app"')
  })
})
