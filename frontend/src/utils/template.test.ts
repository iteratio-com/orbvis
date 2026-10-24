import { describe, expect, it } from 'vitest'

import type { BoardObject, MonitoringState, ObjectState } from '@/types/api'

import { sanitizeTemplateHtml } from './sanitize'
import {
  formatServicesSummary,
  interpolateTemplate,
  interpolateTemplateHtml,
  resolveTemplate
} from './template'

// Concrete builders (not Partial spreads) so the objects satisfy
// `exactOptionalPropertyTypes` without ever assigning `undefined`.
function makeObject(
  fields: {
    host_name?: string
    service_description?: string
    label?: BoardObject['label']
  } = {}
): BoardObject {
  const obj: BoardObject = { id: 'o1', type: 'host', x: 0, y: 0, url_target: '_blank' }
  if (fields.host_name !== undefined) obj.host_name = fields.host_name
  if (fields.service_description !== undefined) obj.service_description = fields.service_description
  if (fields.label !== undefined) obj.label = fields.label
  return obj
}

function makeState(
  fields: {
    state?: MonitoringState
    output?: string
    perf_data?: string
    acknowledged?: boolean
    in_downtime?: boolean
    stale?: boolean
  } = {}
): ObjectState {
  return {
    object_id: 'o1',
    type: 'host',
    state: fields.state ?? 'UP',
    output: fields.output ?? '',
    perf_data: fields.perf_data ?? '',
    acknowledged: fields.acknowledged ?? false,
    in_downtime: fields.in_downtime ?? false,
    stale: fields.stale ?? false
  }
}

describe('interpolateTemplate', () => {
  it('resolves basic object/state placeholders', () => {
    const obj = makeObject({ host_name: 'web01', service_description: 'CPU' })
    const state = makeState({ state: 'WARNING', output: 'high load' })
    const out = interpolateTemplate('{{host}}/{{service}} is {{state}}: {{output}}', obj, state)
    expect(out).toBe('web01/CPU is WARNING: high load')
  })

  it('uses the label text for {{name}} when set', () => {
    const obj = makeObject({
      host_name: 'web01',
      label: {
        show: true,
        text: 'Frontend',
        x: 0,
        y: 0,
        size: 10,
        color: '#fff',
        background: 'transparent'
      }
    })
    expect(interpolateTemplate('{{name}}', obj, makeState())).toBe('Frontend')
  })

  it('{{output}} is the first line only, {{long_output}} keeps everything', () => {
    const state = makeState({ output: 'summary line\ndetail 1\ndetail 2' })
    expect(interpolateTemplate('{{output}}', makeObject(), state)).toBe('summary line')
    expect(interpolateTemplate('{{long_output}}', makeObject(), state)).toBe(
      'summary line\ndetail 1\ndetail 2'
    )
  })

  it('renders boolean flags as true/false strings', () => {
    const state = makeState({ acknowledged: true, in_downtime: false, stale: true })
    expect(
      interpolateTemplate('{{acknowledged}} {{in_downtime}} {{stale}}', makeObject(), state)
    ).toBe('true false true')
  })

  it('resolves the first perf metric and a named metric', () => {
    const state = makeState({ perf_data: 'rta=0.5ms;100;200 pl=0%' })
    expect(interpolateTemplate('{{metric}}', makeObject(), state)).toBe('0.5ms')
    expect(interpolateTemplate('{{metric_unit}}', makeObject(), state)).toBe('ms')
    expect(interpolateTemplate('{{metric:pl}}', makeObject(), state)).toBe('0%')
  })

  it('returns empty string for an unknown named metric', () => {
    const state = makeState({ perf_data: 'rta=0.5ms' })
    expect(interpolateTemplate('[{{metric:missing}}]', makeObject(), state)).toBe('[]')
  })

  it('ignores inherited object properties as placeholders', () => {
    expect(interpolateTemplate('[{{constructor}}][{{toString}}]', makeObject(), makeState())).toBe(
      '[][]'
    )
  })

  it('returns empty string for unknown placeholders and missing state', () => {
    expect(interpolateTemplate('[{{nope}}]', makeObject(), undefined)).toBe('[]')
    expect(interpolateTemplate('[{{state}}]', makeObject(), undefined)).toBe('[]')
  })
})

