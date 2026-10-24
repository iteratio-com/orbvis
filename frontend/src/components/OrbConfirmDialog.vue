<template>
  <CmkPopupDialog :open="open" :icon="icon" :title="title" @close="$emit('cancel')">
    <CmkParagraph v-if="message" class="orb-confirm-dialog__message">
      {{ message }}
    </CmkParagraph>
    <div class="orb-confirm-dialog__actions">
      <CmkButton :variant="confirmVariant" @click="$emit('confirm')">
        {{ confirmLabel || _t('Confirm') }}
      </CmkButton>
      <CmkButton variant="secondary" @click="$emit('cancel')">
        {{ cancelLabel || _t('Cancel') }}
      </CmkButton>
    </div>
  </CmkPopupDialog>
</template>

<script setup lang="ts">
import { computed } from 'vue'

import CmkButton from '@/components/cmk/CmkButton'
import CmkPopupDialog from '@/components/cmk/CmkPopupDialog'
import CmkParagraph from '@/components/cmk/typography/CmkParagraph'

import usei18n from '@/vendor/cmk/lib/i18n'

type DialogVariant = 'error' | 'warning' | 'success' | 'info'
type ButtonVariant =
  'primary' | 'secondary' | 'optional' | 'success' | 'warning' | 'danger' | 'info'

const props = withDefaults(
  defineProps<{
    open: boolean
    title: string
    message?: string
    confirmLabel?: string
    cancelLabel?: string
    confirmVariant?: ButtonVariant
    variant?: DialogVariant
  }>(),
  {
    message: '',
    confirmLabel: '',
    cancelLabel: '',
    confirmVariant: 'warning',
    variant: 'warning'
  }
)

defineEmits<{ confirm: []; cancel: [] }>()
const { _t } = usei18n()

const ICON_BY_VARIANT: Record<DialogVariant, string> = {
  error: 'error',
  warning: 'warning',
  success: 'success',
  info: 'info-circle'
}
const icon = computed(() => ICON_BY_VARIANT[props.variant])
</script>

<style scoped>
.orb-confirm-dialog__message {
  margin-bottom: var(--dimension-6);
}

.orb-confirm-dialog__actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--dimension-3);
}
</style>
