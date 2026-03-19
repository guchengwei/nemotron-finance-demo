import type { ReactNode } from 'react'
import Sidebar from './Sidebar'
import StepIndicator from './StepIndicator'

interface Props {
  children: ReactNode
}

export default function Layout({ children }: Props) {
  return (
    <div className="flex min-h-screen overflow-hidden bg-fin-canvas text-fin-ink">
      <Sidebar />
      <div className="flex flex-1 flex-col overflow-hidden">
        <header className="flex-shrink-0 border-b border-fin-border/80 bg-fin-surface/90 px-8 py-5 backdrop-blur">
          <StepIndicator />
        </header>
        <main className="flex-1 overflow-auto px-8 py-8">
          {children}
        </main>
      </div>
    </div>
  )
}
