// StatsBar.tsx — Persistent top bar showing graph stats with 5s auto-refresh

import { useState, useEffect, useCallback } from 'react'
import * as api from '../api/client'
import type { GraphStats } from '../types/graph'

interface StatsBarProps {
  onReset: () => void
}

export default function StatsBar({ onReset }: StatsBarProps) {
  const [stats, setStats] = useState<GraphStats | null>(null)
  const [resetting, setResetting] = useState(false)

  const loadStats = useCallback(() => {
    api.fetchStats()
      .then(setStats)
      .catch(() => {
        // Silently ignore — backend may not be ready yet
      })
  }, [])

  useEffect(() => {
    loadStats()
    const id = setInterval(loadStats, 5000)
    return () => clearInterval(id)
  }, [loadStats])

  async function handleReset() {
    if (!confirm('Delete all resources and edges from the graph?')) return
    setResetting(true)
    try {
      await api.resetGraph()
      setStats(null)
      onReset()
    } catch {
      // ignore
    } finally {
      setResetting(false)
    }
  }

  return (
    <div className="stats-bar">
      <span className="brand">InfraGraph</span>

      {stats ? (
        <>
          <span className="stat">{stats.node_count} resources</span>
          <span className="stat">{stats.edge_count} edges</span>
          <span className="stat">{stats.isolated_count} isolated</span>
          {stats.circular_dependencies > 0 && (
            <span className="badge-red">{stats.circular_dependencies} cycles</span>
          )}
          {stats.most_connected && (
            <span className="stat" style={{ color: '#a6adc8', fontSize: 11 }}>
              most connected: <strong style={{ color: '#cdd6f4' }}>{stats.most_connected.name}</strong>
              &nbsp;({stats.most_connected.degree})
            </span>
          )}
        </>
      ) : (
        <span className="stat" style={{ color: '#45475a' }}>connecting…</span>
      )}

      <span style={{ flex: 1 }} />

      <button
        onClick={handleReset}
        disabled={resetting}
        style={{
          background: 'none',
          border: '1px solid #313244',
          color: '#f38ba8',
          cursor: 'pointer',
          padding: '3px 10px',
          borderRadius: 4,
          fontSize: 12,
          opacity: resetting ? 0.5 : 1,
        }}
      >
        {resetting ? 'Resetting…' : 'Reset graph'}
      </button>
    </div>
  )
}
