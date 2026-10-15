import type { ReactNode } from "react"

export type SceneSpec = {
  id: string
  steps: number
  View: (props: { step: number }) => ReactNode
}
