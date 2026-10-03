import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import type { BoardObject as BoardObjectType } from '@/types/api'

import BoardObject from './BoardObject.vue'

function makeImageObject(overrides: Partial<BoardObjectType> = {}): BoardObjectType {
  return {
    id: 'image_1',
    type: 'image',
    x: 100,
    y: 100,
    image_src: 'box.svg',
    label: { show: false, x: 0, y: 0, size: 11, color: '#fff', background: 'transparent' },
    url_target: '_blank',
    z: 1,
    ...overrides
  }
}

function imgStyle(object: BoardObjectType, iconSize: number): CSSStyleDeclaration {
  const wrapper = mount(BoardObject, { props: { object, state: undefined, iconSize } })
  return (wrapper.find('img.orb-obj__icon-img').element as HTMLImageElement).style
}

describe('BoardObject – image size', () => {
  it('scales an image to an explicit image_size, keeping its aspect', () => {
    const style = imgStyle(
      makeImageObject({
        display: { mode: 'icon', image: 'box.svg', image_size: 100 }
      }),
      100
    )
    expect(style.width).toBe('100px')
    expect(style.height).toBe('100px')
    expect(style.objectFit).toBe('contain')
  })

  it('only caps an image at the board icon size without an explicit image_size', () => {
    const style = imgStyle(makeImageObject(), 32)
    expect(style.width).toBe('')
    expect(style.maxWidth).toBe('32px')
    expect(style.maxHeight).toBe('32px')
  })
})
