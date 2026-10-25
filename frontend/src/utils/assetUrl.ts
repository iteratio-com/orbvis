// A stored icon/background reference is a bare filename; encoding it keeps a
// value with a path separator inside its asset directory and keeps quotes out
// of the HTML strings Leaflet markers are built from.
export function imageAssetUrl(name: string): string {
  return `${import.meta.env.BASE_URL}images/${encodeURIComponent(name)}`
}

export function backgroundAssetUrl(name: string): string {
  return `${import.meta.env.BASE_URL}boards/backgrounds/${encodeURIComponent(name)}`
}
