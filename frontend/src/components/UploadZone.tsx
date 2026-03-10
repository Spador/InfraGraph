// UploadZone.tsx — Drag-and-drop or click-to-upload IaC files

import { useRef, useState, useCallback, DragEvent } from 'react'
import type { ParseResult } from '../types/graph'

interface UploadZoneProps {
  onUploadTerraform: (file: File) => Promise<ParseResult>
  onUploadKubernetes: (file: File) => Promise<ParseResult>
}

type ToastKind = 'success' | 'error'

interface Toast {
  message: string
  kind: ToastKind
}

export default function UploadZone({ onUploadTerraform, onUploadKubernetes }: UploadZoneProps) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [uploading, setUploading] = useState(false)
  const [dragging, setDragging] = useState(false)
  const [toast, setToast] = useState<Toast | null>(null)

  function showToast(message: string, kind: ToastKind) {
    setToast({ message, kind })
    setTimeout(() => setToast(null), 3500)
  }

  const handleFile = useCallback(async (file: File) => {
    const ext = file.name.split('.').pop()?.toLowerCase() ?? ''
    const uploader = ext === 'tf'
      ? onUploadTerraform
      : (ext === 'yaml' || ext === 'yml')
        ? onUploadKubernetes
        : ext === 'zip'
          ? onUploadTerraform  // backend infers content from zip
          : null

    if (!uploader) {
      showToast(`Unsupported file type: .${ext}`, 'error')
      return
    }

    setUploading(true)
    try {
      const result = await uploader(file)
      showToast(`+${result.node_count} nodes, +${result.edge_count} edges`, 'success')
    } catch (err) {
      showToast(`Error: ${(err as Error).message}`, 'error')
    } finally {
      setUploading(false)
      if (inputRef.current) inputRef.current.value = ''
    }
  }, [onUploadTerraform, onUploadKubernetes])

  const handleInputChange = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) handleFile(file)
  }, [handleFile])

  const handleDrop = useCallback((e: DragEvent<HTMLDivElement>) => {
    e.preventDefault()
    setDragging(false)
    const file = e.dataTransfer.files?.[0]
    if (file) handleFile(file)
  }, [handleFile])

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
      <div style={{ fontSize: 11, color: '#a6adc8', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
        Upload IaC files
      </div>

      {/* Drop zone */}
      <div
        onClick={() => !uploading && inputRef.current?.click()}
        onDragOver={e => { e.preventDefault(); setDragging(true) }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
        style={{
          border: `1px dashed ${dragging ? '#cba6f7' : '#313244'}`,
          borderRadius: 6,
          padding: '16px 8px',
          textAlign: 'center',
          cursor: uploading ? 'wait' : 'pointer',
          color: dragging ? '#cba6f7' : '#45475a',
          fontSize: 12,
          background: dragging ? 'rgba(203,166,247,0.05)' : 'transparent',
          transition: 'all 0.15s',
        }}
      >
        {uploading ? (
          <span style={{ color: '#cba6f7' }}>Uploading…</span>
        ) : (
          <>
            <div style={{ fontSize: 20, marginBottom: 6 }}>⬆</div>
            <div>Drop .tf, .yaml, or .zip</div>
            <div style={{ marginTop: 4, fontSize: 11 }}>or click to browse</div>
          </>
        )}
      </div>

      <input
        ref={inputRef}
        type="file"
        accept=".tf,.yaml,.yml,.zip"
        style={{ display: 'none' }}
        onChange={handleInputChange}
      />

      {/* Toast */}
      {toast && (
        <div style={{
          padding: '6px 10px',
          borderRadius: 4,
          fontSize: 12,
          background: toast.kind === 'success' ? 'rgba(39,174,96,0.15)' : 'rgba(243,139,168,0.15)',
          color: toast.kind === 'success' ? '#a6e3a1' : '#f38ba8',
          border: `1px solid ${toast.kind === 'success' ? '#27ae60' : '#f38ba8'}`,
          wordBreak: 'break-word',
        }}>
          {toast.message}
        </div>
      )}

      {/* Accepted formats */}
      <div style={{ fontSize: 10, color: '#45475a', lineHeight: 1.6 }}>
        <div>• <code style={{ color: '#89b4fa' }}>.tf</code> — Terraform</div>
        <div>• <code style={{ color: '#a6e3a1' }}>.yaml / .yml</code> — Kubernetes</div>
        <div>• <code style={{ color: '#f9e2af' }}>.zip</code> — archive of either</div>
      </div>
    </div>
  )
}
