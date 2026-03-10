// GraphCanvas.tsx — D3 force-directed graph rendered in SVG

import { useRef, useEffect } from 'react'
import * as d3 from 'd3'
import type { GraphNode, GraphEdge } from '../types/graph'
import { nodeColor } from '../types/graph'

// ---------------------------------------------------------------------------
// D3 simulation types
// ---------------------------------------------------------------------------

interface SimNode extends d3.SimulationNodeDatum {
  id: string
  name: string
  type: string
  file: string
  line_number: number
  source: string
  radius: number
}

interface SimEdge extends d3.SimulationLinkDatum<SimNode> {
  _source: string
  _target: string
}

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface GraphCanvasProps {
  nodes: GraphNode[]
  edges: GraphEdge[]
  hiddenTypes?: Set<string>
  selectedNodeId?: string | null
  onNodeClick?: (node: GraphNode) => void
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function buildDegreeMap(nodes: GraphNode[], edges: GraphEdge[]): Map<string, number> {
  const map = new Map<string, number>(nodes.map(n => [n.id, 0]))
  for (const e of edges) {
    map.set(e.source, (map.get(e.source) ?? 0) + 1)
    map.set(e.target, (map.get(e.target) ?? 0) + 1)
  }
  return map
}

function nodeRadius(degree: number): number {
  return 5 + Math.sqrt(degree) * 3
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function GraphCanvas({
  nodes,
  edges,
  hiddenTypes = new Set(),
  selectedNodeId = null,
  onNodeClick,
}: GraphCanvasProps) {
  const svgRef = useRef<SVGSVGElement>(null)

  useEffect(() => {
    const svg = svgRef.current
    if (!svg) return

    // Clear previous render
    d3.select(svg).selectAll('*').remove()

    // Filter by hidden types
    const visibleNodes = nodes.filter(n => !hiddenTypes.has(n.type))
    const visibleNodeIds = new Set(visibleNodes.map(n => n.id))
    const visibleEdges = edges.filter(
      e => visibleNodeIds.has(e.source) && visibleNodeIds.has(e.target)
    )

    const width = svg.clientWidth || 800
    const height = svg.clientHeight || 600

    // Build degree map for radius sizing
    const degreeMap = buildDegreeMap(visibleNodes, visibleEdges)

    // Deep-copy for D3 mutation
    const simNodes: SimNode[] = visibleNodes.map(n => ({
      ...n,
      radius: nodeRadius(degreeMap.get(n.id) ?? 0),
    }))

    const simEdges: SimEdge[] = visibleEdges.map(e => ({
      source: e.source,
      target: e.target,
      _source: e.source,
      _target: e.target,
    }))

    // Root SVG group (zoom target)
    const root = d3.select(svg)
    const g = root.append('g').attr('class', 'graph-root')

    // ── Arrowhead marker ────────────────────────────────────────────────────
    const defs = root.append('defs')
    defs.append('marker')
      .attr('id', 'arrowhead')
      .attr('viewBox', '0 -5 10 10')
      .attr('refX', 10)
      .attr('refY', 0)
      .attr('markerWidth', 6)
      .attr('markerHeight', 6)
      .attr('orient', 'auto')
      .append('path')
      .attr('d', 'M0,-5L10,0L0,5')
      .attr('fill', '#64748b')

    // ── Empty state ─────────────────────────────────────────────────────────
    if (simNodes.length === 0) {
      root.append('text')
        .attr('x', width / 2)
        .attr('y', height / 2)
        .attr('text-anchor', 'middle')
        .attr('fill', '#64748b')
        .attr('font-size', '16px')
        .text('Upload a .tf or .yaml file to visualize your infrastructure')
      return
    }

    // ── D3 force simulation ─────────────────────────────────────────────────
    const simulation = d3
      .forceSimulation<SimNode>(simNodes)
      .force(
        'link',
        d3.forceLink<SimNode, SimEdge>(simEdges)
          .id(d => d.id)
          .distance(80)
      )
      .force('charge', d3.forceManyBody<SimNode>().strength(-300))
      .force('center', d3.forceCenter(width / 2, height / 2))
      .force('collision', d3.forceCollide<SimNode>().radius(d => d.radius + 5))

    // ── Edge lines ──────────────────────────────────────────────────────────
    const linkSel = g
      .append('g')
      .attr('class', 'links')
      .selectAll<SVGLineElement, SimEdge>('line')
      .data(simEdges)
      .join('line')
      .attr('stroke', '#334155')
      .attr('stroke-width', 1.5)
      .attr('marker-end', 'url(#arrowhead)')

    // ── Node circles ────────────────────────────────────────────────────────
    const nodeSel = g
      .append('g')
      .attr('class', 'nodes')
      .selectAll<SVGCircleElement, SimNode>('circle')
      .data(simNodes)
      .join('circle')
      .attr('r', d => d.radius)
      .attr('fill', d => nodeColor(d.type))
      .attr('stroke', d => d.id === selectedNodeId ? '#ffffff' : 'transparent')
      .attr('stroke-width', d => d.id === selectedNodeId ? 2.5 : 0)
      .attr('cursor', 'pointer')
      .on('click', (_event, d) => {
        // Reconstruct original GraphNode (without simulation fields)
        const original = nodes.find(n => n.id === d.id)
        if (original && onNodeClick) onNodeClick(original)
      })

    // ── Labels ──────────────────────────────────────────────────────────────
    const labelSel = g
      .append('g')
      .attr('class', 'labels')
      .selectAll<SVGTextElement, SimNode>('text')
      .data(simNodes)
      .join('text')
      .attr('font-size', '10px')
      .attr('fill', '#94a3b8')
      .attr('text-anchor', 'middle')
      .attr('pointer-events', 'none')
      .text(d => d.name.length > 14 ? d.name.slice(0, 13) + '…' : d.name)

    // ── Drag behavior ────────────────────────────────────────────────────────
    const drag = d3
      .drag<SVGCircleElement, SimNode>()
      .on('start', (event, d) => {
        if (!event.active) simulation.alphaTarget(0.3).restart()
        d.fx = d.x
        d.fy = d.y
      })
      .on('drag', (event, d) => {
        d.fx = event.x
        d.fy = event.y
      })
      .on('end', (event, d) => {
        if (!event.active) simulation.alphaTarget(0)
        d.fx = null
        d.fy = null
      })

    nodeSel.call(drag)

    // ── Zoom behavior ────────────────────────────────────────────────────────
    const zoom = d3
      .zoom<SVGSVGElement, unknown>()
      .scaleExtent([0.1, 10])
      .on('zoom', event => {
        g.attr('transform', (event as d3.D3ZoomEvent<SVGSVGElement, unknown>).transform.toString())
      })

    root.call(zoom)

    // ── Simulation tick ──────────────────────────────────────────────────────
    simulation.on('tick', () => {
      linkSel
        .attr('x1', d => (d.source as SimNode).x ?? 0)
        .attr('y1', d => (d.source as SimNode).y ?? 0)
        .attr('x2', d => {
          // Shorten line so arrowhead sits at node edge
          const src = d.source as SimNode
          const tgt = d.target as SimNode
          const dx = (tgt.x ?? 0) - (src.x ?? 0)
          const dy = (tgt.y ?? 0) - (src.y ?? 0)
          const dist = Math.sqrt(dx * dx + dy * dy) || 1
          return (tgt.x ?? 0) - (dx / dist) * (tgt.radius + 2)
        })
        .attr('y2', d => {
          const src = d.source as SimNode
          const tgt = d.target as SimNode
          const dx = (tgt.x ?? 0) - (src.x ?? 0)
          const dy = (tgt.y ?? 0) - (src.y ?? 0)
          const dist = Math.sqrt(dx * dx + dy * dy) || 1
          return (tgt.y ?? 0) - (dy / dist) * (tgt.radius + 2)
        })

      nodeSel
        .attr('cx', d => d.x ?? 0)
        .attr('cy', d => d.y ?? 0)

      labelSel
        .attr('x', d => d.x ?? 0)
        .attr('y', d => (d.y ?? 0) + (d.radius + 12))
    })

    return () => { simulation.stop() }
  }, [nodes, edges, hiddenTypes, selectedNodeId, onNodeClick])

  return (
    <svg
      ref={svgRef}
      style={{ width: '100%', height: '100%', display: 'block', background: '#0f1117' }}
    />
  )
}
