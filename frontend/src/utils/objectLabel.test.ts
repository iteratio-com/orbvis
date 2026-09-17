import { describe, expect, it } from 'vitest'

import type { BoardObject, ObjectState } from '@/types/api'

import {
  labelShowFromChoice,
  labelShowToChoice,
  resolveBoardLabelOptions,
  resolveLabelOverride,
  resolveLabelText,
  resolveLabelVisible
} from './objectLabel'

function makeObject(fields: { text?: string | null; show?: boolean } = {}): BoardObject {
  const obj: BoardObject = { id: 'o1', type: 'host', x: 0, y: 0, url_target: '_blank' }
  obj.host_name = 'web01'
  obj.label = {
    show: fields.show ?? true,
    text: fields.text ?? null,
    x: 0,
    y: 0,
    size: 10,
    color: '#fff',
    background: 'transparent'
  }
  return obj
}

function makeState(labels: Record<string, string> = {}): ObjectState {
  return {
    object_id: 'o1',
    type: 'host',
    state: 'UP',
    output: '',
    perf_data: '',
    acknowledged: false,
    in_downtime: false,
    stale: false,
    labels
  }
}

describe('resolveLabelOverride', () => {
  it('prefers the board over the global setting', () => {
    expect(resolveLabelOverride(false, true)).toBe(false)
    expect(resolveLabelOverride(true, false)).toBe(true)
  })

  it('falls back to the global setting and then to null', () => {
    expect(resolveLabelOverride(null, true)).toBe(true)
    expect(resolveLabelOverride(undefined, false)).toBe(false)
    expect(resolveLabelOverride(null, null)).toBeNull()
  })
})

describe('resolveBoardLabelOptions', () => {
  it('prefers the board over the global settings for both values', () => {
    expect(
      resolveBoardLabelOptions(
        { label_show_override: false, label_template: 'board' },
        { label_show_override: true, label_template: 'global' }
      )
    ).toEqual({ show: false, template: 'board' })
  })

  it('falls back to the global settings and then to null', () => {
    expect(
      resolveBoardLabelOptions({}, { label_show_override: true, label_template: 'global' })
    ).toEqual({ show: true, template: 'global' })
    expect(resolveBoardLabelOptions({ label_template: '' }, {})).toEqual({
      show: null,
      template: null
    })
  })
})

describe('resolveLabelVisible', () => {
  it('lets the object decide without an override', () => {
    expect(resolveLabelVisible(makeObject({ show: true }), null)).toBe(true)
    expect(resolveLabelVisible(makeObject({ show: false }), null)).toBe(false)
  })

  it('keeps objects without label config hidden unless the caller defaults to shown', () => {
    const obj = makeObject()
    delete obj.label
    expect(resolveLabelVisible(obj, null)).toBe(false)
    expect(resolveLabelVisible(obj, undefined)).toBe(false)
    expect(resolveLabelVisible(obj, null, true)).toBe(true)
    expect(resolveLabelVisible(obj, false, true)).toBe(false)
  })

  it('an override wins over the object switch in both directions', () => {
    expect(resolveLabelVisible(makeObject({ show: true }), false)).toBe(false)
    expect(resolveLabelVisible(makeObject({ show: false }), true)).toBe(true)
  })
})

describe('resolveLabelText', () => {
  it('keeps an explicit object label text', () => {
    expect(resolveLabelText(makeObject({ text: 'Frontend' }), makeState(), '{{name}}')).toBe(
      'Frontend'
    )
  })

  it('renders the template for objects without their own text', () => {
    const state = makeState({ SSB: '12-4' })
    expect(resolveLabelText(makeObject(), state, '{{name}} — {{label:SSB}}')).toBe('web01 — 12-4')
  })

  it('returns an empty string without a template', () => {
    expect(resolveLabelText(makeObject(), makeState(), null)).toBe('')
    expect(resolveLabelText(makeObject(), makeState(), '')).toBe('')
  })
})

describe('labelShowToChoice / labelShowFromChoice', () => {
  it('round-trips the three states', () => {
    expect(labelShowToChoice(true)).toBe('always')
    expect(labelShowToChoice(false)).toBe('never')
    expect(labelShowToChoice(null)).toBe('inherit')
    expect(labelShowToChoice(undefined)).toBe('inherit')
    expect(labelShowFromChoice('always')).toBe(true)
    expect(labelShowFromChoice('never')).toBe(false)
    expect(labelShowFromChoice('inherit')).toBeNull()
  })

  it('treats an unknown or missing choice as inherit', () => {
    expect(labelShowFromChoice('nonsense')).toBeNull()
    expect(labelShowFromChoice(null)).toBeNull()
    expect(labelShowFromChoice(undefined)).toBeNull()
  })
})
