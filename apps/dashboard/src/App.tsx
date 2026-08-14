import { useEffect, useMemo, useState } from 'react'
import './App.css'
import { normalizeClipUrl, sortDetections, type Detection } from './dashboard-data'

type HealthRecord = {
  name: string
  status: 'ok' | 'warn' | 'error'
  detail?: string
}

const serviceEndpoints = [
  { name: 'Foundry Local', url: '/api/foundry/healthz' },
  { name: 'Inference API', url: '/api/inference/healthz' },
  { name: 'Event Rules', url: '/api/rules/healthz' },
  { name: 'Local Store', url: '/api/store/healthz' },
] as const

const defaultServices = serviceEndpoints.map(({ name }) => ({
  name,
  status: 'warn' as const,
  detail: 'Waiting for service check…',
}))

function formatTimestamp(value?: string) {
  if (!value) return 'Unknown'

  const candidate = value.replace('T', ' ').replace('Z', '')
  const parsed = Date.parse(candidate)
  if (Number.isNaN(parsed)) {
    return value
  }

  return new Date(parsed).toLocaleString()
}

function App() {
  const [services, setServices] = useState<HealthRecord[]>(defaultServices)
  const [detections, setDetections] = useState<Detection[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let isMounted = true

    const refresh = async () => {
      try {
        const serviceResults: HealthRecord[] = await Promise.all(
          serviceEndpoints.map(async ({ name, url }): Promise<HealthRecord> => {
            const response = await fetch(url)
            if (!response.ok) {
              throw new Error(`${name} did not respond with a healthy status`)
            }
            const payload = (await response.json()) as { status?: string; details?: string }
            return {
              name,
              status: payload.status === 'ok' ? 'ok' : 'warn',
              detail: payload.status === 'ok' ? 'Healthy' : payload.details ?? 'Status reported but not healthy',
            }
          }),
        )

        const detectionsResponse = await fetch('/api/store/detections')
        if (!detectionsResponse.ok) {
          throw new Error('Unable to load detection records')
        }

        const detectionPayload = (await detectionsResponse.json()) as {
          detections?: Detection[]
        }

        const sortedDetections = sortDetections(detectionPayload.detections ?? []).map((detection) => ({
          ...detection,
          clip_path: normalizeClipUrl(detection.clip_path),
        }))

        if (isMounted) {
          setServices(serviceResults)
          setDetections(sortedDetections)
          setError(null)
        }
      } catch (caughtError) {
        if (isMounted) {
          setServices((current) =>
            current.map((service) => ({
              ...service,
              status: 'error',
              detail: 'Service unreachable',
            })),
          )
          setDetections([])
          setError(
            caughtError instanceof Error
              ? caughtError.message
              : 'Failed to load dashboard data from the PoC services.',
          )
        }
      } finally {
        if (isMounted) {
          setLoading(false)
        }
      }
    }

    void refresh()
    const intervalId = window.setInterval(() => {
      void refresh()
    }, 15000)

    return () => {
      isMounted = false
      window.clearInterval(intervalId)
    }
  }, [])

  const latestDetection = useMemo(() => sortDetections(detections)[0] ?? null, [detections])

  return (
    <main className="dashboard-shell">
      <header className="page-header">
        <div>
          <p className="eyebrow">Tiger PoC</p>
          <h1>Local operations dashboard</h1>
        </div>
        <div className="header-note">
          <span className="dot" />
          Source updates every 15s
        </div>
      </header>

      {error && (
        <div className="alert" role="alert">
          One or more local services are currently unreachable: {error}
        </div>
      )}

      <section className="stats-grid">
        {services.map((service) => (
          <article key={service.name} className="metric-card">
            <div className="metric-header">
              <span className={`status-indicator ${service.status}`} />
              <h2>{service.name}</h2>
            </div>
            <p className="metric-status">{service.status === 'ok' ? 'Healthy' : service.status === 'warn' ? 'Checking' : 'Unavailable'}</p>
            <p className="metric-detail">{service.detail}</p>
          </article>
        ))}
      </section>

      <section className="content-grid">
        <article className="panel preview-panel">
          <div className="panel-header">
            <h2>Latest event preview</h2>
            <span className="pill">Browser-safe</span>
          </div>

          <div className="preview-frame">
            {latestDetection?.clip_path ? (
              <video controls src={latestDetection.clip_path} />
            ) : (
              <div className="preview-placeholder">
                <strong>No saved clip is currently available.</strong>
                <span>The dashboard shows a browser-safe status instead of trying to stream RTSP directly.</span>
              </div>
            )}
          </div>

          <div className="latest-detail">
            <div>
              <label>Label</label>
              <strong>{latestDetection?.label ?? 'No detection'}</strong>
            </div>
            <div>
              <label>Confidence</label>
              <strong>{latestDetection?.confidence ? `${(latestDetection.confidence * 100).toFixed(0)}%` : '—'}</strong>
            </div>
            <div>
              <label>Camera</label>
              <strong>{latestDetection?.camera_id ?? '—'}</strong>
            </div>
          </div>
        </article>

        <article className="panel detail-panel">
          <div className="panel-header">
            <h2>Recent detections</h2>
            <span className="pill">{detections.length} events</span>
          </div>

          <ul className="detection-list">
            {detections.slice(0, 5).map((detection) => (
              <li key={`${detection.timestamp ?? 'unknown'}-${detection.label ?? 'event'}`} className="detection-item">
                <div className="detection-head">
                  <strong>{detection.label ?? 'Unknown object'}</strong>
                  <span>{detection.confidence ? `${(detection.confidence * 100).toFixed(0)}%` : '—'}</span>
                </div>
                <div className="detection-meta">
                  <span>{detection.camera_id ?? 'unknown camera'}</span>
                  <span>{formatTimestamp(detection.timestamp)}</span>
                </div>
              </li>
            ))}
          </ul>
        </article>
      </section>

      <section className="panel system-panel">
        <div className="panel-header">
          <h2>System notes</h2>
          <span className="pill subtle">Local-first</span>
        </div>
        <div className="system-notes">
          <p>
            The dashboard relies on the repo’s existing health and persistence contract. It does not assume browser-native RTSP playback.
          </p>
          <p>
            If a true live camera feed is needed later, the safest next step is a dedicated MJPEG or WebRTC proxy rather than streaming RTSP directly into the browser.
          </p>
        </div>
        <div className="status-row">
          <span>Refresh cadence</span>
          <strong>{loading ? 'Loading…' : '15 seconds'}</strong>
        </div>
      </section>
    </main>
  )
}

export default App
