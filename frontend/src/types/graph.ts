// graph.ts — TypeScript interfaces for InfraGraph data model

export interface GraphNode {
  id: string          // "aws_s3_bucket.uploads" or "Deployment/default/app"
  name: string        // Resource name as declared in source file
  type: string        // Resource type, e.g. "aws_s3_bucket", "Deployment"
  file: string        // Relative path to source file
  line_number: number // Line number of declaration (0 if unavailable)
  source: string      // "terraform" or "kubernetes"
}

export interface GraphEdge {
  source: string      // ID of the dependent resource
  target: string      // ID of the dependency
}

export interface GraphData {
  nodes: GraphNode[]
  edges: GraphEdge[]
}

export interface MostConnected {
  id: string
  name: string
  type: string
  degree: number
}

export interface GraphStats {
  node_count: number
  edge_count: number
  most_connected: MostConnected | null
  isolated_count: number
  circular_dependencies: number
}

export interface ParseResult {
  node_count: number
  edge_count: number
}

// ---------------------------------------------------------------------------
// Node color map — keyed by resource type string
// ---------------------------------------------------------------------------
export const NODE_COLORS: Record<string, string> = {
  // Terraform — AWS
  aws_instance:          '#4A90D9',  // blue
  aws_s3_bucket:         '#27AE60',  // green
  aws_iam_role:          '#E74C3C',  // red
  aws_iam_policy:        '#C0392B',  // dark red
  aws_vpc:               '#16A085',  // teal
  aws_subnet:            '#1ABC9C',  // cyan
  aws_security_group:    '#D35400',  // burnt orange
  aws_lb:                '#8E44AD',  // purple
  aws_db_instance:       '#F39C12',  // amber
  aws_lambda_function:   '#2980B9',  // steel blue
  aws_cloudfront_distribution: '#1F618D',
  // Terraform — GCP
  google_compute_instance:  '#EA4335',
  google_storage_bucket:    '#34A853',
  // Terraform — Azure
  azurerm_resource_group:   '#0078D4',
  azurerm_virtual_network:  '#50E6FF',
  // Terraform — meta
  variable:              '#BDC3C7',  // light gray
  output:                '#95A5A6',  // gray
  // Kubernetes
  Deployment:            '#8E44AD',  // purple
  Service:               '#E67E22',  // orange
  ConfigMap:             '#F1C40F',  // yellow
  Secret:                '#FF69B4',  // pink
  Ingress:               '#3498DB',  // blue
  StatefulSet:           '#9B59B6',  // violet
  DaemonSet:             '#2ECC71',  // emerald
  Job:                   '#E67E22',
  CronJob:               '#D35400',
  ServiceAccount:        '#7F8C8D',
  HorizontalPodAutoscaler: '#1ABC9C',
  PersistentVolumeClaim: '#95A5A6',
  // Fallback
  default:               '#95A5A6',
}

export function nodeColor(type: string): string {
  return NODE_COLORS[type] ?? NODE_COLORS.default
}
