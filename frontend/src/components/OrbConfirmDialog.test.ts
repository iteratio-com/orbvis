import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import { defineComponent } from 'vue'

import OrbConfirmDialog from './OrbConfirmDialog.vue'

const DialogStub = defineComponent({
  props: { title: { type: String, default: '' }, icon: { type: String, default: '' } },
  emits: ['close'],
  template: `<div class="dialog" :data-icon="icon"><h2>{{ title }}</h2><slot /></div>`
})
const ButtonStub = defineComponent({
  props: { variant: { type: String, default: '' } },
  emits: ['click'],
  template: `<button :data-variant="variant" @click="$emit('click')"><slot /></button>`
})

function render(props: Record<string, unknown> = {}) {
  return mount(OrbConfirmDialog, {
    props: { open: true, title: 'Delete board?', ...props },
    global: {
      stubs: { CmkPopupDialog: DialogStub, CmkButton: ButtonStub }
    }
  })
}

describe('OrbConfirmDialog', () => {
  it('renders the title as the dialog heading and the message in a paragraph', () => {
    const wrapper = render({ message: 'This cannot be undone.' })
    expect(wrapper.find('h2').text()).toBe('Delete board?')
    expect(wrapper.find('.orb-confirm-dialog__message').text()).toBe('This cannot be undone.')
  })

  it('omits the message paragraph when no message is given', () => {
    expect(render().find('.orb-confirm-dialog__message').exists()).toBe(false)
  })

  it('falls back to default Confirm/Cancel labels', () => {
    const buttons = render().findAll('button')
    expect(buttons).toHaveLength(2)
    expect(buttons[0]!.text()).toBe('Confirm')
    expect(buttons[1]!.text()).toBe('Cancel')
  })

  it('uses custom labels when provided', () => {
    const buttons = render({ confirmLabel: 'Delete', cancelLabel: 'Keep' }).findAll('button')
    expect(buttons[0]!.text()).toBe('Delete')
    expect(buttons[1]!.text()).toBe('Keep')
  })

  it('emits confirm / cancel from the respective buttons', async () => {
    const wrapper = render()
    const buttons = wrapper.findAll('button')
    await buttons[0]!.trigger('click')
    await buttons[1]!.trigger('click')
    expect(wrapper.emitted('confirm')).toHaveLength(1)
    expect(wrapper.emitted('cancel')).toHaveLength(1)
  })

  it('emits cancel when the dialog is dismissed (overlay / close)', () => {
    const wrapper = render()
    wrapper.findComponent(DialogStub).vm.$emit('close')
    expect(wrapper.emitted('cancel')).toHaveLength(1)
  })

  it('maps the variant to a dialog icon and keeps the confirm-button variant independent', () => {
    const wrapper = render({ variant: 'error', confirmVariant: 'danger' })
    expect(wrapper.find('.dialog').attributes('data-icon')).toBe('error')
    expect(wrapper.findAll('button')[0]!.attributes('data-variant')).toBe('danger')
  })
})
