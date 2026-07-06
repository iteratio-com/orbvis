# cmk-additions/

OrbVis-owned files that follow cmk-frontend-vue layout and style but have
no upstream counterpart — they are NOT part of the vendored tree under
`src/vendor/cmk/` and are not subject to the vendor drift-check:

- `form/private/forms/FormOrb*.vue` — OrbVis custom FormSpec widgets,
  registered via `src/composables/orbFormComponents.ts`.

The relative paths mirror the cmk-frontend-vue source layout on purpose:
the checkmk-integration generator (in preparation, see
`docs/architecture.md` "Long-term") relocates this directory into the
generated built-in tree with a predictable path mapping.

Unlike `src/vendor/cmk/`, everything here is linted/formatted with the
regular OrbVis toolchain and may be edited freely.
