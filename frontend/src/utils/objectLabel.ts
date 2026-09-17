import type { BoardConfig, BoardObject, GlobalSettings, ObjectState } from '@/types/api'
import { interpolateTemplate } from '@/utils/template'

/**
 * Merge the board-wide and instance-wide object-label switches.
 *
 * The board wins over the global default, and ``null`` at both levels leaves
 * the decision with each object.
 */
export function resolveLabelOverride(
  boardShow: boolean | null | undefined,
  globalShow: boolean | null | undefined
): boolean | null {
  if (typeof boardShow === 'boolean') return boardShow
  if (typeof globalShow === 'boolean') return globalShow
  return null
}

/**
 * Board-wide caption options, merged with the global settings once per board
 * instead of in every object: the visibility override and the label template.
 */
export interface BoardLabelOptions {
  show: boolean | null
  template: string | null
}

export function resolveBoardLabelOptions(
  config: Pick<BoardConfig, 'label_show_override' | 'label_template'>,
  settings: Pick<GlobalSettings, 'label_show_override' | 'label_template'>
): BoardLabelOptions {
  return {
    show: resolveLabelOverride(config.label_show_override, settings.label_show_override),
    template: config.label_template || settings.label_template || null
  }
}

/**
 * Whether the caption of a board object is rendered.
 *
 * A board-wide or instance-wide override wins over the object's own switch —
 * that is what it is for: flipping every object at once without touching each
 * one. Without an override the object decides; ``defaultShow`` covers objects
 * that carry no label config at all (hidden on regular boards, shown on the
 * worldmap, as before).
 */
export function resolveLabelVisible(
  object: BoardObject,
  override: boolean | null | undefined,
  defaultShow = false
): boolean {
  if (typeof override === 'boolean') return override
  return object.label?.show ?? defaultShow
}

/**
 * Caption text of a board object, or '' when neither the object nor a template
 * defines one (the caller then falls back to the object name, as before).
 *
 * An object with its own label text always keeps it. The template takes the
 * same placeholders as the hover template, so '{{name}} — {{label:SSB}}'
 * captions every object on a board at once.
 */
export function resolveLabelText(
  object: BoardObject,
  state: ObjectState | undefined,
  template: string | null | undefined
): string {
  if (object.label?.text) return object.label.text
  if (!template) return ''
  return interpolateTemplate(template, object, state)
}

/** The three states the board and global label switch can be in. */
export type LabelShowChoice = 'inherit' | 'always' | 'never'

/** Persisted ``bool | null`` → dropdown choice. */
export function labelShowToChoice(show: boolean | null | undefined): LabelShowChoice {
  if (show === true) return 'always'
  if (show === false) return 'never'
  return 'inherit'
}

/** Dropdown choice → persisted ``bool | null``. */
export function labelShowFromChoice(choice: string | null | undefined): boolean | null {
  if (choice === 'always') return true
  if (choice === 'never') return false
  return null
}
