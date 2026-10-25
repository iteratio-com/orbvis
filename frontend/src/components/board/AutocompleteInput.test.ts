import { mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { MockInstance } from 'vitest'

import AutocompleteInput from './AutocompleteInput.vue'

let scrollIntoView: MockInstance<HTMLElement['scrollIntoView']>
const onWindowKey = vi.fn()

beforeEach(() => {
  scrollIntoView = vi.spyOn(HTMLElement.prototype, 'scrollIntoView')
  window.addEventListener('keydown', onWindowKey)
})

afterEach(() => {
  scrollIntoView.mockRestore()
  window.removeEventListener('keydown', onWindowKey)
  onWindowKey.mockReset()
  document.body.innerHTML = ''
})

async function mountOpen(suggestions: string[]) {
  const wrapper = mount(AutocompleteInput, {
    props: { modelValue: '', suggestions },
    attachTo: document.body
  })
  const input = wrapper.find('input')
  await input.trigger('focus')
  return { wrapper, input }
}

function dropdown(): Element | null {
  return document.querySelector('.orb-autocomplete__dropdown')
}

describe('AutocompleteInput', () => {
  it('keeps Escape from reaching window listeners while the list is open', async () => {
    const { wrapper, input } = await mountOpen(['alpha', 'beta'])
    expect(dropdown()).not.toBeNull()

    await input.trigger('keydown', { key: 'Escape' })
    expect(onWindowKey).not.toHaveBeenCalled()
    expect(dropdown()).toBeNull()

    // With the list already closed, a second Escape must reach the modal.
    await input.trigger('keydown', { key: 'Escape' })
    expect(onWindowKey).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })

  it('does not commit a highlight hidden by Escape', async () => {
    const { wrapper, input } = await mountOpen(['alpha', 'beta'])
    await input.trigger('keydown', { key: 'ArrowDown' })
    await input.trigger('keydown', { key: 'Escape' })
    await input.trigger('keydown', { key: 'Enter' })
    expect(wrapper.emitted('change')).toBeUndefined()
    wrapper.unmount()
  })

  it('follows the highlighted value when the suggestions are replaced', async () => {
    const { wrapper, input } = await mountOpen(['alpha', 'beta', 'gamma'])
    await input.trigger('keydown', { key: 'ArrowDown' })
    await input.trigger('keydown', { key: 'ArrowDown' })

    await wrapper.setProps({ suggestions: ['aardvark', 'alpha', 'beta', 'gamma'] })
    await input.trigger('keydown', { key: 'Enter' })
    expect(wrapper.emitted('change')).toEqual([['beta']])
    wrapper.unmount()
  })

  it('drops the highlight when the highlighted value disappears', async () => {
    const { wrapper, input } = await mountOpen(['alpha', 'beta', 'gamma'])
    await input.trigger('keydown', { key: 'ArrowDown' })
    await input.trigger('keydown', { key: 'ArrowDown' })

    await wrapper.setProps({ suggestions: ['alpha', 'gamma'] })
    await input.trigger('keydown', { key: 'Enter' })
    expect(wrapper.emitted('change')).toBeUndefined()
    wrapper.unmount()
  })

  it('scrolls the highlighted option into view on keyboard navigation', async () => {
    const { wrapper, input } = await mountOpen(['alpha', 'beta', 'gamma'])
    await input.trigger('keydown', { key: 'ArrowDown' })
    await input.trigger('keydown', { key: 'ArrowDown' })
    await wrapper.vm.$nextTick()

    const options = document.querySelectorAll('.orb-autocomplete__option')
    expect(scrollIntoView).toHaveBeenLastCalledWith({ block: 'nearest' })
    expect(scrollIntoView.mock.contexts.at(-1)).toBe(options[1])
    wrapper.unmount()
  })

  it('does not scroll when the suggestions refresh without navigation', async () => {
    const { wrapper, input } = await mountOpen(['alpha', 'beta', 'gamma'])
    await input.trigger('keydown', { key: 'ArrowDown' })
    await wrapper.vm.$nextTick()
    scrollIntoView.mockClear()

    await wrapper.setProps({ suggestions: ['aardvark', 'alpha', 'beta', 'gamma'] })
    await wrapper.vm.$nextTick()
    expect(scrollIntoView).not.toHaveBeenCalled()
    wrapper.unmount()
  })
})
