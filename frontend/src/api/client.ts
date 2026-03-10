// client.ts — Typed API client for InfraGraph backend

import type { GraphData, GraphStats, ParseResult } from '../types/graph'

const BASE_URL = (import.meta.env.VITE_API_URL as string | undefined) ?? ''

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, init)
  if (!res.ok) {
    const body = await res.json().catch(() => ({ error: res.statusText }))
    throw new Error((body as { error?: string }).error ?? res.statusText)
  }
  return res.json() as Promise<T>
}

// ---------------------------------------------------------------------------
// Graph endpoints
// ---------------------------------------------------------------------------

export function fetchGraph(): Promise<GraphData> {
  return request<GraphData>('/graph')
}

export function fetchSubgraph(resourceId: string): Promise<GraphData> {
  return request<GraphData>(`/graph/resource/${encodeURIComponent(resourceId)}`)
}

export function fetchStats(): Promise<GraphStats> {
  return request<GraphStats>('/graph/stats')
}

export function resetGraph(): Promise<{ deleted: number }> {
  return request<{ deleted: number }>('/graph/reset', { method: 'POST' })
}

// ---------------------------------------------------------------------------
// Parse endpoints
// ---------------------------------------------------------------------------

function uploadFile(endpoint: string, file: File): Promise<ParseResult> {
  const form = new FormData()
  form.append('file', file)
  return request<ParseResult>(endpoint, { method: 'POST', body: form })
}

export function uploadTerraform(file: File): Promise<ParseResult> {
  return uploadFile('/parse/terraform', file)
}

export function uploadKubernetes(file: File): Promise<ParseResult> {
  return uploadFile('/parse/kubernetes', file)
}
