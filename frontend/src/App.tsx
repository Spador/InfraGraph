// App.tsx — Root layout wiring all components together

import { useState } from 'react'
import './App.css'
import GraphCanvas from './components/GraphCanvas'
import StatsBar from './components/StatsBar'
import UploadZone from './components/UploadZone'
import FilterControls from './components/FilterControls'
import NodeDetailPanel from './components/NodeDetailPanel'
import { useGraph } from './hooks/useGraph'
import type { GraphNode } from './types/graph'

export default function App() {
  const {
    nodes,
    edges,
    selectedNode,
    setSelectedNode,
    refresh,
    uploadTerraform,
    uploadKubernetes,
  } = useGraph()

  const [hiddenTypes, setHiddenTypes] = useState<Set<string>>(new Set())

  function handleNodeClick(node: GraphNode) {
    setSelectedNode(selectedNode?.id === node.id ? null : node)
  }

  return (
    <div className="app">
      {/* ── Stats bar ── */}
      <StatsBar onReset={refresh} />

      <div className="app-body">
        {/* ── Left sidebar ── */}
        <div className="sidebar">
          <UploadZone
            onUploadTerraform={uploadTerraform}
            onUploadKubernetes={uploadKubernetes}
          />
          <div style={{ borderTop: '1px solid #313244', paddingTop: 12 }}>
            <FilterControls
              nodes={nodes}
              hiddenTypes={hiddenTypes}
              onChange={setHiddenTypes}
            />
          </div>
        </div>

        {/* ── Graph canvas ── */}
        <div className="canvas-area">
          <GraphCanvas
            nodes={nodes}
            edges={edges}
            hiddenTypes={hiddenTypes}
            selectedNodeId={selectedNode?.id ?? null}
            onNodeClick={handleNodeClick}
          />
        </div>

        {/* ── Node detail panel ── */}
        <NodeDetailPanel
          node={selectedNode}
          onClose={() => setSelectedNode(null)}
        />
      </div>
    </div>
  )
}
