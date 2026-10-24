import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { reactive } from 'vue'

import { clearDataBindingCache } from '@/composables/useDataBinding'
import { useAuthStore } from '@/stores/auth'
import type { DataElement } from '@/types/api'
import { createElement } from '@/utils/presentationElements'

import PresentationGadgetMetricField from './PresentationGadgetMetricField.vue'

const { mockConnectionsApi } = vi.hoisted(() => ({
  mockConnectionsApi: {
    objects: vi.fn().mockResolvedValue([]),
    perfMetrics: vi.fn()
  }
}))

vi.mock('@/api/client', () => ({
  connectionsApi: mockConnectionsApi
}))

function boundIcon(): DataElement {
  return {
    ...(createElement('data', 0, 0) as DataElement),
    object_type: 'service',
    host_name: 'web01',
    service_description: 'CPU load'
  }
}

describe('PresentationGadgetMetricField', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    useAuthStore().accessToken = 'tok'
    clearDataBindingCache()
    mockConnectionsApi.perfMetrics.mockReset()
    mockConnectionsApi.perfMetrics.mockResolvedValue([{ name: 'load1', title: 'CPU load' }])
  })

  it('fetches metrics when an icon element is switched to gadget mode', async () => {
    // The canvas patches elements in place (Object.assign), so the prop
    // identity never changes — only the nested display object does.
    const element = reactive(boundIcon())
    const wrapper = mount(PresentationGadgetMetricField, {
      props: { element, connectionId: 'live_1' }
    })
    await flushPromises()
    expect(mockConnectionsApi.perfMetrics).not.toHaveBeenCalled()

    Object.assign(element, { display: { mode: 'gadget' } })
    await flushPromises()

    expect(mockConnectionsApi.perfMetrics).toHaveBeenCalledWith(
      'live_1',
      'web01',
      'tok',
      'CPU load'
    )
    expect(wrapper.emitted('patch')).toBeUndefined()
  })
})
