// useGraph.ts — Central state hook for graph data, selection, and uploads

import { useState, useEffect, useCallback } from 'react'
import type { GraphNode, GraphEdge, ParseResult } from '../types/graph'
import * as api from '../api/client'

interface UseGraphReturn {
  nodes: GraphNode[]
  edges: GraphEdge[]
  loading: boolean
  error: string | null
  selectedNode: GraphNode | null
  setSelectedNode: (node: GraphNode | null) => void
  refresh: () => void
  uploadTerraform: (file: File) => Promise<ParseResult>
  uploadKubernetes: (file: File) => Promise<ParseResult>
}

export function useGraph(): UseGraphReturn {
  const [nodes, setNodes] = useState<GraphNode[]>([])
  const [edges, setEdges] = useState<GraphEdge[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null)
  const [tick, setTick] = useState(0)

  // Fetch graph whenever tick increments (initial load + after uploads)
  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)

    api.fetchGraph()
      .then(data => {
        if (!cancelled) {
          setNodes(data.nodes)
          setEdges(data.edges)
        }
      })
      .catch(err => {
        if (!cancelled) {
          setError((err as Error).message)
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => { cancelled = true }
  }, [tick])

  const refresh = useCallback(() => setTick(t => t + 1), [])

  const uploadTerraform = useCallback(async (file: File): Promise<ParseResult> => {
    const result = await api.uploadTerraform(file)
    refresh()
    return result
  }, [refresh])

  const uploadKubernetes = useCallback(async (file: File): Promise<ParseResult> => {
    const result = await api.uploadKubernetes(file)
    refresh()
    return result
  }, [refresh])

  return {
    nodes,
    edges,
    loading,
    error,
    selectedNode,
    setSelectedNode,
    refresh,
    uploadTerraform,
    uploadKubernetes,
  }
}
