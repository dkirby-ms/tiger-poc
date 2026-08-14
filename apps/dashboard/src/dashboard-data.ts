export type Detection = {
  timestamp?: string
  camera_id?: string
  label?: string
  confidence?: number
  model_id?: string
  source_id?: string
  zone?: string | null
  bbox?: number[] | null
  clip_path?: string | null
}

export function normalizeClipUrl(value?: string | null): string | null {
  if (!value) {
    return null
  }

  if (value.startsWith('/api/')) {
    return value
  }

  if (value.startsWith('/data/')) {
    const fileName = value.split('/').at(-1)
    if (!fileName) {
      return null
    }
    return `/api/store/clips/${encodeURIComponent(fileName)}`
  }

  return value
}

export function sortDetections(detections: Detection[]): Detection[] {
  return [...detections].sort((left, right) => {
    const leftKey = left.timestamp ?? ''
    const rightKey = right.timestamp ?? ''
    return rightKey.localeCompare(leftKey)
  })
}
