import type { ReactNode } from 'react'
import Sidebar from './Sidebar'
import StepIndicator from './StepIndicator'

interface Props {
  children: ReactNode
}

export default function Layout({ children }: Props) {
  return (
    <div className="flex h-screen overflow-hidden bg-[#0a0a0f]">
      <Sidebar />
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Top bar */}
        <header className="flex-shrink-0 bg-[#141420] border-b border-[rgba(118,185,0,0.1)] px-6 py-3">
          <StepIndicator />
        </header>
        {/* Main content */}
        <main className="flex-1 overflow-auto p-6">
          {children}
        </main>
      </div>
    </div>
  )
}
