import { describe, expect, it } from 'vitest'

import { backgroundAssetUrl, imageAssetUrl } from './assetUrl'

describe('asset URLs', () => {
  it('keeps a plain filename readable', () => {
    expect(imageAssetUrl('server.svg')).toBe('/images/server.svg')
    expect(backgroundAssetUrl('demo.png')).toBe('/boards/backgrounds/demo.png')
  })

  it('keeps a traversal attempt inside the asset directory', () => {
    expect(imageAssetUrl('../../check_mk/logout.py')).toBe('/images/..%2F..%2Fcheck_mk%2Flogout.py')
    expect(backgroundAssetUrl('../x')).toBe('/boards/backgrounds/..%2Fx')
  })

  it('encodes characters that would break out of an HTML attribute', () => {
    expect(imageAssetUrl('a" onerror="alert(1)')).not.toContain('"')
  })
})