describe('interpolateTemplateHtml → sanitizeTemplateHtml pipeline', () => {
  // The hover / context menu render this pair via v-html. Plugin output comes
  // from the monitored device, so the values are escaped before the template's
  // own markup goes through the sanitizer.
  function render(template: string, state: ObjectState): string {
    return sanitizeTemplateHtml(interpolateTemplateHtml(template, makeObject(), state))
  }

  it('keeps the markup of the template itself', () => {
    expect(render('<b>{{state}}</b>', makeState({ state: 'DOWN' }))).toBe('<b>DOWN</b>')
  })

  it('renders a <script> smuggled through plugin output as text', () => {
    const html = render('<b>{{output}}</b>', makeState({ output: '<script>alert(1)</script>SAFE' }))
    expect(html).toBe('<b>&lt;script&gt;alert(1)&lt;/script&gt;SAFE</b>')
  })

  it('renders tags the sanitizer would allow as text, too', () => {
    // <img> and <a> are allowed template markup; from plugin output they must
    // not turn into elements (tracking pixels, phishing links).
    const html = render(
      '{{output}}',
      makeState({ output: '<img src=x onerror="alert(1)"><a href="https://evil">x</a>' })
    )
    expect(html).not.toContain('<img')
    expect(html).not.toContain('<a')
    expect(html).toContain('&lt;img')
  })

  it('escapes values inside attributes of the template', () => {
    const html = render(
      '<a href="https://cmk/{{output}}">go</a>',
      makeState({ output: '" onclick="alert(1)' })
    )
    const link = new DOMParser().parseFromString(html, 'text/html').querySelector('a')
    expect(link?.hasAttribute('onclick')).toBe(false)
    expect(link?.getAttribute('href')).toBe('https://cmk/" onclick="alert(1)')
  })

  it('escapes raw perf data', () => {
    const html = render('{{perf_data}}', makeState({ perf_data: "'<b>x</b>'=1;;;" }))
    expect(html).not.toContain('<b>')
    expect(html).toContain('&lt;b&gt;')
  })

  it('keeps markup from the board configuration, which editors own', () => {
    const obj = makeObject({
      host_name: 'web01',
      label: {
        show: true,
        text: '<b>Core</b>&nbsp;Switch',
        x: 0,
        y: 0,
        size: 11,
        color: '#fff',
        background: 'transparent'
      }
    })
    const html = sanitizeTemplateHtml(
      interpolateTemplateHtml('{{name}} {{host}}', obj, makeState())
    )
    expect(html).toBe('<b>Core</b>\u00a0Switch web01')
  })
})

describe('interpolateTemplate (text contexts)', () => {
  it('leaves values unescaped for plain-text rendering', () => {
    expect(
      interpolateTemplate('{{output}}', makeObject(), makeState({ output: 'a < b & c' }))
    ).toBe('a < b & c')
  })
})

describe('resolveTemplate', () => {
  it('prefers object, then map, then global', () => {
    expect(resolveTemplate('obj', 'map', 'global')).toBe('obj')
    expect(resolveTemplate(null, 'map', 'global')).toBe('map')
    expect(resolveTemplate('', '', 'global')).toBe('global')
    expect(resolveTemplate(null, undefined, null)).toBeNull()
  })
})

describe('formatServicesSummary', () => {
  it('orders counts worst-first and omits zero buckets', () => {
    expect(formatServicesSummary({ ok: 12, warning: 2, critical: 1, unknown: 0, pending: 0 })).toBe(
      '1 CRIT · 2 WARN · 12 OK'
    )
  })

  it('returns empty string when there is no summary', () => {
    expect(formatServicesSummary(undefined)).toBe('')
  })
})
