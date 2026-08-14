import { describe, expect, it } from 'vitest'

import { normalizeClipUrl, sortDetections } from './dashboard-data'

describe('normalizeClipUrl', () => {
  it('converts absolute local-store paths into a browser-safe API URL', () => {
    expect(normalizeClipUrl('/data/detections/clips/camera-1-20260813T215340142829Z.mp4')).toBe(
      '/api/store/clips/camera-1-20260813T215340142829Z.mp4',
    )
  })

  it('keeps already browser-safe URLs unchanged', () => {
    expect(normalizeClipUrl('/api/store/clips/example.mp4')).toBe('/api/store/clips/example.mp4')
  })
})

describe('sortDetections', () => {
  it('puts the latest detection first', () => {
    const detections = [
      { timestamp: '20260813T215340142829Z', label: 'older' },
      { timestamp: '20260813T215340190000Z', label: 'newer' },
      { timestamp: '20260813T215340180000Z', label: 'middle' },
    ]

    expect(sortDetections(detections).map((detection) => detection.label)).toEqual([
      'newer',
      'middle',
      'older',
    ])
  })
})
